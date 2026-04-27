"""BFS crawler for web crawling with incremental updates."""

from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
import json

import structlog

from .crawler import crawl_page, CrawledPage
from .link_extractor import extract_links, should_crawl_url, ExtractedLink
from .seed_manager import SeedManager, SeedURL
from .typesense_client import TypesenseClient

logger = structlog.get_logger()


@dataclass
class CrawlState:
    """State for BFS crawling."""
    url_depths: dict[str, int] = field(default_factory=dict)
    visited_urls: set[str] = field(default_factory=set)
    discovered_urls: set[str] = field(default_factory=set)
    failed_urls: set[str] = field(default_factory=set)
    last_crawl_time: dict[str, str] = field(default_factory=dict)

    # BFS queue: (url, depth)
    queue: deque[tuple[str, int]] = field(default_factory=deque)

    def enqueue(self, url: str, depth: int) -> None:
        if url not in self.visited_urls and url not in self.queue:
            self.queue.append((url, depth))
            self.discovered_urls.add(url)

    def dequeue(self) -> tuple[str, int] | None:
        if self.queue:
            return self.queue.popleft()
        return None

    def mark_visited(self, url: str, depth: int) -> None:
        self.visited_urls.add(url)
        self.url_depths[url] = depth
        self.last_crawl_time[url] = datetime.utcnow().isoformat()

    def mark_failed(self, url: str) -> None:
        self.failed_urls.add(url)

    def save(self, path: Path) -> None:
        data = {
            "url_depths": self.url_depths,
            "visited_urls": list(self.visited_urls),
            "discovered_urls": list(self.discovered_urls),
            "failed_urls": list(self.failed_urls),
            "last_crawl_time": self.last_crawl_time,
        }
        path.write_text(json.dumps(data, indent=2))

    def load(self, path: Path) -> None:
        if not path.exists():
            return
        data = json.loads(path.read_text())
        self.url_depths = data.get("url_depths", {})
        self.visited_urls = set(data.get("visited_urls", []))
        self.discovered_urls = set(data.get("discovered_urls", []))
        self.failed_urls = set(data.get("failed_urls", []))
        self.last_crawl_time = data.get("last_crawl_time", {})


@dataclass
class CrawlStats:
    """Statistics for crawling operation."""
    pages_crawled: int = 0
    pages_failed: int = 0
    new_urls_discovered: int = 0
    new_domains_discovered: int = 0
    pages_indexed: int = 0
    start_time: str = ""
    end_time: str = ""


class BFSCrawler:
    """BFS crawler with incremental updates."""

    def __init__(
        self,
        seed_manager: SeedManager,
        typesense: TypesenseClient,
        max_concurrent: int = 3,
        max_depth: int = 2,
        crawl_delay: float = 1.0,
        state_dir: Path | None = None,
    ):
        self.seed_manager = seed_manager
        self.typesense = typesense
        self.max_concurrent = max_concurrent
        self.max_depth = max_depth
        self.crawl_delay = crawl_delay
        self.state_dir = state_dir or Path("./crawl_state")

        self.state = CrawlState()
        self.stats = CrawlStats()

        # Load state if exists
        self.state_file = self.state_dir / "crawl_state.json"
        self.seed_state_file = self.state_dir / "seeds.json"

    async def initialize(self) -> None:
        """Initialize crawler."""
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.state.load(self.state_file)
        self.seed_manager.load(self.seed_state_file)

        # Ensure typesense collection exists
        await self.typesense.ensure_collection()

        # Enqueue seed URLs if queue is empty
        if not self.state.queue:
            for seed in self.seed_manager.get_pending_seeds():
                if seed.url not in self.state.visited_urls:
                    self.state.enqueue(seed.url, 1)
                    logger.info("seed_enqueued", url=seed.url, domain=seed.domain)

        logger.info(
            "crawler_initialized",
            queue_size=len(self.state.queue),
            visited=len(self.state.visited_urls),
            domains=len(self.seed_manager.domains),
        )

    async def _crawl_with_extraction(
        self,
        url: str,
        depth: int,
        semaphore: asyncio.Semaphore,
    ) -> list[ExtractedLink]:
        """Crawl a URL and extract links."""
        async with semaphore:
            try:
                page = await crawl_page(url, delay=self.crawl_delay)

                if not page.success:
                    self.state.mark_failed(url)
                    logger.warning("crawl_failed", url=url, error=page.error)
                    return []

                self.state.mark_visited(url, depth)
                self.stats.pages_crawled += 1

                # Index the page
                try:
                    await self.typesense.index_page(
                        url=page.url,
                        title=page.title,
                        content=page.content,
                        snippet=page.snippet,
                        domain=page.domain,
                    )
                    self.stats.pages_indexed += 1
                    logger.debug("page_indexed", url=url, title=page.title)
                except Exception as e:
                    logger.warning("index_failed", url=url, error=str(e))

                # Extract links if under depth limit
                if depth < self.max_depth:
                    from bs4 import BeautifulSoup
                    if page.raw_html:
                        soup = BeautifulSoup(page.raw_html, "html.parser")
                        html = str(soup)
                    else:
                        html = page.content

                    links = extract_links(html, url)
                    return links

                return []

            except Exception as e:
                self.state.mark_failed(url)
                self.stats.pages_failed += 1
                logger.error("crawl_error", url=url, error=str(e))
                return []

    async def crawl(
        self,
        max_pages: int = 100,
        max_time_seconds: int = 300,
    ) -> CrawlStats:
        """Run BFS crawl with batched concurrent processing.

        Args:
            max_pages: Maximum pages to crawl in this run
            max_time_seconds: Maximum time to run

        Returns:
            CrawlStats with crawl statistics
        """
        self.stats = CrawlStats()
        self.stats.start_time = datetime.utcnow().isoformat()

        await self.initialize()

        start = datetime.utcnow()
        semaphore = asyncio.Semaphore(self.max_concurrent)

        logger.info("crawl_started", queue_size=len(self.state.queue), max_pages=max_pages)

        while self.stats.pages_crawled < max_pages:
            # Check time limit
            elapsed = (datetime.utcnow() - start).total_seconds()
            if elapsed > max_time_seconds:
                logger.info("crawl_time_limit", elapsed=elapsed)
                break

            # Batch dequeue up to max_concurrent items
            batch_items: list[tuple[str, int]] = []
            for _ in range(self.max_concurrent):
                if self.stats.pages_crawled + len(batch_items) >= max_pages:
                    break

                item = self.state.dequeue()
                if not item:
                    break

                url, depth = item

                # Skip already visited
                if url in self.state.visited_urls:
                    continue

                # Check if should crawl
                if not should_crawl_url(url, self.seed_manager.domains, self.max_depth, self.state.url_depths):
                    continue

                # Check if needs recrawl (recently crawled)
                last_crawled = self.state.last_crawl_time.get(url)
                if last_crawled:
                    last_time = datetime.fromisoformat(last_crawled)
                    if datetime.utcnow() - last_time < timedelta(days=7):
                        continue

                batch_items.append((url, depth))

            if not batch_items:
                logger.info("crawl_queue_empty")
                break

            # Crawl batch concurrently
            tasks = [
                self._crawl_with_extraction(url, depth, semaphore)
                for url, depth in batch_items
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Process discovered links
            for i, links in enumerate(results):
                if isinstance(links, Exception):
                    logger.warning("crawl_batch_error", error=str(links))
                    continue

                for link in links:
                    if link.domain not in self.seed_manager.domains:
                        self.seed_manager.add_discovered_domain(link.domain)
                        self.stats.new_domains_discovered += 1
                        logger.info("new_domain_discovered", domain=link.domain)

                    _, depth = batch_items[i]
                    self.state.enqueue(link.url, depth + 1)
                    self.stats.new_urls_discovered += 1

            # Save state periodically
            if self.stats.pages_crawled % 10 == 0:
                self._save_state()

        self.stats.end_time = datetime.utcnow().isoformat()
        self._save_state()

        logger.info(
            "crawl_completed",
            pages_crawled=self.stats.pages_crawled,
            pages_indexed=self.stats.pages_indexed,
            new_domains=self.stats.new_domains_discovered,
            queue_remaining=len(self.state.queue),
        )

        return self.stats

    def _save_state(self) -> None:
        """Save crawler state."""
        self.state.save(self.state_file)
        self.seed_manager.save(self.seed_state_file)

    def get_stats(self) -> dict[str, Any]:
        """Get current crawl statistics."""
        return {
            "crawl": {
                "pages_crawled": self.stats.pages_crawled,
                "pages_failed": self.stats.pages_failed,
                "pages_indexed": self.stats.pages_indexed,
                "new_urls_discovered": self.stats.new_urls_discovered,
                "new_domains": self.stats.new_domains_discovered,
            },
            "state": {
                "visited_urls": len(self.state.visited_urls),
                "discovered_urls": len(self.state.discovered_urls),
                "queue_size": len(self.state.queue),
                "failed_urls": len(self.state.failed_urls),
            },
            "seeds": self.seed_manager.get_stats(),
        }

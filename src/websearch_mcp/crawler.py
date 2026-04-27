"""Crawler module using trafilatura."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from urllib.parse import urlparse

import structlog
import trafilatura

logger = structlog.get_logger()


@dataclass
class CrawledPage:
    """Result of crawling a page."""
    url: str
    title: str
    content: str
    snippet: str
    domain: str
    raw_html: str | None = None
    success: bool = True
    error: str | None = None


async def crawl_page(url: str, delay: float = 0.0) -> CrawledPage:
    """Crawl a single page using trafilatura.

    Args:
        url: URL to crawl
        delay: Delay before crawling (rate limiting)

    Returns:
        CrawledPage with extracted content
    """
    if delay > 0:
        await asyncio.sleep(delay)

    try:
        downloaded = await asyncio.to_thread(trafilatura.fetch_url, url)
        if not downloaded:
            return CrawledPage(
                url=url,
                title=url,
                content="",
                snippet="",
                domain=urlparse(url).netloc,
                success=False,
                error="Failed to download",
            )

        extracted = await asyncio.to_thread(
            trafilatura.extract,
            downloaded,
            include_comments=False,
            include_tables=True,
            output_format="json",
        )

        if not extracted:
            extracted = await asyncio.to_thread(
                trafilatura.extract,
                downloaded,
                output_format="txt",
            )
            content = extracted if extracted else ""
        else:
            import json
            data = json.loads(extracted)
            content = data.get("text", "")

        # Build title
        title = urlparse(url).netloc
        if extracted:
            import json
            try:
                data = json.loads(extracted)
                title = data.get("title", title)
            except (json.JSONDecodeError, TypeError):
                pass

        # Generate snippet
        snippet = content[:300] + "..." if len(content) > 300 else content
        parsed = urlparse(url)

        return CrawledPage(
            url=url,
            title=title,
            content=content,
            snippet=snippet,
            domain=parsed.netloc,
            success=True,
        )

    except Exception as e:
        logger.warning("crawl_failed", url=url, error=str(e))
        return CrawledPage(
            url=url,
            title=url,
            content="",
            snippet="",
            domain=urlparse(url).netloc,
            success=False,
            error=str(e),
        )


async def crawl_pages(
    urls: list[str],
    concurrency: int = 3,
    delay: float = 1.0,
) -> list[CrawledPage]:
    """Crawl multiple pages concurrently with per-domain rate limiting.

    Args:
        urls: List of URLs to crawl
        concurrency: Max concurrent crawls
        delay: Minimum delay between requests to the same domain

    Returns:
        List of CrawledPage results
    """
    semaphore = asyncio.Semaphore(concurrency)
    domain_last_crawl: dict[str, float] = {}

    async def crawl_with_domain_rate_limit(url: str) -> CrawledPage:
        parsed = urlparse(url)
        domain = parsed.netloc

        # Per-domain rate limiting: only sleep if last crawl was too recent
        now = time.time()
        last = domain_last_crawl.get(domain, 0)
        elapsed = now - last
        if elapsed < delay and last > 0:
            await asyncio.sleep(delay - elapsed)

        async with semaphore:
            page = await crawl_page(url)
            domain_last_crawl[domain] = time.time()
            return page

    tasks = [crawl_with_domain_rate_limit(url) for url in urls]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    crawled: list[CrawledPage] = []
    for r in results:
        if isinstance(r, Exception):
            logger.warning("crawl_task_exception", error=str(r))
            continue
        crawled.append(r)

    return crawled

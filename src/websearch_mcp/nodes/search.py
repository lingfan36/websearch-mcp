"""Search node — queries Typesense first, falls back to live web search."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime
from urllib.parse import urlparse

import structlog

from ..config import get_settings
from ..crawler import crawl_pages, CrawledPage
from ..schema import (
    RewriterOutput,
    RewrittenQuery,
    SearchResult,
    SearchDepth,
)
from ..trace import TraceManager
from ..schema import NodeType
from ..typesense_client import get_typesense_client

logger = structlog.get_logger()


class SearchNode:
    """Searches Typesense first, falls back to live web search + index."""

    def __init__(self, max_concurrent: int = 3):
        self.max_concurrent = max_concurrent
        self.typesense = get_typesense_client()

    async def _search_single(
        self,
        query: RewrittenQuery,
    ) -> list[SearchResult]:
        """Search with a single query using Typesense."""
        depth_to_results = {
            SearchDepth.QUICK: 3,
            SearchDepth.BALANCED: 10,
            SearchDepth.DEEP: 20,
        }
        max_results = depth_to_results.get(query.search_depth, 10)

        try:
            results = await self.typesense.search(query.query, max_results=max_results)

            return [
                SearchResult(
                    id=str(uuid.uuid4()),
                    query_used=query.query,
                    source="typesense",
                    url=r["url"],
                    title=r["title"],
                    snippet=r.get("snippet", ""),
                )
                for r in results
            ]

        except Exception as e:
            logger.warning("search_query_failed", query=query.query, error=str(e))
            return []

    async def _search_web_fallback(
        self,
        queries: list[RewrittenQuery],
        max_results: int = 10,
    ) -> list[SearchResult]:
        """Fall back to live web search when Typesense has no results."""
        from ..fetch import search_web, fetch_and_extract

        results: list[SearchResult] = []
        seen_urls: set[str] = set()

        for q in queries[:3]:
            try:
                web_results = await search_web(q.query, max_results=max_results)
                for r in web_results:
                    if r["url"] not in seen_urls:
                        seen_urls.add(r["url"])
                        results.append(SearchResult(
                            id=str(uuid.uuid4()),
                            query_used=q.query,
                            source="web_search",
                            url=r["url"],
                            title=r.get("title", r["url"]),
                            snippet=r.get("snippet", ""),
                        ))
            except Exception as e:
                logger.warning("web_search_fallback_failed", query=q.query, error=str(e))

        logger.info("web_fallback_results", count=len(results))
        return results

    async def _index_results(self, pages: list[CrawledPage]) -> int:
        """Index crawled pages into Typesense for future searches."""
        indexed = 0
        for page in pages:
            if not page.success or not page.content:
                continue
            try:
                await self.typesense.index_page(
                    url=page.url,
                    title=page.title,
                    content=page.content[:10000],
                    snippet=page.snippet[:300],
                    domain=page.domain,
                )
                indexed += 1
            except Exception as e:
                logger.warning("index_failed", url=page.url, error=str(e))

        if indexed:
            logger.info("search_indexed_new_pages", count=indexed)
        return indexed

    async def _crawl_results(
        self,
        results: list[SearchResult],
        crawl_concurrency: int = 3,
    ) -> list[CrawledPage]:
        """Crawl pages for full content."""
        if not results:
            return []

        urls = [r.url for r in results]
        crawled = await crawl_pages(urls, concurrency=crawl_concurrency)
        return crawled

    async def run(
        self,
        rewriter_output: RewriterOutput,
        crawl: bool = True,
        trace: TraceManager | None = None,
    ) -> tuple[list[SearchResult], list[CrawledPage]]:
        """Run search: local index first, web fallback if empty.

        Args:
            rewriter_output: Output from rewriter node
            crawl: Whether to crawl pages for full content
            trace: Optional trace manager

        Returns:
            Tuple of (search_results, crawled_pages)
        """
        if not rewriter_output.queries:
            logger.warning("search_no_queries")
            return [], []

        logger.info("search_start", query_count=len(rewriter_output.queries))

        # Phase 1: Search local Typesense index
        tasks = [self._search_single(q) for q in rewriter_output.queries]
        all_results_lists = await asyncio.gather(*tasks, return_exceptions=True)

        all_results: list[SearchResult] = []
        for results in all_results_lists:
            if isinstance(results, list):
                all_results.extend(results)
            elif isinstance(results, Exception):
                logger.warning("search_query_error", error=str(results))

        # Deduplicate by URL
        seen_urls: set[str] = set()
        deduped: list[SearchResult] = []
        for r in all_results:
            if r.url not in seen_urls:
                seen_urls.add(r.url)
                deduped.append(r)

        source = "typesense"

        # Phase 2: If local index is empty, fall back to live web search
        if not deduped:
            logger.info("search_falling_back_to_web", queries=len(rewriter_output.queries))
            web_results = await self._search_web_fallback(
                rewriter_output.queries,
                max_results=10,
            )
            for r in web_results:
                if r.url not in seen_urls:
                    seen_urls.add(r.url)
                    deduped.append(r)
            source = "web_fallback"

        if not deduped:
            logger.warning("search_no_results_any_source")
            return [], []

        # Phase 3: Crawl pages for full content
        crawled_pages: list[CrawledPage] = []
        if crawl:
            crawled_pages = await self._crawl_results(deduped)

            content_map = {p.url: p for p in crawled_pages}
            for r in deduped:
                if r.url in content_map:
                    page = content_map[r.url]
                    r.raw_content = page.content if page.success else None

            # Phase 4: Index newly fetched web pages into Typesense
            if source == "web_fallback":
                new_pages = [p for p in crawled_pages if p.success]
                await self._index_results(new_pages)

        if trace:
            trace.log_event(
                node=NodeType.SEARCH,
                action="search_crawl",
                input_data=[q.query for q in rewriter_output.queries],
                output_data={
                    "search_results": len(deduped),
                    "crawled_pages": len(crawled_pages),
                    "successful_crawls": sum(1 for p in crawled_pages if p.success),
                    "source": source,
                },
                metadata={
                    "query_count": len(rewriter_output.queries),
                    "sources_used": list(set(r.source for r in deduped)),
                },
            )

        logger.info("search_done", results=len(deduped), crawled=len(crawled_pages), source=source)
        return deduped, crawled_pages

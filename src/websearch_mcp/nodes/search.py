"""Search node — queries Typesense for relevant pages."""

from __future__ import annotations

import uuid
from datetime import datetime

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
    """Searches using Typesense and crawls pages for content."""

    def __init__(self, max_concurrent: int = 3):
        self.max_concurrent = max_concurrent
        self.typesense = get_typesense_client()

    async def _search_single(
        self,
        query: RewrittenQuery,
    ) -> list[SearchResult]:
        """Search with a single query using Typesense."""
        settings = get_settings()

        # Map search depth to max_results
        depth_to_results = {
            SearchDepth.QUICK: 3,
            SearchDepth.BALANCED: 10,
            SearchDepth.DEEP: 20,
        }
        max_results = depth_to_results.get(query.search_depth, 10)

        try:
            # Search Typesense
            results = await self.typesense.search(query.query, max_results=max_results)

            search_results = []
            for r in results:
                search_results.append(SearchResult(
                    id=str(uuid.uuid4()),
                    query_used=query.query,
                    source="typesense",
                    url=r["url"],
                    title=r["title"],
                    snippet=r.get("snippet", ""),
                ))

            return search_results

        except Exception as e:
            logger.warning("search_query_failed", query=query.query, error=str(e))
            return []

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
        """Run search and optionally crawl pages.

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

        # Search all queries
        all_results: list[SearchResult] = []
        for q in rewriter_output.queries:
            results = await self._search_single(q)
            all_results.extend(results)

        # Deduplicate by URL
        seen_urls: set[str] = set()
        deduped: list[SearchResult] = []
        for r in all_results:
            if r.url not in seen_urls:
                seen_urls.add(r.url)
                deduped.append(r)

        # Optionally crawl for full content
        crawled_pages: list[CrawledPage] = []
        if crawl:
            crawled_pages = await self._crawl_results(deduped)

            # Update search results with full content
            content_map = {p.url: p for p in crawled_pages}
            for r in deduped:
                if r.url in content_map:
                    page = content_map[r.url]
                    r.raw_content = page.content if page.success else None

        if trace:
            trace.log_event(
                node=NodeType.SEARCH,
                action="search_crawl",
                input_data=[q.query for q in rewriter_output.queries],
                output_data={
                    "search_results": len(deduped),
                    "crawled_pages": len(crawled_pages),
                    "successful_crawls": sum(1 for p in crawled_pages if p.success),
                },
                metadata={
                    "query_count": len(rewriter_output.queries),
                    "sources_used": list(set(r.source for r in deduped)),
                },
            )

        logger.info("search_done", results=len(deduped), crawled=len(crawled_pages))
        return deduped, crawled_pages

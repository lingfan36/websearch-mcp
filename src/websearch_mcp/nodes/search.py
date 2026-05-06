"""Search node — queries Typesense first, falls back to live web search."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime
from typing import Protocol
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


class SearchStrategy(Protocol):
    """Protocol for search strategies (swarm pattern)."""

    async def search(self, query: RewrittenQuery) -> list[SearchResult]:
        """Execute search with this strategy."""
        ...


class TypesenseStrategy:
    """Search using local Typesense index."""

    def __init__(self):
        self.typesense = get_typesense_client()

    async def search(self, query: RewrittenQuery) -> list[SearchResult]:
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
            logger.warning("typesense_search_failed", query=query.query, error=str(e))
            return []


class WebSearchStrategy:
    """Search using live Jina web search."""

    async def search(self, query: RewrittenQuery) -> list[SearchResult]:
        from ..fetch import search_web

        try:
            web_results = await search_web(query.query, max_results=10)
            return [
                SearchResult(
                    id=str(uuid.uuid4()),
                    query_used=query.query,
                    source="web_search",
                    url=r["url"],
                    title=r.get("title", r["url"]),
                    snippet=r.get("snippet", ""),
                )
                for r in web_results
            ]
        except Exception as e:
            logger.warning("web_search_failed", query=query.query, error=str(e))
            return []


class ParallelSearchNode:
    """Swarm-style parallel search with multiple strategies."""

    def __init__(self, max_concurrent: int = 3):
        self.max_concurrent = max_concurrent
        self.strategies: list[SearchStrategy] = [
            TypesenseStrategy(),
            WebSearchStrategy(),
        ]

    async def run(
        self,
        rewriter_output: RewriterOutput,
        crawl: bool = True,
        trace: TraceManager | None = None,
    ) -> tuple[list[SearchResult], list[CrawledPage]]:
        """Run parallel search across all strategies.

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

        logger.info("parallel_search_start", query_count=len(rewriter_output.queries), strategies=len(self.strategies))

        # Launch all strategies in parallel for each query
        tasks = []
        for query in rewriter_output.queries:
            for strategy in self.strategies:
                tasks.append(self._search_with_strategy(query, strategy))

        results_by_strategy = await asyncio.gather(*tasks, return_exceptions=True)

        # Flatten and deduplicate results
        all_results: list[SearchResult] = []
        seen_urls: set[str] = set()
        for results in results_by_strategy:
            if isinstance(results, list):
                for r in results:
                    if r.url not in seen_urls:
                        seen_urls.add(r.url)
                        all_results.append(r)
            elif isinstance(results, Exception):
                logger.warning("strategy_error", error=str(results))

        logger.info("parallel_search_got_results", total=len(all_results))

        if not all_results:
            logger.warning("parallel_search_no_results")
            return [], []

        # Crawl pages for full content
        crawled_pages: list[CrawledPage] = []
        if crawl:
            crawled_pages = await crawl_pages(
                [r.url for r in all_results],
                concurrency=self.max_concurrent,
            )

            content_map = {p.url: p for p in crawled_pages}
            for r in all_results:
                if r.url in content_map:
                    page = content_map[r.url]
                    r.raw_content = page.content if page.success else None

        if trace:
            trace.log_event(
                node=NodeType.SEARCH,
                action="parallel_search",
                input_data=[q.query for q in rewriter_output.queries],
                output_data={
                    "search_results": len(all_results),
                    "crawled_pages": len(crawled_pages),
                    "successful_crawls": sum(1 for p in crawled_pages if p.success),
                },
                metadata={
                    "query_count": len(rewriter_output.queries),
                    "strategy_count": len(self.strategies),
                    "sources": list(set(r.source for r in all_results)),
                },
            )

        return all_results, crawled_pages

    async def _search_with_strategy(
        self,
        query: RewrittenQuery,
        strategy: SearchStrategy,
    ) -> list[SearchResult]:
        """Run a single strategy for a single query."""
        try:
            return await strategy.search(query)
        except Exception as e:
            logger.warning("search_strategy_error", strategy=type(strategy).__name__, error=str(e))
            return []


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
        from ..fetch import search_web

        results: list[SearchResult] = []
        seen_urls: set[str] = set()

        async def _search_one(q: RewrittenQuery) -> list[SearchResult]:
            try:
                web_results = await search_web(q.query, max_results=max_results)
                return [
                    SearchResult(
                        id=str(uuid.uuid4()),
                        query_used=q.query,
                        source="web_search",
                        url=r["url"],
                        title=r.get("title", r["url"]),
                        snippet=r.get("snippet", ""),
                    )
                    for r in web_results
                    if r["url"] not in seen_urls
                ]
            except Exception as e:
                logger.warning("web_search_fallback_failed", query=q.query, error=str(e))
                return []

        # Run all queries concurrently
        results_lists = await asyncio.gather(
            *[_search_one(q) for q in queries[:3]],
            return_exceptions=True,
        )

        for res in results_lists:
            if isinstance(res, list):
                results.extend(res)

        # Deduplicate after gather
        seen_urls.clear()
        deduped = []
        for r in results:
            if r.url not in seen_urls:
                seen_urls.add(r.url)
                deduped.append(r)

        logger.info("web_fallback_results", count=len(deduped))
        return deduped

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

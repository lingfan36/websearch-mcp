"""Typesense client for search operations (async wrapper)."""

from __future__ import annotations

import asyncio
from typing import Any

import structlog
import typesense

from .config import get_settings

logger = structlog.get_logger()

# Schema for webpages collection
WEBPAGES_SCHEMA = {
    "name": "webpages",
    "fields": [
        {"name": "url", "type": "string"},
        {"name": "title", "type": "string"},
        {"name": "content", "type": "string"},
        {"name": "snippet", "type": "string"},
        {"name": "crawled_at", "type": "int64"},
        {"name": "domain", "type": "string"},
    ],
    "default_sorting_field": "crawled_at",
}


def _create_sync_client() -> typesense.Client:
    """Create synchronous Typesense client."""
    settings = get_settings()
    return typesense.Client({
        "nodes": [{
            "host": settings.typesense_host,
            "port": str(settings.typesense_port),
            "protocol": "http",
        }],
        "api_key": settings.typesense_api_key,
        "connection_timeout_seconds": 10,
    })


class TypesenseClient:
    """Async wrapper for Typesense search operations."""

    def __init__(self):
        self.settings = get_settings()
        self._client: typesense.Client | None = None

    @property
    def client(self) -> typesense.Client:
        if self._client is None:
            self._client = _create_sync_client()
        return self._client

    async def ensure_collection(self) -> None:
        """Ensure the webpages collection exists."""
        def _sync_ensure():
            try:
                self.client.collections["webpages"].retrieve()
                logger.info("typesense_collection_exists")
            except typesense.exceptions.ObjectNotFound:
                logger.info("typesense_creating_collection")
                self.client.collections.create(WEBPAGES_SCHEMA)
                logger.info("typesense_collection_created")

        await asyncio.to_thread(_sync_ensure)

    async def index_page(
        self,
        url: str,
        title: str,
        content: str,
        snippet: str,
        domain: str,
    ) -> dict[str, Any]:
        """Index a single page (runs in thread pool)."""
        import time
        document = {
            "url": url,
            "title": title,
            "content": content[:10000],  # Truncate to avoid limits
            "snippet": snippet,
            "crawled_at": int(time.time()),
            "domain": domain,
        }

        def _sync_index():
            return self.client.collections["webpages"].documents.upsert(document)

        return await asyncio.to_thread(_sync_index)

    async def search(
        self,
        query: str,
        max_results: int = 10,
    ) -> list[dict[str, Any]]:
        """Search for pages matching query (runs in thread pool).

        Returns list of {url, title, snippet, domain}
        """
        search_params = {
            "q": query,
            "query_by": "title,content,snippet",
            "limit": max_results,
            "include_fields": "url,title,snippet,domain",
        }

        def _sync_search():
            return self.client.multi_search.perform({
                "searches": [
                    {"collection": self.settings.typesense_collection, **search_params}
                ]
            }, {})

        try:
            result = await asyncio.to_thread(_sync_search)
            hits = result["results"][0].get("hits", [])
            return [
                {
                    "url": hit["document"]["url"],
                    "title": hit["document"]["title"],
                    "snippet": hit["document"]["snippet"],
                    "domain": hit["document"]["domain"],
                }
                for hit in hits
            ]
        except Exception as e:
            logger.warning("typesense_search_failed", error=str(e))
            return []

    def close(self) -> None:
        """Close client connection."""
        # Typesense sync client doesn't need explicit close
        pass


# Singleton instance
_typesense_client: TypesenseClient | None = None


def get_typesense_client() -> TypesenseClient:
    """Get Typesense client singleton."""
    global _typesense_client
    if _typesense_client is None:
        _typesense_client = TypesenseClient()
    return _typesense_client

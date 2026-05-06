"""Resource registry for MCP server (MCP 2025-11-25)."""

from __future__ import annotations

from typing import Any
from dataclasses import dataclass

from mcp.types import Resource

import structlog

logger = structlog.get_logger()


@dataclass
class MCPResource:
    """An MCP resource with URI, name, description, and mime type."""
    uri: str
    name: str
    description: str = ""
    mime_type: str = "text/plain"

    def to_mcp_resource(self) -> Resource:
        """Convert to MCP Resource object."""
        return Resource(
            uri=self.uri,
            name=self.name,
            description=self.description,
            mimeType=self.mime_type,
        )


class ResourceRegistry:
    """Registry for MCP resources."""

    def __init__(self):
        self._resources: dict[str, MCPResource] = {}

    def register(
        self,
        uri: str,
        name: str,
        description: str = "",
        mime_type: str = "text/plain",
    ) -> None:
        """Register a resource."""
        self._resources[uri] = MCPResource(
            uri=uri,
            name=name,
            description=description,
            mime_type=mime_type,
        )
        logger.debug("resource_registered", uri=uri, name=name)

    async def read(self, uri: str) -> str | None:
        """Read a resource by URI. Override in subclass for dynamic resources."""
        resource = self._resources.get(uri)
        if resource is None:
            return None
        # Default: return placeholder. Override for actual content.
        return f"Resource: {resource.name}"

    def list_resources(self) -> list[Resource]:
        """List all registered resources as MCP Resource objects."""
        return [r.to_mcp_resource() for r in self._resources.values()]

    def get(self, uri: str) -> MCPResource | None:
        """Get a resource by URI."""
        return self._resources.get(uri)


class DynamicResourceRegistry(ResourceRegistry):
    """Resource registry with dynamic content loading."""

    def __init__(self):
        super().__init__()
        self._read_handlers: dict[str, Any] = {}

    def register_with_handler(
        self,
        uri: str,
        name: str,
        description: str = "",
        mime_type: str = "text/plain",
        read_handler: Any = None,
    ) -> None:
        """Register a resource with a custom read handler."""
        self.register(uri, name, description, mime_type)
        if read_handler:
            self._read_handlers[uri] = read_handler

    async def read(self, uri: str) -> str | None:
        """Read resource using custom handler if available."""
        if uri in self._read_handlers:
            handler = self._read_handlers[uri]
            if callable(handler):
                return await handler(uri)
        return await super().read(uri)


def create_default_registry() -> DynamicResourceRegistry:
    """Create registry with default WebSearch MCP resources."""
    registry = DynamicResourceRegistry()

    # Crawl state resource
    async def read_crawl_state(uri: str) -> str:
        import json
        from pathlib import Path
        state_file = Path("crawl_state/crawl_state.json")
        if state_file.exists():
            data = json.loads(state_file.read_text())
            return json.dumps(data, indent=2)
        return "{}"

    registry.register_with_handler(
        uri="websearch://crawl/state",
        name="crawl_state",
        description="Current crawl state including visited URLs and queue",
        mime_type="application/json",
        read_handler=read_crawl_state,
    )

    # Seeds resource
    async def read_seeds(uri: str) -> str:
        import json
        from pathlib import Path
        seeds_file = Path("crawl_state/seeds.json")
        if seeds_file.exists():
            data = json.loads(seeds_file.read_text())
            return json.dumps(data, indent=2)
        return "{}"

    registry.register_with_handler(
        uri="websearch://crawl/seeds",
        name="crawl_seeds",
        description="Seed URLs for web crawling",
        mime_type="application/json",
        read_handler=read_seeds,
    )

    # Config resource
    async def read_config(uri: str) -> str:
        from ..config import get_settings
        settings = get_settings()
        return settings.model_dump_json(indent=2)

    registry.register_with_handler(
        uri="websearch://config",
        name="config",
        description="Current WebSearch MCP configuration",
        mime_type="application/json",
        read_handler=read_config,
    )

    return registry
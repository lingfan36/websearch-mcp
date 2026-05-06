"""Tool registry for MCP server."""

from __future__ import annotations

from typing import Any, Awaitable, Callable
from dataclasses import dataclass

from mcp.types import Tool, TextContent
import structlog

logger = structlog.get_logger()

ToolHandler = Callable[[dict[str, Any]], Awaitable[list[TextContent]]]


@dataclass
class RegisteredTool:
    """A registered tool with its handler and schema."""
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: ToolHandler

    def to_mcp_tool(self) -> Tool:
        """Convert to MCP Tool object."""
        return Tool(
            name=self.name,
            description=self.description,
            inputSchema=self.input_schema,
        )


class ToolRegistry:
    """Registry for MCP tools with lazy loading."""

    def __init__(self):
        self._tools: dict[str, RegisteredTool] = {}

    def register(
        self,
        name: str,
        description: str,
        input_schema: dict[str, Any],
        handler: ToolHandler,
    ) -> None:
        """Register a tool with its handler."""
        self._tools[name] = RegisteredTool(
            name=name,
            description=description,
            input_schema=input_schema,
            handler=handler,
        )
        logger.debug("tool_registered", name=name)

    async def call(self, name: str, arguments: dict[str, Any]) -> list[TextContent]:
        """Call a registered tool by name."""
        if name not in self._tools:
            raise ValueError(f"Unknown tool: {name}")
        return await self._tools[name].handler(arguments)

    def list_tools(self) -> list[Tool]:
        """List all registered tools as MCP Tool objects."""
        return [t.to_mcp_tool() for t in self._tools.values()]

    def get_tool(self, name: str) -> RegisteredTool | None:
        """Get a registered tool by name."""
        return self._tools.get(name)


# === Pre-built tool handlers ===

async def web_search_quick_handler(args: dict[str, Any]) -> list[TextContent]:
    """Handler for web_search_quick tool."""
    import json
    from ..fetch import search_web, fetch_and_extract

    query = args.get("query", "")
    max_results = min(args.get("max_results", 10), 10)
    fetch_content = args.get("fetch_content", False)

    results = await search_web(query, max_results=max_results)

    if fetch_content and results:
        async def _fetch_one(r: dict[str, Any]) -> None:
            try:
                content, _ = await fetch_and_extract(r["url"], max_length=3000, check_robots=False)
                r["content"] = content[:3000]
            except Exception as e:
                r["content"] = f"<error>{e}</error>"

        import asyncio
        await asyncio.gather(*[_fetch_one(r) for r in results[:3]])

    return [TextContent(
        type="text",
        text=json.dumps(results, ensure_ascii=False, indent=2),
    )]


async def web_search_handler(args: dict[str, Any]) -> list[TextContent]:
    """Handler for web_search tool (deep research)."""
    import json
    from ..search_handler import handle_web_search

    result = await handle_web_search(
        query=args.get("query", ""),
        depth=args.get("depth", "balanced"),
    )
    return [TextContent(
        type="text",
        text=json.dumps(result, ensure_ascii=False, indent=2),
    )]


async def fetch_handler(args: dict[str, Any]) -> list[TextContent]:
    """Handler for fetch tool."""
    from ..fetch import fetch_and_extract

    content = await fetch_and_extract(
        url=args.get("url", ""),
        max_length=args.get("max_length", 5000),
        start_index=args.get("start_index", 0),
        raw=args.get("raw", False),
    )
    return [TextContent(type="text", text=content)]


async def fetch_with_insights_handler(args: dict[str, Any]) -> list[TextContent]:
    """Handler for fetch_with_insights tool."""
    import json
    from ..smart_fetch import smart_fetch

    result = await smart_fetch(
        url=args.get("url", ""),
        follow_depth=args.get("follow_depth", 2),
        max_length=args.get("max_length", 8000),
    )
    return [TextContent(
        type="text",
        text=json.dumps(result, ensure_ascii=False, indent=2),
    )]


async def fetch_batch_handler(args: dict[str, Any]) -> list[TextContent]:
    """Handler for fetch_batch tool."""
    import json
    import asyncio
    from ..fetch import fetch_and_extract

    urls = args.get("urls", [])[:10]
    max_length = args.get("max_length", 3000)

    async def _fetch_one(u: str) -> dict[str, Any]:
        try:
            content = await fetch_and_extract(u, max_length=max_length, check_robots=True)
            return {"url": u, "success": True, "content": content}
        except Exception as e:
            return {"url": u, "success": False, "error": str(e)}

    results = await asyncio.gather(*[_fetch_one(u) for u in urls])
    return [TextContent(
        type="text",
        text=json.dumps(list(results), ensure_ascii=False, indent=2),
    )]


def create_default_registry() -> ToolRegistry:
    """Create registry with default WebSearch MCP tools."""
    registry = ToolRegistry()

    registry.register(
        name="web_search_quick",
        description="""Fast web search using Jina Search API. No local LLM needed.

Returns search results with titles, URLs, and snippets instantly.
Optionally fetches top results' full content.

**Best for:** Quick lookups, finding specific information, comparing sources.
**For deep research:** Use `web_search` instead.""",
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "max_results": {"type": "integer", "default": 10, "description": "Max search results (1-10)"},
                "fetch_content": {"type": "boolean", "default": False, "description": "Fetch full content of top 3 results"},
            },
            "required": ["query"],
        },
        handler=web_search_quick_handler,
    )

    registry.register(
        name="web_search",
        description="""Deep research pipeline using indexed knowledge base.

Searches a pre-built index, uses query rewriting, fact extraction, quality
evaluation, and multi-source synthesis.

**Best for:** Complex research, multi-topic synthesis.
**For fast searches:** Use `web_search_quick` instead.

Returns: answer, citations, confidence (0-1), key_findings.""",
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "depth": {"type": "string", "enum": ["quick", "balanced", "deep"], "default": "balanced"},
            },
            "required": ["query"],
        },
        handler=web_search_handler,
    )

    registry.register(
        name="fetch",
        description="""Fetch a URL and return content as markdown.

Uses three-layer fallback: Jina Reader → local parser → Playwright browser.

**Best for:** Real-time data, specific URLs, trending topics.
Supports max_length, start_index (pagination), raw mode.""",
        input_schema={
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL to fetch"},
                "max_length": {"type": "integer", "default": 5000},
                "start_index": {"type": "integer", "default": 0},
                "raw": {"type": "boolean", "default": False},
            },
            "required": ["url"],
        },
        handler=fetch_handler,
    )

    registry.register(
        name="fetch_with_insights",
        description="""Smart fetcher with AI-powered link following.

Automatically follows relevant links, extracts structured data.
E.g. GitHub trending → auto-parse repos, stars, descriptions.

**Best for:** Research, comparisons, extracting multiple data points.""",
        input_schema={
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL to analyze"},
                "follow_depth": {"type": "integer", "default": 2},
                "max_length": {"type": "integer", "default": 8000},
            },
            "required": ["url"],
        },
        handler=fetch_with_insights_handler,
    )

    registry.register(
        name="fetch_batch",
        description="""Batch fetch multiple URLs concurrently.

Fetches up to 10 URLs in parallel and returns all results.
Each URL uses the same three-layer fallback as `fetch`.

**Best for:** Comparing multiple pages, gathering data from several sources.""",
        input_schema={
            "type": "object",
            "properties": {
                "urls": {"type": "array", "items": {"type": "string"}, "description": "URLs to fetch (max 10)"},
                "max_length": {"type": "integer", "default": 3000, "description": "Max chars per URL"},
            },
            "required": ["urls"],
        },
        handler=fetch_batch_handler,
    )

    return registry
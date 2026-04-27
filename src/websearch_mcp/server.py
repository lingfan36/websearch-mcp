"""MCP WebSearch Server — lightweight entry point with lazy loading."""

from __future__ import annotations

import json
import sys
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# Lightweight — only import MCP SDK at startup
# Heavy modules (ollama, trafilatura, typesense, etc.) load on first tool call

server = Server("websearch-mcp")


@server.list_tools()
async def list_tools() -> list[Tool]:
    """List available tools."""
    return [
        Tool(
            name="web_search",
            description="""Deep research pipeline using indexed knowledge base.

Searches a pre-built index, uses query rewriting, fact extraction, quality
evaluation, and multi-source synthesis.

**Best for:** Complex research, multi-topic synthesis.
**For real-time data:** Use `fetch` or `fetch_with_insights` instead.

Returns: answer, citations, confidence (0-1), key_findings.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query",
                    },
                    "depth": {
                        "type": "string",
                        "enum": ["quick", "balanced", "deep"],
                        "default": "balanced",
                    },
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="fetch",
            description="""Fetch a URL and return content as markdown.

**Best for:** Real-time data, specific URLs, trending topics.
Supports max_length, start_index (pagination), raw mode.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to fetch"},
                    "max_length": {"type": "integer", "default": 5000},
                    "start_index": {"type": "integer", "default": 0},
                    "raw": {"type": "boolean", "default": False},
                },
                "required": ["url"],
            },
        ),
        Tool(
            name="fetch_with_insights",
            description="""Smart fetcher with AI-powered link following.

Automatically follows relevant links, extracts structured data.
E.g. GitHub trending → auto-parse repos, stars, descriptions.

**Best for:** Research, comparisons, extracting multiple data points.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to analyze"},
                    "follow_depth": {"type": "integer", "default": 2},
                    "max_length": {"type": "integer", "default": 8000},
                },
                "required": ["url"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Handle tool calls — heavy imports happen here, not at startup."""
    if name == "web_search":
        from .search_handler import handle_web_search
        result = await handle_web_search(
            query=arguments.get("query", ""),
            depth=arguments.get("depth", "balanced"),
        )
        return [TextContent(
            type="text",
            text=json.dumps(result, ensure_ascii=False, indent=2),
        )]

    elif name == "fetch":
        from .fetch import fetch_and_extract
        content = await fetch_and_extract(
            url=arguments.get("url", ""),
            max_length=arguments.get("max_length", 5000),
            start_index=arguments.get("start_index", 0),
            raw=arguments.get("raw", False),
        )
        return [TextContent(type="text", text=content)]

    elif name == "fetch_with_insights":
        from .smart_fetch import smart_fetch
        result = await smart_fetch(
            url=arguments.get("url", ""),
            follow_depth=arguments.get("follow_depth", 2),
            max_length=arguments.get("max_length", 8000),
        )
        return [TextContent(
            type="text",
            text=json.dumps(result, ensure_ascii=False, indent=2),
        )]

    else:
        raise ValueError(f"Unknown tool: {name}")


def main():
    """Entry point — starts instantly, loads modules on demand."""
    import asyncio
    import logging

    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    logging.basicConfig(level=logging.WARNING)  # Quiet by default
    asyncio.run(_serve())


async def _serve():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


if __name__ == "__main__":
    main()

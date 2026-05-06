"""MCP WebSearch Server — lightweight entry point with lazy loading."""

from __future__ import annotations

import sys
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent, Resource, Prompt

# Import registries from registries/ subpackage
from .registries.tool_registry import create_default_registry as create_tool_registry_full
from .registries.resource_registry import create_default_registry as create_resource_registry_full
from .registries.prompt_registry import create_default_registry as create_prompt_registry_full

# Lightweight — only import MCP SDK at startup
# Heavy modules (ollama, trafilatura, typesense, etc.) load on first tool call

server = Server("websearch-mcp")

# Create registries
_tool_registry = create_tool_registry_full()
_resource_registry = create_resource_registry_full()
_prompt_registry = create_prompt_registry_full()


@server.list_tools()
async def list_tools() -> list[Tool]:
    """List available tools."""
    return _tool_registry.list_tools()


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Handle tool calls — delegate to tool registry."""
    return await _tool_registry.call(name, arguments)


# === Optional: resources and prompts ===
# Uncomment if MCP server supports list_resources / list_prompts

# @server.list_resources()
# async def list_resources() -> list[Resource]:
#     """List available resources."""
#     return _resource_registry.list_resources()

# @server.read_resource()
# async def read_resource(uri: str) -> str:
#     """Read a resource by URI."""
#     content = await _resource_registry.read(uri)
#     if content is None:
#         raise ValueError(f"Unknown resource: {uri}")
#     return content

# @server.list_prompts()
# async def list_prompts() -> list[Prompt]:
#     """List available prompts."""
#     return _prompt_registry.list_prompts()

# @server.get_prompt()
# async def get_prompt(name: str, arguments: dict[str, Any] | None = None) -> str:
#     """Get prompt content."""
#     return await _prompt_registry.get_prompt(name, arguments)


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
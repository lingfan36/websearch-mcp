"""MCP WebSearch Server."""

from __future__ import annotations

import json
import uuid
from typing import Any

import structlog
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from .llm import LLMClient, create_llm_client
from .nodes.rewriter import RewriterNode
from .nodes.search import SearchNode
from .nodes.extractor import ExtractorNode
from .nodes.evaluator import EvaluatorNode
from .nodes.synthesizer import SynthesizerNode
from .fetch import fetch_and_extract
from .smart_fetch import smart_fetch
from .schema import (
    Citation,
    Gap,
    SearchDepth,
    SearchSession,
    SearchTrace,
)
from .trace import create_trace_manager, TraceManager

logger = structlog.get_logger()

# Server instance
server = Server("websearch-mcp")


def create_tools() -> list[Tool]:
    """Create MCP tools."""
    return [
        Tool(
            name="web_search",
            description="""Web search with deep research capabilities using indexed knowledge base.

Searches through a pre-built index for comprehensive, well-researched answers.
Uses query rewriting, fact extraction, quality evaluation, and synthesis.

**Best for:** Complex research questions, multi-topic queries, synthesizing information from multiple sources.

**For real-time data** (trending topics, live scores, current news): Use the `fetch` tool directly to get the latest from specific URLs.

Returns structured results with citations and confidence scores.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query. Supports complex questions.",
                    },
                    "depth": {
                        "type": "string",
                        "enum": ["quick", "balanced", "deep"],
                        "default": "balanced",
                        "description": "Search depth. quick=fast response, balanced=default, deep=most thorough.",
                    },
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="fetch",
            description="""Direct URL fetcher for real-time content from any website.

Fetches and extracts content as readable markdown. Automatically handles
HTML-to-markdown conversion, pagination, and content truncation.

**When to use fetch:**
- Trending topics, live data, current news
- Specific URLs you know exist
- GitHub trending, Twitter, news sites
- Any content that needs to be fresh/real-time

**When to use fetch_with_insights instead:**
- Want AI to automatically follow links and extract key information
- Need structured data from multiple pages
- Researching a topic that requires exploring multiple pages

Supports:
- max_length: Control response size (default 5000 chars)
- start_index: Pagination for large content
- raw: Return original HTML if needed
- Automatic robots.txt compliance""",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "URL to fetch",
                    },
                    "max_length": {
                        "type": "integer",
                        "default": 5000,
                        "description": "Maximum number of characters to return",
                    },
                    "start_index": {
                        "type": "integer",
                        "default": 0,
                        "description": "Character index to start from (for pagination)",
                    },
                    "raw": {
                        "type": "boolean",
                        "default": False,
                        "description": "Return raw HTML instead of markdown",
                    },
                },
                "required": ["url"],
            },
        ),
        Tool(
            name="fetch_with_insights",
            description="""Smart fetcher with AI-powered link following and data extraction.

Use this when you want the AI to:
- Automatically explore relevant links from a page
- Extract structured information from multiple sources
- Get a comprehensive summary instead of raw content

**Example:** fetch_with_insights("https://github.com/trending") will:
1. Get the trending page
2. Follow top repository links
3. Extract repo names, stars, descriptions
4. Return structured data with key findings

Best for: Research, comparison, extracting multiple data points.
For simple single-page fetch: use `fetch` tool instead.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "URL to fetch and analyze",
                    },
                    "follow_depth": {
                        "type": "integer",
                        "default": 2,
                        "description": "How many link levels to follow (0=none, 1=few, 2=more)",
                    },
                    "max_length": {
                        "type": "integer",
                        "default": 8000,
                        "description": "Max characters per page",
                    },
                },
                "required": ["url"],
            },
        ),
    ]


async def run_search(
    query: str,
    depth: str = "balanced",
    llm: LLMClient | None = None,
) -> dict[str, Any]:
    """Run the full search pipeline.

    Pipeline: Rewriter → ParallelSearch → Extractor → Evaluator → [Synthesizer | Loop]
    """
    if llm is None:
        llm = create_llm_client()

    # Initialize nodes
    rewriter = RewriterNode(llm)
    searcher = SearchNode()
    extractor = ExtractorNode(llm)
    evaluator = EvaluatorNode(llm)
    synthesizer = SynthesizerNode(llm)

    # Create session
    session_id = str(uuid.uuid4())
    session = SearchSession(
        id=session_id,
        original_query=query,
        max_iterations=3,
    )

    # Create trace
    trace = create_trace_manager(session_id)

    logger.info("search_session_start", session_id=session_id, query=query, depth=depth)

    try:
        # === Step 1: Rewrite ===
        rewriter_output = await rewriter.run(query, trace)
        session.rewritten_queries = rewriter_output.queries
        trace.checkpoint("rewriter_done", session, "query rewrite complete")

        # Override depth if specified
        if depth != "balanced":
            depth_map = {"quick": SearchDepth.QUICK, "deep": SearchDepth.DEEP}
            for q in session.rewritten_queries:
                q.search_depth = depth_map.get(depth, SearchDepth.BALANCED)

        # === Search Loop ===
        while session.iterations < session.max_iterations:
            session.iterations += 1
            logger.info("search_iteration_start", iteration=session.iterations)

            # === Step 2: Parallel Search + Crawl ===
            search_results, _ = await searcher.run(rewriter_output, crawl=True, trace=trace)
            session.search_results.extend(search_results)
            trace.checkpoint(f"search_iter{session.iterations}_done", session, "search complete")

            if not search_results:
                logger.warning("search_no_results", iteration=session.iterations)
                break

            # === Step 3: Extract ===
            extractor_output = await extractor.run(search_results, trace)
            session.extracted_facts.merge(extractor_output.facts)
            trace.checkpoint(f"extract_iter{session.iterations}_done", session, "extraction complete")

            # === Step 4: Evaluate ===
            eval_output = await evaluator.run(session, trace)
            trace.checkpoint(f"evaluate_iter{session.iterations}_done", session, f"eval: {eval_output.status}")

            if eval_output.sufficient or eval_output.status == "exhausted":
                break

            # === Not sufficient: identify gaps and continue ===
            session.gaps = eval_output.gaps
            logger.info("search_needs_more", gaps=len(eval_output.gaps), confidence=eval_output.confidence)

            # For next iteration, add gap queries to rewriter output
            new_queries = []
            for gap in eval_output.gaps:
                for sq in gap.suggested_queries[:2]:
                    from .schema import RewrittenQuery
                    new_queries.append(RewrittenQuery(
                        query=sq,
                        rationale=f"gap_filling: {gap.description}",
                        search_depth=SearchDepth.BALANCED,
                    ))

            if new_queries:
                # Replace queries with gap-filling queries for next iteration
                rewriter_output.queries = new_queries

        # === Step 5: Synthesize ===
        trace.checkpoint("before_synthesize", session, "ready to synthesize")
        synth_output = await synthesizer.run(
            session.extracted_facts,
            session.gaps,
            query,
            session.iterations,
            trace,
        )

        # === Build response ===
        result = {
            "answer": synth_output.answer,
            "citations": [c.model_dump() for c in synth_output.citations],
            "confidence": synth_output.confidence,
            "key_findings": synth_output.key_findings,
            "iterations_used": session.iterations,
            "trace_id": trace.trace.id,
            "status": synth_output.status,
        }

        if synth_output.limitations:
            result["limitations"] = synth_output.limitations

        logger.info("search_session_done", session_id=session_id, iterations=session.iterations)
        return result

    except Exception as e:
        logger.error("search_session_failed", session_id=session_id, error=str(e))
        return {
            "answer": f"Search failed: {str(e)}",
            "citations": [],
            "confidence": 0.0,
            "key_findings": [],
            "iterations_used": session.iterations,
            "trace_id": trace.trace.id,
            "status": "failed",
            "error": str(e),
        }
    finally:
        await llm.close()


@server.list_tools()
async def list_tools() -> list[Tool]:
    """List available tools."""
    return create_tools()


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Handle tool calls."""
    if name == "web_search":
        query = arguments.get("query", "")
        depth = arguments.get("depth", "balanced")

        result = await run_search(query, depth)

        return [TextContent(
            type="text",
            text=json.dumps(result, ensure_ascii=False, indent=2),
        )]
    elif name == "fetch":
        url = arguments.get("url", "")
        max_length = arguments.get("max_length", 5000)
        start_index = arguments.get("start_index", 0)
        raw = arguments.get("raw", False)

        content = await fetch_and_extract(
            url=url,
            max_length=max_length,
            start_index=start_index,
            raw=raw,
        )

        return [TextContent(type="text", text=content)]
    elif name == "fetch_with_insights":
        url = arguments.get("url", "")
        follow_depth = arguments.get("follow_depth", 2)
        max_length = arguments.get("max_length", 8000)

        result = await smart_fetch(
            url=url,
            follow_depth=follow_depth,
            max_length=max_length,
        )

        return [TextContent(
            type="text",
            text=json.dumps(result, ensure_ascii=False, indent=2),
        )]
    else:
        raise ValueError(f"Unknown tool: {name}")


def main():
    """Main entry point — sync wrapper for MCP server."""
    import asyncio
    import logging
    import sys

    # Windows UTF-8 fix
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    logging.basicConfig(level=logging.INFO)

    asyncio.run(_serve())


async def _serve():
    """Async server entry point."""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


if __name__ == "__main__":
    main()

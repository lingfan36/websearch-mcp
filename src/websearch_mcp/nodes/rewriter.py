"""Rewriter node — rewrites user query into search-friendly sub-queries."""

from __future__ import annotations

import json
from pathlib import Path

import structlog

from ..llm import LLMClient
from ..schema import (
    RewriterOutput,
    RewrittenQuery,
    SearchDepth,
)
from ..trace import TraceManager
from ..schema import NodeType
from .skill_config import SkillConfig

logger = structlog.get_logger()


REWRITER_PROMPT = """You are a query rewriting assistant for a web search agent.

Given a user's search query, rewrite it into 2-5 more specific sub-queries that will help find comprehensive information.

Guidelines:
- Each sub-query should be search-engine friendly (use specific terms)
- Include different angles/aspects of the original query
- For "compare X and Y" queries, create queries for each entity separately
- For "latest X" queries, include time-specific terms

Return a JSON object with:
- queries: array of objects with query, rationale, search_depth fields
- reasoning: brief explanation of the rewrite strategy

search_depth can be: "quick" (1 result), "balanced" (3 results), or "deep" (5+ results)

Original query: {query}
"""


class RewriterNode:
    """Rewrites user queries into search-friendly sub-queries."""

    def __init__(self, llm: LLMClient, system_prompt: str | None = None):
        self.llm = llm
        self.system_prompt = system_prompt or REWRITER_PROMPT

    @classmethod
    def load_skill(cls, llm: LLMClient, skill_config: SkillConfig | None = None) -> RewriterNode:
        """Create a RewriterNode from a skill config."""
        if skill_config is None:
            return cls(llm)
        return cls(llm, system_prompt=skill_config.system_prompt)

    async def run(
        self,
        query: str,
        trace: TraceManager | None = None,
    ) -> RewriterOutput:
        """Rewrite query into sub-queries.

        Args:
            query: Original user query
            trace: Optional trace manager

        Returns:
            RewriterOutput with sub-queries
        """
        logger.info("rewriter_start", query=query)

        schema = {
            "type": "object",
            "properties": {
                "queries": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string"},
                            "rationale": {"type": "string"},
                            "search_depth": {"type": "string", "enum": ["quick", "balanced", "deep"]},
                        },
                        "required": ["query", "rationale", "search_depth"],
                    },
                },
                "reasoning": {"type": "string"},
            },
            "required": ["queries", "reasoning"],
        }

        try:
            response = await self.llm.chat_str(
                system=self.system_prompt,
                user=REWRITER_PROMPT.format(query=query),
                schema=schema,
            )

            try:
                data = json.loads(response)
            except json.JSONDecodeError as e:
                logger.warning("rewriter_json_parse_failed", error=str(e), response_preview=response[:200])
                raise

            queries = []
            for q in data.get("queries", []):
                if not isinstance(q, dict):
                    continue
                depth_str = q.get("search_depth", "balanced")
                try:
                    depth = SearchDepth(depth_str)
                except ValueError:
                    depth = SearchDepth.BALANCED
                queries.append(RewrittenQuery(
                    query=q.get("query", ""),
                    rationale=q.get("rationale", ""),
                    search_depth=depth,
                ))

            output = RewriterOutput(
                queries=queries,
                reasoning=data.get("reasoning", ""),
                status="success",
            )

            if trace:
                trace.log_event(
                    node=NodeType.REWRITER,
                    action="rewrite",
                    input_data=query,
                    output_data=[q.model_dump() for q in queries],
                    decision={"type": "route", "reason": output.reasoning},
                )

            logger.info("rewriter_done", query_count=len(queries))
            return output

        except Exception as e:
            logger.warning("rewriter_failed", error=str(e))
            # Fallback: use original query
            fallback = RewriterOutput(
                queries=[RewrittenQuery(
                    query=query,
                    rationale="original_query",
                    search_depth=SearchDepth.BALANCED,
                )],
                reasoning=f"rewrite_failed: {e}",
                status="failed",
            )

            if trace:
                trace.log_event(
                    node=NodeType.REWRITER,
                    action="rewrite_fallback",
                    input_data=query,
                    output_data=[q.model_dump() for q in fallback.queries],
                    error={"type": type(e).__name__, "message": str(e), "recoverable": True},
                )

            return fallback

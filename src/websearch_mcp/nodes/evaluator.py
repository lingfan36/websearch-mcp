"""Evaluator node — assesses if search results are sufficient."""

from __future__ import annotations

import json
import structlog

from ..llm import LLMClient
from ..schema import (
    EvaluatorOutput,
    ExtractedFacts,
    Gap,
    GapType,
    SearchSession,
)
from ..trace import TraceManager
from ..schema import NodeType

logger = structlog.get_logger()


EVALUATOR_PROMPT = """You are a search quality evaluator.

Given the original query and extracted facts, determine if the search is sufficient.

Original query: {query}

Extracted facts:
- Entities: {entities}
- Key findings: {findings}
- Statistics: {statistics}
- Quotes: {quotes}
- Timelines: {timelines}

Assess:
1. Does the information cover the main aspects of the query?
2. Are there obvious gaps or missing information?
3. Is the information recent enough if recency matters?
4. Are there any unverified claims or contradictions?

Return a JSON object with:
- sufficient: boolean — true if ready to synthesize
- confidence: float 0-1 — how confident you are
- coverage: object with breadth, depth, recency, authority scores (0-1 each)
- gaps: array of objects with type, description, suggested_queries fields
  - types: "missing_entity", "missing_date", "insufficient_depth", "contradiction"
- reasoning: string explaining your assessment

If sufficient is false, provide specific gaps and suggested queries to fill them.
"""


# History tracking for dead-loop prevention
class GapHistory:
    """Tracks gap history to detect repeated gaps."""

    def __init__(self, threshold: int = 2):
        self.history: dict[str, int] = {}
        self.threshold = threshold

    def record(self, gaps: list[Gap]) -> list[Gap]:
        """Record gaps and return those that have exceeded threshold."""
        repeated = []
        for gap in gaps:
            key = f"{gap.type}:{gap.description[:50]}"
            count = self.history.get(key, 0) + 1
            self.history[key] = count
            if count >= self.threshold:
                repeated.append(gap)
        return repeated

    def reset(self) -> None:
        self.history.clear()


class EvaluatorNode:
    """Evaluates if search results are sufficient."""

    def __init__(
        self,
        llm: LLMClient,
        confidence_threshold: float = 0.7,
        max_iterations: int = 3,
        gap_threshold: int = 2,
    ):
        self.llm = llm
        self.confidence_threshold = confidence_threshold
        self.max_iterations = max_iterations
        self.gap_history = GapHistory(threshold=gap_threshold)

    async def run(
        self,
        session: SearchSession,
        trace: TraceManager | None = None,
    ) -> EvaluatorOutput:
        """Evaluate search sufficiency.

        Args:
            session: Current search session
            trace: Optional trace manager

        Returns:
            EvaluatorOutput with assessment
        """
        facts = session.extracted_facts

        # Dead-loop check: max iterations
        if session.iterations >= self.max_iterations:
            output = EvaluatorOutput(
                sufficient=False,
                confidence=0.5,
                coverage={"breadth": 0.5, "depth": 0.5, "recency": 0.5, "authority": 0.5},
                gaps=[],
                status="exhausted",
                reasoning=f"max_iterations_reached ({self.max_iterations})",
            )
            if trace:
                trace.log_event(
                    node=NodeType.EVALUATOR,
                    action="evaluate",
                    input_data={"iterations": session.iterations},
                    output_data=output.model_dump(),
                    decision={"type": "route", "reason": "max_iterations"},
                )
            return output

        logger.info("evaluator_start", iteration=session.iterations)

        # Format facts for prompt
        entities_text = ", ".join([f"{e['name']}: {e['description']}" for e in facts.entities[:5]])
        findings_text = "\n".join([f"- {f}" for f in facts.key_findings[:5]])
        stats_text = ", ".join([f"{s['label']}: {s['value']}" for s in facts.statistics[:5]])
        quotes_text = "\n".join([f'"{q["text"][:100]}..." - {q.get("source", "unknown")}' for q in facts.quotes[:3]])
        timeline_text = "\n".join([f"{t.get('date', '?')}: {t.get('event', '')}" for t in facts.timelines[:5]])

        schema = {
            "type": "object",
            "properties": {
                "sufficient": {"type": "boolean"},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "coverage": {
                    "type": "object",
                    "properties": {
                        "breadth": {"type": "number"},
                        "depth": {"type": "number"},
                        "recency": {"type": "number"},
                        "authority": {"type": "number"},
                    },
                },
                "gaps": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "type": {"type": "string", "enum": ["missing_entity", "missing_date", "insufficient_depth", "contradiction"]},
                            "description": {"type": "string"},
                            "suggested_queries": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": ["type", "description", "suggested_queries"],
                    },
                },
                "reasoning": {"type": "string"},
            },
            "required": ["sufficient", "confidence", "coverage", "gaps", "reasoning"],
        }

        try:
            response = await self.llm.chat_str(
                system="You are a search quality evaluator. Always respond with valid JSON only.",
                user=EVALUATOR_PROMPT.format(
                    query=session.original_query,
                    entities=entities_text or "None",
                    findings=findings_text or "None",
                    statistics=stats_text or "None",
                    quotes=quotes_text or "None",
                    timelines=timeline_text or "None",
                ),
                schema=schema,
            )

            try:
                data = json.loads(response)
            except json.JSONDecodeError as e:
                logger.warning("evaluator_json_parse_failed", error=str(e), response_preview=response[:200])
                raise

            gaps = []
            for g in data.get("gaps", []):
                if not isinstance(g, dict):
                    continue
                try:
                    gap_type = GapType(g.get("type", "insufficient_depth"))
                except ValueError:
                    gap_type = GapType.INSUFFICIENT_DEPTH
                gaps.append(Gap(
                    type=gap_type,
                    description=g.get("description", ""),
                    suggested_queries=g.get("suggested_queries", []),
                ))

            # Check for repeated gaps
            repeated_gaps = self.gap_history.record(gaps)
            if repeated_gaps:
                logger.warning("evaluator_repeated_gaps", count=len(repeated_gaps))

            sufficient = data.get("sufficient", False)
            confidence = data.get("confidence", 0.5)

            # Apply confidence threshold override
            if confidence >= self.confidence_threshold:
                sufficient = True

            # Check for repeated gaps (dead-loop prevention)
            if repeated_gaps:
                sufficient = False
                status = "exhausted"
                reasoning = "gap_not_resolvable_after_retries"
            elif sufficient:
                status = "ready"
                reasoning = data.get("reasoning", "")
            else:
                status = "needs_more"
                reasoning = data.get("reasoning", "")

            output = EvaluatorOutput(
                sufficient=sufficient,
                confidence=confidence,
                coverage=data.get("coverage", {"breadth": 0.5, "depth": 0.5, "recency": 0.5, "authority": 0.5}),
                gaps=gaps,
                status=status,
                reasoning=reasoning,
            )

            if trace:
                trace.log_event(
                    node=NodeType.EVALUATOR,
                    action="evaluate",
                    input_data={"iteration": session.iterations, "gaps_count": len(gaps)},
                    output_data={
                        "sufficient": sufficient,
                        "confidence": confidence,
                        "status": status,
                    },
                    decision={"type": "route", "reason": reasoning},
                    metadata={"gaps": [g.model_dump() for g in gaps]},
                )

            logger.info("evaluator_done", sufficient=sufficient, confidence=confidence, status=status)
            return output

        except Exception as e:
            logger.warning("evaluator_failed", error=str(e))
            # On error, be conservative
            output = EvaluatorOutput(
                sufficient=False,
                confidence=0.3,
                coverage={"breadth": 0.3, "depth": 0.3, "recency": 0.3, "authority": 0.3},
                gaps=[],
                status="needs_more",
                reasoning=f"eval_error: {e}",
            )

            if trace:
                trace.log_event(
                    node=NodeType.EVALUATOR,
                    action="evaluate_error",
                    error={"type": type(e).__name__, "message": str(e), "recoverable": True},
                )

            return output

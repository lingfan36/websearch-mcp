"""Synthesizer node — synthesizes final answer from extracted facts."""

from __future__ import annotations

import json
import structlog

from ..llm import LLMClient
from ..schema import (
    Citation,
    ExtractedFacts,
    Gap,
    SynthesizerOutput,
)
from ..trace import TraceManager
from ..schema import NodeType

logger = structlog.get_logger()


SYNTHESIZER_PROMPT = """You are a research synthesis assistant.

Given the original query and extracted facts, write a comprehensive, well-structured answer.

Original query: {query}

Extracted information:
- Entities: {entities}
- Key findings: {findings}
- Statistics: {statistics}
- Quotes: {quotes}
- Timelines: {timelines}

{additional_context}

Requirements:
- Write in a clear, informative style
- Include specific facts, numbers, and dates when available
- Use bullet points for key findings
- Acknowledge limitations if information is incomplete
- If gaps exist, mention what couldn't be verified

Return a JSON object with:
- answer: string — the synthesized answer (markdown formatted)
- citations: array of {{text, url, title}} — key citations supporting the answer
- confidence: float 0-1 — confidence in the answer
- key_findings: array of strings — main bullet points
- limitations: string or null — any limitations or unverified claims
"""


class SynthesizerNode:
    """Synthesizes final answer from extracted facts."""

    def __init__(self, llm: LLMClient):
        self.llm = llm

    async def run(
        self,
        facts: ExtractedFacts,
        gaps: list[Gap],
        original_query: str,
        iterations_used: int,
        trace: TraceManager | None = None,
    ) -> SynthesizerOutput:
        """Synthesize final answer.

        Args:
            facts: Extracted facts
            gaps: Identified gaps
            original_query: Original user query
            iterations_used: Number of search iterations
            trace: Optional trace manager

        Returns:
            SynthesizerOutput with final answer
        """
        logger.info("synthesizer_start", iterations=iterations_used)

        # Format facts for prompt - handle both dict and string entity formats
        def format_entity(e):
            if isinstance(e, dict):
                return f"- {e.get('name', 'unknown')}: {e.get('description', '')}"
            return f"- {str(e)}"

        entities_text = "\n".join([format_entity(e) for e in facts.entities[:10]])
        def format_stat(s):
            if isinstance(s, dict):
                return f"- {s.get('label', 'unknown')}: {s.get('value', '')}"
            return f"- {str(s)}"

        findings_text = "\n".join([f"- {f}" for f in facts.key_findings[:10]])
        stats_text = "\n".join([format_stat(s) for s in facts.statistics[:10]])
        quotes_text = "\n".join([
            f'- "{q["text"][:150]}..." — {q.get("source", "unknown")}'
            for q in facts.quotes[:5]
        ])
        timeline_text = "\n".join([
            f"- {t.get('date', '?')}: {t.get('event', '')}"
            for t in facts.timelines[:10]
        ])

        # Gap context
        additional_context = ""
        if gaps:
            gap_text = "\n".join([f"- {g.description}" for g in gaps])
            additional_context = f"\n\nKnown gaps (couldn't verify):\n{gap_text}\n"

        schema = {
            "type": "object",
            "properties": {
                "answer": {"type": "string"},
                "citations": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "text": {"type": "string"},
                            "url": {"type": "string"},
                            "title": {"type": "string"},
                        },
                        "required": ["text", "url", "title"],
                    },
                },
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "key_findings": {"type": "array", "items": {"type": "string"}},
                "limitations": {"type": ["string", "null"]},
            },
            "required": ["answer", "citations", "confidence", "key_findings"],
        }

        try:
            response = await self.llm.chat_str(
                system="You are a research synthesis assistant. Always respond with valid JSON only.",
                user=SYNTHESIZER_PROMPT.format(
                    query=original_query,
                    entities=entities_text or "None found",
                    findings=findings_text or "None found",
                    statistics=stats_text or "None found",
                    quotes=quotes_text or "None found",
                    timelines=timeline_text or "None found",
                    additional_context=additional_context,
                ),
                schema=schema,
            )

            try:
                data = json.loads(response)
            except json.JSONDecodeError as e:
                logger.warning("synthesizer_json_parse_failed", error=str(e), response_preview=response[:200])
                # Try to extract JSON object from markdown/text response
                import re
                match = re.search(r'\{[\s\S]*\}', response)
                if match:
                    try:
                        data = json.loads(match.group(0))
                        logger.info("synthesizer_json_extracted_from_response")
                    except json.JSONDecodeError:
                        data = None
                else:
                    data = None
                if data is None:
                    raise

            citations = [
                Citation(
                    text=c["text"],
                    url=c["url"],
                    title=c["title"],
                )
                for c in data.get("citations", [])
                if c.get("url")
            ]

            output = SynthesizerOutput(
                answer=data.get("answer", ""),
                citations=citations,
                confidence=data.get("confidence", 0.5),
                key_findings=data.get("key_findings", []),
                limitations=data.get("limitations"),
                status="success",
            )

            if trace:
                trace.log_event(
                    node=NodeType.SYNTHESIZER,
                    action="synthesize",
                    input_data={"iterations": iterations_used, "fact_counts": {
                        "entities": len(facts.entities),
                        "findings": len(facts.key_findings),
                        "statistics": len(facts.statistics),
                    }},
                    output_data={
                        "answer_length": len(output.answer),
                        "citation_count": len(output.citations),
                        "confidence": output.confidence,
                    },
                )

            logger.info("synthesizer_done", answer_length=len(output.answer), citations=len(citations))
            return output

        except Exception as e:
            logger.warning("synthesizer_failed", error=str(e))
            # Ultimate fallback: direct拼接
            answer_parts = []
            if facts.key_findings:
                answer_parts.append("Key findings:\n" + "\n".join([f"- {f}" for f in facts.key_findings]))
            if facts.entities:
                def format_entity_fallback(e):
                    if isinstance(e, dict):
                        return f"- {e.get('name', 'unknown')}: {e.get('description', '')}"
                    return f"- {str(e)}"
                answer_parts.append("\nEntities found:\n" + "\n".join([format_entity_fallback(e) for e in facts.entities[:5]]))
            if facts.statistics:
                def format_stat_fallback(s):
                    if isinstance(s, dict):
                        return f"- {s.get('label', 'unknown')}: {s.get('value', '')}"
                    return f"- {str(s)}"
                answer_parts.append("\nStatistics:\n" + "\n".join([format_stat_fallback(s) for s in facts.statistics[:5]]))

            answer = "\n".join(answer_parts) if answer_parts else "Unable to synthesize results."

            # Extract citations from facts - handle both dict and string formats
            citations = []
            for q in facts.quotes[:5]:
                if isinstance(q, dict):
                    text = q.get("text", "")
                    source = q.get("source", "")
                else:
                    text = str(q)
                    source = ""
                if text or source:
                    citations.append(Citation(
                        text=text[:100] if text else "Quote",
                        url=source,
                        title="Quote source"
                    ))

            output = SynthesizerOutput(
                answer=answer,
                citations=citations,
                confidence=0.2,
                key_findings=facts.key_findings[:5],
                limitations="synthesis_failed_fallback",
                status="success",
            )

            if trace:
                trace.log_event(
                    node=NodeType.SYNTHESIZER,
                    action="synthesize_fallback",
                    error={"type": type(e).__name__, "message": str(e), "recoverable": False},
                )

            return output

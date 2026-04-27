"""Extractor node — extracts structured facts from search results."""

from __future__ import annotations

import json
import structlog

from ..llm import LLMClient
from ..schema import (
    ExtractedFacts,
    ExtractorOutput,
    SearchResult,
)
from ..trace import TraceManager
from ..schema import NodeType

logger = structlog.get_logger()


EXTRACTOR_PROMPT = """You are an information extraction assistant.

Given a list of search results (snippets), extract structured factual information.

Extract the following types of information when present:
- entities: Named entities (people, organizations, products, etc.) with descriptions
- key_findings: Key facts or conclusions from the sources
- statistics: Numbers, statistics, metrics with labels
- quotes: Notable direct quotes with attribution
- timelines: Events with dates

Return a JSON object with the extracted information. Only include fields that have meaningful data.

Search results:
{results}
"""


class ExtractorNode:
    """Extracts structured facts from search results."""

    def __init__(self, llm: LLMClient):
        self.llm = llm

    async def run(
        self,
        results: list[SearchResult],
        trace: TraceManager | None = None,
    ) -> ExtractorOutput:
        """Extract facts from search results.

        Args:
            results: List of search results
            trace: Optional trace manager

        Returns:
            ExtractorOutput with extracted facts
        """
        if not results:
            logger.warning("extractor_no_results")
            return ExtractorOutput(
                facts=ExtractedFacts(),
                status="failed",
                error="no results to extract",
            )

        logger.info("extractor_start", result_count=len(results))

        # Prepare results text - prefer raw_content over snippet
        results_text = "\n\n".join([
            f"[{i+1}] {r.title}\nURL: {r.url}\nContent: {r.raw_content if r.raw_content else r.snippet}"
            for i, r in enumerate(results)
        ])

        schema = {
            "type": "object",
            "properties": {
                "entities": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "description": {"type": "string"},
                        },
                        "required": ["name", "description"],
                    },
                },
                "key_findings": {"type": "array", "items": {"type": "string"}},
                "statistics": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "label": {"type": "string"},
                            "value": {"type": "string"},
                        },
                        "required": ["label", "value"],
                    },
                },
                "quotes": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "text": {"type": "string"},
                            "source": {"type": "string"},
                        },
                        "required": ["text", "source"],
                    },
                },
                "timelines": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "date": {"type": "string"},
                            "event": {"type": "string"},
                        },
                        "required": ["date", "event"],
                    },
                },
            },
        }

        try:
            response = await self.llm.chat_str(
                system="You are an information extraction assistant. Always respond with valid JSON only.",
                user=EXTRACTOR_PROMPT.format(results=results_text),
                schema=schema,
            )

            try:
                data = json.loads(response)
            except json.JSONDecodeError as e:
                logger.warning("extractor_json_parse_failed", error=str(e), response_preview=response[:200])
                # Try to extract JSON object from markdown/text response
                import re
                match = re.search(r'\{[\s\S]*\}', response)
                if match:
                    try:
                        data = json.loads(match.group(0))
                        logger.info("extractor_json_extracted_from_response")
                    except json.JSONDecodeError:
                        data = None
                else:
                    data = None
                if data is None:
                    raise

            # Handle flexible entity formats
            entities_data = data.get("entities", [])
            if isinstance(entities_data, dict):
                # LLM returned categorized entities like {people: [], organizations: []}
                # Flatten into simple list
                entities = []
                for category, items in entities_data.items():
                    if isinstance(items, list):
                        entities.extend(items)
                entities_data = entities

            # Normalize to correct types
            def normalize_list(val, item_type="string"):
                if not isinstance(val, list):
                    return []
                result = []
                for item in val:
                    if item_type == "string":
                        result.append(item if isinstance(item, str) else str(item))
                    elif item_type == "dict":
                        result.append(item if isinstance(item, dict) else {"text": str(item)})
                    elif item_type == "entity":
                        if isinstance(item, dict):
                            result.append(item)
                        else:
                            result.append({"name": str(item), "description": ""})
                    elif item_type == "stat":
                        if isinstance(item, dict):
                            result.append(item)
                        else:
                            result.append({"label": "", "value": str(item)})
                    elif item_type == "timeline":
                        if isinstance(item, dict):
                            result.append(item)
                        else:
                            result.append({"date": "", "event": str(item)})
                return result

            facts = ExtractedFacts(
                entities=normalize_list(entities_data, "entity"),
                key_findings=normalize_list(data.get("key_findings", []), "string"),
                statistics=normalize_list(data.get("statistics", []), "stat"),
                quotes=normalize_list(data.get("quotes", []), "dict"),
                timelines=normalize_list(data.get("timelines", []), "timeline"),
            )

            # Calculate source coverage
            source_coverage = {r.url: 1.0 for r in results}

            output = ExtractorOutput(
                facts=facts,
                source_coverage=source_coverage,
                status="success",
            )

            if trace:
                trace.log_event(
                    node=NodeType.EXTRACTOR,
                    action="extract",
                    input_data={"result_count": len(results)},
                    output_data={
                        "entities": len(facts.entities),
                        "findings": len(facts.key_findings),
                    },
                )

            logger.info("extractor_done", entities=len(facts.entities), findings=len(facts.key_findings))
            return output

        except Exception as e:
            logger.warning("extractor_failed", error=str(e))
            # Fallback: simple extraction from snippets
            facts = ExtractedFacts(
                key_findings=[r.snippet for r in results[:3]],
            )
            output = ExtractorOutput(
                facts=facts,
                status="partial",
                error=str(e),
            )

            if trace:
                trace.log_event(
                    node=NodeType.EXTRACTOR,
                    action="extract_fallback",
                    input_data={"result_count": len(results)},
                    output_data={"findings": len(facts.key_findings)},
                    error={"type": type(e).__name__, "message": str(e), "recoverable": True},
                )

            return output

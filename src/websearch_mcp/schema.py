"""Data models for WebSearch Agent."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from pydantic import BaseModel, Field


class SearchDepth(str, Enum):
    QUICK = "quick"
    BALANCED = "balanced"
    DEEP = "deep"


class NodeType(str, Enum):
    REWRITER = "rewriter"
    SEARCH = "search"
    EXTRACTOR = "extractor"
    EVALUATOR = "evaluator"
    SYNTHESIZER = "synthesizer"


class DecisionType(str, Enum):
    ROUTE = "route"
    RETRY = "retry"
    FALLBACK = "fallback"
    SKIP = "skip"


class GapType(str, Enum):
    MISSING_ENTITY = "missing_entity"
    MISSING_DATE = "missing_date"
    INSUFFICIENT_DEPTH = "insufficient_depth"
    CONTRADICTION = "contradiction"


# === Rewriter ===

class RewrittenQuery(BaseModel):
    query: str
    rationale: str
    search_depth: SearchDepth = SearchDepth.BALANCED


class RewriterOutput(BaseModel):
    queries: list[RewrittenQuery]
    reasoning: str
    status: str = "success"  # success | failed


# === Search ===

class SearchResult(BaseModel):
    id: str
    query_used: str
    source: str = "builtin"
    url: str
    title: str
    snippet: str
    raw_content: str | None = None
    relevance_score: float | None = None
    fetched_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    fetch_duration_ms: int | None = None


# === Extractor ===

class ExtractedFacts(BaseModel):
    entities: list[dict[str, str]] = Field(default_factory=list)
    key_findings: list[str] = Field(default_factory=list)
    statistics: list[dict[str, str]] = Field(default_factory=list)
    quotes: list[dict[str, str]] = Field(default_factory=list)
    timelines: list[dict[str, str]] = Field(default_factory=list)

    def merge(self, other: ExtractedFacts) -> None:
        self.entities.extend(other.entities)
        self.key_findings.extend(other.key_findings)
        self.statistics.extend(other.statistics)
        self.quotes.extend(other.quotes)
        self.timelines.extend(other.timelines)


class ExtractorOutput(BaseModel):
    facts: ExtractedFacts = Field(default_factory=ExtractedFacts)
    source_coverage: dict[str, float] = Field(default_factory=dict)
    status: str = "success"  # success | partial | failed
    error: str | None = None


# === Evaluator ===

class Gap(BaseModel):
    type: GapType
    description: str
    suggested_queries: list[str] = Field(default_factory=list)


class EvaluatorOutput(BaseModel):
    sufficient: bool
    confidence: float  # 0-1
    coverage: dict[str, float] = Field(default_factory=dict)
    gaps: list[Gap] = Field(default_factory=list)
    status: str = "ready"  # ready | needs_more | exhausted
    reasoning: str


# === Synthesizer ===

class Citation(BaseModel):
    text: str
    url: str
    title: str


class SynthesizerOutput(BaseModel):
    answer: str
    citations: list[Citation] = Field(default_factory=list)
    confidence: float
    key_findings: list[str] = Field(default_factory=list)
    limitations: str | None = None
    status: str = "success"  # success | failed


# === Session ===

class SearchSession(BaseModel):
    id: str
    original_query: str
    rewritten_queries: list[RewrittenQuery] = Field(default_factory=list)
    search_results: list[SearchResult] = Field(default_factory=list)
    extracted_facts: ExtractedFacts = Field(default_factory=ExtractedFacts)
    gaps: list[Gap] = Field(default_factory=list)
    iterations: int = 0
    max_iterations: int = 3
    total_cost: float = 0.0


# === Trace ===

class TraceEvent(BaseModel):
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    node: NodeType
    action: str
    duration_ms: int = 0
    input_hash: str = ""
    output_hash: str = ""
    decision: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class Checkpoint(BaseModel):
    name: str
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    snapshot: dict[str, Any] = Field(default_factory=dict)
    reason: str


class SearchTrace(BaseModel):
    id: str
    session_id: str
    events: list[TraceEvent] = Field(default_factory=list)
    checkpoints: list[Checkpoint] = Field(default_factory=list)

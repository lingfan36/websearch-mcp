"""Basic tests for the search agent pipeline."""

import pytest


def test_imports():
    """Test that all modules can be imported."""
    from websearch_mcp.schema import (
        SearchSession,
        RewriterOutput,
        SearchResult,
        ExtractorOutput,
        EvaluatorOutput,
        SynthesizerOutput,
        Gap,
        Citation,
        SearchDepth,
    )
    from websearch_mcp.exceptions import (
        WebSearchError,
        RewriterError,
        SearchAPIError,
    )
    from websearch_mcp.trace import TraceManager, create_trace_manager
    from websearch_mcp.llm import LLMClient


def test_schema_models():
    """Test schema model creation."""
    from websearch_mcp.schema import (
        SearchSession,
        RewriterOutput,
        RewrittenQuery,
        SearchDepth,
        SearchResult,
        ExtractedFacts,
        Gap,
        GapType,
    )

    # Test RewriterOutput
    rewriter_out = RewriterOutput(
        queries=[
            RewrittenQuery(
                query="test query",
                rationale="testing",
                search_depth=SearchDepth.BALANCED,
            )
        ],
        reasoning="test",
    )
    assert len(rewriter_out.queries) == 1
    assert rewriter_out.queries[0].query == "test query"

    # Test SearchSession
    session = SearchSession(
        id="test-id",
        original_query="original test",
    )
    assert session.id == "test-id"
    assert session.iterations == 0
    assert session.max_iterations == 3

    # Test Gap
    gap = Gap(
        type=GapType.MISSING_DATE,
        description="Missing date information",
        suggested_queries=["when did X happen", "X date"],
    )
    assert gap.type == GapType.MISSING_DATE
    assert len(gap.suggested_queries) == 2

    # Test ExtractedFacts merge
    facts1 = ExtractedFacts(key_findings=["finding 1"])
    facts2 = ExtractedFacts(key_findings=["finding 2"])
    facts1.merge(facts2)
    assert len(facts1.key_findings) == 2


def test_trace_manager():
    """Test trace manager."""
    from websearch_mcp.trace import create_trace_manager
    from websearch_mcp.schema import NodeType

    trace = create_trace_manager("test-session")
    assert trace.session_id == "test-session"

    trace.log_event(
        node=NodeType.REWRITER,
        action="test_action",
        duration_ms=100,
        metadata={"test": "value"},
    )

    assert len(trace.trace.events) == 1
    assert trace.trace.events[0].node == NodeType.REWRITER

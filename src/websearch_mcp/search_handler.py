"""Lazy-loaded web search handler."""

from __future__ import annotations

import uuid
from typing import Any

import structlog

logger = structlog.get_logger()


async def handle_web_search(
    query: str,
    depth: str = "balanced",
) -> dict[str, Any]:
    """Run the full search pipeline — all heavy imports happen here."""
    from .llm import create_llm_client
    from .nodes.rewriter import RewriterNode
    from .nodes.search import SearchNode
    from .nodes.extractor import ExtractorNode
    from .nodes.evaluator import EvaluatorNode
    from .nodes.synthesizer import SynthesizerNode
    from .schema import SearchSession, SearchDepth, RewrittenQuery, RewriterOutput
    from .trace import create_trace_manager

    llm = create_llm_client()

    rewriter = RewriterNode(llm)
    searcher = SearchNode()
    extractor = ExtractorNode(llm)
    synthesizer = SynthesizerNode(llm)

    session_id = str(uuid.uuid4())
    session = SearchSession(
        id=session_id,
        original_query=query,
        max_iterations=1 if depth == "quick" else 3,
    )
    trace = create_trace_manager(session_id)

    logger.info("search_session_start", session_id=session_id, query=query, depth=depth)

    try:
        # Step 1: Rewrite (skip for quick mode — use raw query)
        if depth == "quick":
            rewriter_output = RewriterOutput(
                queries=[RewrittenQuery(
                    query=query,
                    rationale="quick_mode",
                    search_depth=SearchDepth.QUICK,
                )],
                reasoning="quick mode — no rewrite",
                status="success",
            )
        else:
            rewriter_output = await rewriter.run(query, trace)

        session.rewritten_queries = rewriter_output.queries

        if depth not in ("quick", "balanced"):
            depth_map = {"deep": SearchDepth.DEEP}
            for q in session.rewritten_queries:
                q.search_depth = depth_map.get(depth, SearchDepth.BALANCED)

        # Search + Extract (single iteration for quick, loop for balanced/deep)
        if depth == "quick":
            # Quick path: search → extract → synthesize, no evaluator loop
            session.iterations = 1

            search_results, _ = await searcher.run(rewriter_output, crawl=True, trace=trace)
            session.search_results.extend(search_results)

            if search_results:
                extractor_output = await extractor.run(search_results, trace)
                session.extracted_facts.merge(extractor_output.facts)

            synth_output = await synthesizer.run(
                session.extracted_facts,
                [],
                query,
                1,
                trace,
            )
        else:
            # Full path with evaluator loop
            evaluator = EvaluatorNode(llm)

            while session.iterations < session.max_iterations:
                session.iterations += 1
                logger.info("search_iteration_start", iteration=session.iterations)

                search_results, _ = await searcher.run(rewriter_output, crawl=True, trace=trace)
                session.search_results.extend(search_results)

                if not search_results:
                    logger.warning("search_no_results", iteration=session.iterations)
                    break

                extractor_output = await extractor.run(search_results, trace)
                session.extracted_facts.merge(extractor_output.facts)

                eval_output = await evaluator.run(session, trace)

                if eval_output.sufficient or eval_output.status == "exhausted":
                    break

                session.gaps = eval_output.gaps
                logger.info("search_needs_more", gaps=len(eval_output.gaps), confidence=eval_output.confidence)

                new_queries = []
                for gap in eval_output.gaps:
                    for sq in gap.suggested_queries[:2]:
                        new_queries.append(RewrittenQuery(
                            query=sq,
                            rationale=f"gap_filling: {gap.description}",
                            search_depth=SearchDepth.BALANCED,
                        ))
                if new_queries:
                    rewriter_output.queries = new_queries

            # Synthesize
            synth_output = await synthesizer.run(
                session.extracted_facts,
                session.gaps,
                query,
                session.iterations,
                trace,
            )

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

"""Lazy-loaded web search handler."""

from __future__ import annotations

import uuid
from typing import Any

import structlog

from .hooks import HookManager, HookContext, log_context_hook, log_cost_hook

logger = structlog.get_logger()


async def handle_web_search(
    query: str,
    depth: str = "balanced",
    hook_manager: HookManager | None = None,
) -> dict[str, Any]:
    """Run the full search pipeline — all heavy imports happen here.

    Args:
        query: Search query
        depth: Search depth (quick/balanced/deep)
        hook_manager: Optional hook manager for pre/post events
    """
    from .llm import create_llm_client
    from .nodes.rewriter import RewriterNode
    from .nodes.search import SearchNode
    from .nodes.extractor import ExtractorNode
    from .nodes.evaluator import EvaluatorNode
    from .nodes.synthesizer import SynthesizerNode
    from .schema import SearchSession, SearchDepth, RewrittenQuery, RewriterOutput
    from .trace import create_trace_manager

    # Register default hooks if hook_manager provided but has no hooks
    if hook_manager is not None:
        hooks_registered = False
        try:
            # Check if any hooks are registered
            hooks_registered = bool(hook_manager._pre_hooks or hook_manager._post_hooks)
        except AttributeError:
            pass
        if not hooks_registered:
            hook_manager.register("rewriter", "pre", log_context_hook)
            hook_manager.register("rewriter", "post", log_cost_hook)
            hook_manager.register("search", "pre", log_context_hook)
            hook_manager.register("search", "post", log_cost_hook)
            hook_manager.register("extractor", "pre", log_context_hook)
            hook_manager.register("extractor", "post", log_cost_hook)
            hook_manager.register("evaluator", "pre", log_context_hook)
            hook_manager.register("evaluator", "post", log_cost_hook)
            hook_manager.register("synthesizer", "pre", log_context_hook)
            hook_manager.register("synthesizer", "post", log_cost_hook)

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

    def make_ctx(node_name: str, input_data: Any = None) -> HookContext:
        return HookContext(session_id=session_id, node_name=node_name, input_data=input_data)

    try:
        # Step 1: Rewrite (skip for quick mode — use raw query)
        if hook_manager:
            await hook_manager.fire_pre("rewriter", make_ctx("rewriter", {"query": query}))

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

        if hook_manager:
            await hook_manager.fire_post("rewriter", make_ctx("rewriter", {"query": query}), rewriter_output)

        if depth not in ("quick", "balanced"):
            depth_map = {"deep": SearchDepth.DEEP}
            for q in session.rewritten_queries:
                q.search_depth = depth_map.get(depth, SearchDepth.BALANCED)

        # Search + Extract (single iteration for quick, loop for balanced/deep)
        if depth == "quick":
            # Quick path: search → extract → synthesize, no evaluator loop
            session.iterations = 1

            if hook_manager:
                await hook_manager.fire_pre("search", make_ctx("search", {"queries": [q.model_dump() for q in rewriter_output.queries]}))
            search_results, _ = await searcher.run(rewriter_output, crawl=True, trace=trace)
            if hook_manager:
                await hook_manager.fire_post("search", make_ctx("search", {"queries": [q.model_dump() for q in rewriter_output.queries]}), search_results)
            session.search_results.extend(search_results)

            if search_results:
                if hook_manager:
                    await hook_manager.fire_pre("extractor", make_ctx("extractor", {"result_count": len(search_results)}))
                extractor_output = await extractor.run(search_results, trace)
                if hook_manager:
                    await hook_manager.fire_post("extractor", make_ctx("extractor", {"result_count": len(search_results)}), extractor_output)
                session.extracted_facts.merge(extractor_output.facts)

            if hook_manager:
                await hook_manager.fire_pre("synthesizer", make_ctx("synthesizer", {"query": query, "facts_count": len(session.extracted_facts.key_findings)}))
            synth_output = await synthesizer.run(
                session.extracted_facts,
                [],
                query,
                1,
                trace,
            )
            if hook_manager:
                await hook_manager.fire_post("synthesizer", make_ctx("synthesizer", {"query": query}), synth_output)
        else:
            # Full path with evaluator loop
            evaluator = EvaluatorNode(llm)

            while session.iterations < session.max_iterations:
                session.iterations += 1
                logger.info("search_iteration_start", iteration=session.iterations)

                if hook_manager:
                    await hook_manager.fire_pre("search", make_ctx("search", {"queries": [q.model_dump() for q in rewriter_output.queries], "iteration": session.iterations}))
                search_results, _ = await searcher.run(rewriter_output, crawl=True, trace=trace)
                if hook_manager:
                    await hook_manager.fire_post("search", make_ctx("search", {"iteration": session.iterations}), search_results)
                session.search_results.extend(search_results)

                if not search_results:
                    logger.warning("search_no_results", iteration=session.iterations)
                    break

                if hook_manager:
                    await hook_manager.fire_pre("extractor", make_ctx("extractor", {"result_count": len(search_results), "iteration": session.iterations}))
                extractor_output = await extractor.run(search_results, trace)
                if hook_manager:
                    await hook_manager.fire_post("extractor", make_ctx("extractor", {"iteration": session.iterations}), extractor_output)
                session.extracted_facts.merge(extractor_output.facts)

                if hook_manager:
                    await hook_manager.fire_pre("evaluator", make_ctx("evaluator", {"iteration": session.iterations}))
                eval_output = await evaluator.run(session, trace)
                if hook_manager:
                    await hook_manager.fire_post("evaluator", make_ctx("evaluator", {"iteration": session.iterations}), eval_output)

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
            if hook_manager:
                await hook_manager.fire_pre("synthesizer", make_ctx("synthesizer", {"query": query, "iterations": session.iterations}))
            synth_output = await synthesizer.run(
                session.extracted_facts,
                session.gaps,
                query,
                session.iterations,
                trace,
            )
            if hook_manager:
                await hook_manager.fire_post("synthesizer", make_ctx("synthesizer", {"query": query}), synth_output)

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

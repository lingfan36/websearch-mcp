"""Trace logging for WebSearch Agent."""

from __future__ import annotations

import hashlib
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any

import structlog

from .schema import (
    Checkpoint,
    NodeType,
    SearchSession,
    SearchTrace,
    TraceEvent,
)

logger = structlog.get_logger()


def hash_data(data: Any) -> str:
    """Create short hash of data."""
    if data is None:
        return ""
    s = str(data)
    return hashlib.md5(s.encode()).hexdigest()[:8]


class TraceManager:
    """Manages trace logging for a search session."""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.trace = SearchTrace(id=str(uuid.uuid4()), session_id=session_id)
        self._start_time = datetime.now(timezone.utc)

    def log_event(
        self,
        node: NodeType,
        action: str,
        duration_ms: int = 0,
        input_data: Any = None,
        output_data: Any = None,
        decision: dict[str, Any] | None = None,
        error: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Log a trace event."""
        event = TraceEvent(
            node=node,
            action=action,
            duration_ms=duration_ms,
            input_hash=hash_data(input_data),
            output_hash=hash_data(output_data),
            decision=decision,
            error=error,
            metadata=metadata or {},
        )
        self.trace.events.append(event)

    def checkpoint(self, name: str, session: SearchSession, reason: str) -> None:
        """Create a checkpoint."""
        cp = Checkpoint(
            name=name,
            snapshot={
                "rewritten_queries": len(session.rewritten_queries),
                "search_results": len(session.search_results),
                "gaps": [g.model_dump() for g in session.gaps],
                "iterations": session.iterations,
            },
            reason=reason,
        )
        self.trace.checkpoints.append(cp)

    @contextmanager
    def timed(self, node: NodeType, action: str, **kwargs):
        """Context manager for timing operations."""
        import time
        start = time.perf_counter()
        try:
            yield
        finally:
            duration_ms = int((time.perf_counter() - start) * 1000)
            self.log_event(node, action, duration_ms=duration_ms, **kwargs)

    def to_dict(self) -> dict:
        """Export trace as dict."""
        return self.trace.model_dump()


def create_trace_manager(session_id: str) -> TraceManager:
    """Create a new trace manager."""
    return TraceManager(session_id)

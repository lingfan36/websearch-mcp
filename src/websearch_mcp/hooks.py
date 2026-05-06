"""Hook system for WebSearch MCP — pre/post event handlers."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Awaitable

import structlog

logger = structlog.get_logger()

HookFunc = Callable[..., Awaitable[None]]


@dataclass
class HookContext:
    """Context passed to hook functions."""
    session_id: str
    node_name: str
    input_data: Any = None
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)


class HookManager:
    """Manages pre/post hooks for search pipeline nodes."""

    def __init__(self):
        self._pre_hooks: dict[str, list[HookFunc]] = {}
        self._post_hooks: dict[str, list[HookFunc]] = {}

    def register(self, node: str, hook_type: str, func: HookFunc) -> None:
        """Register a hook for a node.

        Args:
            node: Node name (e.g., "rewriter", "search", "extractor")
            hook_type: "pre" or "post"
            func: Async function that accepts HookContext (and output for post hooks)
        """
        key = f"{node}:{hook_type}"
        if key not in self._pre_hooks:
            if hook_type == "pre":
                self._pre_hooks[key] = []
            else:
                self._post_hooks[key] = []
        else:
            if hook_type == "post":
                self._post_hooks[key] = []

        target = self._pre_hooks if hook_type == "pre" else self._post_hooks
        target[key].append(func)

    def _get_hooks(self, node: str, hook_type: str) -> list[HookFunc]:
        key = f"{node}:{hook_type}"
        if hook_type == "pre":
            return self._pre_hooks.get(key, [])
        return self._post_hooks.get(key, [])

    async def fire_pre(self, node: str, ctx: HookContext) -> None:
        """Fire all pre-hooks for a node."""
        for hook in self._get_hooks(node, "pre"):
            try:
                await hook(ctx)
            except Exception as e:
                logger.warning("hook_pre_failed", node=node, hook=hook.__name__, error=str(e))

    async def fire_post(self, node: str, ctx: HookContext, output: Any = None) -> None:
        """Fire all post-hooks for a node."""
        for hook in self._get_hooks(node, "post"):
            try:
                if output is not None:
                    await hook(ctx, output)
                else:
                    await hook(ctx)
            except Exception as e:
                logger.warning("hook_post_failed", node=node, hook=hook.__name__, error=str(e))


# === Pre-built hooks ===

async def log_context_hook(ctx: HookContext) -> None:
    """Log input context before node runs. Replaces ruflo pre-hook."""
    logger.info(
        "hook_pre",
        session_id=ctx.session_id,
        node=ctx.node_name,
        input_hash=_hash_data(ctx.input_data),
        timestamp=ctx.timestamp,
    )


async def log_cost_hook(ctx: HookContext, output: Any = None) -> None:
    """Log output cost after node runs. Replaces ruflo post-hook."""
    if output is None:
        return

    # Try to extract cost metrics from output
    cost_data = {
        "session_id": ctx.session_id,
        "node": ctx.node_name,
        "timestamp": ctx.timestamp,
    }

    if hasattr(output, "model_dump"):
        data = output.model_dump()
    elif isinstance(output, dict):
        data = output
    else:
        data = {"raw": str(output)[:200]}

    # Extract common cost fields
    if "confidence" in data:
        cost_data["confidence"] = data["confidence"]
    if "status" in data:
        cost_data["status"] = data["status"]

    logger.info("hook_post", **cost_data)


async def cache_hook(ctx: HookContext, output: Any = None) -> None:
    """Simple in-memory cache hook for query results."""
    if output is None:
        return

    # Use a module-level cache
    global _hook_cache
    if "_hook_cache" not in globals():
        global _hook_cache
        _hook_cache = {}

    key = f"{ctx.node_name}:{_hash_data(ctx.input_data)}"
    _hook_cache[key] = {
        "output": output,
        "timestamp": ctx.timestamp,
    }


def _hash_data(data: Any) -> str:
    """Create short hash of data."""
    if data is None:
        return ""
    try:
        s = json.dumps(data, sort_keys=True, default=str)
    except (TypeError, ValueError):
        s = str(data)
    return str(hash(s))[:12]


# === Decorator for easy hook registration ===

def node_hook(node_name: str, hook_type: str):
    """Decorator to register a function as a hook for a node.

    Usage:
        @node_hook("rewriter", "pre")
        async def my_hook(ctx: HookContext):
            ...
    """
    def decorator(func: HookFunc) -> HookFunc:
        # Store metadata on the function for later registration
        func._hook_node = node_name
        func._hook_type = hook_type
        return func
    return decorator
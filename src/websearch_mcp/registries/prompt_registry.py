"""Prompt registry for MCP server."""

from __future__ import annotations

from typing import Any
from dataclasses import dataclass

from mcp.types import Prompt, PromptArgument

import structlog

logger = structlog.get_logger()


@dataclass
class MCPPrompt:
    """An MCP prompt with name, description, and arguments."""
    name: str
    description: str = ""
    arguments: list[PromptArgument] | None = None

    def to_mcp_prompt(self) -> Prompt:
        """Convert to MCP Prompt object."""
        return Prompt(
            name=self.name,
            description=self.description,
            arguments=self.arguments or [],
        )


class PromptRegistry:
    """Registry for MCP prompts."""

    def __init__(self):
        self._prompts: dict[str, MCPPrompt] = {}

    def register(
        self,
        name: str,
        description: str = "",
        arguments: list[PromptArgument] | None = None,
    ) -> None:
        """Register a prompt."""
        self._prompts[name] = MCPPrompt(
            name=name,
            description=description,
            arguments=arguments,
        )
        logger.debug("prompt_registered", name=name)

    async def get_prompt(self, name: str, arguments: dict[str, Any] | None = None) -> str:
        """Get prompt content by name. Override for dynamic prompts."""
        prompt = self._prompts.get(name)
        if prompt is None:
            raise ValueError(f"Unknown prompt: {name}")
        # Default: return placeholder. Override for actual content.
        return f"Prompt: {name}"

    def list_prompts(self) -> list[Prompt]:
        """List all registered prompts as MCP Prompt objects."""
        return [p.to_mcp_prompt() for p in self._prompts.values()]

    def get(self, name: str) -> MCPPrompt | None:
        """Get a prompt by name."""
        return self._prompts.get(name)


class DynamicPromptRegistry(PromptRegistry):
    """Prompt registry with dynamic content loading."""

    def __init__(self):
        super().__init__()
        self._prompt_handlers: dict[str, Any] = {}

    def register_with_handler(
        self,
        name: str,
        description: str = "",
        arguments: list[PromptArgument] | None = None,
        prompt_handler: Any = None,
    ) -> None:
        """Register a prompt with a custom handler."""
        self.register(name, description, arguments)
        if prompt_handler:
            self._prompt_handlers[name] = prompt_handler

    async def get_prompt(self, name: str, arguments: dict[str, Any] | None = None) -> str:
        """Get prompt using custom handler if available."""
        if name in self._prompt_handlers:
            handler = self._prompt_handlers[name]
            if callable(handler):
                return await handler(name, arguments or {})
        return await super().get_prompt(name, arguments)


def create_default_registry() -> DynamicPromptRegistry:
    """Create registry with default WebSearch MCP prompts."""
    registry = DynamicPromptRegistry()

    # Research prompt
    async def research_prompt(name: str, args: dict[str, Any]) -> str:
        topic = args.get("topic", "unknown")
        depth = args.get("depth", "balanced")
        return f"""You are a research assistant. Research the topic: {topic}

Use the web_search tool for {'deep' if depth == 'deep' else 'balanced'} research.
Focus on recent developments and credible sources."""

    registry.register_with_handler(
        name="research",
        description="Conduct research on a topic using web search",
        arguments=[
            PromptArgument(name="topic", description="Topic to research", required=True),
            PromptArgument(name="depth", description="Research depth (quick/balanced/deep)", required=False),
        ],
        prompt_handler=research_prompt,
    )

    # Compare prompt
    async def compare_prompt(name: str, args: dict[str, Any]) -> str:
        subjects = args.get("subjects", "")
        if isinstance(subjects, list):
            subjects = " vs ".join(subjects)
        return f"""Compare and contrast: {subjects}

Use web_search_quick for initial comparison, then web_search for detailed analysis."""

    registry.register_with_handler(
        name="compare",
        description="Compare multiple subjects using web search",
        arguments=[
            PromptArgument(name="subjects", description="Subjects to compare (comma-separated or array)", required=True),
        ],
        prompt_handler=compare_prompt,
    )

    # Fetch and analyze prompt
    async def analyze_prompt(name: str, args: dict[str, Any]) -> str:
        url = args.get("url", "")
        focus = args.get("focus", "general")
        return f"""Analyze the content at: {url}

Focus area: {focus}

Use the fetch tool to get the content, then summarize key findings."""

    registry.register_with_handler(
        name="analyze",
        description="Fetch and analyze a URL with specific focus",
        arguments=[
            PromptArgument(name="url", description="URL to analyze", required=True),
            PromptArgument(name="focus", description="Focus area (general/technical/latest)", required=False),
        ],
        prompt_handler=analyze_prompt,
    )

    return registry
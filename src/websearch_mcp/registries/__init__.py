"""Registries package — tool, resource, and prompt registries."""

from .tool_registry import ToolRegistry, ToolHandler, create_default_registry as create_tool_registry
from .resource_registry import ResourceRegistry, MCPResource, DynamicResourceRegistry, create_default_registry as create_resource_registry
from .prompt_registry import PromptRegistry, MCPPrompt, DynamicPromptRegistry, create_default_registry as create_prompt_registry

__all__ = [
    "ToolRegistry",
    "ToolHandler",
    "create_tool_registry",
    "ResourceRegistry",
    "MCPResource",
    "DynamicResourceRegistry",
    "create_resource_registry",
    "PromptRegistry",
    "MCPPrompt",
    "DynamicPromptRegistry",
    "create_prompt_registry",
]
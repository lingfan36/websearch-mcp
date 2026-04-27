"""LLM client for Ollama."""

from __future__ import annotations

import json
import re
from typing import Any

import httpx
import structlog

from .exceptions import LLMRateLimitError, RewriterError

logger = structlog.get_logger()

DEFAULT_OLLAMA_URL = "http://localhost:11434/v1/chat/completions"
DEFAULT_MODEL = "qwen2.5:1.5b"


def _extract_json_with_balanced_braces(content: str) -> str | None:
    """Extract JSON by finding balanced braces.

    This handles cases where the LLM returns text before/after JSON
    or when the JSON has nested objects.
    """
    # Find the first opening brace
    start = content.find('{')
    if start == -1:
        return None

    # Find JSON by tracking brace balance
    depth = 0
    in_string = False
    escape = False

    for i in range(start, len(content)):
        c = content[i]

        if escape:
            escape = False
            continue

        if c == '\\':
            escape = True
            continue

        if c == '"' and not escape:
            in_string = not in_string
            continue

        if in_string:
            continue

        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                # Found balanced JSON
                return content[start:i+1]

    return None


class LLMClient:
    """Ollama LLM client (OpenAI compatible)."""

    def __init__(
        self,
        api_url: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
    ):
        self.api_url = api_url or DEFAULT_OLLAMA_URL
        self.model = model or DEFAULT_MODEL
        self.timeout = timeout if timeout is not None else 30.0
        self._client: httpx.AsyncClient | None = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def chat(
        self,
        messages: list[dict[str, str]],
        schema: dict[str, Any] | None = None,
        temperature: float = 0.3,
    ) -> str:
        """Call LLM with messages.

        Args:
            messages: Chat messages [{role: "user" | "system" | "assistant", content: str}]
            schema: Optional JSON schema to constrain output
            temperature: Sampling temperature

        Returns:
            Response text content

        Raises:
            RewriterError: On API error or rate limit
        """
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }

        if schema:
            # Ollama doesn't support response_format - add schema to system prompt instead
            schema_hint = f"\n\nRespond ONLY with valid JSON matching this schema:\n{json.dumps(schema, indent=2)}"
            if messages[0]["role"] == "system":
                messages[0]["content"] += schema_hint
            else:
                messages.insert(0, {"role": "system", "content": schema_hint})

        try:
            response = await self.client.post(self.api_url, json=payload)
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"]

            # Strip markdown code fences if present
            content = content.strip()
            if content.startswith("```"):
                lines = content.split("\n")
                # Remove first line (```json or ```)
                if lines[0].startswith("```"):
                    lines = lines[1:]
                # Remove last line (```)
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                content = "\n".join(lines).strip()

            # Remove invalid control characters (except \n, \r, \t)
            content = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', content)
            # Also remove \r if it's not followed by \n (normalized line endings)
            content = re.sub(r'\r(?!\n)', '', content)

            # Validate JSON only when schema is requested
            if schema:
                try:
                    json.loads(content)
                except json.JSONDecodeError as e:
                    logger.warning("llm_response_not_valid_json", error=str(e), content_preview=content[:200])
                    # Try to find JSON with balanced braces
                    content = _extract_json_with_balanced_braces(content)
                    if content is None:
                        raise RewriterError(f"Invalid JSON response: {e}")
                    # Verify the extracted content is valid JSON
                    try:
                        json.loads(content)
                    except json.JSONDecodeError as verify_e:
                        logger.warning("llm_json_extraction_failed", error=str(verify_e))
                        raise RewriterError(f"Invalid JSON response: {e}")

            return content
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                raise LLMRateLimitError("Rate limit exceeded")
            raise RewriterError(f"HTTP {e.response.status_code}: {e.response.text}")
        except httpx.RequestError as e:
            logger.warning("llm_request_error", error_type=type(e).__name__, error_message=str(e), error_args=e.args)
            raise RewriterError(f"Request error: {e}")
        except (KeyError, IndexError) as e:
            raise RewriterError(f"Invalid response format: {e}")

    async def chat_str(
        self,
        system: str,
        user: str,
        schema: dict[str, Any] | None = None,
    ) -> str:
        """Simple string-based chat."""
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": user})
        return await self.chat(messages, schema=schema)


def create_llm_client() -> LLMClient:
    """Factory for LLM client — reads timeout from config."""
    from .config import get_settings
    settings = get_settings()
    return LLMClient(timeout=settings.llm_timeout)

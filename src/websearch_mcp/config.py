"""Configuration management for WebSearch MCP."""

from __future__ import annotations

import os
from typing import Any
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # LLM
    openai_base_url: str = "https://api.minimaxi.com/v1/chat/completions"
    openai_model: str = "MiniMax-M2.7"
    llm_timeout: float = 120.0

    # Typesense
    typesense_host: str = "localhost"
    typesense_port: int = 8108
    typesense_api_key: str = "xyz"
    typesense_collection: str = "webpages"

    # Crawler
    crawler_timeout: float = 30.0
    crawler_max_depth: int = 1
    crawler_delay: float = 1.0  # 请求间隔（秒）

    # Search
    max_search_results: int = 10

    # Pipeline
    max_iterations: int = 3
    confidence_threshold: float = 0.7

    # Fetch strategy
    use_jina_reader: bool = True
    jina_reader_url: str = "https://r.jina.ai/"
    jina_search_url: str = "https://s.jina.ai/"
    jina_api_key: str = ""
    use_browser_fallback: bool = False

    @property
    def typesense_url(self) -> str:
        return f"http://{self.typesense_host}:{self.typesense_port}"


_settings: Settings | None = None


def get_settings() -> Settings:
    """Get settings singleton."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings

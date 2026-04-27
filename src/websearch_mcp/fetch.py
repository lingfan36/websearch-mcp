"""Fetch module — fetch URLs and extract content as markdown."""

from __future__ import annotations

import time
from typing import Tuple
from urllib.parse import urlparse, urlunparse

import httpx
import markdownify
import readabilipy.simple_json
import structlog

from .exceptions import FetchError

logger = structlog.get_logger()

DEFAULT_USER_AGENT = "Mozilla/5.0 (compatible; WebSearchMCP/1.0)"

# --- Global HTTP client (connection pooling) ---
_global_client: httpx.AsyncClient | None = None


async def _get_client() -> httpx.AsyncClient:
    global _global_client
    if _global_client is None or _global_client.is_closed:
        _global_client = httpx.AsyncClient(
            timeout=30.0,
            follow_redirects=True,
            limits=httpx.Limits(
                max_connections=20,
                max_keepalive_connections=10,
            ),
        )
    return _global_client


# --- robots.txt cache ---
_robots_cache: dict[str, tuple[bool, float]] = {}
_ROBOTS_CACHE_TTL = 300  # 5 minutes

# --- HTTP response cache ---
_fetch_cache: dict[str, tuple[str, str, float]] = {}  # url -> (content, prefix, timestamp)
_FETCH_CACHE_TTL = 600  # 10 minutes


def extract_content_from_html(html: str) -> str:
    """Extract and convert HTML content to Markdown using readabilipy + markdownify.

    Args:
        html: Raw HTML content to process

    Returns:
        Simplified markdown version of the content
    """
    try:
        ret = readabilipy.simple_json.simple_json_from_html_string(
            html, use_readability=True
        )
        if not ret.get("content"):
            logger.warning("readabilipy_no_content")
            return ""
        content = markdownify.markdownify(
            ret["content"],
            heading_style=markdownify.ATX,
        )
        return content
    except Exception as e:
        logger.warning("content_extraction_failed", error=str(e))
        return ""


def get_robots_txt_url(url: str) -> str:
    """Get the robots.txt URL for a given website URL."""
    parsed = urlparse(url)
    return urlunparse((parsed.scheme, parsed.netloc, "/robots.txt", "", "", ""))


async def check_robots_txt(url: str, user_agent: str = DEFAULT_USER_AGENT) -> bool:
    """Check if URL can be fetched according to robots.txt.

    Results are cached per domain for 5 minutes.

    Returns:
        True if allowed, False otherwise
    """
    from protego import Protego

    domain = urlparse(url).netloc
    now = time.time()

    # Check cache
    if domain in _robots_cache:
        allowed, ts = _robots_cache[domain]
        if now - ts < _ROBOTS_CACHE_TTL:
            return allowed

    robots_url = get_robots_txt_url(url)

    try:
        client = await _get_client()
        response = await client.get(robots_url, headers={"User-Agent": user_agent})
        if response.status_code >= 400:
            _robots_cache[domain] = (True, now)
            return True  # No robots.txt or error, assume allowed
    except Exception:
        _robots_cache[domain] = (True, now)
        return True

    robot_txt = response.text
    processed_robot_txt = "\n".join(
        line for line in robot_txt.splitlines() if not line.strip().startswith("#")
    )

    try:
        robot_parser = Protego.parse(processed_robot_txt)
        result = robot_parser.can_fetch(url, user_agent)
    except Exception:
        result = True

    _robots_cache[domain] = (result, now)
    return result


async def fetch_url(
    url: str,
    user_agent: str = DEFAULT_USER_AGENT,
    force_raw: bool = False,
    timeout: float = 30.0,
) -> Tuple[str, str]:
    """Fetch URL and return content ready for LLM.

    Args:
        url: URL to fetch
        user_agent: User agent string
        force_raw: Skip markdown conversion
        timeout: Request timeout in seconds

    Returns:
        Tuple of (content, prefix) where prefix is empty for markdown or error message for raw
    """
    content_type = ""

    try:
        client = await _get_client()
        response = await client.get(url, headers={"User-Agent": user_agent}, timeout=timeout)

        if response.status_code >= 400:
            raise FetchError(f"HTTP {response.status_code}")

        page_raw = response.text
        content_type = response.headers.get("content-type", "")

    except httpx.TimeoutException:
        raise FetchError("Request timed out")
    except httpx.RequestError as e:
        raise FetchError(f"Request failed: {e}")

    # Check if HTML
    is_html = (
        "<html" in page_raw[:100].lower() or
        "text/html" in content_type or
        not content_type
    )

    if is_html and not force_raw:
        markdown_content = extract_content_from_html(page_raw)
        if markdown_content:
            return markdown_content, ""
        else:
            # Fallback: return raw
            return page_raw, f"Content type {content_type}, markdown extraction failed:\n"

    return (
        page_raw,
        f"Content type {content_type}, returning raw content:\n",
    )


async def fetch_and_extract(
    url: str,
    max_length: int = 5000,
    start_index: int = 0,
    raw: bool = False,
    check_robots: bool = True,
) -> str:
    """Fetch URL and return truncated markdown content.

    Results are cached in memory for 10 minutes.

    Args:
        url: URL to fetch
        max_length: Maximum characters to return
        start_index: Start position for pagination
        raw: Return raw HTML instead of markdown
        check_robots: Whether to check robots.txt

    Returns:
        Content with status prefix
    """
    # Check response cache (only for first page, no pagination)
    cache_key = f"{url}:{raw}"
    now = time.time()
    if start_index == 0 and cache_key in _fetch_cache:
        content, prefix, ts = _fetch_cache[cache_key]
        if now - ts < _FETCH_CACHE_TTL:
            content_to_use = content
            prefix_to_use = prefix
        else:
            del _fetch_cache[cache_key]
            content_to_use = None
            prefix_to_use = None
    else:
        content_to_use = None
        prefix_to_use = None

    if content_to_use is None:
        # Check robots.txt
        if check_robots:
            allowed = await check_robots_txt(url)
            if not allowed:
                return f"<error>robots.txt forbids fetching this URL: {url}</error>"

        # Fetch
        content_to_use, prefix_to_use = await fetch_url(url, force_raw=raw)

        # Cache the full response
        if start_index == 0:
            _fetch_cache[cache_key] = (content_to_use, prefix_to_use, now)

    # Truncate
    original_length = len(content_to_use)

    if start_index >= original_length:
        return "<error>No more content available.</error>"

    truncated = content_to_use[start_index:start_index + max_length]

    if not truncated:
        return "<error>No more content available.</error>"

    # Build response
    result = f"{prefix_to_use}Contents of {url}:\n{truncated}"

    # Add pagination hint if truncated
    remaining = original_length - (start_index + len(truncated))
    if len(truncated) == max_length and remaining > 0:
        next_start = start_index + len(truncated)
        result += f"\n\n<error>Content truncated. Use start_index={next_start} to get more.</error>"

    return result

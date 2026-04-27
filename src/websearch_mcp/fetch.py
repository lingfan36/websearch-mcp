"""Fetch module — fetch URLs and extract content as markdown."""

from __future__ import annotations

from typing import Tuple
from urllib.parse import urlparse, urlunparse

import httpx
import markdownify
import readabilipy.simple_json
import structlog

from .exceptions import FetchError

logger = structlog.get_logger()

DEFAULT_USER_AGENT = "Mozilla/5.0 (compatible; WebSearchMCP/1.0)"


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

    Returns:
        True if allowed, False otherwise
    """
    from protego import Protego

    robots_url = get_robots_txt_url(url)

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(robots_url, follow_redirects=True)
            if response.status_code >= 400:
                return True  # No robots.txt or error, assume allowed
    except Exception:
        return True  # Network error, assume allowed

    robot_txt = response.text
    processed_robot_txt = "\n".join(
        line for line in robot_txt.splitlines() if not line.strip().startswith("#")
    )

    try:
        robot_parser = Protego.parse(processed_robot_txt)
        return robot_parser.can_fetch(url, user_agent)
    except Exception:
        return True


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
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            response = await client.get(url, headers={"User-Agent": user_agent})

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

    This mimics the fetch MCP server behavior.

    Args:
        url: URL to fetch
        max_length: Maximum characters to return
        start_index: Start position for pagination
        raw: Return raw HTML instead of markdown
        check_robots: Whether to check robots.txt

    Returns:
        Content with status prefix
    """
    # Check robots.txt
    if check_robots:
        allowed = await check_robots_txt(url)
        if not allowed:
            return f"<error>robots.txt forbids fetching this URL: {url}</error>"

    # Fetch
    content, prefix = await fetch_url(url, force_raw=raw)

    # Truncate
    original_length = len(content)

    if start_index >= original_length:
        return "<error>No more content available.</error>"

    truncated = content[start_index:start_index + max_length]

    if not truncated:
        return "<error>No more content available.</error>"

    # Build response
    result = f"{prefix}Contents of {url}:\n{truncated}"

    # Add pagination hint if truncated
    remaining = original_length - (start_index + len(truncated))
    if len(truncated) == max_length and remaining > 0:
        next_start = start_index + len(truncated)
        result += f"\n\n<error>Content truncated. Use start_index={next_start} to get more.</error>"

    return result
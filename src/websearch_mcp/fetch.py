"""Fetch module — fetch URLs with three-layer fallback strategy.

Layer 1: Jina Reader API (fast, high quality)
Layer 2: Local HTTP + readabilipy + markdownify
Layer 3: Playwright browser (for protected sites)
"""

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

# --- Access denied detection ---
_ACCESS_DENIED_CODES = {403, 429, 503, 520, 521, 522, 523, 524}
_ACCESS_DENIED_SIGNALS = [
    "cloudflare", "access denied", "forbidden", "captcha",
    "rate limit", "security check", "human verification",
    "ray id", "robot check",
]


def extract_content_from_html(html: str) -> str:
    """Extract and convert HTML content to Markdown using readabilipy + markdownify."""
    try:
        ret = readabilipy.simple_json.simple_json_from_html_string(
            html, use_readability=True
        )
        if not ret.get("content"):
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
    parsed = urlparse(url)
    return urlunparse((parsed.scheme, parsed.netloc, "/robots.txt", "", "", ""))


def _is_access_denied(status_code: int | None = None, content: str = "") -> bool:
    """Detect if the response indicates access restriction."""
    if status_code and status_code in _ACCESS_DENIED_CODES:
        return True
    lower = content[:2000].lower()
    return any(sig in lower for sig in _ACCESS_DENIED_SIGNALS)


async def check_robots_txt(url: str, user_agent: str = DEFAULT_USER_AGENT) -> bool:
    """Check if URL can be fetched according to robots.txt. Results cached 5 min."""
    from protego import Protego

    domain = urlparse(url).netloc
    now = time.time()

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
            return True
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


# ---- Layer 1: Jina Reader ----

def _jina_headers(accept: str = "text/markdown") -> dict[str, str]:
    """Build headers for Jina API calls."""
    from .config import get_settings
    settings = get_settings()
    headers = {"Accept": accept}
    if settings.jina_api_key:
        headers["Authorization"] = f"Bearer {settings.jina_api_key}"
    return headers


async def _fetch_with_jina(url: str, timeout: float = 30.0) -> Tuple[str, str]:
    """Fetch via Jina Reader API."""
    from .config import get_settings
    settings = get_settings()
    jina_url = f"{settings.jina_reader_url}{url}"

    client = await _get_client()
    response = await client.get(
        jina_url,
        headers=_jina_headers(),
        timeout=timeout,
    )
    if response.status_code >= 400:
        raise FetchError(f"Jina Reader HTTP {response.status_code}")

    content = response.text
    if not content.strip():
        raise FetchError("Jina Reader returned empty content")

    logger.info("fetch_jina_ok", url=url, length=len(content))
    return content, ""


# ---- Quick web search via Jina Search ----

async def search_web(
    query: str,
    max_results: int = 10,
    timeout: float = 30.0,
) -> list[dict[str, str]]:
    """Search the web using Jina Search API. No local LLM needed.

    Returns list of dicts: {title, url, snippet, date, content}
    """
    from .config import get_settings
    settings = get_settings()

    search_url = f"{settings.jina_search_url}{query}"
    headers = _jina_headers("text/markdown")
    headers["X-Return-Format"] = "text"

    client = await _get_client()
    response = await client.get(search_url, headers=headers, timeout=timeout)

    if response.status_code >= 400:
        raise FetchError(f"Jina Search HTTP {response.status_code}")

    text = response.text
    results = _parse_search_results(text, max_results)
    logger.info("search_web_ok", query=query, results=len(results))
    return results


def _parse_search_results(text: str, max_results: int) -> list[dict[str, str]]:
    """Parse Jina Search response into structured results."""
    import re
    results = []

    # Jina returns results as [N] Title / [N] URL / [N] Description blocks
    pattern = re.compile(
        r'\[(\d+)\]\s+Title:\s*(.+?)(?:\n|\r\n)'
        r'\[\1\]\s+URL Source:\s*(.+?)(?:\n|\r\n)'
        r'(?:\[\1\]\s+Description:\s*(.+?)(?:\n|\r\n))?'
        r'(?:\[\1\]\s+Date:\s*(.+?)(?:\n|\r\n))?',
        re.DOTALL,
    )

    seen_urls = set()
    for m in pattern.finditer(text):
        if len(results) >= max_results:
            break

        url = m.group(3).strip().split('?')[0].split('&')[0]
        if url in seen_urls:
            continue
        seen_urls.add(url)

        results.append({
            "title": m.group(2).strip(),
            "url": url,
            "snippet": (m.group(4) or "").strip()[:300],
            "date": (m.group(5) or "").strip(),
        })

    # Fallback: if structured parsing fails, extract URLs from text
    if not results:
        url_pattern = re.compile(r'https?://[^\s\)"\'<>]+')
        seen = set()
        for u in url_pattern.finditer(text):
            url = u.group(0).rstrip('.,;:)').split('?')[0]
            if url in seen or 'jina.ai' in url:
                continue
            seen.add(url)
            results.append({"title": url, "url": url, "snippet": "", "date": ""})
            if len(results) >= max_results:
                break

    return results


# ---- Layer 2: Local HTTP + readabilipy ----

async def _fetch_raw(
    url: str,
    user_agent: str = DEFAULT_USER_AGENT,
    force_raw: bool = False,
    timeout: float = 30.0,
) -> Tuple[str, str]:
    """Direct HTTP fetch + HTML-to-markdown conversion."""
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

    is_html = (
        "<html" in page_raw[:100].lower() or
        "text/html" in content_type or
        not content_type
    )

    if is_html and not force_raw:
        # Check for access denied in response content
        if _is_access_denied(None, page_raw[:5000]):
            raise FetchError("Access denied detected in content")

        markdown_content = extract_content_from_html(page_raw)
        if markdown_content:
            return markdown_content, ""
        return page_raw, f"Content type {content_type}, markdown extraction failed:\n"

    return page_raw, f"Content type {content_type}, returning raw content:\n"


# ---- Layer 3: Playwright browser (lazy import) ----

async def _fetch_with_browser(url: str, timeout: float = 30.0) -> Tuple[str, str]:
    """Fetch using Playwright — only called when access is denied."""
    from .browser_fetch import fetch_with_browser
    return await fetch_with_browser(url, timeout)


# ---- Main entry: three-layer fallback ----

async def fetch_url(
    url: str,
    user_agent: str = DEFAULT_USER_AGENT,
    force_raw: bool = False,
    timeout: float = 30.0,
) -> Tuple[str, str]:
    """Fetch URL with three-layer fallback.

    Layer 1: Jina Reader API (fast, clean markdown)
    Layer 2: Local HTTP + readabilipy (handles most sites)
    Layer 3: Playwright browser (protected sites only)
    """
    from .config import get_settings
    settings = get_settings()

    access_denied = False
    last_error: Exception | None = None

    # Layer 1: Jina Reader
    if settings.use_jina_reader:
        try:
            return await _fetch_with_jina(url, timeout)
        except Exception as e:
            last_error = e
            logger.debug("fetch_jina_failed", url=url, error=str(e))

    # Layer 2: Local HTTP + readabilipy
    try:
        return await _fetch_raw(url, user_agent, force_raw, timeout)
    except FetchError as e:
        last_error = e
        if _is_access_denied(None, str(e)):
            access_denied = True
            logger.info("fetch_access_denied", url=url, falling_back="browser")
        else:
            raise

    # Layer 3: Playwright (only when access denied and browser enabled)
    if access_denied and settings.use_browser_fallback:
        try:
            return await _fetch_with_browser(url, timeout)
        except Exception as e:
            logger.warning("fetch_browser_failed", url=url, error=str(e))
            if last_error:
                raise last_error from e
            raise

    if last_error:
        raise last_error
    raise FetchError("All fetch methods failed")


async def fetch_and_extract(
    url: str,
    max_length: int = 5000,
    start_index: int = 0,
    raw: bool = False,
    check_robots: bool = True,
) -> str:
    """Fetch URL and return truncated markdown content. Results cached 10 min."""
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
        if check_robots:
            allowed = await check_robots_txt(url)
            if not allowed:
                return f"<error>robots.txt forbids fetching this URL: {url}</error>"

        content_to_use, prefix_to_use = await fetch_url(url, force_raw=raw)

        if start_index == 0:
            _fetch_cache[cache_key] = (content_to_use, prefix_to_use, now)

    original_length = len(content_to_use)

    if start_index >= original_length:
        return "<error>No more content available.</error>"

    truncated = content_to_use[start_index:start_index + max_length]

    if not truncated:
        return "<error>No more content available.</error>"

    result = f"{prefix_to_use}Contents of {url}:\n{truncated}"

    remaining = original_length - (start_index + len(truncated))
    if len(truncated) == max_length and remaining > 0:
        next_start = start_index + len(truncated)
        result += f"\n\n<error>Content truncated. Use start_index={next_start} to get more.</error>"

    return result

"""Smart fetch tool with planning and reasoning capabilities."""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any, Coroutine
from urllib.parse import urlparse, urljoin

import structlog

from .fetch import fetch_url
from .llm import LLMClient, create_llm_client

logger = structlog.get_logger()

# Pattern to extract GitHub repo info from plain text listings
GITHUB_REPO_PATTERN = re.compile(
    r'##\s+([\w-]+)\s*/\s*([\w-]+)\s*\n(.*?)(?=\n##|\Z)',
    re.DOTALL | re.IGNORECASE
)
GITHUB_STARS_PATTERN = re.compile(
    r'(\d+(?:,\d+)*)\s+(\d+(?:,\d+)*)\s+Built\s+by\s+(\d+(?:,\d+)*)\s+stars\s+today',
    re.IGNORECASE
)
GITHUB_LANG_PATTERN = re.compile(r'\n([A-Za-z#]+)\s+[\d,]+', re.IGNORECASE)

# Detection patterns for URLs that should be followed
FOLLOW_PATTERNS = [
    r'/[^/]+/[^/]+',  # GitHub repo paths like /user/repo
    r'/issues/\d+',    # Issue pages
    r'/pull/\d+',      # PR pages
    r'/discussions',   # Discussion pages
]

# Extract URLs from markdown content
URL_PATTERN = re.compile(r'\[([^\]]+)\]\(([^)]+)\)|https?://[^\s\)"\'<>]+')


def extract_urls(content: str, base_url: str = "") -> list[tuple[str, str]]:
    """Extract URLs from markdown content.

    Returns list of (title, url) tuples.
    """
    urls = []

    # Find markdown links [title](url)
    for match in re.finditer(r'\[([^\]]+)\]\(([^)]+)\)', content):
        title = match.group(1)
        url = match.group(2)
        # Make absolute
        if not url.startswith('http'):
            url = urljoin(base_url, url)
        urls.append((title, url))

    # Find bare URLs
    for match in re.finditer(r'https?://[^\s\)"\'<>]+', content):
        url = match.group(0).rstrip('.,;:)')
        if base_url:
            full_url = urljoin(base_url, url)
        else:
            full_url = url
        urls.append((full_url, full_url))

    return urls


def extract_github_repos(content: str) -> list[dict[str, Any]]:
    """Extract GitHub repository info from trending page content."""
    repos = []

    # Match ## owner/repo format
    for match in GITHUB_REPO_PATTERN.finditer(content):
        owner = match.group(1).strip()
        repo_name = match.group(2).strip()
        desc_block = match.group(3)

        # Clean description (remove extra whitespace and inline info)
        desc_block = re.sub(r'\s+', ' ', desc_block).strip()
        # Remove language and star info from description
        desc_block = re.sub(r'\n[A-Za-z#]+\s+[\d,]+(\s+\d+)*\s+Built.*$', '', desc_block, flags=re.IGNORECASE)
        description = desc_block.strip()[:200] if desc_block else ""

        # Try to extract stars info
        stars_match = GITHUB_STARS_PATTERN.search(match.group(0))
        lang_match = GITHUB_LANG_PATTERN.search(match.group(0))

        repo_info = {
            "owner": owner,
            "repo": repo_name,
            "url": f"https://github.com/{owner}/{repo_name}",
            "description": description,
            "total_stars": "",
            "today_stars": "",
            "language": "",
        }

        if stars_match:
            repo_info["total_stars"] = stars_match.group(1)
            repo_info["today_stars"] = stars_match.group(2)

        if lang_match:
            repo_info["language"] = lang_match.group(1).strip()

        repos.append(repo_info)

    return repos


def should_follow_url(url: str) -> bool:
    """Decide if a URL is worth following for more details."""
    path = urlparse(url).path

    # Skip common non-useful paths
    skip_paths = ['/login', '/signup', '/search', '/settings', '/profile',
                  '/notifications', '/explore', '/trending', '/about',
                  '/blog', '/docs', '/pricing', '/contact']

    for skip in skip_paths:
        if skip in path:
            return False

    # Follow repo paths and detail pages
    if '/repos/' in url or url.count('/') >= 4:
        return True

    # Follow specific content pages
    for pattern in FOLLOW_PATTERNS:
        if re.search(pattern, url):
            return True

    return False


MAX_TOTAL_OUTPUT = 50_000  # Hard cap on total output chars


async def smart_fetch(
    url: str,
    max_length: int = 5000,
    start_index: int = 0,
    follow_depth: int = 2,
    client: LLMClient | None = None,
    visited: set[str] | None = None,
    _total_budget: int = MAX_TOTAL_OUTPUT,
) -> dict[str, Any]:
    """Fetch URL with intelligent following and extraction.

    This combines fetching + reasoning to:
    1. Get main page content
    2. Identify important links to follow
    3. Extract structured information
    4. Return comprehensive results

    Args:
        url: URL to fetch
        max_length: Max chars per page
        start_index: Pagination start
        follow_depth: How many levels of links to follow (0 = just main page)
        client: LLM client for analysis
        visited: Track visited URLs to avoid loops

    Returns:
        Dict with:
        - content: Main content
        - summary: LLM-generated summary (if available)
        - extracted_data: Structured data extracted
        - followed_urls: List of followed URLs with their content
        - next_cursor: For pagination
        - github_repos: Extracted GitHub repos if applicable
    """
    if visited is None:
        visited = set()

    if url in visited:
        logger.info("smart_fetch_skip_duplicate", url=url)
        return {"content": "", "skipped": True, "reason": "already visited"}

    visited.add(url)
    close_client = False
    if client is None:
        client = create_llm_client()
        close_client = True

    try:
        # Fetch main page
        logger.info("smart_fetch_main", url=url)
        raw_content, _ = await fetch_url(url, force_raw=False)

        full_length = len(raw_content)
        truncated = raw_content[start_index:start_index + max_length]

        result = {
            "url": url,
            "content": truncated,
            "content_length": full_length,
            "followed_urls": [],
            "extracted_data": None,
            "github_repos": [],
        }

        # Budget tracking
        remaining_budget = _total_budget - len(truncated)
        if full_length > start_index + max_length:
            result["next_cursor"] = start_index + max_length

        # Special handling for GitHub trending
        if 'github.com/trending' in url:
            repos = extract_github_repos(raw_content)
            result["github_repos"] = repos
            logger.info("smart_fetch_github_repos", count=len(repos))

        # Analyze and extract structured data (skip trivially short pages)
        if len(truncated) > 500:
            extracted = await extract_with_llm(truncated[:10000], url, client)
            if extracted:
                result["extracted_data"] = extracted

        # Follow relevant links if depth and budget allow (sequential to enforce budget)
        if follow_depth > 0 and remaining_budget > 0:
            if 'github.com/trending' in url and result["github_repos"]:
                candidates = [
                    (f"{r['owner']}/{r['repo']}", r["url"])
                    for r in result["github_repos"][:3]
                    if r["url"] not in visited
                ]
            else:
                urls = extract_urls(truncated, url)
                candidates = [
                    (t, u) for t, u in urls
                    if should_follow_url(u) and u not in visited
                ][:5]

            for title, follow_url in candidates:
                if remaining_budget <= 0:
                    break
                try:
                    sub = await smart_fetch(
                        follow_url,
                        max_length=min(max_length, remaining_budget),
                        follow_depth=follow_depth - 1,
                        client=client,
                        visited=visited,
                        _total_budget=remaining_budget,
                    )
                    if sub.get("skipped"):
                        continue
                    sub["title"] = title
                    result["followed_urls"].append(sub)
                    remaining_budget -= len(json.dumps(sub, ensure_ascii=False))
                except Exception as e:
                    logger.warning("smart_fetch_follow_error", url=follow_url, error=str(e))

        return result

    finally:
        if close_client:
            await client.close()


async def extract_with_llm(content: str, source_url: str, client: LLMClient) -> dict[str, Any] | None:
    """Use LLM to extract structured data from content."""
    from .llm import LLMClient

    schema = {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "description": {"type": "string"},
            "key_points": {"type": "array", "items": {"type": "string"}},
            "metadata": {"type": "object"},
        },
    }

    prompt = f"""Extract structured information from this content.

Source: {source_url}

Content:
{content[:8000]}

Return JSON with:
- title: Main title
- description: Brief summary
- key_points: 3-5 important findings
- metadata: Any relevant metadata (dates, numbers, etc.)
"""

    try:
        response = await client.chat_str(
            system="You are a data extraction assistant. Return valid JSON only.",
            user=prompt,
            schema=schema,
        )

        return json.loads(response)
    except Exception as e:
        logger.warning("extract_with_llm_failed", error=str(e))
        return None
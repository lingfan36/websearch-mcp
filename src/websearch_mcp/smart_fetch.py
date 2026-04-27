"""Smart fetch tool with planning and reasoning capabilities."""

from __future__ import annotations

import re
from typing import Any
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


async def smart_fetch(
    url: str,
    max_length: int = 5000,
    start_index: int = 0,
    follow_depth: int = 2,
    client: LLMClient | None = None,
    visited: set[str] | None = None,
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
        content, _ = await fetch_url(url, force_raw=False)

        result = {
            "url": url,
            "content": content,
            "content_length": len(content),
            "followed_urls": [],
            "extracted_data": None,
            "github_repos": [],
        }

        # Special handling for GitHub trending
        if 'github.com/trending' in url:
            repos = extract_github_repos(content)
            result["github_repos"] = repos
            logger.info("smart_fetch_github_repos", count=len(repos))

        # Analyze and extract structured data
        if len(content) > 100:
            extracted = await extract_with_llm(content[:10000], url, client)
            if extracted:
                result["extracted_data"] = extracted

        # Follow relevant links if depth allows
        if follow_depth > 0:
            # For GitHub trending, construct repo URLs from the listing
            if 'github.com/trending' in url and result["github_repos"]:
                for repo in result["github_repos"][:3]:  # Follow top 3 repos
                    repo_url = repo["url"]
                    if repo_url not in visited:
                        sub_result = await smart_fetch(
                            repo_url,
                            max_length=max_length,
                            follow_depth=follow_depth - 1,
                            client=client,
                            visited=visited,
                        )
                        if not sub_result.get("skipped"):
                            sub_result["title"] = f"{repo['owner']}/{repo['repo']}"
                            result["followed_urls"].append(sub_result)
            else:
                # Generic URL extraction for other pages
                urls = extract_urls(content, url)
                to_follow = [(t, u) for t, u in urls if should_follow_url(u)]

                logger.info("smart_fetch_found_links", count=len(to_follow))

                # Follow up to 5 links
                for title, follow_url in to_follow[:5]:
                    if follow_url not in visited and len(result["followed_urls"]) < 5:
                        sub_result = await smart_fetch(
                            follow_url,
                            max_length=max_length,
                            follow_depth=follow_depth - 1,
                            client=client,
                            visited=visited,
                        )
                        if not sub_result.get("skipped"):
                            sub_result["title"] = title
                            result["followed_urls"].append(sub_result)

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

        import json
        return json.loads(response)
    except Exception as e:
        logger.warning("extract_with_llm_failed", error=str(e))
        return None
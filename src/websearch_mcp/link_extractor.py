"""Link extractor for discovering new URLs from crawled pages."""

from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse
import re
from typing import Any

import structlog

logger = structlog.get_logger()


@dataclass
class ExtractedLink:
    url: str
    text: str
    domain: str
    rel: str = ""


class LinkExtractor(HTMLParser):
    """Extract links from HTML content."""

    def __init__(self, base_url: str):
        super().__init__()
        self.base_url = base_url
        self.base_domain = urlparse(base_url).netloc
        self.links: list[ExtractedLink] = []
        self._current_text = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag not in ("a", "area"):
            return

        href = None
        rel = ""
        for attr_name, attr_value in attrs:
            if attr_name == "href":
                href = attr_value
            if attr_name == "rel":
                rel = attr_value or ""

        if href:
            # Resolve relative URLs
            full_url = urljoin(self.base_url, href)

            # Skip anchors and javascript
            if full_url.startswith(("#", "javascript:", "mailto:", "tel:")):
                return

            # Skip non-http(s)
            if not full_url.startswith(("http://", "https://")):
                return

            self.links.append(ExtractedLink(
                url=full_url,
                text=self._current_text.strip(),
                domain=urlparse(full_url).netloc,
                rel=rel,
            ))

    def handle_data(self, data: str) -> None:
        self._current_text += data + " "

    def handle_endtag(self, tag: str) -> None:
        if tag == "a":
            self._current_text = ""


def extract_links(html: str, base_url: str) -> list[ExtractedLink]:
    """Extract all links from HTML content.

    Args:
        html: HTML content
        base_url: Base URL for resolving relative links

    Returns:
        List of ExtractedLink objects
    """
    extractor = LinkExtractor(base_url)
    try:
        extractor.feed(html)
    except Exception as e:
        logger.warning("link_extraction_failed", url=base_url, error=str(e))

    # Filter out nofollow links (optional)
    # filtered = [l for l in extractor.links if "nofollow" not in l.rel]

    return extractor.links


def is_same_domain(url1: str, url2: str) -> bool:
    """Check if two URLs are from the same domain."""
    return urlparse(url1).netloc == urlparse(url2).netloc


def should_crawl_url(
    url: str,
    allowed_domains: set[str],
    max_depth: int = 2,
    url_depths: dict[str, int] | None = None,
) -> bool:
    """Determine if a URL should be crawled.

    Args:
        url: URL to check
        allowed_domains: Set of allowed domains (from seeds + discovered)
        max_depth: Maximum crawl depth
        url_depths: Map of URL to depth for BFS tracking

    Returns:
        True if URL should be crawled
    """
    parsed = urlparse(url)
    domain = parsed.netloc

    # Must be in allowed domains
    if domain not in allowed_domains:
        return False

    # Check depth limit
    if url_depths is not None:
        depth = url_depths.get(url, 1)
        if depth > max_depth:
            return False

    # Skip common non-content URLs
    skip_patterns = [
        r"\.(pdf|doc|docx|xls|xlsx|ppt|pptx|zip|gz|tar)$",
        r"/(login|signup|register|signin|sign-out|auth)/?$",
        r"^(https?://)?[^/]*\.(facebook|twitter|linkedin|instagram)\.com",
        r"/(checkout|cart|account|settings|profile)/?$",
    ]

    path_lower = url.lower()
    for pattern in skip_patterns:
        if re.search(pattern, path_lower):
            return False

    return True

"""Playwright browser fetcher — last resort for protected sites."""

from __future__ import annotations

import structlog
from typing import Any

from .exceptions import FetchError

logger = structlog.get_logger()

# Global browser instance for reuse
_browser: Any = None
_playwright: Any = None


async def _get_browser() -> Any:
    """Get or create the global Playwright browser instance."""
    global _browser, _playwright
    if _browser is None or not _browser.is_connected():
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            raise FetchError("playwright not installed — run: pip install playwright && playwright install chromium")

        _playwright = await async_playwright().start()
        _browser = await _playwright.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        logger.info("browser_launched")
    return _browser


async def close_browser() -> None:
    """Close the global browser instance."""
    global _browser, _playwright
    if _browser:
        await _browser.close()
        _browser = None
    if _playwright:
        await _playwright.stop()
        _playwright = None


async def fetch_with_browser(url: str, timeout: float = 30.0) -> tuple[str, str]:
    """Fetch URL using Playwright browser.

    Returns (markdown_content, prefix) matching fetch.py convention.
    """
    import asyncio

    from .fetch import extract_content_from_html

    browser = await _get_browser()
    page = await browser.new_page()

    try:
        # Block images, styles, fonts, media to speed up loading
        async def _route_handler(route: Any) -> None:
            if route.request.resource_type() in ("image", "stylesheet", "font", "media"):
                await route.abort()
            else:
                await route.continue_()

        await page.route("**/*", _route_handler)

        await page.set_extra_http_headers({
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        })

        await page.goto(url, timeout=timeout * 1000, wait_until="domcontentloaded")

        # Give dynamic content time to render
        await asyncio.sleep(1.5)

        # Remove non-content elements
        await page.evaluate("""() => {
            const remove = document.querySelectorAll(
                'script, style, nav, header, footer, aside, .advertisement, .ads, .sidebar, .comments, .social-share'
            );
            remove.forEach(el => el.remove());
        }""")

        # Extract main content with fallback chain
        html_content = await page.evaluate("""() => {
            const selectors = [
                'main', 'article', '[role="main"]',
                '.content', '#content', '.post', '.entry-content',
            ];
            for (const sel of selectors) {
                const el = document.querySelector(sel);
                if (el && el.innerHTML.length > 200) return el.innerHTML;
            }
            return document.body.innerHTML;
        }""")

        title = await page.title() or url

        # Convert HTML to markdown using existing utility
        markdown = extract_content_from_html(html_content) if html_content else ""

        if not markdown:
            markdown = await page.evaluate("() => document.body.innerText") or ""

        # Clean excessive whitespace
        import re
        markdown = re.sub(r'\n{3,}', '\n\n', markdown)
        markdown = re.sub(r'^\s+$', '', markdown, flags=re.MULTILINE)

        if not markdown.strip():
            raise FetchError("Browser fetched page but extracted no content")

        logger.info("browser_fetch_ok", url=url, length=len(markdown))
        return markdown, f"[Browser] {title}\n"

    except FetchError:
        raise
    except Exception as e:
        raise FetchError(f"Browser fetch failed: {e}")
    finally:
        await page.close()

<div align="center">

<img src="https://img.icons8.com/3d-fluency/94/search.png" width="80" />

# WebSearch MCP

**Give your AI agent the ability to search and read the web.**

Open-source, self-hosted, MCP-native.

[![PyPI](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![MCP](https://img.shields.io/badge/MCP-Compatible-0EA5E9?style=flat-square)](https://modelcontextprotocol.io/)
[![License: MIT](https://img.shields.io/badge/License-MIT-9333EA?style=flat-square)](LICENSE)
[![GitHub stars](https://img.shields.io/github/stars/lingfan36/websearch-mcp?style=flat-square)](https://github.com/lingfan36/websearch-mcp/stargazers)

[Getting Started](#-getting-started) · [Tools](#-tools) · [Architecture](#-architecture) · [Configuration](#-configuration)

</div>

---

## Why WebSearch MCP?

Most AI coding assistants are blind to the web. They can't search, can't read URLs, can't compare information across pages. WebSearch MCP fixes that with one self-hosted server and zero API fees.

<div align="center">

| | Tavily | Serper | Exa | **WebSearch MCP** |
|:---|:---:|:---:|:---:|:---:|
| Self-hosted | | | | **Y** |
| Zero cost, forever | | | | **Y** |
| Full privacy — no data leaves your machine | | | | **Y** |
| MCP native | Y | Y | Y | **Y** |
| Search the web (no LLM needed) | Y | Y | Y | **Y** |
| Fetch any URL → clean markdown | Y | | Y | **Y** |
| Auto-fallback on blocked sites | | | | **Y** |
| Headless browser for Cloudflare / JS pages | | | | **Y** |
| Batch fetch 10 URLs in parallel | | | | **Y** |
| Deep research with quality evaluation | | | | **Y** |
| Smart link following & data extraction | | | | **Y** |
| Works fully offline | | | | **Y** |

</div>

---

## Tools

### `web_search_quick`

Instant web search via Jina Search API. No local LLM, no waiting.

```
"What are the best Python web frameworks in 2026"
→ 5 results with titles, URLs, and snippets in ~3 seconds
```

Optional: set `fetch_content: true` to auto-fetch full content of the top 3 results in parallel.

### `fetch`

Fetch any URL and get clean markdown back. Three-layer fallback means it just works:

1. **Jina Reader** — Fast, high-quality extraction via API
2. **Local parser** — readabilipy + markdownify, no network dependency
3. **Playwright browser** — Headless Chromium for JavaScript-heavy and protected sites

```
"https://github.com/trending"
→ Full markdown content, automatically extracted
```

### `fetch_batch`

Fetch up to 10 URLs concurrently. Same three-layer fallback per URL.

```
["https://github.com", "https://reddit.com", "https://news.ycombinator.com"]
→ All results fetched in parallel
```

### `web_search`

Deep research pipeline powered by local LLM:

```
"What are the latest breakthroughs in quantum computing?"
→ Structured answer with citations, confidence score, key findings
```

### `fetch_with_insights`

Smart crawler that follows links and extracts structured data:

```
"https://github.com/trending"
→ Repos with stars, descriptions — and auto-follows top repos for details
```

---

## Architecture

### Three-Layer Fetch Engine

The core innovation. Every URL fetch goes through three layers, automatically falling back when needed:

```
   URL
    │
    ▼
┌─────────────────────────────────────────────────────┐
│  Layer 1: Jina Reader API                           │
│  Fast, clean markdown from any URL                  │
│  ────────────────────────                           │
│  ✅ Success → return markdown                       │
│  ❌ Fail → Layer 2                                  │
└──────────────────────┬──────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────┐
│  Layer 2: Local HTTP + readabilipy                  │
│  Direct fetch, no external API needed               │
│  ────────────────────────                           │
│  ✅ Success → return markdown                       │
│  ⚠️  Access denied (403/Cloudflare) → Layer 3      │
│  ❌ Other error → raise                             │
└──────────────────────┬──────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────┐
│  Layer 3: Playwright Headless Browser               │
│  Real Chromium — bypasses JS challenges & captchas  │
│  Blocks images/styles/fonts for speed               │
│  ────────────────────────                           │
│  ✅ Success → return markdown                       │
│  ❌ Fail → raise original error                     │
└─────────────────────────────────────────────────────┘
```

### Deep Research Pipeline

```
 Query ──▶ Rewrite ──▶ Search ──▶ Extract ──▶ Evaluate ─┐
             │           │          │           │         │
             │           │          │           │         │
             ▼           ▼          ▼           ▼         │
         Sub-queries  Parallel   Facts     Sufficient?   │
                                       │           │     │
                                    Yes │        No │     │
                                       ▼           │     │
                                   Synthesize ─────┘─────┘
                                       │
                                       ▼
                              Answer + Citations
```

---

## Getting Started

### 1. Install

```bash
pip install -e .
```

Or use `uvx` for zero-install:
```bash
uvx websearch-mcp
```

### 2. Configure your MCP client

Add to your Claude Code, Cursor, or other MCP client config:

```json
{
  "websearch": {
    "command": "websearch-mcp",
    "env": {
      "JINA_API_KEY": "jina_your_key_here"
    }
  }
}
```

That's it. The `fetch`, `fetch_batch`, and `web_search_quick` tools work immediately.

### 3. Optional: Deep research with local LLM

For the `web_search` deep research pipeline, install Ollama:

```bash
# Install Ollama: https://ollama.com/download
ollama pull qwen2.5:1.5b
```

### 4. Optional: Browser fallback

For Cloudflare-protected and JavaScript-heavy sites:

```bash
pip install playwright
playwright install chromium
```

Set `USE_BROWSER_FALLBACK=true` in your `.env`.

---

## Configuration

All settings are optional with sensible defaults. Configure via `.env` file or environment variables:

```env
# ── Fetch Engine ──────────────────────────────────
JINA_API_KEY=                    # Optional. Free tier works without key.
USE_JINA_READER=true             # Jina Reader as first fetch layer
USE_BROWSER_FALLBACK=false       # Playwright for protected sites

# ── Deep Research (web_search tool) ───────────────
OLLAMA_URL=http://localhost:11434/v1/chat/completions
OLLAMA_MODEL=qwen2.5:1.5b
LLM_TIMEOUT=30

# ── Search Index ──────────────────────────────────
TYPESENSE_HOST=localhost
TYPESENSE_PORT=8108
TYPESENSE_API_KEY=xyz

# ── Crawler ───────────────────────────────────────
CRAWL_CONCURRENCY=3
CRAWLER_MAX_DEPTH=1
```

---

## Python Library

You can also use it directly in Python:

```python
import asyncio
from websearch_mcp.fetch import search_web, fetch_and_extract

async def main():
    # Quick web search
    results = await search_web("best Python ORM 2026")
    for r in results:
        print(f"  {r['title']}")
        print(f"  {r['url']}")

    # Fetch a URL
    content = await fetch_and_extract("https://github.com/trending")
    print(content[:500])

asyncio.run(main())
```

---

## Tech Stack

| Layer | Technology |
|:------|:-----------|
| Protocol | [MCP](https://modelcontextprotocol.io/) |
| Search API | [Jina Search](https://jina.ai/search/) |
| URL Reader | [Jina Reader](https://jina.ai/reader/) + [readabilipy](https://github.com/alanmcruickshank/readabilipy) |
| LLM | [Ollama](https://ollama.ai/) (OpenAI-compatible) |
| Search Index | [Typesense](https://typesense.org/) |
| Crawler | [trafilatura](https://trafilatura.readthedocs.io/) |
| Browser | [Playwright](https://playwright.dev/) (optional) |
| HTML → Markdown | [markdownify](https://github.com/matthewwithanm/python-markdownify) |
| Validation | [Pydantic v2](https://docs.pydantic.dev/) |

---

## Contributing

```bash
git clone https://github.com/lingfan36/websearch-mcp.git
cd websearch-mcp
pip install -e ".[dev]"
pytest
```

PRs welcome.

---

<div align="center">

**MIT License** · Made with care by [Ling Fan](https://github.com/lingfan36)

Found it useful? **[Star this repo](https://github.com/lingfan36/websearch-mcp/stargazers)** — it helps others find it.

</div>

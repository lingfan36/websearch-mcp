<div align="center">

# 🔎 WebSearch MCP

**Self-hosted Tavily alternative. One MCP server, five tools.**

[![GitHub stars](https://img.shields.io/github/stars/lingfan36/websearch-mcp?style=for-the-badge&logo=github)](https://github.com/lingfan36/websearch-mcp/stargazers)
[![PyPI](https://img.shields.io/badge/Python-3.10+-for-the-badge?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![MCP](https://img.shields.io/badge/MCP-Compatible-blue?style=for-the-badge)](https://modelcontextprotocol.org/)
[![License](https://img.shields.io/badge/License-MIT-purple?style=for-the-badge)](LICENSE)

[English](#) · [中文文档](#-中文) · [Report Bug](https://github.com/lingfan36/websearch-mcp/issues) · [Request Feature](https://github.com/lingfan36/websearch-mcp/issues)

</div>

---

## The Problem

Every AI agent needs web search. But existing solutions have tradeoffs:

| | OpenAI Search | Tavily | Serper | **WebSearch MCP** |
|---|---|---|---|---|
| Self-hosted | ❌ | ❌ | ❌ | ✅ |
| Zero API cost | ❌ | ❌ | ❌ | ✅* |
| Privacy-first | ❌ | ❌ | ❌ | ✅ |
| MCP native | ❌ | ✅ | ✅ | ✅ |
| Deep research pipeline | ❌ | ❌ | ❌ | ✅ |
| Smart link following | ❌ | ❌ | ❌ | ✅ |
| Three-layer fetch fallback | ❌ | ❌ | ❌ | ✅ |
| Works offline | ❌ | ❌ | ❌ | ✅ |

> *Deep research uses local Ollama (free). Jina Reader/Search API has a generous free tier.

---

## 🎯 Five Tools, One Server

### `web_search_quick` — Instant Web Search

> Query → Jina Search API → structured results in ~3 seconds. No local LLM needed.

```
Input:  "Python web framework 2026"
Output: [{title, url, snippet}, ...] — optionally with full content of top 3 results
```

### `web_search` — Deep Research Pipeline

> Ask a question → AI rewrites into sub-queries → parallel search → extract facts → evaluate quality → synthesize answer

```
Input:  "What are the latest breakthroughs in quantum computing?"
Output: Structured answer with citations, confidence: 0.95
```

### `fetch` — Smart URL Fetching

> Three-layer fallback: Jina Reader → local parser → Playwright browser. Handles Cloudflare, CAPTCHAs, and protected sites.

```
Input:  "https://news.ycombinator.com"
Output: Clean markdown of the front page
```

### `fetch_batch` — Parallel URL Fetching

> Fetch up to 10 URLs concurrently with the same three-layer fallback.

```
Input:  ["https://github.com", "https://reddit.com", "https://news.ycombinator.com"]
Output: [{url, content}, ...] — all fetched in parallel
```

### `fetch_with_insights` — Smart Crawling

> Fetch page → detect patterns → follow relevant links → extract structured data

```
Input:  "https://github.com/trending"
Output: 13 trending repos with stars, descriptions, and followed details
```

---

## 🚀 Install

```bash
# Option 1: pip
pip install -e .

# Option 2: uvx (recommended, zero install)
uvx websearch-mcp
```

### Requirements

```bash
# Install Ollama and pull a model (for web_search deep research)
curl -fsSL https://ollama.com/install.sh | sh   # Linux/macOS
# or download from https://ollama.com/download    # Windows

ollama pull qwen2.5:1.5b

# Optional: Jina API key for higher rate limits
# Get free key at https://jina.ai/api-dashboard/
# Not required — works without it at lower rate limits
```

---

## 💡 Quick Demo

### In Claude Code / Cursor / Any MCP Client

**Option A: pip install (Recommended)**

```bash
pip install -e /path/to/websearch-mcp
```

```json
{
  "mcpServers": {
    "websearch": {
      "command": "python",
      "args": ["-m", "websearch_mcp"],
      "env": {
        "JINA_API_KEY": "jina_your_key_here"
      }
    }
  }
}
```

**Option B: uvx (if available)**

```json
{
  "mcpServers": {
    "websearch": {
      "command": "uvx",
      "args": ["websearch-mcp"]
    }
  }
}
```

Then your AI agent can search the web:

```
You: What GitHub repos are trending today?

Agent: Let me check...
→ calls fetch_with_insights("https://github.com/trending")

📊 Today's Top Trending Repos:

| # | Repository | Language | Stars Today |
|---|-----------|----------|-------------|
| 1 | mattpocock/skills | Shell | +1,959 |
| 2 | Alishahryar1/free-claude-code | Python | +1,978 |
| 3 | Z4nzu/hackingtool | Python | +7,367 |
| 4 | abhigyanpatwari/GitNexus | TypeScript | +3,499 |
| 5 | microsoft/typescript-go | Go | +922 |
```

### As Python Library

```python
import asyncio
from websearch_mcp.fetch import search_web, fetch_and_extract

async def main():
    # Quick web search (no LLM needed)
    results = await search_web("Python web framework 2026", max_results=5)
    for r in results:
        print(f"{r['title']} — {r['url']}")

    # Fetch a URL with three-layer fallback
    content = await fetch_and_extract("https://github.com/trending", max_length=5000)
    print(content)

asyncio.run(main())
```

---

## 🧠 How It Works

### Three-Layer Fetch Fallback

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  Jina Reader  │────▶│  Local Parser │────▶│  Playwright  │
│  (fast, API)  │     │ (readabilipy) │     │  (browser)   │
└──────────────┘     └──────────────┘     └──────────────┘
        │                    │                     │
   Success ✅          Success ✅          For protected sites
   or fallback          or fallback         (Cloudflare, etc.)
```

### web_search Pipeline

```
┌──────────┐    ┌───────────┐    ┌───────────┐    ┌───────────┐
│  Rewrite  │───▶│   Search   │───▶│  Extract   │───▶│  Evaluate  │
│  Query    │    │  Parallel  │    │   Facts    │    │  Quality   │
└──────────┘    └───────────┘    └───────────┘    └─────┬─────┘
                                                         │
                                              ┌──────────▼──────────┐
                                              │  Sufficient?        │
                                              │  Yes → Synthesize   │
                                              │  No  → Loop back    │
                                              └─────────────────────┘
```

Quick mode skips Rewrite and Evaluate for faster results.

### fetch_with_insights Pipeline

```
┌─────────┐    ┌──────────────┐    ┌──────────────┐    ┌─────────────┐
│  Fetch   │───▶│   Detect     │───▶│   Follow     │───▶│  Extract    │
│  Page    │    │   Patterns   │    │   Links      │    │  Structure  │
└─────────┘    └──────────────┘    └──────────────┘    └─────────────┘
                     │
                     ▼
              ┌──────────────┐
              │ GitHub repos │ → Auto-parse repos, stars, descriptions
              │ News sites   │ → Extract articles, dates, authors
              │ Docs sites   │ → Follow sections, build index
              └──────────────┘
```

---

## 🔧 Configuration

```bash
cp .env.example .env   # or create .env manually
```

```env
# Core — Required for web_search (deep research)
OLLAMA_URL=http://localhost:11434/v1/chat/completions
OLLAMA_MODEL=qwen2.5:1.5b

# Search Index — Optional (without it, only fetch/search tools work)
TYPESENSE_HOST=localhost
TYPESENSE_PORT=8108

# Jina API — Optional (works without key at lower rate limits)
JINA_API_KEY=jina_xxxxx

# Fetch Strategy
USE_JINA_READER=true          # Use Jina Reader as first fetch layer
USE_BROWSER_FALLBACK=false    # Enable Playwright for protected sites

# Performance
LLM_TIMEOUT=30
CRAWL_CONCURRENCY=3
```

### Optional: Playwright Browser Fallback

For sites behind Cloudflare, CAPTCHAs, or other access restrictions:

```bash
pip install playwright
playwright install chromium
```

Then set `USE_BROWSER_FALLBACK=true` in your `.env`.

---

## 📦 Tech Stack

<p align="center">

| Layer | Choice | Why |
|-------|--------|-----|
| Protocol | **MCP** | Industry standard for AI tooling |
| Fast Search | **Jina Search API** | Instant results, no LLM needed |
| URL Reader | **Jina Reader** | High-quality HTML → Markdown |
| LLM | **Ollama** | Free, local, private |
| Search Index | **Typesense** | Fast, typo-tolerant, self-hosted |
| Crawler | **Trafilatura** | Best open-source content extractor |
| Reader | **Readability + Markdownify** | Clean HTML → Markdown |
| Browser | **Playwright** (optional) | Handles protected sites |
| Validation | **Pydantic v2** | Type-safe data models |

</p>

---

## 🗺️ Roadmap

- [ ] **Web UI** — Built-in dashboard for search history and traces
- [ ] **Streaming** — Real-time streaming responses for web_search
- [ ] **Cache Layer** — Redis-based caching for repeated queries
- [ ] **Multi-model** — Support for GPT-4, Claude, Gemini as backends
- [ ] **Plugin System** — Custom extractors for specific sites
- [ ] **Docker Compose** — One-command deployment with Typesense

---

## 🤝 Contributing

```bash
git clone https://github.com/lingfan36/websearch-mcp.git
cd websearch-mcp
pip install -e ".[dev]"
pytest
```

PRs welcome. See [SPEC.md](./SPEC.md) for design docs.

---

## 📄 License

MIT © [Ling Fan](https://github.com/lingfan36)

---

<div align="center">

**If this project helps you, give it a ⭐**

It helps others discover it. Thank you!

</div>

<div align="center">

<img src="https://img.icons8.com/3d-fluency/94/search.png" width="80" />

# WebSearch MCP

**Production-grade web search and research tools for AI agents.**

Open the web for your AI — search, read, extract, and synthesize information at scale.

[![PyPI](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![MCP](https://img.shields.io/badge/MCP-Compatible-0EA5E9?style=flat-square)](https://modelcontextprotocol.io/)
[![License: MIT](https://img.shields.io/badge/License-MIT-9333EA?style=flat-square)](LICENSE)
[![GitHub stars](https://img.shields.io/github/stars/lingfan36/websearch-mcp?style=flat-square)](https://github.com/lingfan36/websearch-mcp/stargazers)

[Features](#features) · [Tools](#tools) · [Architecture](#architecture) · [Quick Start](#quick-start) · [Configuration](#configuration)

</div>

---

## What is WebSearch MCP?

A Model Context Protocol server that gives AI agents real-time access to the web. Not just simple search — a complete research pipeline that:

- **Searches** the live web and local indexes
- **Reads** any URL and extracts clean markdown
- **Understands** content through LLM-powered fact extraction
- **Synthesizes** findings into structured answers with citations
- **Grows** smarter over time by auto-indexing visited pages

Built for AI coding assistants, agents, and research tools that need current, accurate information from the web.

---

## Features

| Capability | Description |
|:-----------|:------------|
| **5 MCP Tools** | `web_search`, `web_search_quick`, `fetch`, `fetch_batch`, `fetch_with_insights` |
| **Parallel Search** | Concurrent queries reduce latency from 69s to ~25s |
| **3-Layer Fetch** | Jina Reader → local parser → Playwright browser |
| **Auto-Indexing** | Web search results automatically indexed to Typesense |
| **Deep Research** | Multi-stage pipeline: rewrite → search → extract → evaluate → synthesize |
| **Hook System** | Pre/post event handlers for logging, caching, cost tracking |
| **Skill Config** | YAML-based configuration for node behavior |
| **Cloud LLM Ready** | OpenAI-compatible API (MiniMax, OpenAI, etc.) |

---

## Tools

### `web_search`

Deep research pipeline for complex queries. Returns structured answers with citations and confidence scores.

```
Input:  "What are today's GitHub trending AI projects?"
Output: {
  answer: "Based on today's data...",
  citations: [{text, url, title}],
  confidence: 0.85,
  key_findings: [...]
}
```

**Pipeline stages:**
1. **Rewrite** — Expand query into 3-5 sub-queries
2. **Search** — Query Typesense first, fallback to live web (parallel)
3. **Extract** — LLM extracts facts, entities, statistics from pages
4. **Evaluate** — Check if findings are sufficient
5. **Synthesize** — Generate structured answer with citations

### `web_search_quick`

Fast web search without LLM overhead. Returns results in ~3 seconds.

```
Input:  {query: "best Rust web frameworks 2026", fetch_content: true}
Output: [{title, url, snippet, content}]
```

### `fetch`

Fetch any URL and get clean markdown. Three-layer fallback handles failures automatically:

1. **Jina Reader** — Fast, high-quality extraction
2. **Local parser** — readabilipy + markdownify, no external dependency
3. **Playwright** — Headless Chromium for Cloudflare/JS-protected sites

### `fetch_batch`

Fetch up to 10 URLs concurrently with the same 3-layer fallback per URL.

### `fetch_with_insights`

Smart crawler that follows relevant links and extracts structured data. Good for researching topics across multiple pages.

---

## Architecture

### Fetch Engine

```
URL → Jina Reader API → Success? → Markdown
              ↓ Fail
     Local HTTP + readabilipy → Success? → Markdown
                    ↓ Fail (403/Cloudflare)
           Playwright Chromium → Markdown
```

### Deep Research Pipeline

```
Query
  │
  ▼
┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌───────────┐
│ Rewrite │───▶│  Search │───▶│ Extract │───▶│ Evaluate│───▶│ Synthesize│
└─────────┘    └─────────┘    └─────────┘    └─────────┘    └───────────┘
     │              │              │              │              │
     ▼              ▼              ▼              ▼              ▼
 Sub-queries   Parallel web    Facts +       Sufficient?    Answer +
                search         entities      No → loop      citations
```

### Smart Index Growth

The local Typesense index grows automatically:

```
Search "AI agents"
      │
      ▼
Typesense hit? ──Yes──→ Return cached
      │
     No
      │
      ▼
Live web search → Fetch pages → Extract content
      │
      ▼
Index to Typesense ← Next search hits local
```

---

## Quick Start

### 1. Install

```bash
pip install -e .
# or zero-install
uvx websearch-mcp
```

### 2. Configure MCP Client

```json
{
  "mcpServers": {
    "websearch": {
      "command": "websearch-mcp",
      "env": {
        "JINA_API_KEY": "your_jina_key",
        "OPENAI_API_KEY": "your_minimax_key"
      }
    }
  }
}
```

### 3. Start Using

```python
# Quick search
results = await web_search_quick("GitHub trending today")

# Deep research
result = await web_search(
    query="What are the latest developments in AI agents?",
    depth="balanced"  # quick / balanced / deep
)
```

---

## Configuration

| Variable | Default | Description |
|:---------|:--------|:------------|
| `JINA_API_KEY` | - | Jina Search/Reader API key |
| `OPENAI_API_KEY` | - | LLM API key (MiniMax, OpenAI, etc.) |
| `OPENAI_BASE_URL` | `https://api.minimaxi.com/v1/chat/completions` | LLM endpoint |
| `OPENAI_MODEL` | `MiniMax-M2.7` | LLM model |
| `LLM_TIMEOUT` | `120` | LLM request timeout (seconds) |
| `TYPESENSE_HOST` | `localhost` | Typesense server host |
| `TYPESENSE_PORT` | `8108` | Typesense server port |
| `USE_BROWSER_FALLBACK` | `false` | Enable Playwright for protected sites |

---

## Tech Stack

| Layer | Technology |
|:------|:-----------|
| Protocol | [MCP](https://modelcontextprotocol.io/) |
| Search | [Jina Search API](https://jina.ai/search/) |
| URL Reading | [Jina Reader](https://jina.ai/reader/) + [readabilipy](https://github.com/alanmcruickshank/readabilipy) |
| LLM | OpenAI-compatible (MiniMax, OpenAI, Ollama, etc.) |
| Search Index | [Typesense](https://typesense.org/) |
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

**MIT License** · [Ling Fan](https://github.com/lingfan36)

Star this repo if you find it useful.

[![GitHub stars](https://img.shields.io/github/stars/lingfan36/websearch-mcp?style=social)](https://github.com/lingfan36/websearch-mcp/stargazers)

</div>

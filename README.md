<div align="center">

# 🔎 WebSearch MCP

**Self-hosted Tavily alternative. One MCP server, three tools.**

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
| Zero API cost | ❌ | ❌ | ❌ | ✅ |
| Privacy-first | ❌ | ❌ | ❌ | ✅ |
| MCP native | ❌ | ✅ | ✅ | ✅ |
| Deep research pipeline | ❌ | ❌ | ❌ | ✅ |
| Smart link following | ❌ | ❌ | ❌ | ✅ |
| Works offline* | ❌ | ❌ | ❌ | ✅ |

> *Offline = local LLM via Ollama. Only URL fetching requires internet.

---

## 🎯 Three Tools, One Server

### `web_search` — Deep Research Pipeline

> Ask a question → AI rewrites into sub-queries → parallel search → extract facts → evaluate quality → synthesize answer

```
Input:  "What are the latest breakthroughs in quantum computing?"
Output: Structured answer with citations, confidence: 0.95
```

### `fetch` — Real-Time URL Fetching

> Fetch any URL → extract clean markdown → return readable content

```
Input:  "https://news.ycombinator.com"
Output: Clean markdown of the front page
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
# Install Ollama and pull a model
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen2.5:1.5b
```

That's it. No API keys. No cloud accounts.

---

## 💡 Quick Demo

### In Claude Code / Cursor / Any MCP Client

Add to your MCP config:

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
from websearch_mcp import run_search, smart_fetch

async def main():
    # Deep research
    result = await run_search("Explain transformer architecture")
    print(result["answer"])
    print(f"Confidence: {result['confidence']}")

    # Smart fetch
    data = await smart_fetch("https://github.com/trending", follow_depth=2)
    for repo in data["github_repos"]:
        print(f"{repo['owner']}/{repo['repo']} +{repo['today_stars']}★")

asyncio.run(main())
```

---

## 🧠 How It Works

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
cp .env.example .env
```

```env
# Core — Required
OLLAMA_URL=http://localhost:11434/v1/chat/completions
OLLAMA_MODEL=qwen2.5:1.5b

# Search Index — Optional (without it, only fetch tools work)
TYPESENSE_HOST=localhost
TYPESENSE_PORT=8108

# Performance
OLLAMA_TIMEOUT=120
CRAWL_CONCURRENCY=3
```

---

## 📦 Tech Stack

<p align="center">

| Layer | Choice | Why |
|-------|--------|-----|
| Protocol | **MCP** | Industry standard for AI tooling |
| LLM | **Ollama** | Free, local, private |
| Search | **Typesense** | Fast, typo-tolerant, self-hosted |
| Crawler | **Trafilatura** | Best open-source content extractor |
| Reader | **Readability + Markdownify** | Clean HTML → Markdown |
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

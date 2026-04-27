# 🔍 WebSearch MCP

> Build your own Tavily-like web search with MCP protocol. Self-hosted, local-first, fully customizable.

[![MCP Server](https://img.shields.io/badge/MCP-Server-blue?style=flat-square)](https://modelcontextprotocol.org/)
[![Python](https://img.shields.io/badge/Python-3.10+-green?style=flat-square)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-purple?style=flat-square)](LICENSE)
[![Stars](https://img.shields.io/github/stars/lingfan36/websearch-mcp?style=flat-square)](https://github.com/lingfan36/websearch-mcp/stargazers)

**WebSearch MCP** is a self-built Model Context Protocol server that brings intelligent web search and content fetching capabilities to your AI agents. Powered by local Ollama LLM — no external API dependencies, no privacy concerns.

---

## ✨ Features

### 🤖 Three Powerful Tools in One

| Tool | Purpose | Best For |
|------|---------|----------|
| **`web_search`** | Deep research pipeline | Complex queries, multi-source synthesis |
| **`fetch`** | Direct URL fetching | Real-time data, specific URLs |
| **`fetch_with_insights`** | Smart crawling + AI extraction | Research, comparisons, structured data |

### 🧠 Intelligent Pipeline

```
User Query → Rewriter → Parallel Search → Extractor → Evaluator → [Loop] → Synthesizer
                    ↓              ↓
               Typesense       Trafilatura
                    ↓              ↓
                    └──────────────┴──→ Ollama (Local LLM)
```

- **Query Rewriting**: Transform queries into 2-5 optimized sub-queries
- **Parallel Search**: Execute multiple searches concurrently
- **Fact Extraction**: Pull structured entities, stats, quotes, timelines
- **Quality Evaluation**: Confidence scoring with iteration loop
- **Smart Synthesis**: Generate comprehensive answers with citations

### 🌐 Real-Time Content Intelligence

```python
# GitHub Trending with AI-powered extraction
result = await smart_fetch("https://github.com/trending", follow_depth=2)

# Returns structured data automatically:
# {
#   "github_repos": [
#     {"owner": "mattpocock", "repo": "skills", "today_stars": "1959", ...},
#     ...
#   ],
#   "followed_urls": [...],
#   "extracted_data": {...}
# }
```

---

## 🚀 Quick Start

### 1. Install

```bash
# Clone and install
git clone https://github.com/lingfan36/websearch-mcp.git
cd websearch-mcp
pip install -e .

# Or use uvx (zero installation)
uvx websearch-mcp
```

### 2. Setup Ollama

```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Pull the default model
ollama pull qwen2.5:1.5b
```

### 3. Run

```bash
# Start the MCP server
python -m websearch_mcp.server

# Or use CLI
websearch --query "What is machine learning?"
```

---

## 📖 Usage

### As MCP Server (Claude Code, Cursor, etc.)

Add to your MCP settings:

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

### As Python Library

```python
import asyncio
from websearch_mcp import run_search, fetch_and_extract, smart_fetch

async def main():
    # Deep research (uses indexed data)
    result = await run_search("What is deep learning?")
    print(result["answer"])

    # Real-time fetch
    content = await fetch_and_extract("https://news.ycombinator.com")

    # Smart fetch with AI insights
    data = await smart_fetch("https://github.com/trending", follow_depth=2)

asyncio.run(main())
```

---

## 🛠️ Tools Reference

### `web_search`

```json
{
  "query": "Explain neural networks",
  "depth": "balanced"
}
```

**Response:**
```json
{
  "answer": "# Neural Networks\n\nNeural networks are...",
  "confidence": 0.95,
  "citations": [
    {"text": "...", "url": "https://...", "title": "..."}
  ],
  "key_findings": ["...", "..."],
  "status": "success"
}
```

### `fetch`

```json
{
  "url": "https://example.com",
  "max_length": 5000,
  "start_index": 0,
  "raw": false
}
```

### `fetch_with_insights`

```json
{
  "url": "https://github.com/trending",
  "follow_depth": 2,
  "max_length": 8000
}
```

---

## 🏗️ Architecture

```
┌────────────────────────────────────────────────────────────────┐
│                        WebSearch MCP                          │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│    ┌──────────────┐   ┌──────────────┐   ┌──────────────────┐ │
│    │  web_search  │   │    fetch    │   │ fetch_with_insights│
│    │   (deep)     │   │  (realtime)  │   │  (smart crawl)   │ │
│    └──────┬───────┘   └──────┬───────┘   └────────┬─────────┘ │
│           │                  │                     │           │
│           └──────────────────┼─────────────────────┘           │
│                              │                                 │
│                    ┌─────────▼─────────┐                      │
│                    │   Pipeline Nodes   │                      │
│                    │  Rewriter          │                      │
│                    │  Search           │                      │
│                    │  Extractor        │                      │
│                    │  Evaluator        │                      │
│                    │  Synthesizer      │                      │
│                    └─────────┬─────────┘                      │
│                              │                                 │
│           ┌──────────────────┼──────────────────┐             │
│           ▼                  ▼                  ▼             │
│    ┌────────────┐    ┌────────────┐    ┌────────────┐       │
│    │  Typesense │    │ Trafilatura │    │   Ollama   │       │
│    │   Index    │    │   Crawler   │    │    LLM     │       │
│    └────────────┘    └────────────┘    └────────────┘       │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

---

## 📦 Tech Stack

| Component | Technology |
|-----------|------------|
| **Protocol** | Model Context Protocol (MCP) |
| **Framework** | mcp-python-sdk |
| **LLM** | Ollama (local, OpenAI-compatible) |
| **Search** | Typesense |
| **Crawling** | Trafilatura + Readabilipy |
| **Markdown** | Markdownify |
| **Data** | Pydantic v2 |

---

## 🔧 Configuration

Create `.env` from `.env.example`:

```bash
cp .env.example .env
```

```env
# Ollama
OLLAMA_URL=http://localhost:11434/v1/chat/completions
OLLAMA_MODEL=qwen2.5:1.5b
OLLAMA_TIMEOUT=120

# Typesense (optional)
TYPESENSE_HOST=localhost
TYPESENSE_PORT=8108
TYPESENSE_KEY=

# Crawler
CRAWL_DELAY=1.0
CRAWL_CONCURRENCY=3
```

---

## 🤝 Contributing

Contributions welcome! Please read [SPEC.md](./SPEC.md) first.

```bash
# Development setup
git clone https://github.com/lingfan36/websearch-mcp.git
cd websearch-mcp
pip install -e ".[dev]"

# Run tests
pytest
```

---

## 📊 Why This Project?

| Feature | OpenAI | Tavily | **WebSearch MCP** |
|---------|--------|--------|-------------------|
| Self-hosted | ❌ | ❌ | ✅ |
| Local LLM | ❌ | ❌ | ✅ |
| No API costs | ❌ | ❌ | ✅ |
| Fully customizable | ❌ | ❌ | ✅ |
| MCP protocol | ❌ | ✅ | ✅ |
| Real-time fetch | ❌ | ✅ | ✅ |

---

## 📄 License

MIT © [Ling Fan](https://github.com/lingfan36)

---

<div align="center">

**⭐ Star this repo if you find it useful!**

*[Powered by Ollama + MCP + Python]*

</div>
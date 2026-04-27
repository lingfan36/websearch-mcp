# WebSearch MCP Server

A self-built MCP (Model Context Protocol) server for intelligent web search and content fetching, powered by local Ollama LLM.

## Features

### 🔍 Intelligent Web Search (`web_search`)
- **Deep research pipeline**: Rewriter → Search → Extractor → Evaluator → Synthesizer
- Multi-query rewriting with parallel execution
- Structured fact extraction and quality evaluation
- Iteration loop for gap-filling until sufficient

### 🌐 Direct URL Fetching (`fetch`)
- Fetch any URL and extract as markdown
- Automatic HTML-to-markdown conversion using Readability
- Pagination support (`max_length`, `start_index`)
- Robots.txt compliance
- Raw HTML mode available

### 🧠 Smart Fetch with Insights (`fetch_with_insights`)
- AI-powered link following and data extraction
- Automatic pattern recognition (e.g., GitHub trending repos)
- Structured data extraction from multiple sources
- Configurable follow depth

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     MCP Server                         │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌──────────────┐    ┌──────────────┐    ┌───────────┐ │
│  │  web_search  │    │    fetch    │    │ fetch_with│ │
│  │   (deep)     │    │  (realtime) │    │ _insights │ │
│  └──────┬───────┘    └──────┬───────┘    └─────┬─────┘ │
│         │                   │                  │       │
│         ▼                   ▼                  ▼       │
│  ┌─────────────────────────────────────────────────┐   │
│  │              Pipeline Nodes                      │   │
│  │  Rewriter → Search → Extractor → Evaluator      │   │
│  │                    ↓                            │   │
│  │               Synthesizer                       │   │
│  └─────────────────────────────────────────────────┘   │
│         │                   │                  │       │
│         ▼                   ▼                  ▼       │
│  ┌────────────┐      ┌────────────┐      ┌──────────┐ │
│  │  Typesense │      │  Trafilatura│      │   LLM    │ │
│  │   (index)  │      │  (crawler)  │      │ (Ollama) │ │
│  └────────────┘      └────────────┘      └──────────┘ │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

## Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/websearch-mcp.git
cd websearch-mcp

# Install dependencies
pip install -e .

# Or use uvx (no installation required)
uvx websearch-mcp
```

## Configuration

### Environment Variables

Create a `.env` file based on `.env.example`:

```env
# Ollama Configuration
OLLAMA_API_URL=http://localhost:11434/v1/chat/completions
OLLAMA_MODEL=qwen2.5:1.5b
OLLAMA_TIMEOUT=120

# Typesense Configuration
TYPESENSE_HOST=localhost
TYPESENSE_PORT=8100
TYPESENSE_KEY=

# Crawler Configuration
CRAWL_DELAY=1.0
CRAWL_CONCURRENCY=3
```

### Ollama Setup

```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Pull the default model (qwen2.5:1.5b)
ollama pull qwen2.5:1.5b

# Or use a different model
ollama pull llama3.2
```

### Typesense Setup (Optional - for web_search)

```bash
# Install Typesense
docker run -d -p 8108:8108 typesense/typesense:latest \
  --data-dir /tmp/typesense-data \
  --api-key=your-api-key

# Index your content (see CLI tools)
python -m websearch_mcp.cli index --help
```

## Usage

### As MCP Server (for Claude Code)

Add to your Claude Code MCP settings:

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
    # Deep search (uses indexed data)
    result = await run_search("What is machine learning?")
    print(result["answer"])

    # Direct fetch (real-time)
    content = await fetch_and_extract("https://github.com/trending")

    # Smart fetch with insights
    result = await smart_fetch("https://github.com/trending", follow_depth=2)

asyncio.run(main())
```

### CLI Tools

```bash
# Index a URL
python -m websearch_mcp.cli index https://example.com

# Search indexed content
python -m websearch_mcp.cli search "machine learning"

# Crawl a website (BFS)
python -m websearch_mcp.cli crawl https://example.com --max-pages 100

# Start the MCP server
python -m websearch_mcp.server
```

## Tools Reference

### web_search

```json
{
  "query": "What is deep learning?",
  "depth": "balanced"  // "quick" | "balanced" | "deep"
}
```

Returns:
```json
{
  "answer": "Deep learning is...",
  "citations": [{"text": "...", "url": "...", "title": "..."}],
  "confidence": 0.95,
  "key_findings": ["...", "..."],
  "iterations_used": 1,
  "status": "success"
}
```

### fetch

```json
{
  "url": "https://news.ycombinator.com/",
  "max_length": 5000,
  "start_index": 0,
  "raw": false
}
```

### fetch_with_insights

```json
{
  "url": "https://github.com/trending",
  "follow_depth": 2,
  "max_length": 8000
}
```

Returns:
```json
{
  "url": "https://github.com/trending",
  "content": "...",
  "github_repos": [
    {"owner": "mattpocock", "repo": "skills", "today_stars": "1959", ...}
  ],
  "followed_urls": [...],
  "extracted_data": {"title": "...", "key_points": [...]}
}
```

## Requirements

- Python 3.10+
- [Ollama](https://ollama.com/) (local LLM server)
- Optional: Typesense (for indexed search)
- Optional: Node.js (for better HTML extraction with Readability.js)

## Dependencies

- `mcp` - MCP server framework
- `httpx` - HTTP client
- `trafilatura` - HTML content extraction
- `readabilipy` - Readability-based extraction
- `markdownify` - HTML to markdown conversion
- `typesense` - Search engine
- `structlog` - Structured logging
- `pydantic` - Data validation

## License

MIT

## Contributing

Contributions welcome! Please read the spec in `SPEC.md` first.
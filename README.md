# WebSearch MCP

**让 AI Agent 实时接入互联网。**

一个生产级的 MCP 服务器，为 AI 编码助手和研究工具提供实时 web 搜索、内容抓取和深度研究能力。

[![PyPI](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![MCP](https://img.shields.io/badge/MCP-Compatible-0EA5E9?style=flat-square)](https://modelcontextprotocol.io/)
[![License: MIT](https://img.shields.io/badge/License-MIT-9333EA?style=flat-square)](LICENSE)
[![GitHub stars](https://img.shields.io/github/stars/lingfan36/websearch-mcp?style=flat-square)](https://github.com/lingfan36/websearch-mcp/stargazers)

---

## 为什么选择 WebSearch MCP？

### 对比其他方案

| 能力 | Tavily | Serper | Exa | **WebSearch MCP** |
|:-----|:------:|:------:|:---:|:-----------------:|
| 搜索 + 抓取一体化 | 部分 | 部分 | 部分 | **完整管道** |
| 3 层自动降级 | ❌ | ❌ | ❌ | **✅** |
| 并行搜索（69s→25s） | ❌ | ❌ | ❌ | **✅** |
| 自动索引增长 | ❌ | ❌ | ❌ | **✅** |
| 深度研究管道 | ❌ | ❌ | ❌ | **✅** |
| Hook 扩展系统 | ❌ | ❌ | ❌ | **✅** |
| Skill YAML 配置 | ❌ | ❌ | ❌ | **✅** |
| MCP 原生 | ✅ | ✅ | ✅ | **✅** |
| 自托管 | ❌ | ❌ | ❌ | **✅** |
| 免费额度 | 1000次/月 | 2500次/月 | 有 | **✅ 永久免费** |

### 核心优势

**1. 永远能拿到数据**
- 其他方案：被 Cloudflare 拦截？返回空结果
- WebSearch MCP：自动降级到 Playwright 浏览器，真机模拟访问

**2. 越用越快**
- 其他方案：每次都请求外部 API，有限额度，有延迟
- WebSearch MCP：自动索引搜索结果，本地 Typesense 命中后 ~100ms 返回

**3. 深度研究不是梦**
- 其他方案：只返回搜索结果
- WebSearch MCP：Query → Rewrite → Search → Extract → Evaluate → Synthesize，带置信度和引用

**4. 完全可控**
- 其他方案：数据经过第三方服务器
- WebSearch MCP：完全自托管，数据不离开你的机器（使用本地 LLM 时）

| 能力 | 说明 |
|:-----|:-----|
| **5 个 MCP 工具** | 覆盖快速搜索、深度研究、URL 抓取、批量处理、智能爬取 |
| **并行搜索** | 多查询并发，延迟从 69s 降至 ~25s |
| **3 层抓取引擎** | Jina Reader → 本地解析 → Playwright 浏览器 |
| **自动索引** | 搜索结果自动写入 Typesense，本地缓存越来越快 |
| **深度研究管道** | Query → Rewrite → Search → Extract → Evaluate → Synthesize |
| **Hook 系统** | Pre/post 事件钩子，支持日志、成本跟踪、缓存 |
| **Skill 配置** | YAML 定义的节点行为配置 |

---

## 工具

### `web_search` — 深度研究

复杂查询的深度研究管道。返回带引用和置信度评分的结构化答案。

```python
result = await web_search(
    query="今天 GitHub 热门 AI 项目有哪些？",
    depth="balanced"  # quick / balanced / deep
)
# 返回: {answer, citations, confidence, key_findings}
```

**执行流程：**
```
Query → Rewrite (生成 3-5 个子查询)
      → Search (并行搜索 Typesense + 实时 web)
      → Extract (LLM 从页面提取事实)
      → Evaluate (评估是否充分)
      → Synthesize (生成带引用的结构化答案)
```

### `web_search_quick` — 快速搜索

无需 LLM 开销的快速 web 搜索，~3 秒返回结果。

```python
results = await web_search_quick(
    query="2026 年最火的编程语言",
    fetch_content=True  # 可选：同时抓取前 3 个结果的内容
)
```

### `fetch` — URL 抓取

抓取任意 URL 并返回干净 markdown。三层自动降级：

1. **Jina Reader API** — 快速、高质量
2. **本地解析器** — readabilipy + markdownify，无外部依赖
3. **Playwright 浏览器** — 处理 Cloudflare/JS 加密站点

```python
content = await fetch(
    url="https://github.com/trending",
    max_length=5000
)
```

### `fetch_batch` — 批量抓取

并发抓取多达 10 个 URL，每个 URL 独立走 3 层降级。

### `fetch_with_insights` — 智能爬取

AI 驱动的链接follow，自动提取结构化数据。适合跨多页面研究主题。

---

## 架构

### 3 层抓取引擎

```
URL
 │
 ▼
┌──────────────────────────────────────────────────┐
│  Layer 1: Jina Reader API                        │
│  ─────────────────────                           │
│  ✅ 成功 → 返回 markdown                          │
│  ❌ 失败 → 降级到 Layer 2                         │
└────────────────────┬─────────────────────────────┘
                     │
                     ▼
┌──────────────────────────────────────────────────┐
│  Layer 2: Local HTTP + readabilipy               │
│  ─────────────────────                           │
│  ✅ 成功 → 返回 markdown                          │
│  ⚠️  403/Cloudflare → Layer 3                   │
│  ❌ 其他错误 → 抛出异常                           │
└────────────────────┬─────────────────────────────┘
                     │
                     ▼
┌──────────────────────────────────────────────────┐
│  Layer 3: Playwright Headless Browser            │
│  ─────────────────────                           │
│  ✅ 成功 → 返回 markdown                          │
│  ❌ 失败 → 抛出原始异常                           │
└──────────────────────────────────────────────────┘
```

### 深度研究管道

```
        ┌─────────┐
        │ Rewrite │
        └────┬────┘
             │  生成子查询
             ▼
        ┌─────────┐
        │ Search  │ ← 并发执行
        └────┬────┘
             │  搜索结果
             ▼
        ┌─────────┐
        │ Extract │ ← LLM 提取事实
        └────┬────┘
             │  事实
             ▼
        ┌─────────┐
        │Evaluate │ ← 足够？
        └────┬────┘
             │  不足 → 循环
             ▼
        ┌──────────┐
        │Synthesize│ ← 生成答案
        └────┬─────┘
             │
             ▼
         Answer
```

### 智能索引增长

```
用户搜索 "量子计算"
        │
        ▼
  Typesense 命中？ ── 是 ──→ 返回缓存结果
        │
       否
        │
        ▼
  实时 web 搜索 → 抓取页面 → 提取内容
        │
        ▼
  写入 Typesense ← 下次搜索命中本地索引
```

每次回退到 web 搜索都会丰富本地索引。使用越久，搜索越快。

---

## 快速开始

### 1. 安装

```bash
pip install -e .
# 或零安装
uvx websearch-mcp
```

### 2. 配置 MCP 客户端

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

### 3. 使用

```python
# 快速搜索（~3秒）
results = await web_search_quick("GitHub trending AI")

# 深度研究（~2分钟）
result = await web_search(
    query="今天最火的 AI 开源项目有哪些？",
    depth="balanced"
)
```

---

## 配置

| 环境变量 | 默认值 | 说明 |
|:---------|:------|:-----|
| `JINA_API_KEY` | - | Jina Search/Reader API Key |
| `OPENAI_API_KEY` | - | LLM API Key |
| `OPENAI_BASE_URL` | `https://api.minimaxi.com/v1/chat/completions` | LLM 端点 |
| `OPENAI_MODEL` | `MiniMax-M2.7` | LLM 模型 |
| `LLM_TIMEOUT` | `120` | LLM 请求超时（秒） |
| `TYPESENSE_HOST` | `localhost` | Typesense 服务器地址 |
| `TYPESENSE_PORT` | `8108` | Typesense 服务器端口 |
| `USE_BROWSER_FALLBACK` | `false` | 启用 Playwright 处理受保护站点 |

---

## 技术栈

| 层级 | 技术 |
|:-----|:-----|
| 协议 | [MCP](https://modelcontextprotocol.io/) |
| 搜索 | [Jina Search API](https://jina.ai/search/) |
| URL 读取 | [Jina Reader](https://jina.ai/reader/) + [readabilipy](https://github.com/alanmcruickshank/readabilipy) |
| LLM | OpenAI 兼容接口（MiniMax、OpenAI、Ollama 等） |
| 搜索索引 | [Typesense](https://typesense.org/) |
| HTML 转换 | [markdownify](https://github.com/matthewwithanm/python-markdownify) |
| 数据验证 | [Pydantic v2](https://docs.pydantic.dev/) |

---

## 贡献

```bash
git clone https://github.com/lingfan36/websearch-mcp.git
cd websearch-mcp
pip install -e ".[dev]"
pytest
```

欢迎提交 PR。

---

## 许可证

MIT License · [Ling Fan](https://github.com/lingfan36)

如果对你有用，请给个 Star。

[![GitHub stars](https://img.shields.io/github/stars/lingfan36/websearch-mcp?style=social)](https://github.com/lingfan36/websearch-mcp/stargazers)

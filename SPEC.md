# WebSearch MCP Server

## 1. Project Overview

**Name:** websearch-mcp
**Type:** MCP Server (Python)
**Core:** 自建搜索 + 研究 pipeline，效果优于 taily 搜索
**Target:** AI Agent / Claude Code 等 LLM 客户端

## 2. Architecture

### 2.1 技术栈

- **语言:** Python 3.11+
- **MCP:** mcp[fastapi] SDK
- **LLM:** Ollama (localhost:11434, OpenAI 兼容)
- **爬虫:** crawl4ai
- **搜索索引:** Typesense
- **正文提取:** trafilatura

### 2.2 系统架构

```
┌─────────────────────────────────────────────────────────┐
│                    Typesense Server                      │
│                  (搜索索引引擎)                           │
└─────────────────────────────────────────────────────────┘
                           ↑
┌─────────────────────────────────────────────────────────┐
│                   MCP Server (Python)                    │
│  ┌─────────┐   ┌─────────┐   ┌─────────┐   ┌────────┐ │
│  │ Rewriter│ → │ Search  │ → │Extractor│ → │Evaluator│ │
│  └─────────┘   └─────────┘   └─────────┘   └────────┘ │
│       ↑                                        │       │
│       └────────────── Synthesizer ←────────────┘       │
└─────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────┐
│                     crawl4ai                            │
│                    (爬虫引擎)                            │
└─────────────────────────────────────────────────────────┘
```

### 2.3 搜索链路

```
用户Query
    ↓
[Rewriter] → 生成多个搜索 query
    ↓
[Search] → Typesense 查询 → 返回 url + snippet
    ↓
[并行 Crawl] → crawl4ai 抓取页面
    ↓
[Extract] → trafilatura 提取正文
    ↓
[Evaluator] → 评估是否足够
    ↓
(不够) → 补充 gap queries → 回到 Search
(够) → [Synthesizer] → 最终回答
```

## 3. MCP Tool 接口

### 3.1 暴露的工具

```python
@mcp.tool()
async def web_search(query: str, depth: str = "balanced") -> str:
    """
    Web search with deep research.

    Args:
        query: Search query (supports complex questions)
        depth: "quick" | "balanced" | "deep", default "balanced"

    Returns:
        JSON string with answer and citations
    """
```

### 3.2 返回格式

```json
{
  "answer": "...",
  "citations": [
    {"text": "...", "url": "https://...", "title": "..."}
  ],
  "confidence": 0.85,
  "key_findings": ["...", "..."],
  "iterations_used": 2,
  "trace_id": "..."
}
```

## 4. Exception Handling

| 节点 | 异常 | 策略 |
|------|------|------|
| Rewriter | 失败 | 降级用原始 query |
| Search | 连接失败 | 降级到 snippet 模式 |
| Crawler | 页面抓取失败 | 跳过，用 snippet |
| Extractor | 解析失败 | 降级到 snippet |
| Evaluator | 死循环 | max_iterations / 同 gap 重复 / 置信度阈值 |
| Synthesizer | 失败 | 终极兜底直接拼接 facts |

## 5. Logging & Trace

- `SearchTrace` — 贯穿整个 session
- `TraceEvent` — 每个节点的时间线事件
- `Checkpoint` — 关键节点状态快照

## 6. Project Structure

```
D:\webSearch\
├── SPEC.md
├── pyproject.toml
├── .env.example
├── src/websearch_mcp/
│   ├── __init__.py
│   ├── server.py           # MCP server 入口
│   ├── schema.py           # 数据模型
│   ├── config.py           # 配置管理
│   ├── llm.py              # LLM 客户端
│   ├── trace.py            # 日志追踪
│   ├── exceptions.py      # 异常定义
│   ├── typesense_client.py # Typesense 客户端
│   ├── crawler.py          # crawl4ai 封装
│   └── nodes/
│       ├── __init__.py
│       ├── rewriter.py     # 查询改写
│       ├── search.py       # 搜索查询
│       ├── extractor.py    # 内容提取
│       ├── evaluator.py    # 质量评估
│       └── synthesizer.py   # 答案合成
└── tests/
```

## 7. Acceptance Criteria

1. MCP server 能正常启动
2. `web_search` 工具能被 LLM 调用
3. 返回带引用的结构化结果
4. 异常情况有降级处理，不崩溃
5. 有 trace 日志可追溯
6. 搜索效果优于 taily（主观评估）

## 8. Dependencies

```toml
crawl4ai>=0.3.0      # 爬虫
typesense>=27.1.0    # 搜索索引
trafilatura>=1.6.0   # 正文提取
BeautifulSoup4>=4.12.0
```

## 9. Out of Scope

- 多用户/并发会话
- 前端界面
- 其他 MCP 工具（仅 web_search 一个）
- Typesense 集群部署（单节点即可）

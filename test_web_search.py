"""Test script for web_search tool (deep research pipeline with local LLM)."""

import asyncio
import json
import os
import time
from pathlib import Path
from dotenv import load_dotenv

# Load .env file
env_path = Path(__file__).parent / ".env"
load_dotenv(env_path)

from websearch_mcp.search_handler import handle_web_search

# ===== 在这里填写搜索内容 =====
QUERY = "2026年5月6日 GitHub trending 热门项目"
DEPTH = "quick"  # quick / balanced / deep
# ================================


async def main():
    if not QUERY:
        print("Error: QUERY is empty. Edit test_web_search.py and set QUERY.")
        return

    print(f"Searching: {QUERY!r} (depth={DEPTH})")
    print("-" * 60)

    start = time.time()
    result = await handle_web_search(query=QUERY, depth=DEPTH)
    elapsed = time.time() - start

    output = json.dumps(result, ensure_ascii=False, indent=2)
    with open("test_result.json", "w", encoding="utf-8") as f:
        f.write(output)
    print(f"Done in {elapsed:.1f}s | status={result.get('status')} | confidence={result.get('confidence')}")
    print("Result saved to test_result.json")


if __name__ == "__main__":
    asyncio.run(main())

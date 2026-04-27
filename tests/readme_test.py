import sys
sys.stdout.reconfigure(encoding='utf-8')
import asyncio
from websearch_mcp.fetch import fetch_url

async def main():
    repos = [
        ("mattpocock/skills - Agent Skills for Real Engineers", "https://raw.githubusercontent.com/mattpocock/skills/main/README.md"),
        ("Z4nzu/hackingtool - ALL IN ONE Hacking Tool", "https://raw.githubusercontent.com/Z4nzu/hackingtool/main/README.md"),
        ("abhigyanpatwari/GitNexus - Zero-Server Code Intelligence", "https://raw.githubusercontent.com/abhigyanpatwari/GitNexus/main/README.md"),
        ("ComposioHQ/awesome-codex-skills - Codex Skills列表", "https://raw.githubusercontent.com/ComposioHQ/awesome-codex-skills/main/README.md"),
        ("codecrafters-io/build-your-own-x - 徒手造轮子", "https://raw.githubusercontent.com/codecrafters-io/build-your-own-x/main/README.md"),
    ]
    for name, url in repos:
        try:
            r = await fetch_url(url)
            content = r[0] if isinstance(r, tuple) else r
            print(f'=== {name} ===')
            print(content[:1000])
            print()
        except Exception as e:
            print(f'=== {name} === Error: {e}')
            print()

asyncio.run(main())
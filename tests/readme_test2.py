import sys
sys.stdout.reconfigure(encoding='utf-8')
import asyncio
from websearch_mcp.fetch import fetch_url

async def main():
    urls = [
        ("codecrafters-io/build-your-own-x", "https://raw.githubusercontent.com/codecrafters-io/build-your-own-x/master/README.md"),
        ("ComposioHQ/awesome-codex-skills", "https://raw.githubusercontent.com/ComposioHQ/awesome-codex-skills/master/README.md"),
        ("Z4nzu/hackingtool", "https://github.com/Z4nzu/hackingtool"),
        ("gastownhall/beads", "https://raw.githubusercontent.com/gastownhall/beads/main/README.md"),
        ("trycua/cua", "https://raw.githubusercontent.com/trycua/cua/main/README.md"),
    ]
    for name, url in urls:
        try:
            r = await fetch_url(url)
            content = r[0] if isinstance(r, tuple) else r
            print(f'=== {name} ===')
            print(content[:1200])
            print()
        except Exception as e:
            print(f'=== {name} === Error: {e}\n')

asyncio.run(main())
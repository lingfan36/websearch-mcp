"""Test script for web_search MCP tool."""

import asyncio
import json
import sys

# MCP protocol messages
def create_request():
    return {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test", "version": "1.0.0"}
        }
    }

def create_tool_call():
    return {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/call",
        "params": {
            "name": "web_search",
            "arguments": {"query": "What is artificial intelligence?", "depth": "quick"}
        }
    }

async def test_mcp():
    import subprocess
    from mcp.types import TextContent

    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "websearch_mcp.server",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd="D:/webSearch"
    )

    # Send initialize
    init_msg = json.dumps(create_request()) + "\n"
    proc.stdin.write(init_msg.encode())
    await proc.stdin.drain()

    # Read response
    resp = await asyncio.wait_for(proc.stdout.readline(), timeout=5)
    print(f"Initialize response: {resp.decode().strip()}")

    # Send tool call
    tool_msg = json.dumps(create_tool_call()) + "\n"
    proc.stdin.write(tool_msg.encode())
    await proc.stdin.drain()

    # Read responses (may be multiple)
    try:
        while True:
            resp = await asyncio.wait_for(proc.stdout.readline(), timeout=30)
            if not resp:
                break
            data = resp.decode().strip()
            if data:
                print(f"Response: {data}")
    except asyncio.TimeoutError:
        print("Timeout waiting for response")

    proc.terminate()
    await proc.wait()

if __name__ == "__main__":
    asyncio.run(test_mcp())

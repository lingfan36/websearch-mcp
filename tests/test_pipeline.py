"""Simple test to verify core pipeline works."""

import asyncio
import sys
sys.path.insert(0, "src")

from websearch_mcp.llm import LLMClient
from websearch_mcp.nodes.rewriter import RewriterNode
from websearch_mcp.nodes.search import SearchNode
from websearch_mcp.nodes.extractor import ExtractorNode
from websearch_mcp.nodes.evaluator import EvaluatorNode
from websearch_mcp.nodes.synthesizer import SynthesizerNode
from websearch_mcp.typesense_client import get_typesense_client
from websearch_mcp.schema import SearchSession

async def test_pipeline():
    print("=== Testing Search Pipeline ===\n")

    # 1. Test LLM
    print("1. Testing LLM connection...")
    llm = LLMClient()
    try:
        resp = await llm.chat_str(system="", user="Say 'hello' in one word")
        print(f"   LLM response: {resp}\n")
    except Exception as e:
        print(f"   LLM error: {e}\n")
        return
    finally:
        await llm.close()

    # 2. Test Typesense
    print("2. Testing Typesense connection...")
    ts = get_typesense_client()
    try:
        await ts.ensure_collection()
        print("   Typesense collection ready\n")
    except Exception as e:
        print(f"   Typesense error: {e}\n")

    # 3. Test Rewriter
    print("3. Testing Rewriter node...")
    llm = LLMClient()
    rewriter = RewriterNode(llm)
    try:
        result = await rewriter.run("What is machine learning?")
        print(f"   Rewritten queries: {len(result.queries)}")
        for q in result.queries[:3]:
            print(f"   - {q.query}\n")
    except Exception as e:
        print(f"   Rewriter error: {e}\n")
    finally:
        await llm.close()

    print("=== Test Complete ===")
    print("Note: Search will return empty until data is indexed.")

if __name__ == "__main__":
    asyncio.run(test_pipeline())

"""Test full search pipeline with some indexed data."""

import asyncio
import sys
sys.path.insert(0, "src")

from websearch_mcp.typesense_client import get_typesense_client
from websearch_mcp.nodes.search import SearchNode
from websearch_mcp.nodes.extractor import ExtractorNode
from websearch_mcp.nodes.synthesizer import SynthesizerNode
from websearch_mcp.schema import RewriterOutput, RewrittenQuery, SearchDepth
from websearch_mcp.llm import LLMClient

async def index_sample_data():
    """Index some sample pages."""
    ts = get_typesense_client()
    await ts.ensure_collection()

    pages = [
        {
            "url": "https://en.wikipedia.org/wiki/Artificial_intelligence",
            "title": "Artificial intelligence - Wikipedia",
            "content": "Artificial intelligence (AI) is intelligence demonstrated by machines, in contrast to the natural intelligence displayed by humans and animals. Leading AI textbooks define the field as the study of 'intelligent agents': any device that perceives its environment and takes actions that maximize its chance of success.",
            "snippet": "Artificial intelligence is intelligence demonstrated by machines...",
            "domain": "wikipedia.org",
        },
        {
            "url": "https://en.wikipedia.org/wiki/Machine_learning",
            "title": "Machine learning - Wikipedia",
            "content": "Machine learning (ML) is a field of inquiry in artificial intelligence which studies the construction and study of systems that can learn from data. Machine learning is sometimes combined with data mining, which focuses more on exploratory data analysis.",
            "snippet": "Machine learning is a field of inquiry in artificial intelligence...",
            "domain": "wikipedia.org",
        },
        {
            "url": "https://en.wikipedia.org/wiki/Deep_learning",
            "title": "Deep learning - Wikipedia",
            "content": "Deep learning is part of a broader family of machine learning methods based on artificial neural networks with representation learning. Learning can be supervised, semi-supervised or unsupervised.",
            "snippet": "Deep learning is part of machine learning methods based on neural networks...",
            "domain": "wikipedia.org",
        },
    ]

    for page in pages:
        await ts.index_page(**page)
        print(f"Indexed: {page['title']}")

async def test_search():
    print("=== Testing Full Search Pipeline ===\n")

    # Index sample data
    print("1. Indexing sample data...")
    await index_sample_data()
    print()

    # Test search
    print("2. Testing Search node...")
    searcher = SearchNode()

    rewriter_output = RewriterOutput(
        queries=[
            RewrittenQuery(query="artificial intelligence", rationale="test", search_depth=SearchDepth.BALANCED),
        ],
        reasoning="test"
    )

    results, _ = await searcher.run(rewriter_output, crawl=False)
    print(f"   Search found {len(results)} results")
    for r in results[:3]:
        print(f"   - {r.title}: {r.snippet[:80]}...")
    print()

    # Test extractor + synthesizer
    if results:
        print("3. Testing Extractor + Synthesizer...")
        llm = LLMClient()
        extractor = ExtractorNode(llm)
        synthesizer = SynthesizerNode(llm)

        ext_result = await extractor.run(results)
        print(f"   Extracted: {len(ext_result.facts.entities)} entities, {len(ext_result.facts.key_findings)} findings")

        synth_result = await synthesizer.run(
            ext_result.facts,
            [],
            "What is artificial intelligence?",
            1
        )
        print(f"   Synthesized answer length: {len(synth_result.answer)} chars")
        print(f"   Confidence: {synth_result.confidence}")
        print()
        print("   Answer preview:")
        print("   " + synth_result.answer[:300].replace("\n", "\n   ") + "...")

        await llm.close()

    print("\n=== Test Complete ===")

if __name__ == "__main__":
    asyncio.run(test_search())

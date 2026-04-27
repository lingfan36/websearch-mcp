"""CLI commands for the search crawler."""

from __future__ import annotations

import asyncio
import argparse
import logging
from pathlib import Path

from .seed_manager import create_default_seed_manager
from .typesense_client import get_typesense_client
from .bfs_crawler import BFSCrawler

logging.basicConfig(level=logging.INFO)


async def crawl_command(
    max_pages: int = 100,
    max_time: int = 300,
    max_depth: int = 2,
    concurrent: int = 3,
    state_dir: str = "./crawl_state",
) -> None:
    """Run the BFS crawler."""
    seed_manager = create_default_seed_manager()
    typesense = get_typesense_client()

    crawler = BFSCrawler(
        seed_manager=seed_manager,
        typesense=typesense,
        max_concurrent=concurrent,
        max_depth=max_depth,
        state_dir=Path(state_dir),
    )

    print(f"Starting BFS crawl: max_pages={max_pages}, max_depth={max_depth}")
    stats = await crawler.crawl(max_pages=max_pages, max_time_seconds=max_time)

    print("\n=== Crawl Complete ===")
    print(f"Pages crawled: {stats.pages_crawled}")
    print(f"Pages indexed: {stats.pages_indexed}")
    print(f"Pages failed: {stats.pages_failed}")
    print(f"New domains: {stats.new_domains_discovered}")
    print(f"Queue remaining: {len(crawler.state.queue)}")


def status_command(state_dir: str = "./crawl_state") -> None:
    """Show crawler status."""
    from .seed_manager import SeedManager
    from .bfs_crawler import CrawlState

    state_dir = Path(state_dir)

    # Load states
    seed_manager = SeedManager()
    seed_manager.load(state_dir / "seeds.json")

    crawl_state = CrawlState()
    crawl_state.load(state_dir / "crawl_state.json")

    print("\n=== Crawler Status ===")
    print(f"State directory: {state_dir}")
    print()
    print("Seeds:")
    print(f"  Total: {len(seed_manager.seeds)}")
    print(f"  Enabled: {len([s for s in seed_manager.seeds if s.enabled])}")
    print(f"  Domains tracked: {len(seed_manager.domains)}")
    print()
    print("Crawl State:")
    print(f"  Visited URLs: {len(crawl_state.visited_urls)}")
    print(f"  Discovered URLs: {len(crawl_state.discovered_urls)}")
    print(f"  Queue size: {len(crawl_state.queue)}")
    print(f"  Failed URLs: {len(crawl_state.failed_urls)}")

    # Typesense stats
    try:
        ts = get_typesense_client()
        result = ts.client.collections["webpages"].retrieve()
        print()
        print("Typesense:")
        print(f"  Documents: {result.get('num_documents', 'unknown')}")
    except Exception as e:
        print(f"\nTypesense: Error - {e}")


def main() -> None:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(description="WebSearch MCP Crawler")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Crawl command
    crawl_parser = subparsers.add_parser("crawl", help="Run BFS crawler")
    crawl_parser.add_argument("--max-pages", type=int, default=100)
    crawl_parser.add_argument("--max-time", type=int, default=300)
    crawl_parser.add_argument("--max-depth", type=int, default=2)
    crawl_parser.add_argument("--concurrent", type=int, default=3)
    crawl_parser.add_argument("--state-dir", type=str, default="./crawl_state")

    # Status command
    status_parser = subparsers.add_parser("status", help="Show crawler status")
    status_parser.add_argument("--state-dir", type=str, default="./crawl_state")

    args = parser.parse_args()

    if args.command == "crawl":
        asyncio.run(crawl_command(
            max_pages=args.max_pages,
            max_time=args.max_time,
            max_depth=args.max_depth,
            concurrent=args.concurrent,
            state_dir=args.state_dir,
        ))
    elif args.command == "status":
        status_command(state_dir=args.state_dir)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

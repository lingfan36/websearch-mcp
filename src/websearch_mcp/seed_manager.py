"""Seed URL manager for BFS crawling."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import structlog

logger = structlog.get_logger()


class Category(str, Enum):
    AI = "ai"
    TECH = "tech"
    NEWS = "news"
    BLOG = "blog"
    DOCUMENTATION = "documentation"
    GENERAL = "general"


@dataclass
class SeedURL:
    url: str
    category: Category
    priority: int = 1  # 1-5, higher = more important
    description: str = ""
    last_crawled: str | None = None
    crawl_count: int = 0
    enabled: bool = True

    @property
    def domain(self) -> str:
        return urlparse(self.url).netloc


@dataclass
class SeedManager:
    """Manages seed URLs for BFS crawling."""
    seeds: list[SeedURL] = field(default_factory=list)
    domains: set[str] = field(default_factory=set)  # Track allowed domains
    state_file: Path | None = None

    def add_seed(
        self,
        url: str,
        category: str = "general",
        priority: int = 1,
        description: str = "",
    ) -> None:
        """Add a seed URL."""
        seed = SeedURL(
            url=url,
            category=Category(category),
            priority=priority,
            description=description,
        )
        self.seeds.append(seed)
        self.domains.add(seed.domain)
        logger.info("seed_added", url=url, domain=seed.domain, category=category)

    def remove_seed(self, url: str) -> None:
        """Remove a seed URL."""
        self.seeds = [s for s in self.seeds if s.url != url]
        # Rebuild domains
        self.domains = {s.domain for s in self.seeds if s.enabled}

    def get_pending_seeds(self) -> list[SeedURL]:
        """Get seeds that haven't been crawled recently."""
        return [s for s in self.seeds if s.enabled]

    def mark_crawled(self, url: str) -> None:
        """Mark a seed as crawled."""
        for seed in self.seeds:
            if seed.url == url:
                seed.last_crawled = datetime.utcnow().isoformat()
                seed.crawl_count += 1
                break

    def is_domain_allowed(self, domain: str) -> bool:
        """Check if a domain is allowed (from seeds or discovered)."""
        return domain in self.domains

    def add_discovered_domain(self, domain: str) -> None:
        """Add a newly discovered domain."""
        self.domains.add(domain)

    def get_stats(self) -> dict[str, Any]:
        """Get crawling statistics."""
        return {
            "total_seeds": len(self.seeds),
            "enabled_seeds": len([s for s in self.seeds if s.enabled]),
            "total_domains": len(self.domains),
            "by_category": {
                cat.value: len([s for s in self.seeds if s.category == cat])
                for cat in Category
            },
        }

    def save(self, path: Path) -> None:
        """Save state to file."""
        data = {
            "seeds": [
                {
                    "url": s.url,
                    "category": s.category.value,
                    "priority": s.priority,
                    "description": s.description,
                    "last_crawled": s.last_crawled,
                    "crawl_count": s.crawl_count,
                    "enabled": s.enabled,
                }
                for s in self.seeds
            ],
            "domains": list(self.domains),
        }
        path.write_text(json.dumps(data, indent=2))
        logger.info("seed_manager_saved", path=str(path))

    def load(self, path: Path) -> None:
        """Load state from file."""
        if not path.exists():
            logger.info("seed_manager_no_state", path=str(path))
            return

        data = json.loads(path.read_text())
        self.seeds = [
            SeedURL(
                url=s["url"],
                category=Category(s.get("category", "general")),
                priority=s.get("priority", 1),
                description=s.get("description", ""),
                last_crawled=s.get("last_crawled"),
                crawl_count=s.get("crawl_count", 0),
                enabled=s.get("enabled", True),
            )
            for s in data.get("seeds", [])
        ]
        self.domains = set(data.get("domains", []))
        logger.info("seed_manager_loaded", seeds=len(self.seeds), domains=len(self.domains))


# Default AI-focused seed URLs
DEFAULT_SEEDS = [
    # AI Research & News - many of these are blocked, adding more accessible ones
    ("https://arxiv.org/", Category.AI, 5, "AI research papers"),
    ("https://huggingface.co/papers", Category.AI, 5, "Hugging Face papers"),  # often blocked
    ("https://www.anthropic.com/research", Category.AI, 5, "Anthropic research"),  # often blocked
    ("https://openai.com/research", Category.AI, 5, "OpenAI research"),  # often blocked
    ("https://blog.google/technology/ai/", Category.AI, 4, "Google AI blog"),  # often blocked
    ("https://www.microsoft.com/en-us/research/blog/", Category.AI, 4, "Microsoft research"),
    ("https://www.deepmind.com/blog", Category.AI, 5, "DeepMind blog"),  # redirects
    ("https://ai.googleblog.com/", Category.AI, 4, "Google AI blog posts"),  # often blocked
    ("https://www.technologyreview.com/topic/artificial-intelligence/", Category.AI, 3, "MIT Tech Review AI"),

    # AI News & Media
    ("https://venturebeat.com/category/ai/", Category.NEWS, 4, "VentureBeat AI"),  # rate limited
    ("https://www.theverge.com/ai-artificial-intelligence", Category.NEWS, 3, "The Verge AI"),
    ("https://arstechnica.com/ai/", Category.NEWS, 4, "Ars Technica AI"),
    ("https://www.wired.com/tag/artificial-intelligence/", Category.NEWS, 3, "Wired AI"),
    ("https://www.reuters.com/technology/artificial-intelligence/", Category.NEWS, 3, "Reuters AI"),  # often blocked
    ("https://www.bloomberg.com/technology", Category.NEWS, 3, "Bloomberg Tech"),  # often blocked
    ("https://www.semafor.com/tech", Category.NEWS, 2, "Semafor Tech"),
    ("https://techcrunch.com/category/artificial-intelligence/", Category.NEWS, 4, "TechCrunch AI"),
    ("https://www.theregister.com/category/ai/", Category.NEWS, 2, "The Register AI"),
    ("https://www.zdnet.com/topic/artificial-intelligence/", Category.NEWS, 3, "ZDNet AI"),

    # AI Documentation & Tutorials
    ("https://docs.anthropic.com/", Category.DOCUMENTATION, 5, "Anthropic docs"),
    ("https://platform.openai.com/docs", Category.DOCUMENTATION, 5, "OpenAI docs"),  # often blocked
    ("https://python.langchain.com/docs", Category.DOCUMENTATION, 4, "LangChain docs"),
    ("https://docs.python.org/3/", Category.DOCUMENTATION, 3, "Python docs"),
    ("https://docs.google.com/document/d/", Category.DOCUMENTATION, 2, "Google Docs"),
    ("https://github.com/features/copilot", Category.DOCUMENTATION, 4, "GitHub Copilot"),  # often blocked
    ("https://ollama.com/blog", Category.BLOG, 4, "Ollama blog"),
    ("https://www.llamaindex.ai/blog", Category.BLOG, 4, "LlamaIndex blog"),
    ("https://docs.mistral.ai/", Category.DOCUMENTATION, 4, "Mistral docs"),  # often blocked

    # Tech Blogs
    ("https://blogs.nvidia.com/", Category.BLOG, 4, "NVIDIA blog"),
    ("https://aws.amazon.com/blogs/machine-learning/", Category.BLOG, 4, "AWS ML blog"),
    ("https://cloud.google.com/blog/products/ai-machine-learning", Category.BLOG, 4, "Google Cloud AI"),  # often blocked
    ("https://blog.cloudflare.com/tag/ai/", Category.BLOG, 3, "Cloudflare AI"),
    ("https://stackoverflow.com/questions/tagged/artificial-intelligence", Category.AI, 3, "Stack Overflow AI"),  # often blocked
    ("https://news.ycombinator.com/", Category.NEWS, 3, "Hacker News"),  # often blocked

    # More accessible sites
    ("https://en.wikipedia.org/wiki/Artificial_intelligence", Category.AI, 5, "Wikipedia AI"),
    ("https://www.ibm.com/topics/artificial-intelligence", Category.AI, 4, "IBM AI"),
    ("https://www.sas.com/en_us/insights/analytics/what-is-artificial-intelligence.html", Category.AI, 3, "SAS AI"),
    ("https://www.oracle.com/artificial-intelligence/", Category.AI, 3, "Oracle AI"),
    ("https://www.nvidia.com/en-us/ai/", Category.AI, 4, "NVIDIA AI hub"),
    ("https://www.intel.com/content/www/us/en/artificial-intelligence.html", Category.AI, 3, "Intel AI"),
    ("https://www.coursera.org/articles/what-is-artificial-intelligence", Category.AI, 4, "Coursera AI"),
    ("https://builtin.com/artificial-intelligence", Category.AI, 4, "Builtin AI"),
    ("https://www.guru99.com/artificial-intelligence.html", Category.AI, 3, "Guru99 AI"),
    ("https://www.geeksforgeeks.org/artificial-intelligence/", Category.AI, 3, "GeeksforGeeks AI"),
    ("https://www.techtarget.com/searchenterpriseai/definition/artificial-intelligence", Category.AI, 4, "TechTarget AI"),
]


def create_default_seed_manager() -> SeedManager:
    """Create a seed manager with default AI-focused URLs."""
    manager = SeedManager()
    for url, category, priority, description in DEFAULT_SEEDS:
        manager.add_seed(url, category.value, priority, description)
    return manager

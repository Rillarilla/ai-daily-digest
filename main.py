#!/usr/bin/env python3
"""
AI Daily Digest - Main entry point.

Collects AI news from multiple sources, summarizes with Claude,
and sends a beautifully formatted email digest.
"""

import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path

import yaml

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from collectors import (
    collect_all_rss,
    collect_arxiv,
    collect_twitter,
    collect_hackernews,
    NewsItem,
)
from processors import ClaudeSummarizer, process_items
from email_sender import send_digest_email


def load_config(config_path: str = "config/sources.yaml") -> dict:
    """Load configuration from YAML file."""
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


async def collect_all_sources(config: dict) -> list[NewsItem]:
    """Collect news from all configured sources."""
    tasks = []

    # RSS sources
    if config.get("rss_sources"):
        tasks.append(collect_all_rss(config["rss_sources"]))

    # arXiv papers
    if config.get("arxiv", {}).get("enabled", True):
        tasks.append(collect_arxiv(config.get("arxiv", {})))

    # Twitter/X
    if config.get("twitter", {}).get("enabled", True):
        tasks.append(collect_twitter(config.get("twitter", {})))

    # Hacker News
    if config.get("hackernews", {}).get("enabled", True):
        tasks.append(collect_hackernews(config.get("hackernews", {})))

    # Run all collectors concurrently
    results = await asyncio.gather(*tasks, return_exceptions=True)

    all_items = []
    for result in results:
        if isinstance(result, list):
            all_items.extend(result)
        elif isinstance(result, Exception):
            print(f"Collector error: {result}")

    return all_items


def main():
    """Main entry point."""
    print(f"\n{'='*60}")
    print(f"🤖 AI Daily Digest - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*60}\n")

    # Load config
    config_path = Path(__file__).parent / "config" / "sources.yaml"
    config = load_config(str(config_path))

    # Get output settings
    output_config = config.get("output", {})
    category_names = output_config.get("category_names", {})
    max_per_category = output_config.get("max_per_category", 5)

    # Collect from all sources
    print("📡 Collecting from sources...")
    all_items = asyncio.run(collect_all_sources(config))
    print(f"   Total collected: {len(all_items)} items\n")

    if not all_items:
        print("❌ No items collected. Check your configuration and network.")
        return 1

    # Process items (dedupe, filter, group)
    print("🔄 Processing items...")
    categories = process_items(all_items, max_per_category=max_per_category)
    total_items = sum(len(items) for items in categories.values())
    print(f"   After processing: {total_items} items in {len(categories)} categories\n")

    # Generate summaries with Claude
    highlights = ""
    if os.environ.get("ANTHROPIC_API_KEY"):
        print("🧠 Generating AI summaries...")
        try:
            summarizer = ClaudeSummarizer()
            highlights = summarizer.generate_daily_highlights(categories, category_names)
            print("   Highlights generated\n")
        except Exception as e:
            print(f"   Summarizer error: {e}\n")
    else:
        print("⚠️  ANTHROPIC_API_KEY not set, skipping AI summaries\n")

    # Send email
    to_email = os.environ.get("TO_EMAIL", "rillahai@gmail.com")
    print(f"📧 Sending email to {to_email}...")

    success = send_digest_email(
        to_email=to_email,
        categories=categories,
        category_names=category_names,
        highlights=highlights,
    )

    if success:
        print("\n✅ Daily digest sent successfully!")
        return 0
    else:
        print("\n❌ Failed to send email. Check SMTP configuration.")
        return 1


if __name__ == "__main__":
    sys.exit(main())

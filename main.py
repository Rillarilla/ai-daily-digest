#!/usr/bin/env python3
"""
AI Daily Digest - Main entry point.

Collects AI news from multiple sources, summarizes with Gemini,
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
from processors import GeminiSummarizer, process_items
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


async def translate_items(items: list[NewsItem], summarizer) -> list[NewsItem]:
    """翻译英文内容为中文 (Parallel)"""
    print(f"🌐 Translating {len(items)} items...")

    # Use the summarizer's parallel processing method directly
    # But we need to filter IRRELEVANT ones afterwards

    # We'll use a custom processing loop here to keep the IRRELEVANT filtering logic
    # but utilize parallel execution

    tasks = []
    for item in items:
        tasks.append(summarizer.summarize_and_translate(item))

    results = await asyncio.gather(*tasks, return_exceptions=True)

    valid_items = []
    translated_count = 0

    for i, result in enumerate(results):
        item = items[i]

        if isinstance(result, Exception):
            print(f"   Translation error for '{item.title[:30]}...': {result}")
            # Keep original on error
            valid_items.append(item)
            continue

        title, summary, is_translated = result

        # Filter irrelevant content
        if summary and "IRRELEVANT" in summary:
            print(f"   🚫 Skipping irrelevant item: {item.title}")
            continue

        item.title = title
        item.summary = summary
        item.is_translated = is_translated
        if is_translated:
            translated_count += 1

        valid_items.append(item)

    print(f"   Translated {translated_count} items (Filtered {len(items) - len(valid_items)} irrelevant)\n")
    return valid_items


async def main_async():
    """Main entry point (Async)."""
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
    all_items = await collect_all_sources(config)
    print(f"   Total collected: {len(all_items)} items\n")

    if not all_items:
        print("❌ No items collected. Check your configuration and network.")
        return 1

    # Process items (dedupe, filter, group)
    print("🔄 Processing items...")
    categories = process_items(all_items, max_per_category=max_per_category)
    total_items = sum(len(items) for items in categories.values())
    print(f"   After processing: {total_items} items in {len(categories)} categories\n")

    # Initialize summarizer
    summarizer = None
    highlights = ""

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        # Fallback check
        if os.environ.get("ANTHROPIC_API_KEY"):
            print("⚠️  ANTHROPIC_API_KEY found but GEMINI_API_KEY is missing.")
            print("    The project has migrated to Google Gemini. Please set GEMINI_API_KEY.")

    if api_key:
        print("🧠 Initializing Gemini AI...")
        try:
            summarizer = GeminiSummarizer(api_key=api_key)

            # Translate items in each category (Processing categories sequentially, items parallel)
            for cat_name, items in categories.items():
                categories[cat_name] = await translate_items(items, summarizer)

            # Generate highlights
            print("✨ Generating daily highlights...")
            highlights = await summarizer.generate_daily_highlights(categories, category_names)
            print("   Highlights generated\n")
        except Exception as e:
            print(f"   AI error: {e}\n")
    else:
        print("⚠️  GEMINI_API_KEY not set, skipping AI translation and summaries\n")

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


def main():
    """Wrapper for async main."""
    sys.exit(asyncio.run(main_async()))


if __name__ == "__main__":
    sys.exit(main())

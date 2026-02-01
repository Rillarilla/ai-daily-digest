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
from dotenv import load_dotenv

# Load environment variables from .env file if it exists
load_dotenv()

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
from publishers.feishu_publisher import FeishuPublisher


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
                valid_items, _ = await summarizer.process_and_filter_items(items)
                categories[cat_name] = valid_items

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

        # Publish to Feishu if enabled
        publishers_config = config.get("publishers", {})
        feishu_config = publishers_config.get("feishu", {})

        if feishu_config.get("enabled", False):
            print("\n🚀 Publishing to Feishu...")
            publisher = FeishuPublisher()
            if publisher.is_configured():
                # Construct Markdown content
                date_str = datetime.now().strftime("%Y-%m-%d")
                title = feishu_config.get("title_format", "AI Daily Digest - {date}").format(date=date_str)

                md_content = ""
                if highlights:
                    md_content += "## ⚡ 今日要点\n\n"
                    # Highlights is already formatted HTML-ish/text mixed, let's clean it or use it.
                    # The summarizer returns HTML div/span blocks now. We need text for Feishu.
                    # Actually, summarizer.generate_daily_highlights returns HTML string.
                    # We might need to strip HTML for Feishu markdown.
                    # Quick hack: use regex to strip tags for now.
                    import re
                    clean_highlights = re.sub(r'<[^>]+>', '', highlights).strip()
                    # Fix spacing
                    clean_highlights = re.sub(r'\n\s*\n', '\n\n', clean_highlights)
                    md_content += clean_highlights + "\n\n"

                for cat_id in output_config.get("category_order", []):
                    if cat_id not in categories or not categories[cat_id]:
                        continue

                    cat_name = category_names.get(cat_id, cat_id)
                    md_content += f"## {cat_name}\n\n"

                    for item in categories[cat_id]:
                        md_content += f"### [{item.title}]({item.url})\n"
                        md_content += f"- 来源: {item.source}\n"
                        if item.summary:
                             # Clean summary of HTML if any
                             clean_summary = re.sub(r'<[^>]+>', '', item.summary).strip()
                             md_content += f"- 摘要: {clean_summary}\n"
                        md_content += "\n"

                doc_url = await publisher.publish(title, md_content)
                if doc_url:
                    print(f"   Document available at: {doc_url}")

                # Publish to Feishu Bot (Push)
                bot_config = publishers_config.get("feishu_bot", {})
                if bot_config.get("enabled", False):
                    chat_id_str = bot_config.get("chat_id") or os.environ.get("FEISHU_BOT_CHAT_ID")
                    if chat_id_str:
                        # Support multiple chat IDs separated by comma
                        chat_ids = [cid.strip() for cid in chat_id_str.split(',') if cid.strip()]

                        if chat_ids:
                            print(f"\n🤖 Pushing to {len(chat_ids)} Feishu Bot Group(s)...")
                            for cid in chat_ids:
                                # Pass categories and category_names to build the card
                                await publisher.send_digest_card(cid, title, highlights, categories, category_names)
                        else:
                            print("   ⚠️ Feishu bot enabled but no valid chat IDs found")
                    else:
                        print("   ⚠️ Feishu bot enabled but FEISHU_BOT_CHAT_ID not set")
            else:
                print("   ⚠️ Feishu publisher enabled but credentials not found (FEISHU_APP_ID/SECRET)")

        return 0
    else:
        print("\n❌ Failed to send email. Check SMTP configuration.")
        return 1


def main():
    """Wrapper for async main."""
    sys.exit(asyncio.run(main_async()))


if __name__ == "__main__":
    sys.exit(main())

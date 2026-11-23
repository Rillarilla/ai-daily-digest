#!/usr/bin/env python3
"""
AI Daily Digest - Main entry point.

Collects AI news from multiple sources, summarizes with Gemini,
and publishes a PDF digest to Feishu.
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
    collect_waytoagi,
    NewsItem,
)
from processors import GeminiSummarizer, process_items
from email_sender import EmailSender, WEASYPRINT_AVAILABLE
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

    # WayToAGI daily knowledge base
    if config.get("waytoagi", {}).get("enabled", True):
        tasks.append(collect_waytoagi(config.get("waytoagi", {})))

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

    # Initialize summarizer (service account file or GOOGLE_SA_JSON env var)
    highlights = ""
    sa_file = Path(__file__).parent / "transsion-sw-cd-6610d5d50199.json"
    sa_available = sa_file.exists() or os.environ.get("GOOGLE_SA_JSON")

    if sa_available:
        print("🧠 Initializing Gemini AI (Vertex AI)...")
        try:
            sa_path = str(sa_file) if sa_file.exists() else None
            summarizer = GeminiSummarizer(service_account_file=sa_path)

            # Semantic dedup BEFORE translation (saves API calls)
            print("🔍 Semantic deduplication...")
            categories = await summarizer.semantic_deduplicate(categories)
            total_items = sum(len(items) for items in categories.values())
            print(f"   After dedup: {total_items} items\n")

            # Translate items in each category
            for cat_name, items in categories.items():
                valid_items, _ = await summarizer.process_and_filter_items(items)
                categories[cat_name] = valid_items

            # 移除处理后为空的分类
            categories = {k: v for k, v in categories.items() if v}

            # Generate highlights
            print("✨ Generating daily highlights...")
            highlights = await summarizer.generate_daily_highlights(categories, category_names)
            print("   Highlights generated\n")
        except Exception as e:
            print(f"   AI error: {e}\n")
    else:
        print("⚠️  Service account not found (no file or GOOGLE_SA_JSON), skipping AI processing\n")

    publishers_config = config.get("publishers", {})
    feishu_config = publishers_config.get("feishu", {})
    bot_config = publishers_config.get("feishu_bot", {})
    if not feishu_config.get("enabled") or not bot_config.get("enabled"):
        print("Feishu bot delivery is disabled. Use generate_preview.py for a local preview.")
        return 1

    publisher = FeishuPublisher()
    if not publisher.is_configured():
        print("Feishu credentials not configured (FEISHU_APP_ID/SECRET).")
        return 1

    chat_id_str = bot_config.get("chat_id") or os.environ.get("FEISHU_BOT_CHAT_ID", "")
    chat_ids = [cid.strip() for cid in chat_id_str.split(",") if cid.strip()]
    if not chat_ids:
        print("Feishu delivery has no valid chat IDs (FEISHU_BOT_CHAT_ID).")
        return 1

    date_str = datetime.now().strftime("%Y-%m-%d")
    title = feishu_config.get("title_format", "AI Daily Digest - {date}").format(date=date_str)
    doc_url = None

    if WEASYPRINT_AVAILABLE:
        renderer = EmailSender()
        html_content = renderer.render_email(categories, category_names, highlights)
        pdf_dir = Path(__file__).parent / "output"
        pdf_dir.mkdir(exist_ok=True)
        pdf_path = str(pdf_dir / f"AI_Daily_Digest_{date_str}.pdf")
        if renderer.generate_pdf(html_content, pdf_path):
            doc_url = await publisher.upload_pdf(pdf_path, title, chat_ids[0])

    if doc_url:
        print(f"   PDF available at: {doc_url}")
    else:
        print("   Feishu PDF not available; sending the summary card without a PDF link.")

    print(f"\n🤖 Pushing to {len(chat_ids)} Feishu Bot Group(s)...")
    sent = 0
    for cid in chat_ids:
        if await publisher.send_digest_card(cid, title, highlights, categories, category_names, doc_url):
            sent += 1

    print("\n🧹 Checking for old documents to clean up...")
    await publisher.cleanup_old_documents()

    if sent != len(chat_ids):
        print(f"Feishu delivered to {sent}/{len(chat_ids)} groups.")
        return 1

    print("\n✅ Daily digest completed!")
    return 0


def main():
    """Wrapper for async main."""
    sys.exit(asyncio.run(main_async()))


if __name__ == "__main__":
    sys.exit(main())

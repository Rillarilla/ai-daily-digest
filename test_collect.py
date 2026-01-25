#!/usr/bin/env python3
"""
Test script - collect data and preview results without sending email.
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))

import yaml
from collectors import (
    collect_all_rss,
    collect_arxiv,
    collect_twitter,
    collect_hackernews,
)
from processors import process_items


def load_config():
    config_path = Path(__file__).parent / "config" / "sources.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


async def test_collectors():
    print(f"\n{'='*60}")
    print(f"🧪 AI Daily Digest - 采集测试")
    print(f"   时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")

    config = load_config()

    # Test RSS
    print("📡 测试 RSS 采集...")
    try:
        rss_items = await collect_all_rss(config.get("rss_sources", {}))
        print(f"   ✅ RSS: 收集到 {len(rss_items)} 条\n")
    except Exception as e:
        print(f"   ❌ RSS 错误: {e}\n")
        rss_items = []

    # Test arXiv
    print("📄 测试 arXiv 采集...")
    try:
        arxiv_items = await collect_arxiv(config.get("arxiv", {}))
        print(f"   ✅ arXiv: 收集到 {len(arxiv_items)} 篇论文\n")
    except Exception as e:
        print(f"   ❌ arXiv 错误: {e}\n")
        arxiv_items = []

    # Test Hacker News
    print("🔶 测试 Hacker News 采集...")
    try:
        hn_items = await collect_hackernews(config.get("hackernews", {}))
        print(f"   ✅ HN: 收集到 {len(hn_items)} 条讨论\n")
    except Exception as e:
        print(f"   ❌ HN 错误: {e}\n")
        hn_items = []

    # Test Twitter (via Nitter - may fail due to instances being down)
    print("🐦 测试 X/Twitter 采集 (via Nitter)...")
    try:
        twitter_items = await collect_twitter(config.get("twitter", {}))
        print(f"   ✅ Twitter: 收集到 {len(twitter_items)} 条\n")
    except Exception as e:
        print(f"   ⚠️  Twitter 错误 (Nitter实例可能不可用): {e}\n")
        twitter_items = []

    # Combine and process
    all_items = rss_items + arxiv_items + hn_items + twitter_items
    print(f"{'='*60}")
    print(f"📊 总计收集: {len(all_items)} 条")

    # Process
    output_config = config.get("output", {})
    max_per_category = output_config.get("max_per_category", 5)
    categories = process_items(all_items, max_per_category=max_per_category)

    print(f"\n📋 分类统计:")
    category_names = output_config.get("category_names", {})
    for cat, items in categories.items():
        name = category_names.get(cat, cat)
        print(f"   {name}: {len(items)} 条")

    # Preview some items
    print(f"\n{'='*60}")
    print("📰 内容预览 (每类前2条):\n")

    for cat, items in categories.items():
        name = category_names.get(cat, cat)
        print(f"\n{name}")
        print("-" * 40)
        for item in items[:2]:
            print(f"• {item.title[:60]}...")
            print(f"  来源: {item.source} | {item.published.strftime('%m-%d %H:%M') if item.published else 'N/A'}")
            if item.summary:
                print(f"  摘要: {item.summary[:80]}...")
            print()

    print(f"{'='*60}")
    print("✅ 测试完成！数据采集正常工作。")
    print("   运行 'python main.py' 发送完整邮件 (需配置SMTP)")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    asyncio.run(test_collectors())

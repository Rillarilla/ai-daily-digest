#!/usr/bin/env python3
"""
Generate email preview HTML file (no email sending).
"""

import asyncio
import sys
import os
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))

import yaml
from jinja2 import Environment, FileSystemLoader

from collectors import (
    collect_all_rss,
    collect_arxiv,
    collect_twitter,
    collect_hackernews,
)
from processors import process_items, GeminiSummarizer


def load_config():
    config_path = Path(__file__).parent / "config" / "sources.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


async def generate_preview():
    print("📡 Collecting data...")
    config = load_config()

    # Collect
    tasks = [
        collect_all_rss(config.get("rss_sources", {})),
        collect_arxiv(config.get("arxiv", {})),
        collect_hackernews(config.get("hackernews", {})),
        collect_twitter(config.get("twitter", {})),
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    all_items = []
    for result in results:
        if isinstance(result, list):
            all_items.extend(result)

    print(f"   Collected {len(all_items)} items")

    # Process
    output_config = config.get("output", {})
    category_names = output_config.get("category_names", {})
    categories = process_items(all_items, max_per_category=5)

    # Render template
    template_dir = Path(__file__).parent / "templates"
    jinja_env = Environment(loader=FileSystemLoader(template_dir))
    template = jinja_env.get_template("email.html")

    item_count = sum(len(items) for items in categories.values())

    # Mock highlights (fallback)
    highlights = """1. TechCrunch 报道 Motional 将在2025年于拉斯维加斯推出无人驾驶 robotaxi 服务，重心转向 AI 驱动的技术架构
2. Google 针对特定医疗查询移除了 AI Overviews 功能，此前被曝出提供误导性健康信息
3. arXiv 最新论文聚焦图神经网络训练和大模型集成解码技术
4. 36氪：智谱单日涨幅超31%，国内大模型概念股活跃
5. 印度信实工业宣布776亿美元投资计划，将建设印度最大 AI 数据中心"""

    # Try to generate real highlights and process items if API key is present
    api_key = os.environ.get("GEMINI_API_KEY")
    if api_key:
        print("\n✨ GEMINI_API_KEY found, processing items and generating real highlights...")
        try:
            summarizer = GeminiSummarizer(api_key=api_key)

            # Translate and filter items in each category
            for cat_name, items in categories.items():
                valid_items, _ = await summarizer.process_and_filter_items(items)
                categories[cat_name] = valid_items

            # Recount items after filtering
            item_count = sum(len(items) for items in categories.values())

            # Note: We are passing translated/filtered items here.
            generated_highlights = await summarizer.generate_daily_highlights(categories, category_names)
            if generated_highlights:
                highlights = generated_highlights
        except Exception as e:
            print(f"⚠️ Failed to process/generate highlights: {e}")
            print("   Using fallback mock highlights.")

    html = template.render(
        date=datetime.now().strftime("%Y年%m月%d日"),
        item_count=item_count,
        highlights=highlights,
        categories=categories,
        category_names=category_names,
    )

    # Save preview
    output_path = Path(__file__).parent / "email_preview.html"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"\n✅ Email preview generated: {output_path}")
    print("   Open this file in browser to see the email design")


if __name__ == "__main__":
    asyncio.run(generate_preview())

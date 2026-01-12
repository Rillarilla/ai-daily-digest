"""
Gemini-based summarizer for news items.
"""

import os
from typing import Optional
import google.generativeai as genai
from collectors.base import NewsItem


class GeminiSummarizer:
    """Use Gemini to summarize and highlight key news."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY not set")
        genai.configure(api_key=self.api_key)
        self.model = genai.GenerativeModel("gemini-2.0-flash")

    def summarize_item(self, item: NewsItem) -> str:
        """Generate a concise summary for a single news item."""
        if item.summary and len(item.summary) < 150:
            return item.summary

        prompt = f"""请用1-2句中文简洁概括这条新闻的核心内容，突出最重要的信息点：

标题：{item.title}
来源：{item.source}
内容：{item.summary or item.content or '无'}

要求：
- 用中文回复
- 1-2句话，不超过100字
- 提取最有价值的信息
- 不要说"这篇文章讲述了..."这类开头"""

        try:
            response = self.model.generate_content(prompt)
            return response.text.strip()
        except Exception as e:
            print(f"Summarize error: {e}")
            return item.summary or ""

    def generate_daily_highlights(
        self,
        items_by_category: dict[str, list[NewsItem]],
        category_names: dict[str, str]
    ) -> str:
        """Generate overall daily highlights summary."""

        # Prepare content for Gemini
        content_parts = []
        for category, items in items_by_category.items():
            cat_name = category_names.get(category, category)
            content_parts.append(f"\n## {cat_name}")
            for item in items[:5]:
                content_parts.append(f"- {item.title} ({item.source})")

        all_content = "\n".join(content_parts)

        prompt = f"""作为AI行业分析师，请根据今日收集的AI新闻，撰写一段"今日要点"摘要。

今日新闻列表：
{all_content}

要求：
1. 用中文撰写
2. 3-5个要点，用数字编号
3. 每个要点1-2句话
4. 突出最重要、最具影响力的动态
5. 如果有重大发布/融资/突破，优先提及
6. 风格：专业但易读，像给同事的早间简报"""

        try:
            response = self.model.generate_content(prompt)
            return response.text.strip()
        except Exception as e:
            print(f"Highlights error: {e}")
            return "今日AI动态收集完成，请查看下方详情。"

    def batch_summarize(
        self,
        items: list[NewsItem],
        max_items: int = 20
    ) -> list[NewsItem]:
        """Batch summarize multiple items (for efficiency)."""
        # For now, just summarize items without existing good summaries
        for item in items[:max_items]:
            if not item.summary or len(item.summary) > 300:
                item.summary = self.summarize_item(item)
        return items


# Alias for backward compatibility
ClaudeSummarizer = GeminiSummarizer

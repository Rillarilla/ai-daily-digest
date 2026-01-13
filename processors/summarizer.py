"""
Gemini-based summarizer for news items with translation support.
"""

import os
import re
from typing import Optional
import google.generativeai as genai
from collectors.base import NewsItem


def is_english(text: str) -> bool:
    """检查文本是否主要是英文。"""
    if not text:
        return False
    # 统计ASCII字母占比
    ascii_letters = sum(1 for c in text if c.isascii() and c.isalpha())
    total_letters = sum(1 for c in text if c.isalpha())
    if total_letters == 0:
        return False
    return ascii_letters / total_letters > 0.7


class GeminiSummarizer:
    """Use Gemini to summarize, translate and highlight key news."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY not set")
        genai.configure(api_key=self.api_key)
        self.model = genai.GenerativeModel("gemini-2.0-flash")

    def translate_to_chinese(self, text: str) -> str:
        """将英文文本翻译成中文。"""
        if not text or not is_english(text):
            return text

        prompt = f"""请将以下英文内容翻译成简洁的中文：

{text}

要求：
- 保持原意，译文流畅自然
- 专业术语保留英文（如：GPT、LLM、Transformer等）
- 不要添加任何解释或额外内容
- 直接返回翻译结果"""

        try:
            response = self.model.generate_content(prompt)
            return response.text.strip()
        except Exception as e:
            print(f"Translation error: {e}")
            return text

    def summarize_and_translate(self, item: NewsItem) -> tuple[str, str, bool]:
        """生成摘要并翻译标题和内容。返回 (标题, 摘要, 是否已翻译)。"""
        title = item.title
        summary = item.summary or ""
        is_translated = False

        # 如果是英文内容，翻译标题和摘要
        if is_english(title) or is_english(summary):
            prompt = f"""请将以下新闻翻译成中文，并生成简洁摘要：

标题：{item.title}
来源：{item.source}
内容：{item.summary or item.content or '无'}

请按以下格式返回（每行一个，不要标签）：
翻译后的标题
一句话中文摘要（不超过80字）"""

            try:
                response = self.model.generate_content(prompt)
                lines = response.text.strip().split('\n')
                if len(lines) >= 2:
                    title = lines[0].strip()
                    summary = lines[1].strip()
                    is_translated = True
            except Exception as e:
                print(f"Translate & summarize error: {e}")

        # 如果是中文但没有好的摘要，生成摘要
        elif not summary or len(summary) > 200:
            summary = self.summarize_item(item)

        return title, summary, is_translated

    def summarize_item(self, item: NewsItem) -> str:
        """Generate a concise summary for a single news item."""
        if item.summary and len(item.summary) < 150 and not is_english(item.summary):
            return item.summary

        prompt = f"""请用1-2句中文简洁概括这条新闻的核心内容：

标题：{item.title}
来源：{item.source}
内容：{item.summary or item.content or '无'}

要求：
- 用中文回复
- 1-2句话，不超过80字
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
        """Generate overall daily highlights summary with HTML formatting."""

        # Prepare content for Gemini
        content_parts = []
        for category, items in items_by_category.items():
            cat_name = category_names.get(category, category)
            content_parts.append(f"\n## {cat_name}")
            for item in items[:5]:
                content_parts.append(f"- {item.title} ({item.source})")

        all_content = "\n".join(content_parts)

        prompt = f"""作为AI行业分析师，请根据今日收集的AI新闻，撰写"今日要点"摘要。

今日新闻列表：
{all_content}

要求：
1. 用中文撰写
2. 3-5个要点
3. 每个要点1-2句话，独立成段
4. 突出最重要、最具影响力的动态
5. 如果有重大发布/融资/突破，优先提及
6. 风格：专业但易读，像给同事的早间简报

请按以下格式输出（每个要点独立一段，用数字开头）：
1. 第一个要点内容...

2. 第二个要点内容...

3. 第三个要点内容..."""

        try:
            response = self.model.generate_content(prompt)
            raw_text = response.text.strip()
            # 转换为HTML格式，每个要点变成独立的div块
            return self._format_highlights_html(raw_text)
        except Exception as e:
            print(f"Highlights error: {e}")
            return "今日AI动态收集完成，请查看下方详情。"

    def _format_highlights_html(self, text: str) -> str:
        """将要点文本转换为HTML格式。"""
        # 按数字分割要点
        pattern = r'(\d+)[.、．]\s*'
        parts = re.split(pattern, text)

        html_parts = []
        i = 1
        while i < len(parts):
            if parts[i].isdigit():
                number = parts[i]
                content = parts[i + 1].strip() if i + 1 < len(parts) else ""
                if content:
                    html_parts.append(
                        f'<div class="highlight-item">'
                        f'<span class="highlight-number">{number}</span>'
                        f'<span class="highlight-text">{content}</span>'
                        f'</div>'
                    )
                i += 2
            else:
                i += 1

        if html_parts:
            return '\n'.join(html_parts)
        else:
            # 如果解析失败，返回原文本
            return f'<div class="highlight-item"><span class="highlight-text">{text}</span></div>'

    def process_items_with_translation(
        self,
        items: list[NewsItem],
        max_items: int = 30
    ) -> list[NewsItem]:
        """处理新闻项：翻译英文内容并生成摘要。"""
        for item in items[:max_items]:
            title, summary, is_translated = self.summarize_and_translate(item)
            item.title = title
            item.summary = summary
            # 添加翻译标记
            item.is_translated = is_translated
        return items

    def batch_summarize(
        self,
        items: list[NewsItem],
        max_items: int = 20
    ) -> list[NewsItem]:
        """Batch summarize multiple items (for efficiency)."""
        return self.process_items_with_translation(items, max_items)


# Alias for backward compatibility
ClaudeSummarizer = GeminiSummarizer

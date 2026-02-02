"""
Gemini-based summarizer for news items with translation support.
"""

import os
import re
import asyncio
from typing import Optional
import google.generativeai as genai
from collectors.base import NewsItem


def is_english(text: str) -> bool:
    """检查文本是否主要是英文。"""
    if not text:
        return False

    # 优先检查是否包含一定比例的中文字符
    # 统计中文字符 (\u4e00-\u9fff)
    chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    total_chars = len(text)

    if total_chars > 0 and (chinese_chars / total_chars) > 0.05:
        # 如果中文字符占比超过5%，认为是中文
        return False

    # 统计ASCII字母占比 (用于区分英文和其他非中文语言)
    ascii_letters = sum(1 for c in text if c.isascii() and c.isalpha())
    total_letters = sum(1 for c in text if c.isalpha())
    if total_letters == 0:
        return False
    return ascii_letters / total_letters > 0.7


class GeminiSummarizer:
    """Use Gemini to summarize, translate and highlight key news."""

    def __init__(self, api_key: Optional[str] = None, model: str = "gemini-2.0-flash"):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        if not self.api_key:
            # Fallback to specific GEMINI key if passed or env var
            self.api_key = os.environ.get("GEMINI_API_KEY")

        if not self.api_key:
            raise ValueError("GEMINI_API_KEY not set. Please set GEMINI_API_KEY in your environment.")

        genai.configure(api_key=self.api_key)
        self.model = genai.GenerativeModel(model)
        # Limit concurrent requests to avoid rate limits
        self.semaphore = asyncio.Semaphore(5)

    async def translate_to_chinese(self, text: str) -> str:
        """将英文文本翻译成中文。"""
        if not text:
            return ""

        # 简单长度检查，如果太短可能不需要翻译或API开销不值得
        if len(text) < 5:
            return text

        prompt = f"""You are a professional translator. Translate the following text to Simplified Chinese (简体中文).

Text:
{text}

Requirements:
- Output ONLY the translated text.
- No explanations, no quotes.
- Keep technical terms in English (e.g. LLM, GPT, Transformer).
- Keep it concise."""

        try:
            async with self.semaphore:
                response = await self.model.generate_content_async(prompt)
            return response.text.strip()
        except Exception as e:
            print(f"Translation error: {e}")
            return text

    async def summarize_and_translate(self, item: NewsItem) -> tuple[str, str, bool]:
        """生成摘要并翻译标题和内容。返回 (标题, 摘要, 是否已翻译)。"""
        title = item.title
        summary = item.summary or ""
        is_translated = False

        # 优先使用完整内容进行总结
        content_to_summarize = item.content if item.content and len(item.content) > len(item.summary or "") else (item.summary or "无")

        # 限制输入长度，避免token溢出
        if len(content_to_summarize) > 10000:
             content_to_summarize = content_to_summarize[:10000] + "..."

        prompt = f"""Analyze this news item and write a summary in Simplified Chinese.

Title: {item.title}
Source: {item.source}
Content: {content_to_summarize}

Task:
1. **Filter**: Is this related to AI, LLMs, Machine Learning, or Tech Industry?
   - If NOT related (e.g. general politics, crime, sports), OR if content is empty/meaningless, return "IRRELEVANT".
2. **Summarize**: Write a concise summary in **Simplified Chinese (简体中文)**.
   - **Do NOT include** prefixes like "AI: YES", "AI相关", or "Based on title".
   - **Do NOT include** English explanations.
   - If content is empty but title is informative, summarize based on title.
   - Length: **50-100 words** (strictly < 200 characters).

Format:
Line 1: [Chinese Title]
Line 2: [Chinese Summary]

Example Output:
OpenAI发布GPT-5预览版
OpenAI今日发布了GPT-5预览版，性能较上一代提升3倍。新模型支持实时语音对话，推理成本降低50%。
"""

        try:
            async with self.semaphore:
                response = await self.model.generate_content_async(prompt)
            lines = response.text.strip().split('\n')

            # Check for IRRELEVANT response
            if len(lines) > 0 and "IRRELEVANT" in lines[0].upper():
                title = item.title
                summary = "IRRELEVANT"
                is_translated = False
            elif len(lines) >= 2:
                # 清理可能的前缀
                raw_title = lines[0].strip()
                title = re.sub(r'^(中文)?标题[:：]\s*', '', raw_title).strip()
                # Remove markdown bold/italic
                title = title.replace('**', '').replace('*', '')

                # 剩下的部分作为摘要，可能有换行
                raw_summary = "\n".join(lines[1:]).strip()
                summary = re.sub(r'^摘要[:：]\s*', '', raw_summary).strip()

                # 检查摘要是否包含无效内容
                if "request result" in summary.lower() or "javascript is disabled" in summary.lower():
                     summary = "暂无详细内容"

                # 强制中文检查 (简单)
                if is_english(summary) and len(summary) > 20:
                     # Gemini ignored instruction, try simple translation
                     summary = await self.translate_to_chinese(summary)

                is_translated = True
            else:
                # Fallback format
                if is_english(response.text):
                     summary = await self.translate_to_chinese(response.text)
                else:
                     summary = response.text.strip()
                is_translated = False

        except Exception as e:
            print(f"Translate & summarize error for '{item.title[:20]}...': {e}")
            # Fallback: Just translate the original summary if it exists
            if item.summary and is_english(item.summary):
                 summary = await self.translate_to_chinese(item.summary)
            else:
                 summary = item.summary or ""

        # Final Length Check
        if summary and len(summary) > 300:
            summary = summary[:297] + "..."

        return title, summary, is_translated

    async def summarize_item(self, item: NewsItem) -> str:
        """Generate a concise summary for a single news item (Chinese content)."""
        content_to_summarize = item.content if item.content and len(item.content) > len(item.summary or "") else (item.summary or "无")

        if len(content_to_summarize) > 10000:
             content_to_summarize = content_to_summarize[:10000] + "..."

        prompt = f"""Summarize this news in Simplified Chinese.

Title: {item.title}
Source: {item.source}
Content: {content_to_summarize}

Task:
1. **Filter**: If not AI/Tech related, return "IRRELEVANT".
2. **Summarize**:
   - Language: **Simplified Chinese**.
   - Length: **50-100 words** (strictly < 200 characters).
   - Style: News brief.

Output ONLY the summary text. No prefixes."""

        try:
            async with self.semaphore:
                response = await self.model.generate_content_async(prompt)
            result = response.text.strip()
            result = result.replace('```', '').strip()
            result = re.sub(r'^(中文)?标题[:：]\s*', '', result)
            result = re.sub(r'^摘要[:：]\s*', '', result)

            if "IRRELEVANT" in result.upper():
                return "IRRELEVANT"

            # Final Length Check
            if len(result) > 300:
                result = result[:297] + "..."

            return result
        except Exception as e:
            print(f"Summarize error: {e}")
            return item.summary or ""

    async def generate_daily_highlights(
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
2. **只选择3条最抓人眼球、最重要的新闻**
3. 每个要点1-2句话，独立成段
4. **务必保证句子完整**，不要截断
5. 选择标准：重大发布、融资事件、技术突破、行业影响力
6. 风格：简洁有力，像新闻头条

请按以下格式输出（只要3条）：
1. 第一个要点（完整句子）。

2. 第二个要点（完整句子）。

3. 第三个要点（完整句子）。"""

        try:
            async with self.semaphore:
                response = await self.model.generate_content_async(prompt)
            raw_text = response.text.strip()
            # 转换为HTML格式，每个要点变成独立的div块
            return self._format_highlights_html(raw_text)
        except Exception as e:
            print(f"Highlights error: {e}")
            return "今日AI动态收集完成，请查看下方详情。"

    def _format_highlights_html(self, text: str) -> str:
        """将要点文本转换为HTML格式。"""
        html_parts = []

        # 尝试匹配数字列表 (1. xxx)
        pattern_num = r'(\d+)[.、．]\s*'
        parts_num = re.split(pattern_num, text)

        if len(parts_num) > 1:
            i = 1
            while i < len(parts_num):
                if parts_num[i].isdigit():
                    number = parts_num[i]
                    content = parts_num[i + 1].strip() if i + 1 < len(parts_num) else ""
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
        else:
            # 尝试匹配无序列表 (- xxx 或 * xxx)
            lines = text.split('\n')
            counter = 1
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                # 移除开头的 - 或 * 或 •
                clean_line = re.sub(r'^[-*•]\s*', '', line)
                if clean_line:
                    html_parts.append(
                        f'<div class="highlight-item">'
                        f'<span class="highlight-number">{counter}</span>'
                        f'<span class="highlight-text">{clean_line}</span>'
                        f'</div>'
                    )
                    counter += 1

        if html_parts:
            return '\n'.join(html_parts)
        else:
            # 如果解析失败，返回原文本
            return f'<div class="highlight-item"><span class="highlight-text">{text}</span></div>'

    async def process_items_with_translation(
        self,
        items: list[NewsItem],
        max_items: int = 30
    ) -> list[NewsItem]:
        """处理新闻项：翻译英文内容并生成摘要 (Parallel)."""
        tasks = []
        for item in items[:max_items]:
            tasks.append(self.summarize_and_translate(item))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        processed_items = []
        for i, result in enumerate(results):
            if isinstance(result, tuple):
                title, summary, is_translated = result
                item = items[i]
                item.title = title
                item.summary = summary
                item.is_translated = is_translated
                processed_items.append(item)
            elif isinstance(result, Exception):
                 print(f"Error processing item {items[i].title}: {result}")
                 processed_items.append(items[i]) # Keep original on error

        return processed_items

    async def process_and_filter_items(
        self,
        items: list[NewsItem],
        max_items: int = 30
    ) -> tuple[list[NewsItem], int]:
        """
        Process items with translation and filter out irrelevant content.
        Returns (valid_items, translated_count).
        """
        print(f"🌐 Translating {len(items)} items...")

        # Parallel processing
        tasks = []
        for item in items:
            tasks.append(self.summarize_and_translate(item))

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
        return valid_items, translated_count

    async def batch_summarize(
        self,
        items: list[NewsItem],
        max_items: int = 20
    ) -> list[NewsItem]:
        """Batch summarize multiple items (for efficiency)."""
        return await self.process_items_with_translation(items, max_items)

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
    """检查文本是否主要是英文（或非中文）。"""
    if not text:
        return False

    # 只要包含任意中文字符，就暂且认为是中文（为了容忍大量英文术语的情况）
    # 但如果中文字符极少（例如只有1-2个），可能只是误夹杂
    chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')

    # 如果没有中文字符，肯定是外语/英文
    if chinese_chars == 0:
        return True

    # 如果有中文，但占比极低 (<1%)，也视为英文 (可能是 "AI: YES" 这种)
    if len(text) > 0 and (chinese_chars / len(text)) < 0.01:
        return True

    return False


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

        prompt = f"""Analyze the following news item and return a JSON object.

Title: {item.title}
Source: {item.source}
Content: {content_to_summarize}

Task:
1. **Strict Filter**: Is this news primarily about **Artificial Intelligence (AI), LLMs, Machine Learning, or Generative AI**?
   - **MUST be relevant to AI**.
   - Set "is_relevant": false for:
     - General Tech news (e.g. new phones, generic cloud services, IT earnings).
     - Crypto / Blockchain / Web3.
     - General Politics / Policy (unless specifically about AI regulation).
     - Science / Space (unless AI is the core method).
2. **Summarize**: Write a concise summary in **Simplified Chinese (简体中文)**.
   - Length: 50-100 words.
   - Tone: Professional news brief.
   - **Important**: Do NOT include any prefixes like "AI: YES", "Title:", "Summary:". Just the raw content.

Return ONLY a valid JSON object with this structure:
{{
    "is_relevant": boolean,
    "title": "Translated Chinese Title (if original is English)",
    "summary": "Chinese Summary"
}}
"""

        try:
            async with self.semaphore:
                # Use generation_config to enforce JSON if supported, but prompt engineering usually works well
                response = await self.model.generate_content_async(prompt)

            text_response = response.text.strip()

            # Clean up potential markdown code blocks
            if text_response.startswith("```json"):
                text_response = text_response[7:]
            if text_response.startswith("```"):
                text_response = text_response[3:]
            if text_response.endswith("```"):
                text_response = text_response[:-3]

            import json
            try:
                data = json.loads(text_response.strip())

                # Check relevance
                if not data.get("is_relevant", True):
                    return item.title, "IRRELEVANT", False

                title = data.get("title", item.title).strip()
                summary = data.get("summary", "").strip()
                is_translated = True # JSON output means we processed it

                # Final sanity check for "AI: YES" in title/summary just in case
                title = re.sub(r'^AI[:：]\s*(YES|NO|Related).*?[:：]\s*', '', title, flags=re.IGNORECASE).strip()

                # 1. Fallback for empty summary
                if not summary:
                     if title:
                         summary = f"{title}（点击查看详情）"
                     else:
                         summary = "暂无详细摘要，请点击标题查看原文。"

                # 2. Force translation if still English (Double Insurance)
                if is_english(summary) and len(summary) > 10:
                    try:
                        summary = await self.translate_to_chinese(summary)
                    except Exception:
                        pass # Keep original if translation fails

                if is_english(title) and len(title) > 5:
                    try:
                        title = await self.translate_to_chinese(title)
                    except Exception:
                        pass

                return title, summary, is_translated

            except json.JSONDecodeError:
                print(f"JSON Parse Error for '{item.title}': {text_response[:50]}...")
                # Fallback to simple text extraction if JSON fails
                return item.title, "Summary generation failed (JSON Error)", False

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

        prompt = f"""Summarize the following news item and return a JSON object.

Title: {item.title}
Source: {item.source}
Content: {content_to_summarize}

Task:
1. **Strict Filter**: Is this news primarily about **Artificial Intelligence (AI), LLMs, Machine Learning, or Generative AI**?
   - Set "is_relevant": false for General Tech, Crypto, Politics, Science (unless AI-centric).
2. **Summarize**:
   - Language: **Simplified Chinese**.
   - Length: 50-100 words.
   - Style: News brief.

Return ONLY a valid JSON object:
{{
    "is_relevant": boolean,
    "summary": "Chinese Summary"
}}
"""

        try:
            async with self.semaphore:
                response = await self.model.generate_content_async(prompt)

            text_response = response.text.strip()
            # Clean up potential markdown code blocks
            if text_response.startswith("```json"):
                text_response = text_response[7:]
            if text_response.startswith("```"):
                text_response = text_response[3:]
            if text_response.endswith("```"):
                text_response = text_response[:-3]

            import json
            try:
                data = json.loads(text_response.strip())
                if not data.get("is_relevant", True):
                    return "IRRELEVANT"
                return data.get("summary", "").strip()
            except json.JSONDecodeError:
                # Fallback
                result = response.text.strip()
                result = result.replace('```', '').strip()
                if "IRRELEVANT" in result.upper():
                    return "IRRELEVANT"
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

        prompt = f"""作为AI行业分析师，请根据以下新闻列表，选出今日最重要的3条新闻要点。

News List:
{all_content}

Task:
1. Select exactly 3 most impactful AI news items (major releases, funding, breakthroughs).
2. Write a concise summary for each in **Simplified Chinese**.
3. **Important**: Return ONLY a valid JSON object. No other text.

Format:
{{
    "highlights": [
        "第一个要点（完整句子，中文）",
        "第二个要点（完整句子，中文）",
        "第三个要点（完整句子，中文）"
    ]
}}
"""

        try:
            async with self.semaphore:
                response = await self.model.generate_content_async(prompt)

            text_response = response.text.strip()
            # Clean up potential markdown code blocks
            if text_response.startswith("```json"):
                text_response = text_response[7:]
            if text_response.startswith("```"):
                text_response = text_response[3:]
            if text_response.endswith("```"):
                text_response = text_response[:-3]

            import json
            try:
                data = json.loads(text_response.strip())
                highlights_list = data.get("highlights", [])

                # Format as HTML
                html_parts = []
                for i, highlight in enumerate(highlights_list, 1):
                    # Final sanity check for prefixes
                    clean_highlight = re.sub(r'^(AI[:：]\s*(YES|NO|Related)|Title:|Summary:).*?[:：]\s*', '', highlight, flags=re.IGNORECASE).strip()
                    if clean_highlight:
                        html_parts.append(
                            f'<div class="highlight-item">'
                            f'<span class="highlight-number">{i}</span>'
                            f'<span class="highlight-text">{clean_highlight}</span>'
                            f'</div>'
                        )

                if html_parts:
                    return '\n'.join(html_parts)

            except json.JSONDecodeError:
                print(f"JSON Parse Error for highlights: {text_response[:50]}...")
                # Fallback to old text parsing
                return self._format_highlights_html(response.text.strip())

            return "今日AI动态收集完成，请查看下方详情。"

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

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

        # 如果是英文内容，翻译标题和摘要
        if is_english(title) or is_english(summary):
            # 优先使用完整内容进行总结
            content_to_summarize = item.content if item.content and len(item.content) > len(item.summary or "") else (item.summary or "无")

            prompt = f"""请阅读以下新闻，并用中文撰写一个详细的摘要：

标题：{item.title}
来源：{item.source}
内容：{content_to_summarize}

你的任务是：
1. **严格筛选**：这条新闻是否与**泛AI技术、产品、应用或行业动态**直接相关？
   - 关注：AI模型(LLM)、生成式AI(AIGC)、机器学习(ML)、AI硬件(GPU/芯片)、AI应用(如ChatGPT, Claude, Copilot)、自动驾驶、机器人等。
   - **过滤**：如果只是普通的科技、政治、社会新闻（如枪击案、税收政策、普通手机发布）且**没有核心AI技术成分**，请**直接返回 "IRRELEVANT"**。
2. **提取与总结**（如果相关）：
   - 用中文撰写，长度约100-150字。
   - 内容要详细，包含核心事实、数据、影响或关键结论。
   - 避免泛泛而谈，提取具体信息。

要求：
- 直接返回结果，不要包含任何前缀（如"中文标题："）。
- 格式：
  第一行：中文标题
  第二行开始：中文摘要
- 如果无关，仅返回 "IRRELEVANT"。"""

            try:
                async with self.semaphore:
                    response = await self.model.generate_content_async(prompt)
                lines = response.text.strip().split('\n')

                # Check for IRRELEVANT response
                if len(lines) > 0 and "IRRELEVANT" in lines[0]:
                    title = item.title
                    summary = "IRRELEVANT"
                    is_translated = False
                elif len(lines) >= 2:
                    # 清理可能的前缀
                    raw_title = lines[0].strip()
                    title = re.sub(r'^(中文)?标题[:：]\s*', '', raw_title).strip()

                    # 剩下的部分作为摘要，可能有换行
                    raw_summary = "\n".join(lines[1:]).strip()
                    summary = re.sub(r'^摘要[:：]\s*', '', raw_summary).strip()

                    # 检查摘要是否包含无效内容 (TechCrunch fix)
                    if "request result" in summary.lower() or "javascript is disabled" in summary.lower() or len(summary) < 10:
                        # 尝试回退到原始摘要的翻译
                        original_summary = item.summary or ""
                        if original_summary and len(original_summary) > 10:
                            summary = await self.translate_to_chinese(original_summary)
                        else:
                            summary = "暂无详细内容"

                    is_translated = True
                else:
                    # Fallback if format is unexpected but not irrelevant
                    title = item.title
                    summary = response.text.strip()
                    is_translated = False

            except Exception as e:
                print(f"Translate & summarize error: {e}")

        # 对于中文内容，或者未被翻译的英文内容，进行智能摘要和过滤（特别是针对36Kr等多条混合的情况）
        else:
            new_summary = await self.summarize_item(item)
            if new_summary:
                summary = new_summary

        return title, summary, is_translated

    async def summarize_item(self, item: NewsItem) -> str:
        """Generate a concise summary for a single news item, handling mixed content."""
        # 优先使用完整内容进行总结
        content_to_summarize = item.content if item.content and len(item.content) > len(item.summary or "") else (item.summary or "无")

        prompt = f"""请阅读以下新闻，这可能是一条包含多条快讯的汇总，也可能是一篇单独的文章。

标题：{item.title}
来源：{item.source}
内容：{content_to_summarize}

你的任务是：
1. **严格筛选**：这条新闻必须与**人工智能(AI)、大模型(LLM)、机器学习(ML)、生成式AI(AIGC)**直接相关。
   - 如果只是普通科技新闻（如手机发布、互联网八卦、普通融资）而没有明确的AI技术或应用核心，请**直接返回 "IRRELEVANT"**。
   - 即使提到了"智能"二字，如果不是AI技术相关的（如"智能家电"、"智能手机"），也算无关。
2. **提取与总结**：
   - 如果是**多条快讯汇总**：只提取与AI相关的条目。
   - 如果是**单篇文章**：生成100-150字的中文摘要。

要求：
- 直接返回摘要内容，**不要包含任何标题前缀**（如"中文标题："、"摘要："等）。
- 如果内容无关，仅返回 "IRRELEVANT"。"""

        try:
            async with self.semaphore:
                response = await self.model.generate_content_async(prompt)
            result = response.text.strip()
            # 移除可能的markdown引用块符号
            result = result.replace('```', '').strip()

            # 再次清理可能的前缀
            result = re.sub(r'^(中文)?标题[:：]\s*', '', result)
            result = re.sub(r'^摘要[:：]\s*', '', result)

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
2. 3-5个要点
3. 每个要点1-2句话，独立成段
4. **务必保证句子完整**，不要截断。
5. 突出最重要、最具影响力的动态
6. 风格：专业但易读，像给同事的早间简报

请按以下格式输出（每个要点独立一段，用数字开头）：
1. 第一个要点内容（完整句子）。

2. 第二个要点内容（完整句子）。

3. 第三个要点内容（完整句子）。"""

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

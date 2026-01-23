"""
arXiv paper collector - fetches latest AI/ML papers from top AI companies.
"""

import asyncio
from datetime import datetime
from typing import Optional
import aiohttp
import xml.etree.ElementTree as ET
from .base import BaseCollector, NewsItem


# 知名AI公司和研究机构的关键词 -> 显示名称映射
AI_COMPANIES_MAP = {
    # 美国科技巨头
    "openai": "OpenAI",
    "google": "Google",
    "deepmind": "DeepMind",
    "google deepmind": "DeepMind",
    "anthropic": "Anthropic",
    "meta": "Meta",
    "meta ai": "Meta AI",
    "facebook": "Meta",
    "microsoft": "Microsoft",
    "microsoft research": "Microsoft",
    "apple": "Apple",
    "amazon": "Amazon",
    "aws": "Amazon",
    "nvidia": "NVIDIA",
    # AI独角兽/创业公司
    "stability ai": "Stability AI",
    "stability": "Stability AI",
    "mistral": "Mistral AI",
    "cohere": "Cohere",
    "ai21": "AI21 Labs",
    "hugging face": "Hugging Face",
    "huggingface": "Hugging Face",
    "xai": "xAI",
    "inflection": "Inflection AI",
    "character.ai": "Character.AI",
    "adept": "Adept",
    "runway": "Runway",
    # 中国公司
    "baidu": "Baidu",
    "alibaba": "Alibaba",
    "tencent": "Tencent",
    "bytedance": "ByteDance",
    "zhipu": "智谱AI",
    "zhipu ai": "智谱AI",
    "智谱": "智谱AI",
    "moonshot": "月之暗面",
    "月之暗面": "月之暗面",
    "kimi": "月之暗面",
    "deepseek": "DeepSeek",
    "深度求索": "DeepSeek",
    "minimax": "MiniMax",
    "manus": "Manus",
    "stepfun": "阶跃星辰",
    "阶跃星辰": "阶跃星辰",
    "01.ai": "零一万物",
    "零一万物": "零一万物",
    "yi-": "零一万物",
    "baichuan": "百川智能",
    "百川智能": "百川智能",
    "sensetime": "商汤科技",
    "megvii": "旷视科技",
    # 顶尖大学/研究机构
    "stanford": "Stanford",
    "mit ": "MIT",
    "berkeley": "UC Berkeley",
    "cmu": "CMU",
    "carnegie mellon": "CMU",
    "harvard": "Harvard",
    "princeton": "Princeton",
    "oxford": "Oxford",
    "cambridge": "Cambridge",
    "eth zurich": "ETH Zurich",
    "tsinghua": "清华大学",
    "peking": "北京大学",
    "fair": "Meta FAIR",
    "bair": "UC Berkeley",
    "allen institute": "Allen Institute",
    "eleutherai": "EleutherAI",
    "shanghai ai": "上海AI实验室",
    "beijing academy": "北京智源",
    "chinese academy": "中国科学院",
}

# 用于匹配的模式列表
AFFILIATION_PATTERNS = list(AI_COMPANIES_MAP.keys())


class ArxivCollector(BaseCollector):
    """Collect papers from arXiv - filtered by top AI companies."""

    API_URL = "http://export.arxiv.org/api/query"

    def __init__(self, config: dict):
        super().__init__(config)
        self.categories = config.get("categories", ["cs.AI", "cs.LG"])
        self.max_results = config.get("max_results", 50)  # Fetch more to filter
        self.filter_companies = config.get("filter_companies", True)

    async def collect(self) -> list[NewsItem]:
        """Fetch latest papers from arXiv."""
        if not self.is_enabled():
            return []

        # Build query for multiple categories
        cat_query = " OR ".join([f"cat:{cat}" for cat in self.categories])
        query = f"({cat_query})"

        params = {
            "search_query": query,
            "start": 0,
            "max_results": self.max_results,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    self.API_URL,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status != 200:
                        print(f"[arXiv] HTTP {response.status}")
                        return []
                    content = await response.text()
        except Exception as e:
            print(f"[arXiv] Fetch error: {e}")
            return []

        items = self._parse_response(content)

        # 过滤只保留知名AI公司的论文，并添加机构标签
        if self.filter_companies:
            items = self._filter_and_tag_by_company(items)

        print(f"[arXiv] Collected {len(items)} papers from top AI companies")
        return items

    def _detect_organization(self, title: str, summary: str, authors: list[str]) -> Optional[str]:
        """检测论文来源机构，返回机构名称"""
        all_text = f"{title} {summary} {' '.join(authors)}".lower()

        # 按优先级匹配（先匹配大公司）
        priority_patterns = [
            "openai", "deepmind", "google deepmind", "anthropic", "meta ai",
            "microsoft", "nvidia", "deepseek", "moonshot", "zhipu",
            "mistral", "cohere", "stability"
        ]

        # 先检查高优先级
        for pattern in priority_patterns:
            if pattern in all_text:
                return AI_COMPANIES_MAP.get(pattern)

        # 再检查其他
        for pattern in AFFILIATION_PATTERNS:
            if pattern in all_text:
                return AI_COMPANIES_MAP.get(pattern)

        return None

    def _filter_and_tag_by_company(self, items: list[NewsItem]) -> list[NewsItem]:
        """过滤并为论文添加机构标签"""
        filtered = []
        for item in items:
            authors = item.author.split(", ") if item.author else []
            org = self._detect_organization(item.title, item.summary or "", authors)
            if org:
                item.organization = org
                filtered.append(item)
        return filtered

    def _parse_response(self, xml_content: str) -> list[NewsItem]:
        """Parse arXiv API XML response."""
        items = []

        # Define namespace
        ns = {
            "atom": "http://www.w3.org/2005/Atom",
            "arxiv": "http://arxiv.org/schemas/atom"
        }

        try:
            root = ET.fromstring(xml_content)
        except ET.ParseError as e:
            print(f"[arXiv] XML parse error: {e}")
            return []

        for entry in root.findall("atom:entry", ns):
            title = entry.find("atom:title", ns)
            title_text = title.text.strip().replace("\n", " ") if title is not None else ""

            summary = entry.find("atom:summary", ns)
            # Increase limit from 500 to 3000 to capture full abstract for LLM summarization
            summary_text = summary.text.strip().replace("\n", " ")[:3000] if summary is not None else ""

            # Get paper link (prefer abstract page)
            link = ""
            for link_elem in entry.findall("atom:link", ns):
                if link_elem.get("type") == "text/html":
                    link = link_elem.get("href", "")
                    break
                if not link:
                    link = link_elem.get("href", "")

            # Published date
            published_elem = entry.find("atom:published", ns)
            published = None
            if published_elem is not None:
                try:
                    published = datetime.fromisoformat(
                        published_elem.text.replace("Z", "+00:00")
                    )
                except:
                    pass

            # Authors (include affiliation if available)
            authors = []
            for author in entry.findall("atom:author", ns):
                name = author.find("atom:name", ns)
                affiliation = author.find("arxiv:affiliation", ns)
                if name is not None:
                    author_str = name.text
                    if affiliation is not None and affiliation.text:
                        author_str += f" ({affiliation.text})"
                    authors.append(author_str)

            author_str = ", ".join(authors[:3])
            if len(authors) > 3:
                author_str += f" et al. ({len(authors)} authors)"

            # Categories as tags
            tags = []
            for cat in entry.findall("atom:category", ns):
                term = cat.get("term")
                if term:
                    tags.append(term)

            item = NewsItem(
                title=title_text,
                url=link,
                source="arXiv",
                category="papers",
                published=published,
                summary=summary_text,
                author=author_str,
                tags=tags[:5],
            )
            items.append(item)

        return items


async def collect_arxiv(arxiv_config: dict) -> list[NewsItem]:
    """Collect from arXiv."""
    collector = ArxivCollector(arxiv_config)
    return await collector.collect()

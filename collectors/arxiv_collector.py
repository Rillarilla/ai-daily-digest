"""
arXiv paper collector - fetches latest AI/ML papers.
"""

import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional
import aiohttp
import xml.etree.ElementTree as ET
from .base import BaseCollector, NewsItem


class ArxivCollector(BaseCollector):
    """Collect papers from arXiv."""

    API_URL = "http://export.arxiv.org/api/query"

    def __init__(self, config: dict):
        super().__init__(config)
        self.categories = config.get("categories", ["cs.AI", "cs.LG"])
        self.max_results = config.get("max_results", 20)
        self.min_score = config.get("min_score", 0)

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
        print(f"[arXiv] Collected {len(items)} papers")
        return items

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
            summary_text = summary.text.strip().replace("\n", " ")[:500] if summary is not None else ""

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

            # Authors
            authors = []
            for author in entry.findall("atom:author", ns):
                name = author.find("atom:name", ns)
                if name is not None:
                    authors.append(name.text)
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

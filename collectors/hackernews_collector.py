"""
Hacker News collector for AI discussions.
"""

from datetime import datetime, timezone
import asyncio
import re
from datetime import datetime, timezone
import aiohttp
import feedparser
from bs4 import BeautifulSoup
from .base import BaseCollector, NewsItem


class HackerNewsCollector(BaseCollector):
    """Collect AI-related discussions from Hacker News."""

    def __init__(self, config: dict):
        super().__init__(config)
        self.feed_url = config.get(
            "url",
            "https://hnrss.org/newest?q=AI+OR+LLM+OR+GPT+OR+machine+learning"
        )
        self.min_points = config.get("min_points", 50)
        self.max_items = config.get("max_items", 10)

    async def _fetch_article_content(self, url: str) -> str:
        """Fetch and extract main text content from the article URL."""
        if not url or url.startswith("https://news.ycombinator.com"):
            return ""

        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=10) as response:
                    if response.status != 200:
                        return ""

                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')

                    # Remove scripts and styles
                    for script in soup(["script", "style", "nav", "footer", "header"]):
                        script.decompose()

                    # Extract text from paragraphs (simple heuristics)
                    paragraphs = soup.find_all('p')
                    text_content = "\n\n".join([p.get_text().strip() for p in paragraphs if len(p.get_text().strip()) > 50])

                    return text_content[:5000] # Limit content length
        except Exception as e:
            print(f"[HN] Content fetch error for {url}: {e}")
            return ""

    async def collect(self) -> list[NewsItem]:
        """Fetch HN discussions via hnrss.org."""
        if not self.is_enabled():
            return []

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    self.feed_url,
                    timeout=aiohttp.ClientTimeout(total=30),
                    headers={"User-Agent": "AI-Daily-Digest/1.0"}
                ) as response:
                    if response.status != 200:
                        print(f"[HN] HTTP {response.status}")
                        return []
                    content = await response.text()
        except Exception as e:
            print(f"[HN] Fetch error: {e}")
            return []

        feed = feedparser.parse(content)
        candidates = []

        # First pass: Filter and collect candidates
        for entry in feed.entries[:self.max_items * 3]: # Fetch more candidates
            title = entry.get("title", "")
            description = entry.get("description", "")

            # Parse points
            points = 0
            comments = 0
            if "points" in description.lower():
                import re
                points_match = re.search(r'points?:\s*(\d+)', description, re.IGNORECASE)
                if not points_match:
                    points_match = re.search(r'(\d+)\s*points?', description, re.IGNORECASE)
                if points_match:
                    points = int(points_match.group(1))

                comments_match = re.search(r'comments?:\s*(\d+)', description, re.IGNORECASE)
                if not comments_match:
                    comments_match = re.search(r'(\d+)\s*comments?', description, re.IGNORECASE)
                if comments_match:
                    comments = int(comments_match.group(1))

            if points < self.min_points:
                continue

            candidates.append({
                "entry": entry,
                "points": points,
                "comments": comments
            })

        # Sort by score and take top items
        candidates.sort(key=lambda x: x["points"], reverse=True)
        top_candidates = candidates[:self.max_items]

        # Fetch content for top candidates in parallel
        items = []
        fetch_tasks = []

        for cand in top_candidates:
            entry = cand["entry"]
            url = entry.get("link", "")
            fetch_tasks.append(self._fetch_article_content(url))

        # Wait for all fetches
        contents = await asyncio.gather(*fetch_tasks)

        for i, cand in enumerate(top_candidates):
            entry = cand["entry"]
            content_text = contents[i]

            published = None
            if entry.get("published_parsed"):
                try:
                    published = datetime(
                        *entry.published_parsed[:6],
                        tzinfo=timezone.utc
                    )
                except:
                    pass

            # Combine meta info with fetched content
            full_summary = f"Points: {cand['points']}, Comments: {cand['comments']}\n\nArticle Content:\n{content_text}"

            item = NewsItem(
                title=entry.get("title", ""),
                url=entry.get("link", ""),
                source="Hacker News",
                category="social",
                published=published,
                summary=full_summary, # Pass full content to summarizer
                content=content_text, # Also store in content field
                score=cand["points"],
            )
            items.append(item)

        print(f"[HN] Collected {len(items)} items with content")
        return items


async def collect_hackernews(hn_config: dict) -> list[NewsItem]:
    """Collect from Hacker News."""
    collector = HackerNewsCollector(hn_config)
    return await collector.collect()

"""
Hacker News collector for AI discussions.
"""

from datetime import datetime, timezone
import aiohttp
import feedparser
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
        items = []

        for entry in feed.entries[:self.max_items * 2]:
            title = entry.get("title", "")

            # Parse points from title if available (hnrss format)
            points = 0
            comments = 0

            # hnrss includes points in description
            description = entry.get("description", "")
            if "points" in description.lower():
                import re
                # Improved regex to handle "Points: 123" or "123 points"
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

            # Filter by minimum points
            if points < self.min_points:
                continue

            published = None
            if entry.get("published_parsed"):
                try:
                    published = datetime(
                        *entry.published_parsed[:6],
                        tzinfo=timezone.utc
                    )
                except:
                    pass

            item = NewsItem(
                title=title,
                url=entry.get("link", ""),
                source="Hacker News",
                category="social",
                published=published,
                summary=f"{points} points, {comments} comments",
                score=points,
            )
            items.append(item)

            if len(items) >= self.max_items:
                break

        # Sort by score
        items.sort(key=lambda x: x.score, reverse=True)
        print(f"[HN] Collected {len(items)} items")
        return items


async def collect_hackernews(hn_config: dict) -> list[NewsItem]:
    """Collect from Hacker News."""
    collector = HackerNewsCollector(hn_config)
    return await collector.collect()

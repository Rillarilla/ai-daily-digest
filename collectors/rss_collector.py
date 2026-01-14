"""
RSS feed collector - handles all RSS-based sources.
"""

import asyncio
import re
from datetime import datetime, timezone
from typing import Optional
import aiohttp
import feedparser
from .base import BaseCollector, NewsItem


class RSSCollector(BaseCollector):
    """Collect news from RSS feeds."""

    def __init__(self, source_id: str, source_config: dict):
        super().__init__(source_config)
        self.source_id = source_id
        self.feed_url = source_config["url"]
        self.source_name = source_config["name"]
        self.category = source_config.get("category", "general")
        self.keywords = source_config.get("keywords", [])
        self.max_items = source_config.get("max_items", 10)

    async def collect(self) -> list[NewsItem]:
        """Fetch and parse RSS feed."""
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
                        print(f"[{self.source_name}] HTTP {response.status}")
                        return []
                    content = await response.text()
        except Exception as e:
            print(f"[{self.source_name}] Fetch error: {e}")
            return []

        # Parse feed
        feed = feedparser.parse(content)
        items = []

        for entry in feed.entries[:self.max_items * 2]:  # Fetch extra for filtering
            title = entry.get("title", "")
            summary = entry.get("summary", entry.get("description", ""))

            # Apply keyword filter
            if not self.filter_by_keywords(f"{title} {summary}", self.keywords):
                continue

            # Parse publish date
            published = self._parse_date(entry)

            # Extract image URL
            image_url = self._extract_image(entry, summary)

            item = NewsItem(
                title=title,
                url=entry.get("link", ""),
                source=self.source_name,
                category=self.category,
                published=published,
                summary=self._clean_html(summary)[:500],
                author=entry.get("author"),
                tags=[tag.term for tag in entry.get("tags", [])][:5],
                image_url=image_url,
            )
            items.append(item)

            if len(items) >= self.max_items:
                break

        print(f"[{self.source_name}] Collected {len(items)} items")
        return items

    def _extract_image(self, entry, summary: str) -> Optional[str]:
        """从RSS条目中提取图片URL"""
        # 方法1: media:content 或 media:thumbnail
        if hasattr(entry, 'media_content') and entry.media_content:
            for media in entry.media_content:
                if media.get('type', '').startswith('image/') or media.get('medium') == 'image':
                    return media.get('url')

        if hasattr(entry, 'media_thumbnail') and entry.media_thumbnail:
            return entry.media_thumbnail[0].get('url')

        # 方法2: enclosure
        if hasattr(entry, 'enclosures') and entry.enclosures:
            for enc in entry.enclosures:
                if enc.get('type', '').startswith('image/'):
                    return enc.get('href') or enc.get('url')

        # 方法3: 从 content 中提取 <img> 标签
        content = entry.get('content', [{}])[0].get('value', '') if entry.get('content') else ''
        full_text = summary + content

        img_match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', full_text)
        if img_match:
            img_url = img_match.group(1)
            # 过滤掉太小的图片（通常是图标）
            if not any(x in img_url.lower() for x in ['icon', 'logo', 'avatar', '1x1', 'pixel']):
                return img_url

        # 方法4: image 字段
        if hasattr(entry, 'image') and entry.image:
            if isinstance(entry.image, dict):
                return entry.image.get('href') or entry.image.get('url')
            elif isinstance(entry.image, str):
                return entry.image

        return None

    def _parse_date(self, entry) -> Optional[datetime]:
        """Parse date from feed entry."""
        for date_field in ["published_parsed", "updated_parsed", "created_parsed"]:
            time_struct = entry.get(date_field)
            if time_struct:
                try:
                    return datetime(*time_struct[:6], tzinfo=timezone.utc)
                except:
                    pass
        return None

    def _clean_html(self, text: str) -> str:
        """Remove HTML tags from text."""
        clean = re.sub(r'<[^>]+>', '', text)
        clean = re.sub(r'\s+', ' ', clean).strip()
        return clean


async def collect_all_rss(rss_config: dict) -> list[NewsItem]:
    """Collect from all configured RSS sources."""
    collectors = []

    for source_id, source_config in rss_config.items():
        if source_config.get("enabled", True):
            collectors.append(RSSCollector(source_id, source_config))

    # Run all collectors concurrently
    tasks = [c.collect() for c in collectors]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    all_items = []
    for result in results:
        if isinstance(result, list):
            all_items.extend(result)
        elif isinstance(result, Exception):
            print(f"Collector error: {result}")

    return all_items

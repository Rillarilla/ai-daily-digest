"""
Twitter/X collector via Nitter and other alternatives.
"""

import asyncio
import random
from datetime import datetime, timezone
from typing import Optional
import aiohttp
import feedparser
from .base import BaseCollector, NewsItem


class TwitterCollector(BaseCollector):
    """Collect tweets via Nitter RSS or other alternatives."""

    def __init__(self, config: dict):
        super().__init__(config)
        self.method = config.get("method", "nitter")
        self.accounts = config.get("accounts", [])
        self.nitter_instances = config.get("nitter_instances", [
            "https://nitter.privacydev.net",
            "https://nitter.poast.org",
        ])
        self.search_terms = config.get("search_terms", [])

    async def collect(self) -> list[NewsItem]:
        """Collect tweets from configured accounts."""
        if not self.is_enabled():
            return []

        all_items = []

        # Try to collect from each account
        for account in self.accounts:
            items = await self._collect_account(account)
            all_items.extend(items)
            # Small delay to be nice to Nitter
            await asyncio.sleep(0.5)

        print(f"[Twitter/X] Collected {len(all_items)} items")
        return all_items

    async def _collect_account(self, account: dict) -> list[NewsItem]:
        """Collect tweets from a single account via Nitter RSS."""
        username = account.get("username", "")
        display_name = account.get("name", username)

        # Try each Nitter instance
        random.shuffle(self.nitter_instances)  # Randomize to distribute load

        for instance in self.nitter_instances:
            rss_url = f"{instance}/{username}/rss"
            items = await self._fetch_nitter_rss(rss_url, display_name)
            if items:
                return items

        return []

    async def _fetch_nitter_rss(
        self, url: str, source_name: str
    ) -> list[NewsItem]:
        """Fetch and parse Nitter RSS feed."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    timeout=aiohttp.ClientTimeout(total=15),
                    headers={"User-Agent": "AI-Daily-Digest/1.0"}
                ) as response:
                    if response.status != 200:
                        return []
                    content = await response.text()
        except Exception:
            return []

        feed = feedparser.parse(content)
        items = []

        for entry in feed.entries[:5]:  # Latest 5 tweets per account
            title = entry.get("title", "")
            if not title:
                continue

            # Clean up Nitter formatting
            title = self._clean_tweet(title)

            # Skip retweets unless significant
            if title.startswith("RT @"):
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
                title=title[:280],  # Truncate to tweet length
                url=entry.get("link", ""),
                source=f"@{source_name}" if not source_name.startswith("@") else source_name,
                category="social",
                published=published,
                summary=None,
                author=source_name,
            )
            items.append(item)

        return items

    def _clean_tweet(self, text: str) -> str:
        """Clean up tweet text."""
        import re
        # Remove pic.twitter links
        text = re.sub(r'pic\.twitter\.com/\S+', '', text)
        # Remove multiple spaces
        text = re.sub(r'\s+', ' ', text).strip()
        return text


async def collect_twitter(twitter_config: dict) -> list[NewsItem]:
    """Collect from Twitter/X."""
    collector = TwitterCollector(twitter_config)
    return await collector.collect()

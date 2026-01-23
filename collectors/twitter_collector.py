"""
Twitter/X collector via Nitter and other alternatives.
"""

import asyncio
import random
from datetime import datetime, timezone
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

        if self.method != "nitter":
            print(f"[Twitter] Warning: Method '{self.method}' is not fully supported. Defaulting to Nitter RSS logic.")

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
        instances = self.nitter_instances.copy()
        random.shuffle(instances)  # Randomize to distribute load

        for instance in instances:
            rss_url = f"{instance.rstrip('/')}/{username}/rss"
            items = await self._fetch_nitter_rss(rss_url, display_name)
            if items:
                return items

        print(f"[Twitter] Could not fetch updates for @{username} from any Nitter instance")
        return []

    async def _fetch_nitter_rss(
        self, url: str, source_name: str
    ) -> list[NewsItem]:
        """Fetch and parse Nitter RSS feed."""
        try:
            # Browser-like headers to avoid blocking
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "application/rss+xml,application/xml;q=0.9,*/*;q=0.8"
            }
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    timeout=aiohttp.ClientTimeout(total=10, connect=5),
                    headers=headers
                ) as response:
                    if response.status != 200:
                        # Silently fail for individual instances to avoid log spam
                        return []
                    content = await response.text()

                    if not content or "Rate limit exceeded" in content:
                        return []
        except Exception:
            # Silently fail for individual instances
            return []

        try:
            feed = feedparser.parse(content)
            if feed.get("bozo"):
                return []

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
        except Exception as e:
            print(f"[Twitter] Error parsing feed content: {e}")
            return []

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

"""
WayToAGI daily knowledge base collector.

Scrapes the public WayToAGI Feishu wiki:
https://waytoagi.feishu.cn/wiki/QPe5w5g7UisbEkkow8XcDmOpn8e

The wiki has a "近 7 日更新日志" section with daily article summaries.
Content is embedded as escaped JSON in the HTML (no login required).
"""

import json
import re
from datetime import datetime, timezone, timedelta
from typing import Optional
import aiohttp

from .base import BaseCollector, NewsItem

# The public Feishu wiki URL for WayToAGI daily updates
WIKI_URL = "https://waytoagi.feishu.cn/wiki/QPe5w5g7UisbEkkow8XcDmOpn8e"

# Regex: find mention_doc article blocks - captures wiki token and title
# Raw HTML uses \"raw_url\":\"URL\" with literal backslash-escaped quotes
ARTICLE_RE = re.compile(
    r'\\"raw_url\\":\\"https://waytoagi\.feishu\.cn/wiki/(\w+)'
    r'.{1,200}?\\"title\\":\\"([^\\"]+)\\"',
    re.DOTALL,
)

# Regex: find text block summaries - "《 》summary text"
# Text content uses regular (unescaped) JSON quotes in the HTML
SUMMARY_RE = re.compile(
    r'"text":\{"0":"[^》]*》([^"]{15,}?)"',
)

SCRIPT_RE = re.compile(r"<script[^>]*>(.*?)</script>", re.DOTALL)
CLIENT_VARS_RE = re.compile(
    r"clientVars:\s*Object\((\{.*\})\)\s*\}\s*\);\s*window\.docxSSREditable",
    re.DOTALL,
)
DATE_HEADING_RE = re.compile(r"\s*(\d{1,2}) 月 (\d{1,2}) 日\s*")


class WayToAGICollector(BaseCollector):
    """Collect daily AI knowledge base selections from WayToAGI Feishu wiki."""

    def __init__(self, config: dict):
        super().__init__(config)
        self.max_items = config.get("max_items", 10)

    async def collect(self) -> list[NewsItem]:
        if not self.is_enabled():
            return []

        html = await self._fetch_wiki()
        if not html:
            return []

        # Try today first, fall back up to 3 days (covers weekends/holidays)
        beijing_now = datetime.now(timezone(timedelta(hours=8)))
        for delta in range(4):
            date = beijing_now - timedelta(days=delta)
            items = self._parse_date(html, date)
            if items:
                print(
                    f"[WayToAGI] Collected {len(items)} items "
                    f"for {date.month}月{date.day}日 from Feishu wiki"
                )
                return items[: self.max_items]

        print("[WayToAGI] No content found in the last 4 days")
        return []

    async def _fetch_wiki(self):
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "zh-CN,zh;q=0.9",
        }
        # Feishu needs a guest session cookie set via the redirect chain before
        # it serves the full SSR HTML with embedded document blocks.
        # Strategy: use ONE persistent session across requests so cookies from
        # the first redirect are reused on the second (retry) request.
        try:
            async with aiohttp.ClientSession() as session:
                for attempt in range(3):
                    try:
                        async with session.get(
                            WIKI_URL,
                            headers=headers,
                            timeout=aiohttp.ClientTimeout(total=30),
                            allow_redirects=True,
                        ) as resp:
                            if resp.status != 200:
                                print(f"[WayToAGI] HTTP {resp.status}")
                                return None
                            html = await resp.text()
                            # Full HTML with embedded blocks is >800KB.
                            # Smaller response = JS-only shell, retry with cookies.
                            if len(html) > 800_000:
                                print(f"[WayToAGI] Fetched wiki ({len(html):,} bytes)")
                                return html
                            print(
                                f"[WayToAGI] Got stripped HTML ({len(html):,} bytes), "
                                f"retrying with session cookies ({attempt + 1}/3)..."
                            )
                    except Exception as e:
                        print(f"[WayToAGI] Fetch error (attempt {attempt + 1}): {e}")
        except Exception as e:
            print(f"[WayToAGI] Session error: {e}")
        return None

    def _date_heading(self, date: datetime) -> str:
        """Generate date heading text as it appears in the wiki HTML.

        Feishu renders '3月9日' as ' 3 月 9 日' with spaces.
        """
        return f" {date.month} 月 {date.day} 日"

    def _parse_date(self, html: str, date: datetime) -> list[NewsItem]:
        """Extract articles for a specific date from the wiki HTML."""
        items = self._parse_date_from_block_map(html, date)
        if items:
            return items

        return self._parse_date_legacy(html, date)

    def _parse_date_from_block_map(self, html: str, date: datetime) -> list[NewsItem]:
        """Parse Feishu's SSR block tree instead of relying on string slicing."""
        client_vars = self._extract_client_vars(html)
        if not client_vars:
            return []

        block_map = client_vars.get("data", {}).get("block_map", {})
        block_sequence = client_vars.get("data", {}).get("block_sequence", [])
        if not block_map or not block_sequence:
            return []

        target_heading = None
        for block_id in block_sequence:
            block = block_map.get(block_id, {}).get("data", {})
            if block.get("type") != "heading3":
                continue

            heading_text = self._extract_block_text(block)
            match = DATE_HEADING_RE.fullmatch(heading_text)
            if not match:
                continue

            month, day = int(match.group(1)), int(match.group(2))
            if month == date.month and day == date.day:
                target_heading = block
                break

        if not target_heading:
            return []

        pub_date = date.replace(
            hour=12, minute=0, second=0, microsecond=0,
            tzinfo=timezone(timedelta(hours=8)),
        )

        items = []
        seen = set()

        for child_id in target_heading.get("children", []):
            child = block_map.get(child_id, {}).get("data", {})
            if child.get("type") != "bullet":
                continue

            mention = self._extract_mention_doc(child)
            if not mention:
                continue

            token = mention.get("token", "").strip()
            title = mention.get("title", "").strip()
            raw_url = mention.get("raw_url", "").strip()

            if not token or not title or token in seen:
                continue
            seen.add(token)

            url = raw_url.split("?", 1)[0] if raw_url else f"https://waytoagi.feishu.cn/wiki/{token}"
            summary = self._clean_summary(self._extract_block_text(child))

            items.append(
                NewsItem(
                    title=title,
                    url=url,
                    source="WayToAGI",
                    category="china",
                    published=pub_date,
                    summary=summary,
                    tags=["知识库精选", "WayToAGI"],
                )
            )

        return items

    def _parse_date_legacy(self, html: str, date: datetime) -> list[NewsItem]:
        """Fallback parser for older HTML layouts."""
        date_heading = self._date_heading(date)

        # Find the start of this date's section
        date_idx = html.find(date_heading)
        if date_idx < 0:
            return []

        # Find the end: beginning of previous day's section
        prev_heading = self._date_heading(date - timedelta(days=1))
        end_idx = html.find(prev_heading, date_idx + len(date_heading))
        if end_idx < 0:
            end_idx = min(date_idx + 60_000, len(html))

        section = html[date_idx:end_idx]

        # Extract articles and summaries
        articles = list(ARTICLE_RE.finditer(section))
        summaries = [m.group(1) for m in SUMMARY_RE.finditer(section)]

        # Use noon Beijing time so the item survives the 24-hour UTC filter.
        # midnight+08:00 = previous day 16:00 UTC, easily falls outside window.
        pub_date = date.replace(
            hour=12, minute=0, second=0, microsecond=0,
            tzinfo=timezone(timedelta(hours=8)),
        )
        items = []
        seen = set()

        for i, m in enumerate(articles):
            token = m.group(1)
            title = m.group(2).strip()

            if not title or len(title) < 3 or token in seen:
                continue
            seen.add(token)

            url = f"https://waytoagi.feishu.cn/wiki/{token}"

            summary = self._clean_summary(summaries[i] if i < len(summaries) else None)

            items.append(
                NewsItem(
                    title=title,
                    url=url,
                    source="WayToAGI",
                    category="china",
                    published=pub_date,
                    summary=summary,
                    tags=["知识库精选", "WayToAGI"],
                )
            )

        return items

    def _extract_client_vars(self, html: str) -> Optional[dict]:
        """Extract Feishu's SSR payload from the page HTML."""
        for script in SCRIPT_RE.findall(html):
            if "window.DATA = Object.assign" not in script or "block_map" not in script:
                continue

            match = CLIENT_VARS_RE.search(script)
            if not match:
                continue

            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                continue

        return None

    def _extract_block_text(self, block: dict) -> str:
        """Read the plain text stored on a Feishu block."""
        return (
            block.get("text", {})
            .get("initialAttributedTexts", {})
            .get("text", {})
            .get("0", "")
        )

    def _extract_mention_doc(self, block: dict) -> Optional[dict]:
        """Read the linked document metadata from a bullet block."""
        apool = block.get("text", {}).get("apool", {}).get("numToAttrib", {})
        for attrib in apool.values():
            if not isinstance(attrib, list) or len(attrib) < 2:
                continue
            if attrib[0] != "inline-component":
                continue

            try:
                component = json.loads(attrib[1])
            except json.JSONDecodeError:
                continue

            if component.get("type") == "mention_doc":
                return component.get("data", {})

        return None

    def _clean_summary(self, summary: Optional[str]) -> Optional[str]:
        if not summary:
            return None

        summary = summary.replace("《 》", "", 1)
        summary = re.sub(r"\s+", " ", summary).strip()
        if len(summary) < 15:
            return None
        return summary


async def collect_waytoagi(config: dict) -> list[NewsItem]:
    """Convenience function to collect WayToAGI items."""
    collector = WayToAGICollector(config)
    return await collector.collect()

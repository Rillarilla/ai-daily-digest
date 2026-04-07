#!/usr/bin/env python3
"""
Regression tests for the WayToAGI collector.
"""

import json
import unittest
from datetime import datetime

from collectors.waytoagi_collector import WayToAGICollector


def make_bullet(block_id: str, token: str, title: str, summary: str) -> dict:
    component = json.dumps(
        {
            "id": f"{block_id}-mention",
            "type": "mention_doc",
            "data": {
                "file_type": 16,
                "icon_type": 22,
                "token": token,
                "tenant_id": "tenant",
                "raw_url": f"https://waytoagi.feishu.cn/wiki/{token}?from=from_copylink",
                "title": title,
            },
        },
        ensure_ascii=False,
    )
    return {
        "id": block_id,
        "version": 1,
        "data": {
            "type": "bullet",
            "parent_id": "heading-0406",
            "comments": [],
            "revisions": [],
            "locked": False,
            "hidden": False,
            "author": "author",
            "children": [],
            "text": {
                "apool": {
                    "nextNum": 3,
                    "numToAttrib": {
                        "0": ["author", "author"],
                        "1": ["inline-component", component],
                        "2": ["link-id", f"{block_id}-link"],
                    },
                },
                "initialAttributedTexts": {
                    "attribs": {"0": "*0+1*0*1*2+1*0+5"},
                    "text": {"0": f"《 》{summary}"},
                },
            },
            "align": "",
            "folded": False,
        },
    }


class WayToAGICollectorTest(unittest.TestCase):
    def setUp(self):
        self.collector = WayToAGICollector({"enabled": True, "max_items": 10})

        client_vars = {
            "data": {
                "block_sequence": [
                    "root",
                    "heading-0406",
                    "bullet-1",
                    "image-1",
                    "bullet-2",
                    "heading-0405",
                    "bullet-old",
                ],
                "block_map": {
                    "root": {
                        "id": "root",
                        "version": 1,
                        "data": {
                            "type": "page",
                            "children": ["heading-0406", "heading-0405"],
                        },
                    },
                    "heading-0406": {
                        "id": "heading-0406",
                        "version": 1,
                        "data": {
                            "type": "heading3",
                            "children": ["bullet-1", "image-1", "bullet-2"],
                            "text": {
                                "initialAttributedTexts": {
                                    "text": {"0": " 4 月 6 日"},
                                },
                            },
                        },
                    },
                    "image-1": {
                        "id": "image-1",
                        "version": 1,
                        "data": {
                            "type": "image",
                            "children": [],
                        },
                    },
                    "heading-0405": {
                        "id": "heading-0405",
                        "version": 1,
                        "data": {
                            "type": "heading3",
                            "children": ["bullet-old"],
                            "text": {
                                "initialAttributedTexts": {
                                    "text": {"0": " 4 月 5 日"},
                                },
                            },
                        },
                    },
                    "bullet-1": make_bullet(
                        "bullet-1",
                        "TOKEN_ONE",
                        "第一篇文章",
                        "这是第一篇文章的摘要，长度足够长。",
                    ),
                    "bullet-2": make_bullet(
                        "bullet-2",
                        "TOKEN_TWO",
                        "第二篇文章",
                        "这是第二篇文章的摘要，也足够长。",
                    ),
                    "bullet-old": make_bullet(
                        "bullet-old",
                        "TOKEN_OLD",
                        "前一天文章",
                        "这是前一天的摘要，不应该混进来。",
                    ),
                },
            },
            "code": 0,
            "message": "success",
            "mode": 7,
        }

        blob = json.dumps(client_vars, ensure_ascii=False)
        self.html = (
            "<html><body><script>"
            "window.DATA = Object.assign({}, window.DATA, { clientVars: Object("
            + blob
            + ") }); "
            "window.docxSSREditable = Boolean(false);"
            "</script></body></html>"
        )

    def test_parse_date_uses_block_tree_without_cross_day_mixups(self):
        items = self.collector._parse_date(self.html, datetime(2026, 4, 6))

        self.assertEqual([item.title for item in items], ["第一篇文章", "第二篇文章"])
        self.assertEqual(
            [item.url for item in items],
            [
                "https://waytoagi.feishu.cn/wiki/TOKEN_ONE",
                "https://waytoagi.feishu.cn/wiki/TOKEN_TWO",
            ],
        )
        self.assertEqual(items[0].summary, "这是第一篇文章的摘要，长度足够长。")
        self.assertEqual(items[1].summary, "这是第二篇文章的摘要，也足够长。")


if __name__ == "__main__":
    unittest.main()

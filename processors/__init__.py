"""
Processors package - summarization, deduplication, etc.
"""

from .summarizer import ClaudeSummarizer
from .deduper import (
    deduplicate_items,
    filter_by_date,
    sort_items,
    group_by_category,
    process_items,
)

__all__ = [
    "ClaudeSummarizer",
    "deduplicate_items",
    "filter_by_date",
    "sort_items",
    "group_by_category",
    "process_items",
]

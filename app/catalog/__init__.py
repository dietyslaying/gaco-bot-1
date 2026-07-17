"""Rule-based media catalogue + cover server.

No LLM. Files-group forum topics + auto_index are the source of truth.
"""
from app.catalog.builder import (
    rebuild_all_filters,
    refresh_series_filter,
    apply_topic_to_filter,
    status,
    build_reply_text,
)
from app.catalog.parser import parse_media, normalize_keyword

__all__ = [
    "rebuild_all_filters",
    "refresh_series_filter",
    "apply_topic_to_filter",
    "status",
    "build_reply_text",
    "parse_media",
    "normalize_keyword",
]

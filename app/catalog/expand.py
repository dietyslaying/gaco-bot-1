"""Expand catalogue filters with fan short names / aliases."""
from __future__ import annotations

import logging
from typing import Optional

from app.catalog.aliases import expand_all
from app.catalog.parser import normalize_keyword

logger = logging.getLogger("catalog.expand")


async def expand_filter_aliases(progress_cb=None) -> dict:
    """
    For every filter (and topic), create additional filter rows that share
    the same reply_text + sticker file_id under short names / aliases.
    """
    from app import database

    import re
    topics = await database.get_all_topics()
    keywords = await database.get_all_filter_keywords()

    # Only expand *series-level* titles — not season/episode/movie granular keys
    _GRANULAR = re.compile(
        r"(?:\bs\d+\b|\be\d+\b|\bseason\b|\bepisode\b|\b\d+x\d+\b|"
        r"\bmovie\b|\bova\b|\bspecial\b|\bona\b|\bpart\b)",
        re.I,
    )

    series = []
    seen_kw = set()
    for t in topics:
        kw = normalize_keyword(t.get("keyword") or t.get("title") or "")
        if kw and kw not in seen_kw:
            series.append({"title": t.get("title") or kw, "keyword": kw})
            seen_kw.add(kw)
    for kw in keywords:
        n = normalize_keyword(kw)
        if not n or n in seen_kw:
            continue
        if _GRANULAR.search(n):
            continue
        # skip very long multi-token episode-like leftovers
        if len(n.split()) > 8:
            continue
        series.append({"title": n, "keyword": n})
        seen_kw.add(n)

    mapping = expand_all(series)  # alias → primary
    logger.info("Alias map size: %s (from %s series)", len(mapping), len(series))

    created = 0
    skipped = 0
    missing_primary = 0
    by_primary: dict[str, int] = {}

    # Cache primary filter payloads
    primary_cache: dict[str, Optional[dict]] = {}

    items = list(mapping.items())
    total = len(items)
    for i, (alias, primary) in enumerate(items, 1):
        if alias == primary:
            skipped += 1
            continue
        if primary not in primary_cache:
            primary_cache[primary] = await database.get_filter(primary)
        data = primary_cache[primary]
        if not data:
            missing_primary += 1
            continue
        # Don't overwrite an existing different series — if alias already has content
        existing = await database.get_filter(alias)
        if existing and existing.get("reply_text") and existing.get("reply_text") != data["reply_text"]:
            # keep existing unique filter
            skipped += 1
            continue
        await database.add_filter(
            alias,
            data["reply_text"],
            file_id=data.get("file_id"),
            keep_existing_file_id=False,
        )
        created += 1
        by_primary[primary] = by_primary.get(primary, 0) + 1
        if progress_cb and (i % 50 == 0 or i == total):
            await progress_cb(i, total, created)

    result = {
        "series": len(series),
        "alias_keys": len(mapping),
        "created": created,
        "skipped": skipped,
        "missing_primary": missing_primary,
        "top_expanded": sorted(by_primary.items(), key=lambda x: -x[1])[:20],
    }
    try:
        from app.catalog.search import reset_alias_cache
        reset_alias_cache()
    except Exception:
        pass
    logger.info("Alias expand done: %s", result)
    return result

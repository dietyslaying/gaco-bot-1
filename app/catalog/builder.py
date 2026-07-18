"""Build classic GACO filters: keyword + dual buttons + optional sticker."""
from __future__ import annotations

import logging
from collections import defaultdict
from typing import Optional

from app.catalog import config as cfg
from app.catalog.parser import parse_media

logger = logging.getLogger("catalog")


def _quality_rank(q: Optional[str]) -> int:
    if not q:
        return 999
    ql = q.lower().strip()
    for i, pref in enumerate(cfg.QUALITY_PRIORITY):
        if pref in ql or ql in pref:
            return i
    return 500


def _safe_btn(text: str) -> str:
    return (text or "Link").replace("[", "(").replace("]", ")")


def build_reply_text(
    title: str = "",
    gaco_url: str = "",
    download_url: str = "",
) -> str:
    """
    Classic dual-button reply matching production UX:

        Here you go!
        [✨ GACO ✨](buttonurl:…)
        [⛩ DOWNLOAD ⛩](buttonurl:…)
    """
    gaco_url = gaco_url or download_url
    download_url = download_url or gaco_url or cfg.DEFAULT_DOWNLOAD_URL
    if cfg.DEFAULT_DOWNLOAD_URL:
        download_url = cfg.DEFAULT_DOWNLOAD_URL

    lines = [cfg.REPLY_TEXT or "Here you go!"]
    if gaco_url:
        lines.append(f"[{_safe_btn(cfg.GACO_BUTTON_TEXT)}](buttonurl:{gaco_url})")
    if download_url:
        lines.append(f"[{_safe_btn(cfg.DOWNLOAD_BUTTON_TEXT)}](buttonurl:{download_url})")
    return "\n".join(lines)


def group_index_rows(rows: list[dict]) -> dict[str, dict]:
    """keyword -> {title, url, message_id, quality, file_count}"""
    buckets: dict[str, list[dict]] = defaultdict(list)
    display_title: dict[str, str] = {}

    for row in rows:
        parsed = parse_media(row.get("file_name") or "", row.get("caption") or "")
        if not parsed or not parsed.keyword:
            continue
        url = row.get("message_url") or row.get("url") or ""
        if not url:
            continue
        display_title.setdefault(parsed.keyword, parsed.title)
        buckets[parsed.keyword].append({
            "url": url,
            "quality": parsed.quality,
            "rank": _quality_rank(parsed.quality),
            "message_id": row.get("message_id") or 0,
            "season": parsed.season if parsed.season is not None else -1,
            "episode": parsed.episode if parsed.episode is not None else -1,
        })

    result: dict[str, dict] = {}
    for keyword, items in buckets.items():
        items.sort(
            key=lambda it: (-it["season"], -it["episode"], it["rank"], -it["message_id"])
        )
        best = items[0]
        result[keyword] = {
            "title": display_title[keyword],
            "url": best["url"],
            "message_id": best["message_id"],
            "quality": best["quality"],
            "file_count": len(items),
        }
    return result


async def write_filter_for_series(
    keyword: str,
    title: str,
    gaco_url: str,
    download_url: str = "",
    sticker_file_id: str = None,
    keep_sticker: bool = True,
) -> None:
    from app import database

    reply = build_reply_text(title, gaco_url, download_url or gaco_url)
    await database.add_filter(
        keyword,
        reply,
        file_id=sticker_file_id,
        keep_existing_file_id=keep_sticker and not sticker_file_id,
    )


async def rebuild_all_filters() -> dict:
    """Rebuild filters from auto_index, merging stickers/URLs from topics when present."""
    from app import database

    rows = await database.get_all_auto_index()
    groups = group_index_rows(rows)
    topics = {t["keyword"]: t for t in await database.get_all_topics()}

    created = 0
    for keyword, meta in groups.items():
        topic = topics.get(keyword)
        gaco = (topic or {}).get("gaco_url") or (topic or {}).get("cover_url") or meta["url"]
        download = (topic or {}).get("download_url") or cfg.DEFAULT_DOWNLOAD_URL or gaco
        sticker = (topic or {}).get("sticker_file_id")
        await write_filter_for_series(
            keyword,
            meta["title"],
            gaco,
            download,
            sticker_file_id=sticker,
            keep_sticker=True,
        )
        created += 1

    # Topic-only series (cover backfill without files indexed yet)
    for keyword, topic in topics.items():
        if keyword in groups:
            continue
        url = topic.get("gaco_url") or topic.get("cover_url")
        if not url:
            continue
        await write_filter_for_series(
            keyword,
            topic.get("title") or keyword.title(),
            url,
            topic.get("download_url") or cfg.DEFAULT_DOWNLOAD_URL or url,
            sticker_file_id=topic.get("sticker_file_id"),
            keep_sticker=True,
        )
        created += 1

    logger.info("Catalogue rebuild: %s filters (index=%s topics=%s)", created, len(rows), len(topics))

    # Season / episode / movie / OVA direct-link filters
    from app.catalog.granular import apply_granular_filters
    granular_stats = await apply_granular_filters()

    # Fan short names / official abbreviations → extra filter keys
    from app.catalog.expand import expand_filter_aliases
    alias_stats = await expand_filter_aliases()

    all_kw = await database.get_all_filter_keywords()
    return {
        "filters": len(all_kw),
        "base_filters": created,
        "indexed": len(rows),
        "topics": len(topics),
        "granular": granular_stats,
        "aliases_created": alias_stats.get("created", 0),
        "keywords": sorted(all_kw)[:50],
    }


async def refresh_series_filter(file_name: str, caption: str = "", message_url: str = "") -> dict:
    """After a new file is indexed: rewrite that series' filter (buttons only; keep sticker)."""
    from app import database

    if not cfg.CATALOG_ENABLED:
        return {"ok": False, "reason": "disabled"}

    parsed = parse_media(file_name, caption)
    if not parsed:
        return {"ok": False, "reason": "unparsed", "file_name": file_name}

    all_rows = await database.get_all_auto_index()
    groups = group_index_rows(all_rows)
    meta = groups.get(parsed.keyword)
    topic = await database.get_topic_by_keyword(parsed.keyword)

    if not meta and not topic:
        if not message_url:
            return {"ok": False, "reason": "no_entries", "keyword": parsed.keyword}
        meta = {"title": parsed.title, "url": message_url, "file_count": 1}

    title = (meta or {}).get("title") or (topic or {}).get("title") or parsed.title
    gaco = (
        (topic or {}).get("gaco_url")
        or (topic or {}).get("cover_url")
        or (meta or {}).get("url")
        or message_url
    )
    download = (topic or {}).get("download_url") or cfg.DEFAULT_DOWNLOAD_URL or gaco
    sticker = (topic or {}).get("sticker_file_id")

    await write_filter_for_series(
        parsed.keyword, title, gaco, download, sticker_file_id=sticker, keep_sticker=True
    )
    return {
        "ok": True,
        "keyword": parsed.keyword,
        "title": title,
        "url": gaco,
        "has_sticker": bool(sticker),
    }


async def apply_topic_to_filter(topic: dict) -> dict:
    """Write/refresh filter from a topics row (after cover backfill)."""
    keyword = topic.get("keyword")
    if not keyword:
        return {"ok": False, "reason": "no_keyword"}
    url = topic.get("gaco_url") or topic.get("cover_url") or ""
    if not url:
        return {"ok": False, "reason": "no_url"}
    await write_filter_for_series(
        keyword,
        topic.get("title") or keyword.title(),
        url,
        topic.get("download_url") or cfg.DEFAULT_DOWNLOAD_URL or url,
        sticker_file_id=topic.get("sticker_file_id"),
        keep_sticker=False,
    )
    return {"ok": True, "keyword": keyword, "has_sticker": bool(topic.get("sticker_file_id"))}


async def status() -> dict:
    from app import database

    rows = await database.get_all_auto_index()
    keywords = await database.get_all_filter_keywords()
    topics_n = await database.count_topics()
    parsed_ok = sum(
        1 for r in rows if parse_media(r.get("file_name") or "", r.get("caption") or "")
    )
    return {
        "enabled": cfg.CATALOG_ENABLED,
        "indexed": len(rows),
        "parseable": parsed_ok,
        "filters": len(keywords),
        "topics": topics_n,
        "session_ready": cfg.session_configured(),
        "gaco_button": cfg.GACO_BUTTON_TEXT,
        "download_button": cfg.DOWNLOAD_BUTTON_TEXT,
        "use_stickers": cfg.USE_STICKERS,
    }

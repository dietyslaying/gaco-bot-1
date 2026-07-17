"""Cover Server — Telethon user session + bot sticker upload.

Full access path:
  * Admin user StringSession walks forum topics in the files group
  * First photo message in each topic = anime cover + description
  * Photo → WEBP sticker via the bot → file_id stored on topics + filters

This is not a separate machine — it is the named subsystem that feeds the cataloguer.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from app.catalog import config as cfg
from app.catalog.parser import normalize_keyword
from app.catalog.builder import apply_topic_to_filter
from app.catalog.sticker import process_cover_image

logger = logging.getLogger("catalog.cover_server")


def _message_url(chat_id: int, message_id: int, username: Optional[str] = None) -> str:
    if username:
        return f"https://t.me/{username}/{message_id}"
    # private supergroup: -100xxxxxxxxxx → t.me/c/<id without -100>/msg
    raw = str(chat_id)
    if raw.startswith("-100"):
        raw = raw[4:]
    else:
        raw = raw.lstrip("-")
    return f"https://t.me/c/{raw}/{message_id}"


def _storage_chat_id() -> int:
    if cfg.COVER_STORAGE_CHAT_ID:
        return int(cfg.COVER_STORAGE_CHAT_ID)
    from app import config as app_cfg
    if app_cfg.ADMINS:
        return int(app_cfg.ADMINS[0])
    raise RuntimeError("Set COVER_STORAGE_CHAT_ID or ADMINS so stickers can be uploaded")


async def _get_telethon_client():
    if not cfg.session_configured():
        raise RuntimeError(
            "Cover server needs TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_SESSION. "
            "Run: python scripts/login_session.py"
        )
    from telethon import TelegramClient
    from telethon.sessions import StringSession

    client = TelegramClient(
        StringSession(cfg.TELEGRAM_SESSION),
        cfg.TELEGRAM_API_ID,
        cfg.TELEGRAM_API_HASH,
    )
    await client.connect()
    if not await client.is_user_authorized():
        await client.disconnect()
        raise RuntimeError("TELEGRAM_SESSION is invalid or expired — re-run login_session.py")
    return client


async def list_forum_topics(client, entity) -> list[dict]:
    """Return [{id, title}, ...] for all forum topics."""
    from telethon.tl.functions.channels import GetForumTopicsRequest
    from telethon.tl.types import MessageActionTopicCreate

    topics: list[dict] = []
    offset_topic = 0
    offset_id = 0
    offset_date = None

    while True:
        result = await client(GetForumTopicsRequest(
            channel=entity,
            offset_date=offset_date,
            offset_id=offset_id,
            offset_topic=offset_topic,
            limit=100,
        ))
        batch = list(getattr(result, "topics", []) or [])
        if not batch:
            break
        for t in batch:
            title = getattr(t, "title", None) or ""
            tid = getattr(t, "id", None)
            if tid is None:
                continue
            topics.append({"id": int(tid), "title": title})
        # pagination
        last = batch[-1]
        offset_topic = getattr(last, "id", offset_topic)
        offset_id = getattr(last, "top_message", offset_id) or offset_id
        if len(batch) < 100:
            break
        await asyncio.sleep(0.2)

    # Deduplicate by id
    seen = {}
    for t in topics:
        seen[t["id"]] = t
    return list(seen.values())


async def find_cover_message(client, entity, topic_id: int) -> Optional[Any]:
    """Oldest messages in topic first; return first with a photo (or document image)."""
    async for msg in client.iter_messages(entity, reply_to=topic_id, reverse=True, limit=30):
        if getattr(msg, "action", None):
            continue
        if msg.photo:
            return msg
        # some covers are uploaded as image documents
        if msg.document and (msg.file and getattr(msg.file, "mime_type", "") or "").startswith("image/"):
            return msg
    return None


async def process_topic(
    client,
    bot,
    entity,
    topic: dict,
    chat_id: int,
    username: Optional[str],
    force: bool = False,
) -> dict:
    from app import database

    thread_id = int(topic["id"])
    title = (topic.get("title") or "").strip() or f"Topic {thread_id}"
    keyword = normalize_keyword(title)
    if len(keyword) < 2:
        return {"ok": False, "reason": "bad_title", "title": title}

    existing = await database.get_topic(thread_id)
    if existing and existing.get("sticker_file_id") and not force:
        # still ensure filter exists
        await apply_topic_to_filter(existing)
        return {"ok": True, "skipped": True, "keyword": keyword, "title": title}

    cover = await find_cover_message(client, entity, thread_id)
    if not cover:
        # still register topic shell for later
        await database.upsert_topic(
            thread_id=thread_id,
            title=title,
            keyword=keyword,
        )
        return {"ok": False, "reason": "no_cover", "keyword": keyword, "title": title}

    cover_url = _message_url(chat_id, cover.id, username)
    description = (cover.message or cover.raw_text or "")[:2000]

    image_bytes = await client.download_media(cover, file=bytes)
    if not image_bytes:
        return {"ok": False, "reason": "download_failed", "keyword": keyword}

    storage = _storage_chat_id()
    sticker_id, photo_id = await process_cover_image(
        bot, storage, image_bytes, prefer_sticker=cfg.USE_STICKERS
    )

    gaco_url = cover_url
    download_url = cfg.DEFAULT_DOWNLOAD_URL or cover_url

    await database.upsert_topic(
        thread_id=thread_id,
        title=title,
        keyword=keyword,
        cover_message_id=cover.id,
        cover_url=cover_url,
        sticker_file_id=sticker_id,
        photo_file_id=photo_id,
        description=description,
        gaco_url=gaco_url,
        download_url=download_url,
    )
    topic_row = await database.get_topic(thread_id)
    await apply_topic_to_filter(topic_row)

    return {
        "ok": True,
        "keyword": keyword,
        "title": title,
        "sticker": bool(sticker_id),
        "photo": bool(photo_id),
        "cover_url": cover_url,
    }


async def backfill(
    bot,
    files_group_id: int | str,
    force: bool = False,
    limit: int = 0,
    progress_cb=None,
) -> dict:
    """
    Full topic scan via user session. Call from admin `/catalog backfill`
    or `python scripts/backfill_topics.py`.
    """
    from app import database

    await database.init_db()
    client = await _get_telethon_client()
    stats = {
        "topics": 0,
        "ok": 0,
        "skipped": 0,
        "no_cover": 0,
        "errors": 0,
        "details": [],
    }

    try:
        entity = await client.get_entity(int(files_group_id))
        username = getattr(entity, "username", None)
        chat_id = int(files_group_id)

        topics = await list_forum_topics(client, entity)
        if limit and limit > 0:
            topics = topics[:limit]
        elif cfg.BACKFILL_LIMIT > 0:
            topics = topics[: cfg.BACKFILL_LIMIT]

        stats["topics"] = len(topics)
        logger.info("Cover server: %s topics to process", len(topics))

        for i, topic in enumerate(topics, 1):
            try:
                result = await process_topic(
                    client, bot, entity, topic, chat_id, username, force=force
                )
                if result.get("skipped"):
                    stats["skipped"] += 1
                elif result.get("ok"):
                    stats["ok"] += 1
                elif result.get("reason") == "no_cover":
                    stats["no_cover"] += 1
                else:
                    stats["errors"] += 1
                stats["details"].append(result)
            except Exception as e:
                logger.exception("topic %s failed: %s", topic, e)
                stats["errors"] += 1
                stats["details"].append({"ok": False, "title": topic.get("title"), "error": str(e)})

            if progress_cb:
                try:
                    await progress_cb(i, len(topics), stats)
                except Exception:
                    pass
            await asyncio.sleep(cfg.BACKFILL_DELAY)
    finally:
        await client.disconnect()

    return stats


async def ingest_live_cover(
    bot,
    thread_id: int,
    title: str,
    message_id: int,
    chat_id: int,
    image_bytes: bytes,
    caption: str = "",
    username: Optional[str] = None,
) -> dict:
    """
    Bot-path cover ingest when a photo lands in a topic (no Telethon needed for that event).
    Still uses bot upload for sticker file_id.
    """
    from app import database

    if not cfg.CATALOG_ENABLED:
        return {"ok": False, "reason": "disabled"}

    keyword = normalize_keyword(title)
    if len(keyword) < 2:
        return {"ok": False, "reason": "bad_title"}

    existing = await database.get_topic(thread_id)
    if existing and existing.get("sticker_file_id"):
        return {"ok": True, "skipped": True, "keyword": keyword}

    cover_url = _message_url(chat_id, message_id, username)
    storage = _storage_chat_id()
    sticker_id, photo_id = await process_cover_image(
        bot, storage, image_bytes, prefer_sticker=cfg.USE_STICKERS
    )
    download_url = cfg.DEFAULT_DOWNLOAD_URL or cover_url

    await database.upsert_topic(
        thread_id=thread_id,
        title=title,
        keyword=keyword,
        cover_message_id=message_id,
        cover_url=cover_url,
        sticker_file_id=sticker_id,
        photo_file_id=photo_id,
        description=(caption or "")[:2000],
        gaco_url=cover_url,
        download_url=download_url,
    )
    topic_row = await database.get_topic(thread_id)
    await apply_topic_to_filter(topic_row)
    return {
        "ok": True,
        "keyword": keyword,
        "sticker": bool(sticker_id),
        "photo": bool(photo_id),
    }

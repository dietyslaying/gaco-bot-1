#!/usr/bin/env python3
"""Run Cover Server backfill: all forum topics → covers → stickers → filters.

Requires:
  BOT_TOKEN, DATABASE_URL, FILES_GROUP_ID
  TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_SESSION
  COVER_STORAGE_CHAT_ID or ADMINS (bot must be able to message that chat)

Usage (from project root):
    python scripts/backfill_topics.py
    python scripts/backfill_topics.py --force --limit 50
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="Re-download covers even if sticker exists")
    ap.add_argument("--limit", type=int, default=0, help="Max topics (0=all)")
    args = ap.parse_args()

    from aiogram import Bot
    from app import config
    from app.catalog.cover_server import backfill

    if not config.BOT_TOKEN:
        print("BOT_TOKEN missing")
        sys.exit(1)
    if not config.FILES_GROUP_ID:
        print("FILES_GROUP_ID missing")
        sys.exit(1)

    bot = Bot(token=config.BOT_TOKEN)

    async def progress(i, total, stats):
        if i == 1 or i % 10 == 0 or i == total:
            print(
                f"[{i}/{total}] ok={stats['ok']} skip={stats['skipped']} "
                f"no_cover={stats['no_cover']} err={stats['errors']}"
            )

    try:
        stats = await backfill(
            bot,
            config.FILES_GROUP_ID,
            force=args.force,
            limit=args.limit,
            progress_cb=progress,
        )
        print()
        print("Done:", {k: v for k, v in stats.items() if k != "details"})
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())

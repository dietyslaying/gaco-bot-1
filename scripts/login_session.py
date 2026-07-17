#!/usr/bin/env python3
"""Generate a Telethon StringSession for the Cover Server.

Prereqs:
  1. Create an app at https://my.telegram.org → api_id + api_hash
  2. Use an account that is ADMIN of the files group

Usage:
    set TELEGRAM_API_ID=12345
    set TELEGRAM_API_HASH=...
    python scripts/login_session.py

Paste the printed TELEGRAM_SESSION into .env
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


async def main():
    api_id = int(os.getenv("TELEGRAM_API_ID", "0") or "0")
    api_hash = os.getenv("TELEGRAM_API_HASH", "")
    if not api_id or not api_hash:
        print("Set TELEGRAM_API_ID and TELEGRAM_API_HASH first (from https://my.telegram.org)")
        api_id = int(input("api_id: ").strip())
        api_hash = input("api_hash: ").strip()

    from telethon import TelegramClient
    from telethon.sessions import StringSession

    client = TelegramClient(StringSession(), api_id, api_hash)
    await client.start()
    session = client.session.save()
    me = await client.get_me()
    print()
    print("=" * 60)
    print(f"Logged in as: {me.first_name} (@{me.username}) id={me.id}")
    print("Add this to your .env (keep secret!):")
    print()
    print(f"TELEGRAM_API_ID={api_id}")
    print(f"TELEGRAM_API_HASH={api_hash}")
    print(f"TELEGRAM_SESSION={session}")
    print("=" * 60)
    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())

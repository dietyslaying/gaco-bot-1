#!/usr/bin/env python3
"""Generate a Telethon StringSession and write TELEGRAM_SESSION into .env.

Uses TELEGRAM_API_ID / TELEGRAM_API_HASH from .env (or prompts).

Usage (from project root):
    python scripts/login_session.py
"""
from __future__ import annotations

import asyncio
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
ENV_PATH = ROOT / ".env"


def _load_env_file():
    try:
        from dotenv import load_dotenv
        load_dotenv(ENV_PATH, override=True)
    except ImportError:
        pass


def _write_session_to_env(session: str) -> None:
    """Set or replace TELEGRAM_SESSION= in .env."""
    line = f"TELEGRAM_SESSION={session}"
    if ENV_PATH.exists():
        text = ENV_PATH.read_text(encoding="utf-8")
        if re.search(r"^TELEGRAM_SESSION=.*$", text, flags=re.M):
            text = re.sub(r"^TELEGRAM_SESSION=.*$", line, text, flags=re.M)
        else:
            if not text.endswith("\n"):
                text += "\n"
            text += line + "\n"
        ENV_PATH.write_text(text, encoding="utf-8")
    else:
        ENV_PATH.write_text(line + "\n", encoding="utf-8")
    print(f"Wrote TELEGRAM_SESSION to {ENV_PATH}")


async def main():
    _load_env_file()
    api_id = int(os.getenv("TELEGRAM_API_ID", "0") or "0")
    api_hash = (os.getenv("TELEGRAM_API_HASH") or "").strip()

    if not api_id or not api_hash:
        print("TELEGRAM_API_ID / TELEGRAM_API_HASH missing in .env")
        api_id = int(input("api_id: ").strip())
        api_hash = input("api_hash: ").strip()

    from telethon import TelegramClient
    from telethon.sessions import StringSession

    print(f"Logging in with api_id={api_id} …")
    print("Enter phone (international, e.g. +1…) and the code Telegram sends.")
    client = TelegramClient(StringSession(), api_id, api_hash)
    await client.start()
    session = client.session.save()
    me = await client.get_me()
    print()
    print("=" * 60)
    print(f"Logged in as: {me.first_name} (@{getattr(me, 'username', None)}) id={me.id}")
    _write_session_to_env(session)
    print("=" * 60)
    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())

#!/usr/bin/env python3
"""Drop and recreate all Postgres tables; flush Redis if configured.

Run from project root:
    python scripts/wipe_db.py
"""
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import database  # noqa: E402


async def wipe_all():
    print("--- Wiping ENTIRE Postgres Database ---")
    await database.init_db()

    try:
        async with database.engine.begin() as conn:
            await conn.run_sync(database.Base.metadata.drop_all)
            await conn.run_sync(database.Base.metadata.create_all)
            print("Successfully dropped and recreated all Postgres tables.")
    except Exception as e:
        print(f"Error wiping database: {e}")

    if database.redis_client:
        try:
            await database.redis_client.flushdb()
            print("Cleared ALL Redis cache.")
        except Exception as e:
            print(f"Error clearing Redis: {e}")


if __name__ == "__main__":
    asyncio.run(wipe_all())

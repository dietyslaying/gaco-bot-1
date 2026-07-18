#!/usr/bin/env python3
"""Expand filters with fan short names / official abbreviations.

Usage (project root):
    python scripts/expand_aliases.py
"""
from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


async def main():
    from app import database, catalog

    await database.init_db()
    before = len(await database.get_all_filter_keywords())
    stats = await catalog.expand_filter_aliases()
    after = len(await database.get_all_filter_keywords())
    print("Before:", before)
    print("After:", after)
    print("Stats:", stats)
    # show some popular shortcuts
    demos = ["aot", "jjk", "op", "opm", "csm", "mha", "onk", "sl", "sxf", "kny", "tbate", "tensura", "cote"]
    print("\nDemo lookups:")
    for d in demos:
        f = await database.get_filter(d)
        print(f"  {d!r:12} →", "HIT" if f else "miss", (f.get("reply_text") or "")[:40] if f else "")


if __name__ == "__main__":
    asyncio.run(main())

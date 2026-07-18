#!/usr/bin/env python3
"""Build season / episode / movie / OVA filters from auto_index."""
from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
logging.basicConfig(level=logging.INFO)


async def main():
    from app import database, catalog
    await database.init_db()
    before = len(await database.get_all_filter_keywords())
    stats = await catalog.apply_granular_filters()
    after = len(await database.get_all_filter_keywords())
    print("Before:", before)
    print("After:", after)
    print("Stats:", stats)
    demos = [
        "oshi no ko s3 e8",
        "oshi no ko s3",
        "sentenced to be a hero s1 e1",
        "ne zha 2019 movie",
        "jjk",
    ]
    print("\nDemos:")
    from app.catalog.search import resolve_search
    for d in demos:
        hit = await resolve_search(d)
        print(f"  {d!r:40} → {hit.kind} kw={hit.keyword} sug={hit.suggestions[:2]}")


if __name__ == "__main__":
    asyncio.run(main())

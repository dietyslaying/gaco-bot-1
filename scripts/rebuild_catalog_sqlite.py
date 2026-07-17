#!/usr/bin/env python3
"""Dry-run / apply catalogue rebuild against the SQLite backup (no Postgres).

Usage:
    python scripts/rebuild_catalog_sqlite.py
    python scripts/rebuild_catalog_sqlite.py --apply
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.catalog.builder import group_index_rows, build_reply_text  # noqa: E402

DEFAULT_DB = ROOT / "backups" / "railway_backup.sqlite"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", type=Path, default=DEFAULT_DB)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    if not args.db.exists():
        print(f"DB not found: {args.db}")
        sys.exit(1)

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    rows = [
        {
            "message_id": r["message_id"],
            "file_name": r["file_name"] or "",
            "caption": r["caption"] or "",
            "message_url": r["message_url"] or "",
            "url": r["message_url"] or "",
        }
        for r in conn.execute(
            "SELECT message_id, file_name, caption, message_url FROM auto_index"
        )
    ]
    groups = group_index_rows(rows)
    print(f"Index rows: {len(rows)}")
    print(f"Filters that would be created: {len(groups)}\n")
    for kw in sorted(groups.keys()):
        meta = groups[kw]
        reply = build_reply_text(meta["title"], meta["url"], meta["url"])
        print(f"  • {meta['title']!r}  key={kw!r}  files={meta['file_count']}")
        print(f"    {reply!r}\n")

    if args.apply:
        # ensure filters table exists
        conn.execute(
            """CREATE TABLE IF NOT EXISTS filters (
                keyword TEXT PRIMARY KEY,
                reply_text TEXT NOT NULL,
                file_id TEXT
            )"""
        )
        conn.execute("DELETE FROM filters")
        for kw, meta in groups.items():
            reply = build_reply_text(meta["title"], meta["url"], meta["url"])
            conn.execute(
                "INSERT OR REPLACE INTO filters (keyword, reply_text, file_id) VALUES (?, ?, NULL)",
                (kw, reply),
            )
        conn.commit()
        n = conn.execute("SELECT COUNT(*) FROM filters").fetchone()[0]
        print(f"Applied. filters={n} → {args.db}")
    else:
        print("(Dry run. Pass --apply to write.)")
    conn.close()


if __name__ == "__main__":
    main()

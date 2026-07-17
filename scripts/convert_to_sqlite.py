#!/usr/bin/env python3
"""Parse a PostgreSQL custom-format (PGDMP) dump and build a structured SQLite DB.

Strategy:
  * Extract CREATE TABLE DDL + column order from the dump text.
  * Locate every zlib-compressed data block in file order.
  * Classify each block by its *content* (column count + value patterns) and
    assign it to the table whose schema fits, so data lands in the right table
    regardless of how the dump interleaves blocks.
  * Emit a clean, normalized SQLite database with PRIMARY KEY / UNIQUE indexes.
"""
import zlib
import re
import sqlite3
import os
from pathlib import Path

# Project root = parent of scripts/
ROOT = Path(__file__).resolve().parents[1]
BACKUP_DIR = ROOT / "backups"

SRC = os.environ.get("GACO_BACKUP_SQL", str(BACKUP_DIR / "railway_backup.sql"))
OUT = os.environ.get("GACO_BACKUP_SQLITE", str(BACKUP_DIR / "railway_backup.sqlite"))

with open(SRC, "rb") as f:
    raw = f.read()
text = raw.decode("latin-1")

# --------------------------------------------------------------------------
# 1. Schema: table name -> ordered list of (column, raw_pg_type)
# --------------------------------------------------------------------------
table_re = re.compile(r"CREATE TABLE public\.(\w+)\s*\((.*?)\);", re.DOTALL)
schema = {}
for m in table_re.finditer(text):
    name = m.group(1)
    cols = []
    for line in m.group(2).split("\n"):
        line = line.strip().strip(",")
        if not line:
            continue
        parts = line.split(None, 1)
        if len(parts) < 2:
            continue
        cols.append((parts[0], parts[1]))
    schema[name] = cols

# --------------------------------------------------------------------------
# 2. All COPY (table data) entries -> ordered list of (table, columns)
# --------------------------------------------------------------------------
copy_re = re.compile(r"COPY public\.(\w+)\s*\((.*?)\) FROM stdin;")
copy_order = []
for m in copy_re.finditer(text):
    cols = [c.strip() for c in m.group(2).split(",")]
    copy_order.append((m.group(1), cols))

# --------------------------------------------------------------------------
# 3. Every zlib stream in file order
# --------------------------------------------------------------------------
streams = []
for i in range(len(raw) - 1):
    if raw[i] == 0x78 and raw[i + 1] in (0x01, 0x9c, 0xda, 0x5e):
        try:
            d = zlib.decompress(raw[i:])
            streams.append((i, d))
        except Exception:
            pass


def is_int(b):
    try:
        int(b)
        return True
    except (ValueError, TypeError):
        return False


def classify(d):
    """Return ('empty', None) or ('data', ncols, rows)."""
    rows = [ln for ln in d.split(b"\n") if ln and ln != b"\\."]
    if not rows:
        return ("empty", 0, [])
    ncols = len(rows[0].split(b"\t"))
    return ("data", ncols, rows)


# --------------------------------------------------------------------------
# 4. Assign each data stream to the best-matching table by content signature
# --------------------------------------------------------------------------
# Build candidate tables grouped by column count.
by_ncols = {}
for name, cols in schema.items():
    by_ncols.setdefault(len(cols), []).append(name)

# Classify streams
classified = []
for pos, d in streams:
    kind, ncols, rows = classify(d)
    classified.append((pos, kind, ncols, rows))

# Match data streams to tables
assignments = {}   # table -> rows
unused_tables = set(schema.keys())
empty_tables = set()

for pos, kind, ncols, rows in classified:
    if kind == "empty":
        # terminator block for some empty table; defer assignment
        empty_tables_unassigned = [t for t in unused_tables if len(schema[t]) == ncols]
        if empty_tables_unassigned:
            t = empty_tables_unassigned[0]
            assignments[t] = []
            unused_tables.discard(t)
        continue

    # data stream -> find matching table by signature
    candidates = [t for t in unused_tables if len(schema[t]) == ncols]
    chosen = None
    if ncols == 4:
        # auto_index vs broadcasts: auto_index has a URL / .mkv filename
        for t in candidates:
            if t == "auto_index":
                chosen = t
                break
            if t == "broadcasts":
                chosen = t
                break
        # prefer auto_index if any row has a URL or media filename
        if "auto_index" in candidates and any(
            b"http" in r or b".mkv" in r or b".mp4" in r for r in rows[:5]
        ):
            chosen = "auto_index"
        elif "broadcasts" in candidates:
            chosen = "broadcasts"
    elif ncols == 2:
        # users: second col is boolean f/t
        if "users" in candidates:
            chosen = "users"
    elif ncols == 3:
        # filters (text), user_activity (numeric), broadcast_sent_messages (numeric)
        if "filters" in candidates:
            # filters has text reply (non-numeric)
            first = rows[0].split(b"\t")
            if not all(is_int(f) for f in first):
                chosen = "filters"
        if chosen is None and "user_activity" in candidates:
            # user_activity: user_id + small int counts
            first = rows[0].split(b"\t")
            if all(is_int(f) for f in first):
                chosen = "user_activity"
        if chosen is None and "broadcast_sent_messages" in candidates:
            first = rows[0].split(b"\t")
            if all(is_int(f) for f in first):
                chosen = "broadcast_sent_messages"
    # fallback: first candidate
    if chosen is None and candidates:
        chosen = candidates[0]

    if chosen:
        assignments[chosen] = rows
        unused_tables.discard(chosen)

# Any table never assigned and not explicitly emptied -> empty
for t in list(unused_tables):
    assignments.setdefault(t, [])

# --------------------------------------------------------------------------
# 5. Type translation PostgreSQL -> SQLite
# --------------------------------------------------------------------------
def sql_type(pg_type):
    t = pg_type.lower()
    if any(k in t for k in ("bigint", "int8", "integer", "int", "serial", "oid")):
        return "INTEGER"
    if any(k in t for k in ("boolean", "bool")):
        return "INTEGER"  # stored as 0/1
    if any(k in t for k in ("character varying", "varchar", "text", "char", "name")):
        return "TEXT"
    if any(k in t for k in ("timestamp", "date", "time")):
        return "TEXT"
    if any(k in t for k in ("numeric", "real", "double", "float", "money")):
        return "REAL"
    return "TEXT"


def coerce(value, pg_type):
    t = pg_type.lower()
    v = value.decode("utf-8", errors="replace") if isinstance(value, bytes) else value
    if v == "" or v is None:
        return None
    if any(k in t for k in ("boolean", "bool")):
        return 1 if v.strip() in ("t", "true", "1") else 0
    if any(k in t for k in ("bigint", "int8", "integer", "int", "serial", "oid")):
        try:
            return int(v)
        except ValueError:
            return v
    if any(k in t for k in ("numeric", "real", "double", "float")):
        try:
            return float(v)
        except ValueError:
            return v
    return v


# --------------------------------------------------------------------------
# 6. Build the SQLite database
# --------------------------------------------------------------------------
if os.path.exists(OUT):
    os.remove(OUT)
conn = sqlite3.connect(OUT)
cur = conn.cursor()
cur.execute("PRAGMA foreign_keys = ON;")

for name, cols in schema.items():
    col_defs = []
    for col, typ in cols:
        notnull = "NOT NULL" if "NOT NULL" in typ else ""
        col_defs.append('"{col}" {type} {nn}'.format(col=col, type=sql_type(typ), nn=notnull).strip())
    ddl = 'CREATE TABLE "{name}" (\n  '.format(name=name) + ",\n  ".join(col_defs) + "\n);"
    cur.execute(ddl)
    print(ddl)
    print()

# Primary keys from constraints (best-effort unique indexes)
pk_re = re.compile(r"ADD CONSTRAINT \w+ PRIMARY KEY \((.*?)\);", re.DOTALL)
for m in pk_re.finditer(text):
    pk_cols = m.group(1).replace('"', "").replace("public.", "").strip()
    # attribute to the table whose name is contained in the constraint name
    # find the constraint line context
    for tname in schema:
        if tname in m.group(0):
            try:
                cur.execute(
                    'CREATE UNIQUE INDEX IF NOT EXISTS "pk_{t}" ON "{t}" ({c});'.format(t=tname, c=pk_cols)
                )
            except sqlite3.Error as e:
                print("PK warn for", tname, e)
            break

# --------------------------------------------------------------------------
# 7. Insert rows
# --------------------------------------------------------------------------
def parse_row(line, ncols):
    fields = line.split(b"\t")
    if len(fields) < ncols:
        fields = fields + [b""] * (ncols - len(fields))
    elif len(fields) > ncols:
        fields = fields[:ncols]
    return fields


for tname, cols in schema.items():
    rows = assignments.get(tname, [])
    if not rows:
        print("Inserted 0 rows into {t} (empty)".format(t=tname))
        continue
    ncols = len(cols)
    placeholders = ", ".join(["?"] * ncols)
    col_list = ", ".join('"{c}"'.format(c=c[0]) for c in cols)
    records = []
    for line in rows:
        fields = parse_row(line, ncols)
        records.append(tuple(coerce(f, cols[i][1]) for i, f in enumerate(fields)))
    cur.executemany(
        'INSERT INTO "{t}" ({cols}) VALUES ({ph});'.format(t=tname, cols=col_list, ph=placeholders),
        records,
    )
    print("Inserted {n} rows into {t}".format(n=len(records), t=tname))

conn.commit()
cur.execute("ANALYZE;")
cur.execute("VACUUM;")

print("\n=== Database summary ===")
for (name,) in cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"):
    cnt = cur.execute('SELECT COUNT(*) FROM "{n}"'.format(n=name)).fetchone()[0]
    print("  {n}: {c} rows".format(n=name, c=cnt))

conn.close()
print("\nCreated", OUT)

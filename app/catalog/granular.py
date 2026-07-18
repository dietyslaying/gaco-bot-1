"""Build season / episode / movie / OVA / special filters from auto_index.

Each granular key points at a direct message URL (best quality encode).
Series-level filters with stickers remain owned by topics + builder.
"""
from __future__ import annotations

import logging
import re
from collections import defaultdict
from typing import Optional

from app.catalog import config as cfg
from app.catalog.builder import build_reply_text, _quality_rank
from app.catalog.parser import parse_media, normalize_keyword, ParsedMedia

logger = logging.getLogger("catalog.granular")

# Max episode-list buttons when building a season pack reply
_SEASON_BUTTON_CAP = int(__import__("os").getenv("CATALOG_SEASON_BUTTONS", "25"))


def _detect_kind_extra(file_name: str, caption: str, parsed: ParsedMedia) -> str:
    """Refine kind: movie | ova | special | ona | episode."""
    blob = f"{file_name or ''} {caption or ''} {parsed.title or ''}".lower()
    if re.search(r"\b(ova|oav)\b", blob):
        return "ova"
    if re.search(r"\b(special|sp\d*|tokubetsu)\b", blob):
        return "special"
    if re.search(r"\b(ona)\b", blob):
        return "ona"
    if re.search(r"\b(movie|film|gekijouban|theatrical)\b", blob):
        return "movie"
    if parsed.kind == "movie":
        return "movie"
    if parsed.season is not None and parsed.episode is not None:
        return "episode"
    return parsed.kind or "unknown"


def _ep_keys(title_kw: str, season: int, episode: int) -> list[str]:
    """Search keys that should open this episode."""
    s, e = int(season), int(episode)
    keys = [
        f"{title_kw} s{s} e{e}",
        f"{title_kw} s{s:02d} e{e:02d}",
        f"{title_kw} s{s}e{e}",
        f"{title_kw} s{s:02d}e{e:02d}",
        f"{title_kw} {s}x{e:02d}",
        f"{title_kw} {s}x{e}",
        f"s{s} e{e} {title_kw}",
        f"s{s}e{e} {title_kw}",
    ]
    # if season 1, also bare episode for convenience
    if s == 1:
        keys += [
            f"{title_kw} e{e}",
            f"{title_kw} e{e:02d}",
            f"{title_kw} episode {e}",
            f"{title_kw} ep {e}",
        ]
    return [normalize_keyword(k) for k in keys]


def _season_keys(title_kw: str, season: int) -> list[str]:
    s = int(season)
    keys = [
        f"{title_kw} s{s}",
        f"{title_kw} s{s:02d}",
        f"{title_kw} season {s}",
        f"s{s} {title_kw}",
        f"season {s} {title_kw}",
    ]
    return [normalize_keyword(k) for k in keys]


def _type_keys(title_kw: str, kind: str, part: Optional[int] = None) -> list[str]:
    keys = [f"{title_kw} {kind}", f"{kind} {title_kw}"]
    if part is not None:
        keys += [
            f"{title_kw} {kind} {part}",
            f"{title_kw} part {part}",
            f"{title_kw} {kind} part {part}",
        ]
    return [normalize_keyword(k) for k in keys]


def _part_from_text(text: str) -> Optional[int]:
    m = re.search(r"\bpart\s*[-_]?\s*(\d+)\b", text or "", re.I)
    if m:
        return int(m.group(1))
    m = re.search(r"\b(?:movie|ova|special)\s*[-_]?\s*(\d+)\b", text or "", re.I)
    if m:
        return int(m.group(1))
    return None


def collect_media_entries(rows: list[dict]) -> list[dict]:
    """Parse auto_index rows into structured media entries."""
    entries = []
    for row in rows:
        parsed = parse_media(row.get("file_name") or "", row.get("caption") or "")
        if not parsed or not parsed.keyword:
            continue
        url = row.get("message_url") or row.get("url") or ""
        if not url:
            continue
        kind = _detect_kind_extra(row.get("file_name") or "", row.get("caption") or "", parsed)
        part = _part_from_text(f"{row.get('file_name')} {row.get('caption')}")
        entries.append({
            "title": parsed.title,
            "keyword": parsed.keyword,
            "season": parsed.season,
            "episode": parsed.episode,
            "quality": parsed.quality,
            "rank": _quality_rank(parsed.quality),
            "label": parsed.label,
            "kind": kind,
            "part": part,
            "url": url,
            "message_id": row.get("message_id") or 0,
            "file_name": row.get("file_name") or "",
        })
    return entries


def best_per_group(items: list[dict], key_fn) -> dict:
    """Keep best quality (+ newest) per group key."""
    best = {}
    for it in items:
        k = key_fn(it)
        prev = best.get(k)
        if prev is None or it["rank"] < prev["rank"] or (
            it["rank"] == prev["rank"] and it["message_id"] > prev["message_id"]
        ):
            best[k] = it
    return best


def build_granular_filter_map(rows: list[dict]) -> dict[str, dict]:
    """
    Returns keyword → {reply_text, title, url, level}
    level: episode | season | movie | ova | special | ona
    """
    entries = collect_media_entries(rows)
    out: dict[str, dict] = {}

    # --- Episodes (best quality per S/E) ---
    eps = [e for e in entries if e["kind"] == "episode" and e["season"] is not None and e["episode"] is not None]
    for it in best_per_group(eps, lambda e: (e["keyword"], e["season"], e["episode"])).values():
        reply = build_reply_text(it["title"], it["url"], it["url"])
        # prepend ep label into reply text for clarity
        reply = f"{it['title']} — S{it['season']} E{it['episode']:02d}\n" + "\n".join(reply.split("\n")[1:])
        meta = {"reply_text": reply, "title": it["title"], "url": it["url"], "level": "episode", "file_id": None}
        for key in _ep_keys(it["keyword"], it["season"], it["episode"]):
            out[key] = meta

    # --- Seasons (best latest ep URL + multi-button pack) ---
    by_season: dict[tuple, list] = defaultdict(list)
    for e in eps:
        by_season[(e["keyword"], e["season"])].append(e)

    for (title_kw, season), items in by_season.items():
        # unique episodes best quality
        best_eps = list(best_per_group(items, lambda e: e["episode"]).values())
        best_eps.sort(key=lambda e: e["episode"])
        title = best_eps[0]["title"]
        # season "landing" = latest episode
        latest = max(best_eps, key=lambda e: (e["episode"], -e["rank"]))
        # multi-button list for season browse
        lines = [f"{title} — Season {season}", cfg.REPLY_TEXT or "Here you go!"]
        for ep in best_eps[:_SEASON_BUTTON_CAP]:
            label = f"S{season} E{ep['episode']:02d}"
            if ep.get("quality"):
                label += f" · {ep['quality']}"
            safe = label.replace("[", "(").replace("]", ")")
            lines.append(f"[{safe}](buttonurl:{ep['url']})")
        # also dual classic buttons to latest
        lines.append(f"[{cfg.GACO_BUTTON_TEXT}](buttonurl:{latest['url']})")
        lines.append(f"[{cfg.DOWNLOAD_BUTTON_TEXT}](buttonurl:{latest['url']})")
        reply = "\n".join(lines)
        meta = {"reply_text": reply, "title": title, "url": latest["url"], "level": "season", "file_id": None}
        for key in _season_keys(title_kw, season):
            out[key] = meta

    # --- Movies / OVA / Special / ONA ---
    for kind in ("movie", "ova", "special", "ona"):
        subset = [e for e in entries if e["kind"] == kind]
        by_tp: dict[tuple, list] = defaultdict(list)
        for e in subset:
            by_tp[(e["keyword"], e.get("part"))].append(e)
        for (title_kw, part), items in by_tp.items():
            best = min(items, key=lambda e: (e["rank"], -e["message_id"]))
            title = best["title"]
            reply = build_reply_text(title, best["url"], best["url"])
            kind_label = kind.upper() if kind != "movie" else "Movie"
            if part is not None:
                header = f"{title} — {kind_label} Part {part}"
            else:
                header = f"{title} — {kind_label}"
            reply = header + "\n" + "\n".join(reply.split("\n")[1:])
            meta = {"reply_text": reply, "title": title, "url": best["url"], "level": kind, "file_id": None}
            for key in _type_keys(title_kw, kind, part):
                out[key] = meta
            # bare title also if this is the only movie for series? skip — series filter owns bare title

    return out


async def apply_granular_filters() -> dict:
    """Write granular filters into DB (does not delete series/alias filters)."""
    from app import database

    rows = await database.get_all_auto_index()
    mapping = build_granular_filter_map(rows)
    written = 0
    by_level: dict[str, int] = defaultdict(int)
    for key, meta in mapping.items():
        await database.add_filter(
            key,
            meta["reply_text"],
            file_id=meta.get("file_id"),
            keep_existing_file_id=True,  # keep sticker if alias/series already set
        )
        written += 1
        by_level[meta["level"]] += 1

    # attach series stickers onto season keys when possible
    topics = {t["keyword"]: t for t in await database.get_all_topics()}
    sticker_boost = 0
    for key, meta in mapping.items():
        if meta["level"] != "season":
            continue
        # extract series kw: remove trailing sN / season n
        m = re.match(r"^(.*?)(?:\s+s\d+|\s+season\s+\d+)$", key)
        series_kw = (m.group(1).strip() if m else "") or meta.get("title", "")
        series_kw = normalize_keyword(series_kw)
        topic = topics.get(series_kw)
        if topic and topic.get("sticker_file_id"):
            await database.add_filter(
                key,
                meta["reply_text"],
                file_id=topic["sticker_file_id"],
                keep_existing_file_id=False,
            )
            sticker_boost += 1

    total = len(await database.get_all_filter_keywords())
    stats = {
        "granular_keys": written,
        "by_level": dict(by_level),
        "season_stickers": sticker_boost,
        "filters_total": total,
        "index_rows": len(rows),
    }
    logger.info("Granular filters applied: %s", stats)
    return stats

"""Deterministic filename / caption parser for GACO media posts.

Knows common naming styles used in the files group — no LLM involved.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class ParsedMedia:
    title: str                 # display title, e.g. "Oshi No Ko"
    keyword: str               # search key, lowercase normalised
    season: Optional[int] = None
    episode: Optional[int] = None
    quality: Optional[str] = None
    label: str = ""            # short button label
    kind: str = "episode"      # "episode" | "movie" | "batch" | "unknown"


# Primary GACO style: S3 08 - Oshi No Ko [720p]
_RE_S_EP_DASH = re.compile(
    r"^S(?P<season>\d+)\s+(?P<episode>\d+)\s*[-–—]\s*(?P<title>.+)$",
    re.I,
)

# Compact: S01-11 Violet Evergarden [Dual] 480p @TAG
_RE_S_EP_COMPACT = re.compile(
    r"^S(?P<season>\d+)[- ]E?(?P<episode>\d+)\s+(?P<title>.+)$",
    re.I,
)

# [S02-E06] One Piece Live Action [480p] [Multi]
_RE_BRACKET_S_E = re.compile(
    r"^\[S(?P<season>\d+)[- ]?E(?P<episode>\d+)\]\s*(?P<title>.+)$",
    re.I,
)

# Hells Paradise S2 - 09 [1080p] [Sub]
_RE_TITLE_S_EP = re.compile(
    r"^(?P<title>.+?)\s+S(?P<season>\d+)\s*[-–—]\s*(?P<episode>\d+)\b(?P<rest>.*)$",
    re.I,
)

# Title S02E09
_RE_TITLE_SXXEXX = re.compile(
    r"^(?P<title>.+?)\s+S(?P<season>\d+)\s*E(?P<episode>\d+)\b(?P<rest>.*)$",
    re.I,
)

_RE_QUALITY = re.compile(
    r"\b(2160p|1080p|720p|480p|360p|4k|hdrip|web-?dl|bluray|bdrip|hd)\b",
    re.I,
)

_RE_EXT = re.compile(r"\.(mkv|mp4|avi|mov|ts|m4v)(\.mkv)?$", re.I)

# Trailing junk after the real title
_RE_STRIP_TRAIL = re.compile(
    r"""(?ix)
    \s* (
        \[ [^\]]* \]                                  # [Dual] [480p] [Multi]
      | @\S+                                          # @XANIME_UNIVERSE
      | \b(dual|multi|sub|subs|raw|batch)\b
      | \b(2160p|1080p|720p|480p|360p|4k|hdrip|web-?dl|bluray|bdrip|hd)\b
      | \b(10bit|8bit|x26[45]|hevc|avc|aac|ddp?5\.?1|6ch|5\.1)\b
    ) \s*
    """,
)

_RE_RELEASE_JUNK = re.compile(
    r"""(?ix)
    \b(
        \d{3,4}p | 4k | 10bit | 8bit | x26[45] | hevc | avc | aac | dts | truehd |
        bluray | bdrip | web-?dl | webrip | hdr | sdr | dual[- ]?audio |
        multi | subs? | eng(?:lish)? | chi(?:nese)? | hindi | jap(?:anese)? |
        ddp?5\.?1 | 6ch | 5\.1 | amzn | nf | dsnp | itunes | pahe | bone |
        hislordshiplinks | esub | gaco | dual | raw
    )\b
    | \[.*?\] | \(.*?\) | \{.*?\} | @\S+
    """
)

_MIN_KEYWORD_LEN = 3


def normalize_keyword(title: str) -> str:
    """Stable search key: lowercase, no punctuation, collapsed spaces."""
    t = (title or "").lower().replace("'", "").replace("'", "")
    t = re.sub(r"[^\w\s]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _strip_title_junk(raw: str) -> str:
    """Remove quality brackets, @tags, encode tokens from a title fragment."""
    t = (raw or "").strip()
    t = t.replace("_", " ")
    # Prefer spaces for dotted release names
    if t.count(".") >= 2:
        t = t.replace(".", " ")
    # Kill @handles early (whole token including underscores-as-spaces)
    t = re.sub(r"@\S+", " ", t)
    # Common channel / group leftovers after @strip
    t = re.sub(
        r"\b(xanime|universe|infinite\s*anime|gaco)\b",
        " ",
        t,
        flags=re.I,
    )
    # Repeatedly strip trailing junk tokens / brackets
    prev = None
    while prev != t:
        prev = t
        t = _RE_STRIP_TRAIL.sub(" ", t)
        t = re.sub(r"\s+", " ", t).strip(" -–—_|.")
    t = re.sub(r"\bmkv\b", " ", t, flags=re.I)
    # "Movie-1 Memory Doll" → "Memory Doll" (keep movie number optional)
    t = re.sub(r"^movie\s*[- ]?\d+\s+", "", t, flags=re.I)
    t = re.sub(r"\s+", " ", t).strip(" -–—_|.")
    return t


def _quality_from(*texts: str) -> Optional[str]:
    for text in texts:
        if not text:
            continue
        m = _RE_QUALITY.search(text)
        if m:
            q = m.group(1)
            return "1080p" if q.lower() == "hd" else q
    return None


def _label(title: str, season: Optional[int], episode: Optional[int], quality: Optional[str]) -> str:
    parts = []
    if season is not None and episode is not None:
        parts.append(f"S{int(season)} E{int(episode):02d}")
    elif episode is not None:
        parts.append(f"E{int(episode):02d}")
    if quality:
        parts.append(quality)
    if not parts:
        return (title or "Watch")[:40]
    return " · ".join(parts)


def _finish(title: str, season: Optional[int], episode: Optional[int],
            quality: Optional[str], kind: str) -> Optional[ParsedMedia]:
    title = _strip_title_junk(title)
    if not title:
        return None
    keyword = normalize_keyword(title)
    if len(keyword) < _MIN_KEYWORD_LEN:
        return None
    return ParsedMedia(
        title=title,
        keyword=keyword,
        season=season,
        episode=episode,
        quality=quality,
        label=_label(title, season, episode, quality),
        kind=kind,
    )


def parse_caption_title(caption: str) -> Optional[str]:
    """Use first non-empty caption line as a human title when present (movies)."""
    if not caption:
        return None
    for line in caption.replace("\\n", "\n").splitlines():
        line = line.strip()
        if not line:
            continue
        line = re.sub(r"\[.*?\]", " ", line)
        line = re.sub(r"\bGACO\b", " ", line, flags=re.I)
        line = re.sub(r"\s+", " ", line).strip(" -–—")
        if len(line) >= 2:
            return line
    return None


def parse_media(file_name: str, caption: str = "") -> Optional[ParsedMedia]:
    """Parse a posted file into structured metadata, or None if unusable."""
    name = (file_name or "").strip()
    name = _RE_EXT.sub("", name)
    quality_hint = _quality_from(file_name or "", caption or "")

    if not name and not caption:
        return None

    candidates = [name] if name else []
    cap_title = parse_caption_title(caption)
    if cap_title:
        candidates.append(cap_title)

    for text in candidates:
        text = text.strip()
        if not text:
            continue

        def _kind_for(blob: str, default: str = "episode") -> str:
            b = blob.lower()
            if re.search(r"\b(ova|oav)\b", b):
                return "ova"
            if re.search(r"\b(special|tokubetsu)\b", b) or re.search(r"\bsp\d*\b", b):
                return "special"
            if re.search(r"\bona\b", b):
                return "ona"
            if re.search(r"\b(movie|film|gekijouban)\b", b):
                return "movie"
            return default

        m = _RE_S_EP_DASH.match(text)
        if m:
            q = quality_hint or _quality_from(m.group("title"))
            kind = _kind_for(text)
            return _finish(m.group("title"), int(m.group("season")), int(m.group("episode")), q, kind)

        m = _RE_BRACKET_S_E.match(text)
        if m:
            q = quality_hint or _quality_from(m.group("title"))
            return _finish(m.group("title"), int(m.group("season")), int(m.group("episode")), q, _kind_for(text))

        m = _RE_S_EP_COMPACT.match(text)
        if m:
            q = quality_hint or _quality_from(m.group("title"))
            return _finish(m.group("title"), int(m.group("season")), int(m.group("episode")), q, _kind_for(text))

        m = _RE_TITLE_S_EP.match(text)
        if m:
            q = quality_hint or _quality_from(m.group("rest"), m.group("title"))
            return _finish(m.group("title"), int(m.group("season")), int(m.group("episode")), q, _kind_for(text))

        m = _RE_TITLE_SXXEXX.match(text)
        if m:
            q = quality_hint or _quality_from(m.group("rest"), m.group("title"))
            return _finish(m.group("title"), int(m.group("season")), int(m.group("episode")), q, _kind_for(text))

    # Movie / free-form fallback: caption title preferred, else cleaned filename
    raw_title = cap_title
    if not raw_title and name:
        cleaned = name.replace(".", " ").replace("_", " ")
        cleaned = _RE_RELEASE_JUNK.sub(" ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" -–—")
        raw_title = cleaned if len(cleaned) >= 2 else None

    if not raw_title:
        return None

    blob = f"{file_name or ''} {caption or ''} {raw_title}"
    kind = "movie"
    if re.search(r"\b(ova|oav)\b", blob, re.I):
        kind = "ova"
    elif re.search(r"\b(special|tokubetsu)\b", blob, re.I) or re.search(r"\bsp\d*\b", blob, re.I):
        kind = "special"
    elif re.search(r"\bona\b", blob, re.I):
        kind = "ona"
    return _finish(raw_title, None, None, quality_hint, kind)

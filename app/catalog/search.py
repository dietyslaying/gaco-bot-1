"""Multi-stage anime search: exact, normalized, partial, fuzzy, auto-index."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from thefuzz import fuzz, process

from app.catalog.parser import normalize_keyword

# Season/episode/type granular keys — excluded from fuzzy candidate pool
_GRANULAR_RE = re.compile(
    r"(?:\bs\d+\b|\be\d+\b|\bseason\b|\bepisode\b|\b\d+x\d+\b|"
    r"\bmovie\b|\bova\b|\bspecial\b|\bona\b|\bpart\b)",
    re.I,
)

# Cache: short alias → primary series keyword
_ALIAS_PRIMARY: dict[str, str] = {}
_ALIAS_BUILT = False
_KEYWORDS_CACHE: list[str] = []
_KEYWORDS_TS = 0.0


@dataclass
class SearchHit:
    kind: str  # exact | partial | fuzzy | auto_index
    keyword: Optional[str] = None
    filter_data: Optional[dict] = None
    score: float = 0
    suggestions: list[str] = None
    auto_results: list[dict] = None

    def __post_init__(self):
        if self.suggestions is None:
            self.suggestions = []
        if self.auto_results is None:
            self.auto_results = []


def is_granular_key(kw: str) -> bool:
    return bool(_GRANULAR_RE.search(kw or ""))


async def _ensure_alias_map():
    global _ALIAS_BUILT, _ALIAS_PRIMARY
    if _ALIAS_BUILT:
        return
    from app import database
    from app.catalog.aliases import CURATED, expand_all, aliases_for

    topics = await database.get_all_topics()
    series = [
        {"title": t.get("title") or t["keyword"], "keyword": normalize_keyword(t["keyword"])}
        for t in topics
        if t.get("keyword")
    ]
    # Fast path: curated short names → primary
    primary_set = {s["keyword"] for s in series}
    alias_map: dict[str, str] = {}
    for s in series:
        for a in aliases_for(s["title"], s["keyword"]):
            alias_map.setdefault(a, s["keyword"])
    for key, vals in CURATED.items():
        pk = normalize_keyword(key)
        # map to existing topic primary if present
        target = pk if pk in primary_set else None
        if not target:
            for s in series:
                if pk in s["keyword"] or s["keyword"] in pk:
                    target = s["keyword"]
                    break
        if not target:
            target = pk
        alias_map.setdefault(pk, target)
        for v in vals:
            alias_map.setdefault(normalize_keyword(v), target)
    # keep expand_all for title-derived aliases on topics only (small set)
    alias_map.update(expand_all(series))
    _ALIAS_PRIMARY = alias_map
    _ALIAS_BUILT = True


def rewrite_query_with_series_alias(q: str) -> list[str]:
    """jjk s1 e1 → jujutsu kaisen s1 e1 using alias map."""
    out = [q]
    if not q or not _ALIAS_PRIMARY:
        return out
    # longest alias prefix first
    for alias in sorted(_ALIAS_PRIMARY.keys(), key=len, reverse=True):
        if len(alias) < 2:
            continue
        primary = _ALIAS_PRIMARY[alias]
        if alias == primary:
            continue
        if q == alias:
            out.append(primary)
        elif q.startswith(alias + " "):
            out.append(primary + q[len(alias):])
    # de-dupe
    seen = set()
    res = []
    for x in out:
        if x not in seen:
            seen.add(x)
            res.append(x)
    return res


def normalize_query(raw: str) -> str:
    """Normalize user input for matching (seasons, eps, punctuation)."""
    q = (raw or "").strip().lower()
    q = q.replace("'", "").replace("'", "")
    # common separators
    q = q.replace(":", " ").replace(";", " ").replace("_", " ").replace("-", " ")
    q = re.sub(r"[\[\]\(\)\{\}]", " ", q)

    # season / episode language → compact tokens
    q = re.sub(r"\bseasons?\s*(\d+)\b", r"s\1", q)
    q = re.sub(r"\beps?(?:isode)?s?\s*(\d+)\b", r"e\1", q)
    q = re.sub(r"\bep\.?\s*(\d+)\b", r"e\1", q)
    q = re.sub(r"\bpart\s*(\d+)\b", r"part \1", q)

    # S01E02 / s1e2 / 1x02
    q = re.sub(r"\bs(\d{1,2})\s*e(\d{1,3})\b", r"s\1 e\2", q)
    q = re.sub(r"\b(\d{1,2})\s*x\s*(\d{1,3})\b", r"s\1 e\2", q)

    # zero-pad cleanup: s01 → s1, e08 → e8 (also keep padded variants later)
    def _strip_zero(m):
        return f"{m.group(1)}{int(m.group(2))}"

    q = re.sub(r"\b(s)0*(\d+)\b", _strip_zero, q)
    q = re.sub(r"\b(e)0*(\d+)\b", _strip_zero, q)

    # type words
    q = re.sub(r"\b(movies?|films?)\b", "movie", q)
    q = re.sub(r"\b(ovas?|oavs?)\b", "ova", q)
    q = re.sub(r"\b(specials?|sp)\b", "special", q)

    q = normalize_keyword(q)
    return q


def query_variants(raw: str) -> list[str]:
    """Ordered unique query forms to try as exact filter keys."""
    base = normalize_query(raw)
    variants = [base]
    if not base:
        return []

    # also try zero-padded s/e
    m = re.search(r"\bs(\d+)\s+e(\d+)\b", base)
    if m:
        s, e = int(m.group(1)), int(m.group(2))
        variants.append(re.sub(r"\bs\d+\s+e\d+\b", f"s{s:02d} e{e:02d}", base))
        variants.append(re.sub(r"\bs\d+\s+e\d+\b", f"s{s}e{e}", base))
        variants.append(re.sub(r"\bs\d+\s+e\d+\b", f"s{s:02d}e{e:02d}", base))
        variants.append(re.sub(r"\bs\d+\s+e\d+\b", f"{s}x{e:02d}", base))

    m = re.search(r"\bs(\d+)\b(?!\s*e)", base)
    if m and " e" not in base:
        s = int(m.group(1))
        variants.append(re.sub(r"\bs\d+\b", f"s{s:02d}", base))
        variants.append(re.sub(r"\bs\d+\b", f"season {s}", base))

    # title without type suffix
    for suf in (" movie", " ova", " special", " ona", " film"):
        if base.endswith(suf):
            variants.append(base[: -len(suf)].strip())

    # raw lower stripped
    variants.append(normalize_keyword(raw))

    # de-dupe preserve order
    seen = set()
    out = []
    for v in variants:
        v = (v or "").strip()
        if v and v not in seen:
            seen.add(v)
            out.append(v)
    return out


def partial_matches(query: str, keywords: list[str], limit: int = 8) -> list[tuple[str, float]]:
    """Incomplete search: prefix/substring + token coverage (word-safe)."""
    q = normalize_query(query)
    if not q or len(q) < 2:
        return []
    tokens = [t for t in q.split() if len(t) >= 1]
    scored: list[tuple[str, float]] = []

    for kw in keywords:
        if not kw or len(kw) < 2:
            continue
        if re.match(r"^[\d\s]+", kw) or not re.search(r"[a-z]{3,}", kw):
            continue
        score = 0.0
        if q == kw:
            score = 100
        elif q in kw:
            score = 88 + max(0, 10 - (len(kw) - len(q)))
        elif kw in q and len(kw) >= 4:
            score = 80
        else:
            # Use extract-style scoring only when first token aligns (cheap gate)
            kw_words = kw.split()
            if tokens and len(tokens[0]) >= 3:
                first = tokens[0]
                if not any(
                    w == first or w.startswith(first) or first.startswith(w[:3]) or fuzz.ratio(first, w) >= 80
                    for w in kw_words
                    if len(w) >= 3
                ):
                    continue
            ts = float(fuzz.token_set_ratio(q, kw))
            score = ts
            if any(t.startswith(tokens[-1]) or tokens[-1].startswith(t[:3]) for t in kw_words if len(tokens[-1]) >= 3 and len(t) >= 3):
                score += 3

        if score >= 70:
            scored.append((kw, score))

    scored.sort(key=lambda x: (-x[1], len(x[0])))
    seen = set()
    out = []
    for kw, sc in scored:
        if kw in seen:
            continue
        seen.add(kw)
        out.append((kw, sc))
        if len(out) >= limit:
            break
    return out


def fuzzy_matches(query: str, keywords: list[str], limit: int = 5) -> list[tuple[str, float]]:
    q = normalize_query(query)
    if not q or len(q) < 2:
        return []
    # Short queries need higher confidence
    cutoff = 78 if len(q) <= 4 else (72 if len(q) <= 8 else 65)
    results = process.extract(
        q,
        keywords,
        scorer=fuzz.WRatio,
        limit=max(limit * 12, 60),
    )
    out = []
    seen = set()
    q_alpha = re.sub(r"[^a-z]", "", q)
    q_words = [w for w in q.split() if len(w) >= 2]
    for kw, score, _ in results:
        if score < cutoff or kw in seen:
            continue
        if len(kw) <= 2 and score < 95:
            continue
        if not re.search(r"[a-z]{3,}", kw):
            continue
        if re.match(r"^[\d\s]+", kw):
            continue
        kw_words = [w for w in kw.split() if len(w) >= 2]
        if q_words and kw_words:
            first = q_words[0]
            if len(first) >= 3:
                ok_token = any(
                    w.startswith(first[:3])
                    or first.startswith(w[:3])
                    or fuzz.ratio(first, w) >= 70
                    for w in kw_words
                )
                if not ok_token:
                    continue
        kw_alpha = re.sub(r"[^a-z]", "", kw)
        if q_alpha and kw_alpha and fuzz.partial_ratio(q_alpha, kw_alpha) < 70:
            continue
        seen.add(kw)
        out.append((kw, float(score)))
        if len(out) >= limit:
            break
    return out


async def resolve_search(raw_query: str) -> SearchHit:
    """Full search pipeline against filters + auto_index."""
    from app import database

    await _ensure_alias_map()

    # Build query variants, including series-alias rewrites (jjk s1 e1 → jujutsu kaisen s1 e1)
    base_variants = query_variants(raw_query)
    variants: list[str] = []
    for v in base_variants:
        variants.extend(rewrite_query_with_series_alias(v))
    # de-dupe
    seen_v = set()
    uniq_variants = []
    for v in variants:
        if v and v not in seen_v:
            seen_v.add(v)
            uniq_variants.append(v)
    variants = uniq_variants

    # 1) Exact filter (all variants)
    for v in variants:
        data = await database.get_filter(v)
        if data:
            return SearchHit(kind="exact", keyword=v, filter_data=data, score=100)

    # 1b) If user asked for series+season/ep but we only have the series card, deliver series
    probe_n = normalize_query(raw_query)
    for cand in rewrite_query_with_series_alias(probe_n):
        # strip trailing season/ep/type → series primary
        stripped = re.sub(
            r"\s+(s\d+.*|season\s+\d+.*|e\d+.*|episode\s+\d+.*|movie|ova|special|ona|part\s+\d+)\s*$",
            "",
            cand,
            flags=re.I,
        ).strip()
        if stripped and stripped != cand:
            data = await database.get_filter(stripped)
            if data:
                return SearchHit(kind="exact", keyword=stripped, filter_data=data, score=92)

    import time as _time
    global _KEYWORDS_CACHE, _KEYWORDS_TS
    now = _time.monotonic()
    if not _KEYWORDS_CACHE or now - _KEYWORDS_TS > 60:
        _KEYWORDS_CACHE = [
            k for k in await database.get_all_filter_keywords()
            if k and len(k.strip()) >= 2
        ]
        _KEYWORDS_TS = now
    keywords = _KEYWORDS_CACHE
    # Fuzzy/partial prefer series + short aliases; still allow granular for partial season queries
    series_keys = [
        k for k in keywords
        if not is_granular_key(k)
        and len(k) >= 3
        and not re.match(r"^[\d\s]+", k)
        and not re.match(r"^s\d", k)
        and re.search(r"[a-z]{3,}", k)
    ]

    # 2) Partial / incomplete (series-level pool first for speed + quality)
    probe = normalize_query(raw_query)
    partial_pool = series_keys
    # if query looks season/ep specific, include granular keys for that title
    if is_granular_key(probe) or re.search(r"\bs\d|\be\d|\bseason\b|\bmovie\b|\bova\b", probe):
        partial_pool = keywords

    for cand in rewrite_query_with_series_alias(probe):
        partial = partial_matches(cand, partial_pool, limit=8)
        if partial:
            best_kw, best_sc = partial[0]
            if best_sc >= 85:
                data = await database.get_filter(best_kw)
                if data:
                    return SearchHit(kind="partial", keyword=best_kw, filter_data=data, score=best_sc)
            if best_sc >= 62:
                if len(partial) == 1 and best_sc >= 72:
                    data = await database.get_filter(best_kw)
                    if data:
                        return SearchHit(kind="partial", keyword=best_kw, filter_data=data, score=best_sc)
                return SearchHit(
                    kind="fuzzy",
                    score=best_sc,
                    suggestions=[kw for kw, _ in partial[:5]],
                )

    # 3) Fuzzy typos against series-level keys (less noise)
    for cand in rewrite_query_with_series_alias(probe):
        fuzzy = fuzzy_matches(cand, series_keys, limit=5)
        if fuzzy:
            best_kw, best_sc = fuzzy[0]
            if best_sc >= 88:
                data = await database.get_filter(best_kw)
                if data:
                    return SearchHit(kind="fuzzy", keyword=best_kw, filter_data=data, score=best_sc)
            if best_sc >= 65:
                return SearchHit(
                    kind="fuzzy",
                    score=best_sc,
                    suggestions=[kw for kw, _ in fuzzy],
                )

    # 4) Auto-index fallback (file names)
    q = normalize_query(raw_query) or raw_query.strip().lower()
    for cand in rewrite_query_with_series_alias(q):
        auto = await database.search_auto_index(cand)
        if auto:
            return SearchHit(kind="auto_index", auto_results=auto, score=40)

    return SearchHit(kind="none", score=0)


def reset_alias_cache():
    """Call after rebuild/expand so search picks up new aliases."""
    global _ALIAS_BUILT, _ALIAS_PRIMARY, _KEYWORDS_CACHE, _KEYWORDS_TS
    _ALIAS_BUILT = False
    _ALIAS_PRIMARY = {}
    _KEYWORDS_CACHE = []
    _KEYWORDS_TS = 0.0

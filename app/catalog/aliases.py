"""Anime search aliases: fan short names, JP/EN alternates, acronyms.

Sources: r/anime common abbreviations, MAL/fandom short names, JP romaji
short forms, and auto-derived variants from topic titles.
"""
from __future__ import annotations

import re
from typing import Iterable

from app.catalog.parser import normalize_keyword

# Primary keyword (as stored after normalize) → extra aliases
# Keys should match normalize_keyword(title) of the main filter when possible.
CURATED: dict[str, list[str]] = {
    # --- big titles ---
    "attack on titan": [
        "aot", "snk", "shingeki", "shingeki no kyojin", "shingeki no kyoujin",
        "attack on titan final season", "進撃の巨人",
    ],
    "jujutsu kaisen": [
        "jjk", "jujutsu", "jujutsu kaisen 0", "呪術廻戦",
    ],
    "demon slayer": [
        "kny", "kimetsu", "kimetsu no yaiba", "demon slayer kimetsu", "鬼滅の刃",
        "ds",
    ],
    "my hero academia": [
        "mha", "bnha", "boku no hero", "boku no hero academia", "hero academia",
        "僕のヒーローアカデミア",
    ],
    "mha vigilantes": [
        "vigilantes", "mha v", "boku no hero vigilantes", "illegals",
    ],
    "one piece": [
        "op", "wanpis", "ワンピース", "onepiece",
    ],
    "one piece live action": [
        "op la", "one piece la", "opla", "one piece netflix",
    ],
    "one punch man": [
        "opm", "one punch", "ワンパンマン",
    ],
    "chainsaw man": [
        "csm", "chainsaw", "チェンソーマン",
    ],
    "oshi no ko": [
        "onk", "oshinoko", "oshi noko", "【推しの子】", "推しの子",
    ],
    "solo leveling": [
        "sl", "ore dake level up", "na honjaman level up", "나 혼자만 레벨업",
    ],
    "frieren": [
        "sousou no frieren", "frieren beyond journeys end", "frieren beyond journey's end",
        "葬送のフリーレン", "sousou",
    ],
    "spy x family": [
        "sxf", "spy family", "spyfamily", "スパイファミリー",
    ],
    "steins gate": [
        "steins;gate", "s;g", "steinsgate", "シュタインズ・ゲート",
    ],
    "rezero starting life in another world": [
        "rezero", "re zero", "re:zero", "re zero kara", "re:zero kara hajimeru",
        "リゼロ",
    ],
    "mushoku tensei jobless reincarnation": [
        "mushoku tensei", "mushoku", "jobless reincarnation", "mt",
        "無職転生",
    ],
    "that time i got reincarnated as a slime": [
        "tensura", "slime", "tensei shitara slime", "关于我转生变成史莱姆这档事",
        "転スラ",
    ],
    "classroom of the elite": [
        "cote", "youkoso jitsuryoku", "youkoso jitsuryoku shijou shugi",
        "ようこそ実力至上主義の教室へ",
    ],
    "kaguya sama love is war": [
        "kaguya", "kaguya sama", "love is war", "kaguya-sama",
        "かぐや様は告らせたい",
    ],
    "jojos bizarre adventure": [
        "jojo", "jjba", "jojos", "jojo bizarre", "ジョジョ",
    ],
    "naruto": [
        "naruto shippuden", "shippuden", "ナルト", "boruto",  # boruto often searched nearby
    ],
    "hells paradise": [
        "jigokuraku", "hell paradise", "地獄楽",
    ],
    "record of ragnarok": [
        "ror", "shuumatsu no valkyrie", "shuumatsu", "終末のワルキューレ",
    ],
    "tokyo revengers": [
        "tr", "tokrev", "東京リベンジャーズ",
    ],
    "tower of god": [
        "tog", "kami no tou", "신의 탑",
    ],
    "vinland saga": [
        "vinland", "ヴィンランド・サガ",
    ],
    "violet evergarden": [
        "ve", "ヴァイオレット・エヴァーガーデン",
    ],
    "ghost in the shell": [
        "gits", "kokaku kidotai", "攻殻機動隊",
    ],
    "gintama": [
        "gin tama", "銀魂",
    ],
    "golden kamuy": [
        "gk", "ゴールデンカムイ",
    ],
    "grand blue": [
        "grandblue", "grand blue dreaming", "ぐらんぶる",
    ],
    "fire force": [
        "enen no shouboutai", "enen", "炎炎ノ消防隊",
    ],
    "doctor stone dr stone": [
        "dr stone", "dr. stone", "drstone", "doctor stone", "ドクターストーン",
    ],
    "dorohedoro": [
        "doro", "ドロヘドロ",
    ],
    "kaiju no 8": [
        "kn8", "kaiju 8", "kaiju no.8", "kaijuu 8 gou", "怪獣8号",
    ],
    "sailor moon": [
        "sm", "bishoujo senshi sailor moon", "美少女戦士セーラームーン",
    ],
    "sakamoto days": [
        "サカモトデイズ",
    ],
    "undead unluck": [
        "uu", "アンデッドアンラック",
    ],
    "wind breaker": [
        "windbreaker", "ウィンドブレイカー",
    ],
    "welcome to demon school iruma kun": [
        "iruma kun", "iruma", "mairimashita iruma kun", "魔入りました！入間くん",
    ],
    "the beginning after the end": [
        "tbate", "beginning after the end",
    ],
    "ascendance of a bookworm": [
        "honzuki", "bookworm", "honzuki no gekokujou", "本好きの下剋上",
    ],
    "saga of tanya the evil": [
        "tanya", "youjo senki", "tanya the evil", "幼女戦記",
    ],
    "heaven officials blessing": [
        "tgcf", "tian guan ci fu", "tianguan cifu", "天官赐福",
    ],
    "toilet bound hanako kun": [
        "hanako kun", "hanako", "jibaku shounen hanako kun", "地縛少年花子くん",
    ],
    "the ancient magus bride": [
        "mahoutsukai no yome", "ancient magus bride", "魔法使いの嫁",
    ],
    "rent a girlfriend": [
        "kanokari", "kanojo okarishimasu", "彼女、お借りします",
    ],
    "umamusume": [
        "uma musume", "pretty derby", "ウマ娘",
    ],
    "lord of mysteries": [
        "lotm", "lordofthemysteries",
    ],
    "100 girlfriends who really love you": [
        "hyakkano", "100 girlfriends", "the 100 girlfriends",
        "kimi no koto ga daidaidaidaidaisuki na 100 nin no kanojo",
    ],
    "campfire cooking in another world with my absurd skill": [
        "tondemo skill", "campfire cooking", "とんでもスキルで異世界放浪メシ",
    ],
    "farming life in another world": [
        "nonbiri", "farming life", "のんびり農",
    ],
    "trapped in a dating sim": [
        "otome game", "trapped in a dating sim the world of otome games",
        "乙女ゲー世界はモブに厳しい世界です",
    ],
    "anohana": [
        "ano hi mita hana", "ano hi mita hana no namae wo bokutachi wa mada shiranai",
        "あの花",
    ],
    "to your eternity": [
        "fumetsu no anata e", "不滅のあなたへ",
    ],
    "chained soldier": [
        "mato seihei no slave", "mato seihei", "魔都精兵のスレイブ",
    ],
    "mf ghost": [
        "mfghost", "mf ゴースト",
    ],
    "fate series": [
        "fate", "type moon", "fate stay night", "fsn", "fate zero", "fgo",
    ],
    "fate strange fake": [
        "strange fake", "fsf",
    ],
    "ace of the diamond diamond no ace": [
        "diamond no ace", "daiya no ace", "ace of diamond", "ダイヤのA",
    ],
    "blue orchestra ao no orchestra": [
        "ao no orchestra", "blue orchestra", "青のオーケストラ",
    ],
    "kekkai sensen blood blockade battlefront": [
        "kekkai sensen", "blood blockade battlefront", "bbb", "血界戦線",
    ],
    "den noh coil dennou coil": [
        "dennou coil", "den noh coil", "電脳コイル",
    ],
    "hitori no shita the outcast": [
        "hitori no shita", "the outcast", "一人之下",
    ],
    "kill blue kill ao": [
        "kill blue", "kill ao", "キルアオ",
    ],
    "odd taxi oddtaxi": [
        "oddtaxi", "odd taxi", "オッドタクシー",
    ],
    "tsuredure children tsurezure children": [
        "tsurezure children", "tsuredure children", "徒然チルドレン",
    ],
    "blades of the guardians biaoren": [
        "biaoren", "blades of the guardians",
    ],
    "devil may cry": [
        "dmc", "devil may cry anime",
    ],
    "pokemon": [
        "pocket monsters", "pokémon", "ポケモン",
    ],
    "pokemon 2023": [
        "pokemon horizons", "pocket monsters 2023",
    ],
    "ranma 1 2": [
        "ranma", "ranma ½", "ranma half", "らんま1/2",
    ],
    "kingdom": [
        "キングダム",
    ],
    "kaiji": [
        "逆境無頼カイジ", "gyakkyou burai kaiji",
    ],
    "liar game": [
        "ライアーゲーム",
    ],
    "ne zha 2019": [
        "nezha", "ne zha", "哪吒", "nezha 2019",
    ],
    "ne zha 2": [
        "nezha 2", "ne zha two", "哪吒2",
    ],
    "new gods nezha reborn": [
        "nezha reborn", "new gods",
    ],
    "trigun stampede": [
        "trigun", "トライガン",
    ],
    "trigun stargaze": [
        "stargaze", "trigun stampede stargaze",
    ],
    "wisteria wand and sword": [  # if mis-key
        "wistoria",
    ],
    "wistoria wand and sword": [
        "wistoria", "tsue to tsurugi no wistoria",
    ],
    "witch hat atelier": [
        "tongari boushi no atelier", "atelier of witch hat",
    ],
    "yamada and the seven witches": [
        "yamada kun and the seven witches", "yamada-kun",
    ],
    "you and i are polar opposites": [
        "polar opposites",
    ],
    "the fragrant flower blooms with dignity": [
        "kaoru hana wa rin to saku", "fragrant flower",
    ],
    "the cafe terrace and its goddesses": [
        "megami no cafe terrace", "cafe terrace",
    ],
    "i got a cheat skill in another world": [
        "cheat skill", "isekai de cheat skill",
    ],
    "am i actually the strongest": [
        "jitsuwa ore saikyou",
    ],
    "angel nextdoor spoils me rotten": [
        "otonari no tenshi", "angel next door",
    ],
    "fist of the north star": [
        "hokuto no ken", "fotns", "北斗の拳",
    ],
    "sentenced to be a hero": [
        "yuusha ni narenakatta ore wa",
    ],
    "daemons of the shadow realm": [
        "yami no sometsuke",
        "daemons shadow realm",
    ],
    "daily life of the immortal king": [
        "xian wang de richang shenghuo", "immortal king",
    ],
    "dusk maiden of amnesia": [
        "tasogare otome x amnesia",
    ],
    "eden of the east": [
        "higashi no eden",
    ],
    "kiznaiver": [
        "キズナイーバー",
    ],
    "isekai quartet": [
        "isekai 4koma",
    ],
    "spy classroom": [
        "spy room", "spy kyoushitsu",
    ],
    "gachiakuta": [
        "ガチアクタ",
    ],
}

# Skip auto-aliases that are too generic / collide hard
_BLOCKLIST = {
    "the", "a", "an", "of", "and", "or", "in", "to", "as", "no", "kun", "sama",
    "san", "chan", "movie", "movies", "anime", "series", "season", "part",
    "vol", "volume", "ova", "ona", "special", "ongoing", "new", "my", "me",
    "i", "you", "is", "are", "with", "for", "on", "at", "from", "by", "be",
    "got", "who", "its", "it", "end", "life", "world", "love", "war", "man",
    "girl", "boy", "days", "blue", "red", "black", "white", "school", "game",
}


def _split_title_parts(title: str) -> list[str]:
    """Split 'EN | JP' style titles and clean."""
    parts = re.split(r"[|｜/／·•]+", title or "")
    return [p.strip() for p in parts if p.strip()]


def auto_aliases_from_title(title: str, keyword: str) -> set[str]:
    """Derive extra search keys from a display title / keyword."""
    out: set[str] = set()
    base = normalize_keyword(keyword or title)
    if base:
        out.add(base)

    for part in _split_title_parts(title) + [keyword, title]:
        n = normalize_keyword(part or "")
        if not n or n in _BLOCKLIST:
            continue
        out.add(n)

        # strip leading articles
        for art in ("the ", "a ", "an "):
            if n.startswith(art):
                out.add(n[len(art):])

        # compact (no spaces)
        compact = n.replace(" ", "")
        if len(compact) >= 3:
            out.add(compact)

        # initials (e.g. attack on titan → aot)
        words = [w for w in n.split() if w not in _BLOCKLIST and len(w) > 0]
        if 2 <= len(words) <= 8:
            initials = "".join(w[0] for w in words if w[0].isalpha())
            if 2 <= len(initials) <= 6:
                out.add(initials)

        # first significant word if long enough and distinctive
        if words and len(words[0]) >= 5:
            out.add(words[0])

        # first two words
        if len(words) >= 2:
            pair = f"{words[0]} {words[1]}"
            if len(pair) >= 5:
                out.add(pair)

    # number / punctuation variants
    for a in list(out):
        out.add(a.replace(" no ", " "))
        out.add(re.sub(r"\s+", " ", a))
        if "1 2" in a:
            out.add(a.replace("1 2", "1/2"))
            out.add(a.replace("1 2", "½"))
        if "no 8" in a:
            out.add(a.replace("no 8", "no.8"))
            out.add(a.replace("no 8", "8"))

    # drop junk
    cleaned = set()
    for a in out:
        a = normalize_keyword(a)
        if not a or a in _BLOCKLIST:
            continue
        if len(a) < 2:
            continue
        # avoid ultra-short 2-letter unless curated later
        if len(a) == 2 and a not in {"op", "sl", "tr", "uu", "ve", "gk", "mt", "ds"}:
            continue
        cleaned.add(a)
    return cleaned


def aliases_for(title: str, keyword: str) -> list[str]:
    """All aliases for a series including curated + auto (excludes primary keyword optionally)."""
    primary = normalize_keyword(keyword or title)
    found: set[str] = set()
    found |= auto_aliases_from_title(title, keyword)

    # match curated by primary or any overlapping auto key
    for key, vals in CURATED.items():
        ck = normalize_keyword(key)
        if ck == primary or ck in found or primary in {normalize_keyword(v) for v in vals}:
            found.add(ck)
            for v in vals:
                found.add(normalize_keyword(v))

    # also try fuzzy: curated key contained in primary
    for key, vals in CURATED.items():
        ck = normalize_keyword(key)
        if ck in primary or primary in ck:
            found.add(ck)
            for v in vals:
                found.add(normalize_keyword(v))

    found.discard("")
    # keep primary in set
    if primary:
        found.add(primary)
    return sorted(found)


def expand_all(series: Iterable[dict]) -> dict[str, str]:
    """
    series items: {title, keyword}
    returns alias_keyword → primary_keyword
    """
    alias_to_primary: dict[str, str] = {}
    # longer / more specific primaries win if conflict — process longer titles last so they override? 
    # Prefer first-seen primary for collisions to avoid OP→opening style issues; curated shorts map explicitly.
    items = list(series)
    items.sort(key=lambda s: len(normalize_keyword(s.get("keyword") or s.get("title") or "")), reverse=True)

    for s in items:
        title = s.get("title") or ""
        keyword = normalize_keyword(s.get("keyword") or title)
        if not keyword:
            continue
        for alias in aliases_for(title, keyword):
            if alias == keyword:
                alias_to_primary.setdefault(alias, keyword)
                continue
            # don't steal another series' primary keyword
            if alias in {normalize_keyword(x.get("keyword") or "") for x in items if x is not s}:
                # only allow if curated explicitly points here
                curated_ok = False
                for key, vals in CURATED.items():
                    if normalize_keyword(key) == keyword and normalize_keyword(alias) in {
                        normalize_keyword(v) for v in vals
                    }:
                        curated_ok = True
                        break
                if not curated_ok:
                    continue
            # first mapping wins for non-primary aliases
            alias_to_primary.setdefault(alias, keyword)

    return alias_to_primary

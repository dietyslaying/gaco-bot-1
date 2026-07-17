"""Rule-based catalogue + cover-server settings (no LLM)."""
import os

# Master switch: auto-refresh filters on new files / covers
CATALOG_ENABLED = os.getenv("CATALOG_ENABLED", "true").lower() in ("1", "true", "yes", "on")

QUALITY_PRIORITY = [
    q.strip().lower()
    for q in os.getenv(
        "CATALOG_QUALITY_PRIORITY",
        "1080p,2160p,4k,720p,hdrip,480p,360p",
    ).split(",")
    if q.strip()
]

# Classic dual-button format (matches GACO UX screenshot):
#   Here you go!
#   [✨ GACO ✨](buttonurl:…)
#   [⛩ DOWNLOAD ⛩](buttonurl:…)
REPLY_TEXT = os.getenv("CATALOG_REPLY_TEXT", "Here you go!")
GACO_BUTTON_TEXT = os.getenv("CATALOG_GACO_BUTTON", "✨ GACO ✨")
DOWNLOAD_BUTTON_TEXT = os.getenv("CATALOG_DOWNLOAD_BUTTON", "⛩ DOWNLOAD ⛩")

# If set, DOWNLOAD always points here; else uses topic/cover URL.
DEFAULT_DOWNLOAD_URL = os.getenv("CATALOG_DOWNLOAD_URL", "")

# Prefer sticker covers; fall back to photo message if conversion fails.
USE_STICKERS = os.getenv("CATALOG_USE_STICKERS", "true").lower() in ("1", "true", "yes", "on")

# --- Cover server (Telethon user session) ---------------------------------
# Get api_id / api_hash from https://my.telegram.org
TELEGRAM_API_ID = int(os.getenv("TELEGRAM_API_ID", "0") or "0")
TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH", "")
TELEGRAM_SESSION = os.getenv("TELEGRAM_SESSION", "")  # StringSession

# Where the bot uploads stickers to obtain a reusable file_id (admin user id or a private channel).
# Defaults to first ADMIN if unset.
COVER_STORAGE_CHAT_ID = os.getenv("COVER_STORAGE_CHAT_ID", "")

# Delay between topics during backfill (seconds) to avoid floods.
BACKFILL_DELAY = float(os.getenv("CATALOG_BACKFILL_DELAY", "0.35"))

# Max topics per backfill run (0 = all)
BACKFILL_LIMIT = int(os.getenv("CATALOG_BACKFILL_LIMIT", "0") or "0")


def session_configured() -> bool:
    return bool(TELEGRAM_API_ID and TELEGRAM_API_HASH and TELEGRAM_SESSION)

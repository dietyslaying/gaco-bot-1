import os
from pathlib import Path

# Load project-root .env for local hosting (no-op if missing / already set)
try:
    from dotenv import load_dotenv
    _env_path = Path(__file__).resolve().parents[1] / ".env"
    load_dotenv(_env_path, override=False)
except ImportError:
    pass

# Bot config — set via environment / .env (never commit real tokens)
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
FILES_GROUP_ID = os.getenv("FILES_GROUP_ID", "")
REQUEST_GROUP_ID = os.getenv("REQUEST_GROUP_ID", "")
REQUEST_GROUP_URL = os.getenv("REQUEST_GROUP_URL", "")
ADMINS = [
    int(admin.strip())
    for admin in os.getenv("ADMINS", "").split(",")
    if admin.strip()
]
DATABASE_URL = os.getenv("DATABASE_URL")
REDIS_URL = os.getenv("REDIS_URL")

# Texts
START_MSG = """JOIN OUR CHANNEL TO USE THIS BOT FOR FREE ✨

STEP : 1 - JOIN CHANNEL
STEP : 2 - CLICK VERIFY"""

VERIFICATION_SUCCESS_MSG = """✅ *You're in!*

You can now search anime by sending me a name.

Examples: `One Piece` · `AOT` · `Naruto` · `JJK`"""

ASK_ANIME_MSG = """Send the name of the anime (English spelling works best).

Eg: One Piece"""

NOT_FOUND_MSG = """Unable to find this anime. Check your spelling and try again, or request it in our Request Group."""

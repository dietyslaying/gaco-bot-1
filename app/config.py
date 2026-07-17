import os

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
FLASK_SECRET = os.getenv("FLASK_SECRET", "change-me")

# Texts
START_MSG = """JOIN OUR CHANNEL TO USE THIS BOT FOR FREE ✨
                  
STEP : 1 - JOIN CHANNEL
STEP : 2 - CLICK VERIFY"""

VERIFICATION_SUCCESS_MSG = r"""_*Congratulations\!✨*_

_*You can now Download & Watch any ANIMES by simply sending me the Anime Name\!*_"""

ASK_ANIME_MSG = """Send the Name of the ANIME in Correct Spelling [English]

Eg: One Piece"""

NOT_FOUND_MSG = """Unable to Find this ANIME, Kindly Check Your Spelling & Try Again OR Request for this Anime in our Request Group"""

HELP_MSG_USER = """Demo Video with Description on how to use the Bot.
(Video pending definition)
Just send me any Anime name or Typos, and I'll find it!"""

HELP_MSG_ADMIN = """Demo Video with Description on how to use the Bot.
(Video pending definition)
/Stats - Shows Bot Statistics
/Broadcast - To Broadcast a message instantly to all Users.
/Ban <user_id> - To Ban Any Users from using the bot
/Unban <user_id> - To Unban
/Filter <Name> [Button](url) - to add an Anime Filter
/Delete <Name> - to delete an existing filter
/catalog - Filters + cover server (rebuild / backfill / on / off)
/admin - Open interactive Admin Panel
"""

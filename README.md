# gaco-bot

Telegram **anime filter / file-delivery bot** for GACO.

- Classic UX: **sticker/cover card** + **✨ GACO ✨** + **⛩ DOWNLOAD ⛩**
- **Catalogue** builds filters from the files group (no LLM)
- **Cover Server** uses a bot admin + **admin user session** to read every forum topic’s first message (pic + description) → sticker → filter

## Layout

```
app/
  bot.py                 # User-facing bot
  config.py
  database.py            # users, filters, auto_index, topics
  catalog/
    parser.py            # Filename → anime name
    builder.py           # Classic dual-button filters
    sticker.py           # Photo → WEBP sticker via bot
    cover_server.py      # Telethon topic walk + live covers
    config.py
  admin/web.py           # Flask dashboard
scripts/
  login_session.py       # Generate TELEGRAM_SESSION
  backfill_topics.py     # CLI full topic scan
  rebuild_catalog_sqlite.py
  start.sh / railway-start.sh
```

## How delivery looks

User types `One Piece` → bot sends:

1. Cover **sticker** (from topic first photo), or text if no cover yet  
2. Buttons: **✨ GACO ✨** · **⛩ DOWNLOAD ⛩**  
3. Default text: `Here you go!`

Same shape as manual:

```text
/filter One Piece [✨ GACO ✨](buttonurl:…)
[⛩ DOWNLOAD ⛩](buttonurl:…)
```

(optionally reply to a sticker so `file_id` is stored)

## Architecture

| Piece | Role |
|-------|------|
| **Bot** (admin in files group) | DMs, search, stickers, live index of new files/photos |
| **User session** (admin account StringSession) | List **all forum topics**, read first cover message, backfill |
| **Cover Server** (`cover_server.py`) | Named subsystem: topic → photo → sticker `file_id` → `topics` + `filters` |
| **Postgres** | `filters`, `auto_index`, `topics`, users, broadcasts |

## Setup

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

### Required env

- `BOT_TOKEN`, `FILES_GROUP_ID`, `ADMINS`, `DATABASE_URL`

### Cover Server (full topic access)

1. Open https://my.telegram.org → create app → `TELEGRAM_API_ID` / `TELEGRAM_API_HASH`  
2. Log in with an account that is **admin** of the files group:

   ```bash
   python scripts/login_session.py
   ```

3. Put printed `TELEGRAM_SESSION` in `.env`  
4. Start a private chat with the bot (or set `COVER_STORAGE_CHAT_ID`) so the bot can upload stickers  
5. Bot + user account both **admin** in the files group (forum topics)

### Run

```bash
python -m app.bot
python -m app.admin.web
# or: bash scripts/start.sh
```

### Backfill all topics

```bash
# CLI
python scripts/backfill_topics.py
python scripts/backfill_topics.py --force --limit 50

# or in Telegram (admin)
/catalog backfill
/catalog backfill force
```

### Other admin commands

| Command | Effect |
|---------|--------|
| `/catalog` | Status (index / topics / session) |
| `/catalog rebuild` | Rebuild filters from auto_index + topics |
| `/catalog on` / `off` | Auto-update toggle |
| `/filter` `/delete` `/filters` | Manual filters |
| `/broadcast` `/ban` `/stats` | Ops |

## Data model (new)

**`topics`** — one row per forum topic:

- `thread_id`, `title`, `keyword`  
- `cover_message_id`, `cover_url`, `description`  
- `sticker_file_id`, `photo_file_id`  
- `gaco_url`, `download_url`  

Filters use `file_id` = sticker (fallback photo) + dual `buttonurl` lines.

## Notes

- Bot API alone cannot scrape full topic history → **user session is required** for full backfill.  
- Live: new topic photos still get covers via the bot path when possible.  
- `TELEGRAM_SESSION` is a **full account secret** — never commit it.  
- Rate-limit backfill with `CATALOG_BACKFILL_DELAY` (default `0.35s`).

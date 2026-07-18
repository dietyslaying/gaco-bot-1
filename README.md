# gaco-bot

Telegram **anime filter / file-delivery bot** for GACO.

- Search by name, short form, season/episode  
- Admin tools **inside Telegram** (`/help`, `/stats`, `/catalog`, …)  
- **No web dashboard** — bot only  
- Deploy on **Railway** (or any host) so it stays online when your laptop is off  

## Layout

```
app/
  bot.py                 # Telegram bot (aiogram) — all UX + admin
  config.py
  database.py
  catalog/               # parser, filters, covers, search, aliases
scripts/
  login_session.py
  backfill_topics.py
  start.sh               # local: bot only
  railway-start.sh       # production: bot only
```

## Always-on deploy (Railway)

1. Push this repo to GitHub (already: `dietyslaying/gaco-bot-1`).
2. [Railway](https://railway.app) → **New Project** → **Deploy from GitHub** → this repo.
3. **Add Postgres** plugin → Railway sets `DATABASE_URL` (use Postgres in production, not SQLite).
4. Set variables (Variables tab):

| Variable | Required |
|----------|----------|
| `BOT_TOKEN` | yes |
| `FILES_GROUP_ID` | yes |
| `REQUEST_GROUP_ID` / `REQUEST_GROUP_URL` | yes |
| `ADMINS` | yes (comma-separated Telegram user IDs) |
| `DATABASE_URL` | yes (from Postgres plugin) |
| `TELEGRAM_API_ID` / `TELEGRAM_API_HASH` / `TELEGRAM_SESSION` | for `/catalog backfill` |
| `COVER_STORAGE_CHAT_ID` | optional (defaults to first admin) |
| `REDIS_URL` | optional |

5. Start command is already `python -m app.bot` (`railway.json` / `Procfile` worker).
6. Deploy → bot polls 24/7. Laptop can be off.

**Important:** SQLite on Railway is wiped on redeploy. Use the Postgres plugin.

## Local run (optional)

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # fill BOT_TOKEN, DATABASE_URL, …
python -m app.bot
# or: bash scripts/start.sh
```

## Admin (in Telegram)

| Command | Use |
|---------|-----|
| `/help` | Admin panel buttons |
| `/stats` | Live stats + leaderboards |
| `/catalog` | Rebuild / backfill / aliases |
| `/filter` `/delete` `/filters` | Manual filters |
| `/broadcast` | Mass message |
| `/ban` `/unban` | Access control |

Users: join channel → verify → type anime name.

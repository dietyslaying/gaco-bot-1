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

## Always-on deploy (Alwaysdata SSH)

The bot must run **on the server**, not your laptop.

### 1. Allow SSH (one-time)

On [Alwaysdata admin](https://admin.alwaysdata.com/) → **SSH** / **Keys**, add this machine’s public key  
(or use password SSH once).

Deploy scripts:

```powershell
# From Windows (repo root), after SSH works:
.\scripts\deploy-alwaysdata.ps1
scp .env chad@ssh-chad.alwaysdata.net:~/gaco-bot/.env
ssh chad@ssh-chad.alwaysdata.net "bash ~/gaco-bot/scripts/alwaysdata/start-bot.sh"
ssh chad@ssh-chad.alwaysdata.net "bash ~/gaco-bot/scripts/alwaysdata/install-cron.sh"
```

On the server:

```bash
bash ~/gaco-bot/scripts/alwaysdata/setup.sh
# create ~/gaco-bot/.env  (BOT_TOKEN, DATABASE_URL, ADMINS, …)
bash ~/gaco-bot/scripts/alwaysdata/start-bot.sh
bash ~/gaco-bot/scripts/alwaysdata/install-cron.sh   # auto-restart every 5 min
bash ~/gaco-bot/scripts/alwaysdata/status-bot.sh
```

Use **Postgres** from Alwaysdata’s database product for `DATABASE_URL` when possible  
(SQLite under `~/gaco-bot/data/` works but is weaker for concurrent use).

Laptop can be off; cron watchdog restarts the bot if it dies.

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

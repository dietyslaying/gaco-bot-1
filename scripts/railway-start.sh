#!/bin/bash
# Railway / production: bot in background, admin web via gunicorn.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# Start the bot in the background
python -m app.bot &

# Admin dashboard in the foreground (Railway provides PORT)
exec gunicorn --bind "0.0.0.0:${PORT:-5000}" "app.admin.web:app"

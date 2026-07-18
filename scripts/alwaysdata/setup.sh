#!/bin/bash
# Run ON the Alwaysdata server after code is uploaded.
# Usage: bash scripts/alwaysdata/setup.sh
set -euo pipefail

APP_DIR="${APP_DIR:-$HOME/gaco-bot}"
cd "$APP_DIR"

echo "==> App dir: $APP_DIR"

if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -U pip wheel
pip install -r requirements.txt

mkdir -p "$HOME/gaco-bot/logs" "$HOME/gaco-bot/data"

if [ ! -f .env ]; then
  echo "WARNING: $APP_DIR/.env missing — create it before starting the bot."
  echo "Copy from .env.example and set BOT_TOKEN, DATABASE_URL, ADMINS, etc."
fi

echo "==> Setup done."
echo "Next: bash scripts/alwaysdata/start-bot.sh"

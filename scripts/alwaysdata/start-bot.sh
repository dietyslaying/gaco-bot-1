#!/bin/bash
# Start bot under nohup (survives SSH disconnect). Alwaysdata keeps the account process.
set -euo pipefail

APP_DIR="${APP_DIR:-$HOME/gaco-bot}"
cd "$APP_DIR"
# shellcheck disable=SC1091
source .venv/bin/activate

mkdir -p logs
PID_FILE="$APP_DIR/logs/bot.pid"
LOG_FILE="$APP_DIR/logs/bot.log"

if [ -f "$PID_FILE" ]; then
  OLD=$(cat "$PID_FILE" || true)
  if [ -n "${OLD:-}" ] && kill -0 "$OLD" 2>/dev/null; then
    echo "Bot already running (pid $OLD). Use stop-bot.sh first."
    exit 0
  fi
fi

# Load .env into environment for the process
if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

nohup python -m app.bot >>"$LOG_FILE" 2>&1 &
echo $! >"$PID_FILE"
echo "Started bot pid=$(cat "$PID_FILE") log=$LOG_FILE"

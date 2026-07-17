#!/bin/bash
# Start Telegram bot + admin dashboard (local dev).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [ -d "venv" ]; then
  # shellcheck disable=SC1091
  source venv/bin/activate
elif [ -d ".venv" ]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

echo "Starting Admin Web Dashboard..."
python -m app.admin.web &
WEB_PID=$!

echo "Starting Anime Telegram Bot..."
python -m app.bot &
BOT_PID=$!

echo ""
echo "✅ Both services are now running!"
echo "➡️ Web Dashboard: http://localhost:${PORT:-5000}"
echo "➡️ Telegram Bot is active."
echo "Press Ctrl+C to stop both."

cleanup() {
    echo ""
    echo "Stopping services..."
    kill "$WEB_PID" 2>/dev/null || true
    kill "$BOT_PID" 2>/dev/null || true
    wait "$WEB_PID" 2>/dev/null || true
    wait "$BOT_PID" 2>/dev/null || true
    echo "Services stopped cleanly."
    exit 0
}

trap cleanup SIGINT SIGTERM
wait

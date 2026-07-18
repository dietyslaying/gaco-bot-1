#!/bin/bash
set -euo pipefail
APP_DIR="${APP_DIR:-$HOME/gaco-bot}"
PID_FILE="$APP_DIR/logs/bot.pid"
if [ -f "$PID_FILE" ]; then
  PID=$(cat "$PID_FILE")
  if kill -0 "$PID" 2>/dev/null; then
    kill "$PID" || true
    sleep 1
    kill -9 "$PID" 2>/dev/null || true
    echo "Stopped $PID"
  else
    echo "Not running"
  fi
  rm -f "$PID_FILE"
else
  pkill -f "python -m app.bot" 2>/dev/null || true
  echo "No pid file; tried pkill"
fi

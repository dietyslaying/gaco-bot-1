#!/bin/bash
# Restart bot if not running (called by cron).
APP_DIR="${APP_DIR:-$HOME/gaco-bot}"
PID_FILE="$APP_DIR/logs/bot.pid"
if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  exit 0
fi
bash "$APP_DIR/scripts/alwaysdata/start-bot.sh"

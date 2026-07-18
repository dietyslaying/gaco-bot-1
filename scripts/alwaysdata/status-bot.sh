#!/bin/bash
APP_DIR="${APP_DIR:-$HOME/gaco-bot}"
PID_FILE="$APP_DIR/logs/bot.pid"
if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  echo "RUNNING pid=$(cat "$PID_FILE")"
  tail -n 20 "$APP_DIR/logs/bot.log" 2>/dev/null || true
else
  echo "STOPPED"
  tail -n 40 "$APP_DIR/logs/bot.log" 2>/dev/null || true
fi

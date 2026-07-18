#!/bin/bash
# Ensure bot restarts if it dies (runs every 5 minutes).
set -euo pipefail
APP_DIR="${APP_DIR:-$HOME/gaco-bot}"
CRON_LINE="*/5 * * * * $APP_DIR/scripts/alwaysdata/watchdog.sh >>$APP_DIR/logs/watchdog.log 2>&1"

mkdir -p "$APP_DIR/logs"
# Install watchdog if missing from crontab
(crontab -l 2>/dev/null | grep -v "gaco-bot/scripts/alwaysdata/watchdog.sh" || true; echo "$CRON_LINE") | crontab -
echo "Cron watchdog installed:"
crontab -l | grep watchdog || true

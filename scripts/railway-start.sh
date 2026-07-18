#!/bin/bash
# Railway / production: Telegram bot only (no web dashboard).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# Foreground process so the platform keeps the container alive
exec python -m app.bot

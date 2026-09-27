#!/usr/bin/env bash
# ==============================================================================
# Reel Studio — Launcher
# Starts the server in the background and opens the web panel in your browser.
# ==============================================================================
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Verify setup was run
if [ ! -d "$DIR/skills/recreate-reel/venv" ] || [ ! -x "$DIR/skills/recreate-reel/bin/ffmpeg" ]; then
  echo "First-time setup required. Running setup.sh..."
  bash "$DIR/setup.sh"
fi

exec bash "$DIR/panel/start.sh"

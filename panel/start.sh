#!/bin/bash
# Reel Studio launcher — the ONLY thing the user runs (via the Desktop app).
# Guarantees: whatever was (or wasn't) running before, after this script the
# CURRENT server code is serving the panel and Brave is showing it.
P="$(cd "$(dirname "$0")" && pwd)"
URL="http://127.0.0.1:7799/"

# The Desktop app launches with a minimal PATH; job sessions inherit the
# server's env, and the skill needs brew tools (ffprobe) + claude on PATH.
export PATH="/opt/homebrew/bin:/usr/local/bin:$HOME/.local/bin:$PATH"

want="$(stat -f %m "$P/server.py" "$P/research.py" 2>/dev/null | sort -n | tail -1)"
got="$(curl -s -m 2 "${URL}api/ping" | sed -n 's/.*"version": "\([0-9]*\)".*/\1/p')"

if [ "$got" != "$want" ]; then
  # No server, a stale server, or something else on the port: clear and start
  # fresh. Running reel jobs are safe — they live in tmux and get re-adopted.
  lsof -ti :7799 2>/dev/null | xargs kill 2>/dev/null
  sleep 0.5
  nohup /usr/bin/python3 "$P/server.py" > "$P/server.log" 2>&1 &
  for i in $(seq 1 30); do
    sleep 0.3
    [ "$(curl -s -m 2 "${URL}api/ping" | sed -n 's/.*"version": "\([0-9]*\)".*/\1/p')" = "$want" ] && break
  done
fi

if command -v open >/dev/null 2>&1; then
  open -a "Brave Browser" "$URL" 2>/dev/null || open "$URL" 2>/dev/null
elif command -v xdg-open >/dev/null 2>&1; then
  xdg-open "$URL" 2>/dev/null &
else
  python3 -m webbrowser "$URL" 2>/dev/null &
fi

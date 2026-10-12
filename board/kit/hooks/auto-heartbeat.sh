#!/bin/sh
# Claude Code PostToolUse hook: refresh the active task claim (at most every 15 minutes; no-op without a claim or for an attended claim).
# Runs after every tool call in every project, so it first looks for a claim file with plain shell and starts
# Python only when one exists. Projects without Keeptrack pay nothing.
d=$PWD
while :; do
  for f in .keeptrack/claim.json .board/claim.json .board-claim.json; do
    if [ -f "$d/$f" ]; then
      p=${f%/*}; [ "$p" != "$f" ] && [ -L "$d/$p" ] && exit 0   # never grep through a symlinked personal folder
      [ -L "$d/$f" ] && exit 0   # a symlinked record is nobody's: never followed, never beaten
      grep -q '"id"' "$d/$f" 2>/dev/null || exit 0   # a record with no card (the session only) costs no python
      grep -q '"attended": true' "$d/$f" 2>/dev/null && exit 0   # a person drives this session: no beats, no python
      command -v python3 >/dev/null 2>&1 || exit 0
      exec python3 "$CLAUDE_PLUGIN_ROOT/keeptrack.py" auto-heartbeat
    fi
  done
  [ "$d" = "/" ] && exit 0
  d=$(dirname "$d")
done

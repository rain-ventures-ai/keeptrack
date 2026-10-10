#!/bin/sh
# Claude Code PostToolUse hook: refresh the active task claim (at most every 5 minutes; no-op without a claim).
command -v python3 >/dev/null 2>&1 || exit 0
exec python3 "$CLAUDE_PLUGIN_ROOT/keeptrack.py" auto-heartbeat

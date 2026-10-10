#!/bin/sh
# Claude Code SessionStart hook: if this project is connected to a Keeptrack board (a personal .keeptrack/config.json,
# never committed, or BOARD_REPO in the environment), print a few lines of context: board, project, your open
# cards. Everywhere else, including teammates' checkouts of the same repo, it prints nothing.
found=""
d=$PWD
while :; do
  for f in .keeptrack/config.json .board/config.json; do
    # a config git tracks came with the repo, not from `keeptrack.py use`: never trust it
    [ -f "$d/$f" ] && ! git -C "$d" ls-files --error-unmatch -- "$f" >/dev/null 2>&1 && found=1
  done
  [ -n "$found" ] || [ "$d" = "/" ] && break
  d=$(dirname "$d")
done
[ -n "$found" ] || [ -n "$BOARD_REPO" ] || exit 0
command -v python3 >/dev/null 2>&1 || exit 0
exec python3 "$CLAUDE_PLUGIN_ROOT/keeptrack.py" here --hook

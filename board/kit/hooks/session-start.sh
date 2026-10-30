#!/bin/sh
# Claude Code SessionStart hook: if this project is connected to a Keeptrack board (a personal .keeptrack/config.json,
# never committed, or BOARD_REPO in the environment), print a few lines of context: board, project, your open
# cards. Everywhere else, including teammates' checkouts of the same repo, it prints nothing.
found=""
tracked() {   # does git track $2 in $1? At most 3 s: a hung git counts as not tracked, and keeptrack.py's own
  # bounded check (_untrusted) decides. Plain sh: timeout(1) is not on every system.
  git -C "$1" ls-files --error-unmatch -- "$2" >/dev/null 2>&1 & g=$!
  ( sleep 3; kill "$g" ) >/dev/null 2>&1 & k=$!
  wait "$g"; r=$?
  kill "$k" 2>/dev/null
  return "$r"
}
d=$PWD
while :; do
  for f in .keeptrack/config.json .board/config.json; do
    # a config git tracks came with the repo, not from `keeptrack.py use`: never trust it
    # (a prefilter only: keeptrack.py makes the final, fail-closed check)
    [ -f "$d/$f" ] && [ ! -L "$d/${f%/*}" ] && [ ! -L "$d/$f" ] \
      && ! tracked "$d" "$f" && found=1 && break   # one wait at most: keeptrack.py decides
  done
  [ -n "$found" ] || [ "$d" = "/" ] && break
  d=$(dirname "$d")
done
[ -n "$found" ] || [ -n "$BOARD_REPO" ] || exit 0
command -v python3 >/dev/null 2>&1 || exit 0
exec python3 "$CLAUDE_PLUGIN_ROOT/keeptrack.py" here --hook

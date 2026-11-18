#!/bin/sh
# Claude Code SessionStart hook: if this project is connected to a Keeptrack board (a personal .keeptrack/config.json,
# never committed, or BOARD_REPO in the environment), print a few lines of context: board, project, your open
# cards. Everywhere else, including teammates' checkouts of the same repo, it prints nothing.
found=""
start=$(date +%s 2>/dev/null) || start=
tracked() {   # does git track $2 in $1? The whole script shares one 3 s budget: a check that starts after
  # that counts as not tracked, and keeptrack.py's own bounded check (_untrusted) decides. A slow git that
  # still answers inside the budget only spends the time it used. Plain sh: timeout(1) is not on every system.
  now=
  if [ -n "$start" ]; then
    now=$(date +%s 2>/dev/null) || now=
    if [ -n "$now" ] && [ $((now - start)) -ge 3 ]; then
      return 1
    fi
  fi
  git -C "$1" ls-files --error-unmatch -- "$2" >/dev/null 2>&1 & g=$!
  left=3
  if [ -n "$start" ] && [ -n "$now" ]; then
    left=$((3 - (now - start)))
    [ "$left" -gt 0 ] || left=1
  fi
  ( sleep "$left"; kill "$g" ) >/dev/null 2>&1 & k=$!
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

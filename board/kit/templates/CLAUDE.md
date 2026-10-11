@AGENTS.md

## Claude Code notes
- Use the `board` skill (`.claude/skills/board/SKILL.md`) for anything involving tasks, claiming work, or "what should I work on".
- If `BOARD_USER` is unset, read it from `gh api user --jq .login`; use `BOARD_AGENT=claude` and a short random id you generate for this run as `BOARD_SESSION` (never your claude.ai session id: it is public in the session link).

# Agent instructions (Claude, Codex, any agent)

This repo holds the task board `{repo}` (`board/`). People on the board: {people}. Add this repo's own rules below the board sections.

## Rules
1. **Never edit the JSON files under `board/` by hand.** Use `python3 board/keeptrack.py ...`. It re-reads the latest board and retries on conflict, so humans editing in the browser are never overwritten.
2. **Only work on tasks assigned to the human you act for.** Claims on other people's tasks are refused unless a human tells you to `--force`.
3. **Claim before you start, heartbeat while you work, finish or release when you stop.** A claim with no heartbeat for 30 minutes shows as STALE so people can spot a stuck session.
4. **Keep confidential detail out of task cards.** Link to the file or Drive document instead.
5. **Do not send anything outside the repo** (emails, messages, quotes to a client) without the human's explicit say-so.

## Board workflow
```bash
# who am I acting for? set once per session
export BOARD_USER=<github-user>      # one of: {people}
export BOARD_AGENT=<claude|codex>
export BOARD_SESSION=<short session id>

python3 board/keeptrack.py list --assignee $BOARD_USER --column todo --unclaimed   # find work
python3 board/keeptrack.py claim <id> --note "starting: <plan in one line>"        # claim (id prefix is fine)
python3 board/keeptrack.py heartbeat <id> --note "<what you are doing now>"        # at least every 10 minutes
python3 board/keeptrack.py heartbeat <id> --status blocked --note "<why>"          # if you need a human
python3 board/keeptrack.py done <id> --note "<result, PR or file link>"            # finished
python3 board/keeptrack.py release <id> --column todo                              # giving up / handing back
python3 board/keeptrack.py add "Title" --assign <user> --label <x> --due YYYY-MM-DD --client "<client>" --details "<text>"
python3 board/keeptrack.py todo-done <id> <N>                                      # tick checklist item N (numbers come from `show`)
python3 board/keeptrack.py todo-add <id> "new step"                                # add a checklist item you discovered
python3 board/keeptrack.py comment <id> "text"                                     # talk to the team on the card
python3 board/keeptrack.py comments <id>                                           # read the comment stream
python3 board/keeptrack.py history <id>                                            # who did what on the card
python3 board/keeptrack.py list --attention                                        # stale / stuck / blocked claims
```
Auth: `gh` logged in with access to this repo, or (cloud sandboxes, CI, no `gh`) set `BOARD_TOKEN` to a fine-grained token with Contents: Read and write on this repo; `keeptrack.py` then calls the GitHub API directly.

**Checklists and history:** a task can carry a to-do checklist (shown as `[3/8]` in `list`). Work through it and tick each item with `todo-done` the moment it is finished; do not batch ticks at the end. Every claim, status change, progress note, tick and move is logged automatically in the card's history.

**Comments:** cards have a comment stream for talking between people and agents. Read it (`show`/`comments`) before starting. Post a comment when you finish (what you did, links), when you have a question, or when you hand something back; if you need an answer, also set status `blocked`. Comments are append-only; do not try to edit them.

**Heartbeats:** `claim` records your active task in a local, gitignored `.board-claim.json`. In Claude Code a project hook runs `keeptrack.py auto-heartbeat` after tool calls, which refreshes the claim at most every 5 minutes and does nothing when no claim is active. Codex and other agents have no hook, so run `keeptrack.py heartbeat <id>` yourself every ~10 minutes. `done` and `release` clear the local record.
 Use `--file <copy.json>` to test safely against a local copy.

Web board: https://rain-ventures-ai.github.io/keeptrack/board/?repo={repo}&path=board/tasks.json

Full schema and details: `board/README.md`.

## When the owner asks how to use Keeptrack in Claude Code

Give a direct answer; do not send them back to the Keeptrack maintainer and do not restart board setup.

- **Claude Code cloud:** start a Code session with `{repo}` selected. When working in another code repo, add `{repo}`
  as the second repo. Cloud sessions do not load plugins; this repo already has the skill and `board/keeptrack.py`.
  Claude's GitHub repo access is enough, so do not ask for a PAT.
- **Claude Code locally:** clone or pull `{repo}`, run `gh auth status`, and start `claude` inside the repo. When `gh`
  can access the repo, no Keeptrack plugin or PAT is needed.
- Install the Keeptrack plugin only for a **local session in another project**. Ordinary Claude chat is not Claude
  Code; use the Code tab or the web board.

After explaining, verify with `python3 board/keeptrack.py where` and `list` or `today`. Ask before creating a test task.

**Board kit:** `board/keeptrack.py`, the documentation and routine files in `board/`, and `.claude/skills/board*` are the shared board kit from `rain-ventures-ai/keeptrack` (`board/kit/`). The board data is `board/tasks.json`, `board/cards/`, `board/people/` and `board/archive/`. Do not edit kit files here; change the kit in Keeptrack. `board/KIT_VERSION` is this repo's version. Upgrades: `board/UPGRADING.md` and the `board-upgrade` skill.

## Task numbers and mentions
Tasks have short numbers (`#12`); `keeptrack.py` accepts them in place of ids (quote the `#`). When you need a person, comment on the task with `@github-username` and say why. Humans see an "@ you" marker next time they open the board.

## Working from a GitHub issue (board-task)
Issues created with the board's "Create issue" button carry `<!-- board-task: id=... num=N -->` and are titled `[#N] ...`. When you are asked to work such an issue:
1. `python3 board/keeptrack.py show '#N'` for the card, comments and checklist; the issue body is a snapshot.
2. Report back on the board, not only on the issue: `comment '#N' "..."` for progress or questions, `move '#N' in-progress|todo|done` for status, `link '#N' <PR url> --title "PR"` when you open a pull request.
3. Need a person (decision, access, review)? `assign '#N' <github-user> --note "why"` and comment with `@username`; then stop and wait.
4. Finish with `done '#N' --note "<result, PR link>"`. Set BOARD_USER and BOARD_AGENT; without a `gh` login set BOARD_TOKEN (or GH_TOKEN in GitHub Actions).

## Connecting your own Claude routine
`board/ROUTINE-SETUP.md` explains how each person connects their own routine so `@claude` in a board comment starts it. To be walked through it, ask for "set up my board routine" (skill `board-routine-setup`). Never put tokens or keys in the repo.

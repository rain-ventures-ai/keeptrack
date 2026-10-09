---
name: board
description: Work from the team board in board/ via board/keeptrack.py. Use for task work and stuck agents, and when asked whether the board is accurate, truthful or up to date or to reconcile task status against GitHub pull requests, releases or deployments.
---

# Team board

The board lives in the `board/` folder; `board/tasks.json` is its entry point. Current boards keep tasks in `board/cards/` and CRM people in `board/people/`. Manage all of it only through `python3 board/keeptrack.py`. Read `AGENTS.md` for the rules; this is the procedure.

## 1. Identify who you act for
Use `BOARD_USER` (or `gh api user --jq .login`). Valid users: the `people` in `board/tasks.json`. Set `BOARD_AGENT=claude` and `BOARD_SESSION` to a short id for this session.

## 2. Find work
```bash
python3 board/keeptrack.py list --assignee "$BOARD_USER" --column todo --unclaimed
python3 board/keeptrack.py list -q "not published"   # search all current task fields
python3 board/keeptrack.py show <id>        # read details, links and contacts before starting
```
If the human named a task, use that one. Do not pick tasks assigned to someone else.

Task links are supporting resources and references for that task (Drive/Dropbox files, issues, PRs, source pages or a
local working path). A person's profile/reference links instead describe that person or company. Their company's
file/folder resources are company-wide working material. Cloud access requires the matching connector/plugin/MCP and
signed-in account; local paths require a session on the computer that holds them. If a resource cannot be opened, say
so and ask the user. Never imply that you read it.

## 3. Claim, work, heartbeat
```bash
python3 board/keeptrack.py claim <id> --note "starting: <one-line plan>"
python3 board/keeptrack.py heartbeat <id> --note "<current step>"     # at each milestone
```
In Claude Code a project hook sends a quiet heartbeat automatically (at most every 5 min) while a claim is active, so the claim does not go stale during long work. The manual heartbeat is for updating the note. Without `gh`, set `BOARD_TOKEN` (fine-grained, Contents read/write on this repo).
If a claim is refused because another session holds it, stop and tell the human. Do not use `--force` unless they say so.

## 3b. Checklist
If `show` lists to-dos, work through them in order and tick each one as soon as it is done. Add steps you discover.
```bash
python3 board/keeptrack.py todo-done <id> <N>      # N is the number shown by `show`
python3 board/keeptrack.py todo-add <id> "<new step>"
python3 board/keeptrack.py todo-undo <id> <N>      # reopen
python3 board/keeptrack.py todo-rm <id> <N>
python3 board/keeptrack.py history <id>            # automatic log of claims, progress notes, ticks and moves
```

## 3c. Comments
`show` prints the latest comments; read them first, since people leave instructions and answers there.
```bash
python3 board/keeptrack.py comments <id>             # full stream
python3 board/keeptrack.py comment <id> "question, update or hand-off"
```
Post a short comment when you finish (what you did, with links) and whenever you need a human.

## 4. Blocked or stuck
```bash
python3 board/keeptrack.py heartbeat <id> --status blocked --note "<exactly what you need>"
```
Then tell the human in your reply.

## 5. Finish
```bash
python3 board/keeptrack.py done <id> --note "<result and link to the file/PR>"
# or hand back:
python3 board/keeptrack.py release <id> --column todo
```

## Adding tasks
```bash
python3 board/keeptrack.py add "Title" --assign <user> --label <label> --due YYYY-MM-DD --client "Acme" --details "<text and URLs>" --todo "step 1" --todo "step 2"
```
`--client` is optional; leave it out for tasks that are not about a client.

## Checking on others
`python3 board/keeptrack.py list --attention` lists stale, stuck and blocked claims.

## Check the board
Run `python3 board/keeptrack.py doctor` after a migration or when the board shows an error. Use the `board-doctor` skill before you run `doctor --fix`.

## Board status and truth audits
Natural requests such as “is my board accurate?”, “these say merged but not published”, “make the statuses truthful” or
“check the board against the repos” belong to this skill. Do not ask the user to name Keeptrack or repeat this repo.
Read [references/status-audits.md](references/status-audits.md) and follow it.

## People and follow-ups (Keeptrack CRM)
If the board has CRM people, use:
`keeptrack.py today` (who to contact), `people`, `person "<name>"`, `person-add` (refuses duplicates), `person-set`, `touch "<name>" "<text>" --channel linkedin|email|call|meeting|note [--draft]`, `sent "<name>"` and `client-link "<company>" <cloud-url-or-local-path>`. `person` lists every labelled email and phone number, profile/reference link, and company file/folder resource. To set up a board from a spreadsheet, email, Trello or folders, use the `onboard-keeptrack` skill (it ends with `import`).
When you write a message for someone, log it with `--draft`. Never send it yourself. Run `sent` only after the human says it is sent.

## Never
- Edit any board JSON file directly.
- Put client-confidential content in card text.
- Contact anyone outside the repo or share prices without the human's explicit approval.

## Numbers and mentions
- Refer to tasks as `#12` (shown on each card); `keeptrack.py show '#12'` works wherever an id is accepted.
- To get a human's attention, add a comment containing `@github-username` plus the reason; they see an "@ you" marker on the card.

## Working from a GitHub issue (board-task)
Issues created with the board's "Create issue" button carry `<!-- board-task: id=... num=N -->` and are titled `[#N] ...`. When you are asked to work such an issue:
1. `python3 board/keeptrack.py show '#N'` for the card, comments and checklist; the issue body is a snapshot.
2. Report back on the board, not only on the issue: `comment '#N' "..."` for progress or questions, `move '#N' in-progress|todo|done` for status, `link '#N' <PR url> --title "PR"` when you open a pull request.
3. Need a person (decision, access, review)? `assign '#N' <github-user> --note "why"` and comment with `@username`; then stop and wait.
4. Finish with `done '#N' --note "<result, PR link>"`. Set BOARD_USER and BOARD_AGENT; without a `gh` login set BOARD_TOKEN (or GH_TOKEN in GitHub Actions).

## Fired from the board (a person assigned their Claude or typed `@claude`)
A routine run starts with a `routine-fire-payload` naming a task number (`#N`) and the person (`@user`). The quick assign action writes a visible `@claude` request first, so both entry paths use the same protocol. The page has already put a claim on the card for this run, so:
1. `export BOARD_USER=<user> BOARD_AGENT=claude BOARD_SESSION=<short id>`; `BOARD_TOKEN` is set in the routine's environment.
2. `python3 board/keeptrack.py claim '#N' --for <user> --agent claude --session "$BOARD_SESSION" --force --note "working"` (`--force` is expected here: it replaces the page's placeholder claim).
3. `keeptrack.py show '#N'` and `keeptrack.py comments '#N'`; do what the newest `@claude` comment from that user asks, and nothing beyond it.
4. Keep the card honest while you work: `heartbeat '#N' --note "..."`, `todo-add` / `todo-done` for steps, `comment '#N'` for anything a human should read, `link '#N' <PR url> --title "PR"` for pull requests, `move '#N' <column>` for status.
5. Need a decision, access or review? `comment` with `@<user>` and the question, `assign '#N' <user> --note "why"`, then stop. Never guess.
6. Finish: `comment` the outcome, `assign '#N' <user>`, `done '#N' --note "<result>"`.

### Command cheat sheet
`list`, `show`, `claim`, `next`, `heartbeat`, `release`, `done`, `add`, `move ID COLUMN`, `assign ID USER... [--add|--remove]`, `link ID URL --title`, `todo-add|todo-done|todo-undo|todo-rm`, `comment`, `comments`, `history`. `ID` may be a task number such as `'#12'`. Columns: `backlog`, `todo`, `in-progress`, `done`. Board members remain in the `people` list in `board/tasks.json`; CRM people are separate records.

## Archive (old items)
Old done tasks, Lost people and long histories move to `board/archive/<year>.json` with `python3 board/keeptrack.py archive` (`--dry-run` first). Search them with `archived -q "<words>"`, and bring one back with `unarchive '#N'`. The board file keeps an index in `archive.files`; do not edit archive files by hand.

# Team board

> **This folder is the task board for this repo.** It is not the repo's other work. A task can reference a client or area (the `client` field) or be about anything else. Leave `client` empty, or use a label like `internal`.

A Trello-style kanban for this repo with no database and no server. The single source of truth is the board folder. Its settings start in [`board/tasks.json`](tasks.json). Two things read it:

- **The web board** — a static page hosted from the public `keeptrack` repo: https://rain-ventures-ai.github.io/keeptrack/board/?repo=<owner>/<repo>&path=board/tasks.json (source: `rain-ventures-ai/keeptrack`, `board/index.html`). It holds no data. It talks to the GitHub API from your browser with a fine-grained token you paste in once (kept in your browser's localStorage, sent only to api.github.com).
- **The agent CLI** — [`board/keeptrack.py`](keeptrack.py), used by Claude, Codex or any script, through your existing `gh` login.

Every CLI and web-board write re-reads the latest board files and retries on a conflict.

## Using the web board
1. Open the hosted page above (the link pre-fills the repo).
2. Settings → check the file path is `board/tasks.json`, add your GitHub username and a **fine-grained token** limited to this repo with **Contents: Read and write**; the Settings dialog links to GitHub's token page with the name, expiry and permission pre-filled.
3. Drag cards between columns, or use ◀ ▶. Double-click or **Edit** for the full card.

Filters: client, **project**, assignee (including "Claimed by an agent"), label, priority, **Needs attention** (overdue, or an agent claim that is stale/stuck/blocked), **Waiting** (cards parked on a person or event), hide done.

## Split storage (schema 4)

### Prioritise List (optional)

Switch List to **Prioritise** for a board-wide priority order and inline scoring. Standard List remains
available; switching back does not delete the optional task fields. Kanban order is independent.
Value is 1–5: agree anchors with your team (for example 1 = minor benefit, 3 = meaningful goal progress,
5 = major near-term goal impact). Effort is XS/S/M/L/XL with relative weights 1/2/3/5/8.
Score is value divided by effort, not a promise or automatic priority. Missing inputs show unscored.
Use manual order for judgement, or explicitly sort by score. Move controls only apply in manual order;
filtered moves use neighbouring visible tasks while leaving the other tasks' relative order intact.
`task-set <id> --value 4 --effort M` edits scoring from the CLI; empty arguments clear either input.
`list --sort score` shows scored tasks first, highest score first (ties use board-wide priority order).
`list --sort priority` reads manual board-wide order. Both accept the normal list filters and never write ranks.
`priority-move '#12' --before '#7'` changes manual board-wide ranking; `--after`, `--top` and `--bottom`
are alternatives. Anchors may be in another column. Status and Kanban rank stay unchanged, and a
concurrent save re-resolves the neighbours on the latest board. Ranking applies to the full board,
not a filtered subset. Archived tasks retain their ranks; use `unarchive` before moving one.
Existing boards need no migration. Turning the layout off is the safe rollback, not restoring old data.

Schema v4 keeps each card and CRM person in a separate file:

```text
board/
  tasks.json
  cards/<task-id>.json
  people/<person-id>.json
  projects/<project-id>.json
  archive/<year>.json
```

`tasks.json` has `"version": 4` and `"layout": "split"`. It keeps board settings, columns, team members, agents, clients, labels, client links (and optional client north stars in `client_info`), `next_num`, and the archive index. It has no `tasks`, `contacts`, or `projects` array.

A card file keeps all card fields. It also has `rank`. A person file keeps all CRM person fields. Each file name must match the item `id`.

New task ids start with `t_`. New person ids start with `p_`. New project ids start with `pr_`. The suffix has 10 lower-case letters or digits. Old ids do not change. Task numbers still come from `next_num`.

`rank` is a base-62 fractional index. It lets one card move without renumbering the other cards. The CLI orders cards in a column by priority, due date, rank, and task number.

The CLI writes only files that changed. Adding a task writes `tasks.json` and one new card file in one commit. A card edit writes only that card. When an API save changes several files, it uses one Git Data API commit. Local `--file` saves use the board folder that contains the selected `tasks.json`.

API reads use the branch tree. Blobs are cached by Git blob SHA under `.keeptrack/cache/` in a connected project (`.board/cache/` in a board repo). The cache is local and ignored by git.

### Migrate from schema 3

Install the v8 web page before anyone migrates a board. Bare `migrate` brings a board up to v3 only. Only `migrate --to 4` splits it.

**Projects on split boards (kit v17+):** deploy the hosted web board (or hard-refresh after Pages updates) and run `kit-update` on the board repo **before** anyone creates or edits projects on a split layout. An older hosted page cannot edit `projects/*.json`; the v17 board only deletes project files when project data was loaded successfully.

Install the new kit on the default branch. Then check the migration:

```bash
python3 board/keeptrack.py migrate --to 4 --dry-run
```

Read the file list and counts. Then migrate:

```bash
python3 board/keeptrack.py migrate --to 4
python3 board/keeptrack.py verify --against keeptrack-v3-backup-YYYYMMDD-HHMM
python3 board/keeptrack.py doctor
```

For a GitHub board, migration creates a tag named `keeptrack-v3-backup-YYYYMMDD-HHMM`. It then writes all new files in one commit. It checks every field before it saves.

To roll back, revert the migration commit. You can also reset to the backup tag. A reset removes all board saves made after the tag. Check with the team before you reset.

### Check and repair

Run `python3 board/keeptrack.py doctor` when a save fails, after migration, or when the board reports an error. Add `--json` for machine-readable output.

Read the report before you run `doctor --fix`. The fix command repairs only safe fields in one save. It never deletes data. It never changes invalid JSON.

Exit code 0 means healthy. Exit code 1 means the report found a problem. Exit code 2 means the tool could not read the board.

## Legacy `tasks.json` schema (version 3)
```jsonc
{
  "version": 3,
  "settings": { "stale_after_minutes": 30 },     // a "running" claim with no heartbeat for this long shows as STALE
  // optional "max_agent_claims": 2 — claim refuses an agent claim when this many others are running (attended and stale ones don't count)
                                                 // v3 optional "stages": ["New", "Contacted", "Talking", "Proposal", "Won", "Lost"] = pipeline stages for people (this is the default)
                                                 // optional "archive": { "done_days": 90, "lost_days": 180, "keep_history": 20 } = archive rules
                                                 // optional "kit_owner": "github-user" = whose Claude upgrades the board kit (default: first person)
                                                 // v43 optional "waiting_days": 7 = chase a wait with no nudge date this many days after it began (0 = off)
                                                 // v60 optional "backlog_research": { "enabled": true, "per_run": 2 } = the relay dispatcher researches bare Backlog cards (off unless enabled is true)
                                                 // v43 optional "min_kit": 43 = the oldest kit that understands every field on the cards (set by the first `wait`; only rises)
  "columns": [{ "id": "todo", "name": "To do" }, ...],
  "people":  [{ "github": "osouthgate", "name": "Oliver" }, { "github": "JezHub", "name": "Jez" }],
                                                 // v28 optional on each member: "emails": ["a@example.com", "a@example.org"], "timezone": "Europe/London"
  "agents":  ["claude", "codex"],
  "clients": ["Acme", "Rain Ventures", "General"],
  "labels":  [{ "name": "call", "color": "#0c66e4" }],
  "contacts": [ /* v3: people in the CRM, see "People (schema 3)" below */ ],
  "client_info": { "Acme": { "north_star": "optional: what success looks like for this client", "links": [{ "title": "Drive or local folder", "url": "https://… or /local/path" }] } },   // v3: north star + working file/folder resources per client
  "projects": [{ "id": "pr_ab12cd34", "client": "Acme", "name": "Phase one rollout", "north_star": "…", "status": "active | done | paused",
                  "links": [], "people": ["name@example.com"], "created": "…", "updated": "…" }],   // optional; split v4 uses projects/<id>.json instead
  "archive": { "files": { "2025": { "tasks": 120, "contacts": 8 } }, "last_run": "…" },   // index of archive/<year>.json, written by `archive`
  "next_num": 13,                                 // next number to hand out; maintained by the web page and keeptrack.py
  "tasks": [{
    "id": "t_ab12cd34",
    "num": 12,                                      // short human number shown as #12 (stable, never reused); assigned automatically in creation order
    "title": "…",
    "column": "todo",
    "client": "Acme",               // optional; empty for tasks not tied to a client
    "project": "pr_ab12cd34",       // optional; links the task to a project id (empty = unchanged behaviour)
    "contact": "p_ab12cd34",        // optional CRM person id
    "priority": "high | medium | low",
    "due": "2026-10-20",                           // due-by date, optional
    "labels": ["call", "reply"],
    "assignees": ["osouthgate", "JezHub"],         // GitHub usernames (people)
    "details": "free text; URLs become clickable",
    "todos":   [{ "id": "d_ab12cd", "text": "…", "done": false, "doneBy": "…", "doneAt": "…" }],   // checklist inside the card (not separate tasks)
    "comments": [{ "id": "c_ab12cd", "at": "…", "by": "JezHub", "text": "append-only stream for people and agents" }],
    // a comment can carry "session_url" (the Claude session that works on it). type "activity" is a one-line event that the web board adds, for example
    // { "type": "activity", "by": "claude", "text": "Claude started a session for @JezHub: https://claude.ai/code/session_…", "session_url": "…", "reply_to": "c_ab12cd" }
    "history": [{ "at": "…", "by": "claude@osouthgate", "text": "✓ step one" }],               // automatic log, newest last, capped at 200
    "links":    [{ "title": "Drive folder or PR", "url": "https://… or /local/path" }],   // task resources/references; GitHub issue/PR/repo URLs show as chips
    "contacts": [{ "name": "…", "role": "…", "email": "…", "phone": "…" }],
    "claim": null,                                 // see below
    "last_run": null,                              // set by `done`: the finished claim, shown as one "Last run" line
    "waiting": null,                               // v43, see "Waiting for" below
    "after": ["t_ab12cd35"],                       // optional: card ids this card runs after, see "Runs after" below
    "agent_cleared": [],                           // v43, optional: newest 20 {what, by, session, at} where an agent run ended or overrode a wait
    "created": "…", "createdBy": "osouthgate", "updated": "…", "updatedBy": "osouthgate"
  }]
}
```
Task order within the array is the order on the board. Humans are assigned with `assignees`; an **agent works on behalf of an assigned human** via a claim.
The web task **Contacts** add field suggests existing CRM people by name, client, role or email. Selecting a person
adds an optional `person_id` to the task's `contacts[]` entry alongside the name/role/email/phone snapshot; it does
not edit the CRM person or create another one. Snapshots are not automatically synchronized when CRM details change.
Manual `Name | role | email | phone` entries remain supported without a `person_id`.

### Your companies (explicit member identity)

A board member may have multiple `own_companies` in their `people[]` member record. These are existing company/client
names, not guessed from a CRM person's employer, task client or which companies happen to be on the board.
In **Settings → Board → Members**, explicitly link a company or use:

```bash
python3 board/keeptrack.py member-set USER --own-company 'Company A' --own-company 'Company B'
python3 board/keeptrack.py member-set USER --remove-own-company 'Company A'
```

The company drawer labels it **Your company** or **Board member company**. Any member link protects company removal;
unlinking one member does not release another member's protection. Unlinking only removes the identity link: company
files, tasks, projects and CRM employer references stay unchanged. Those ordinary references must also be moved before
`client-rm` can succeed. A linked member must explicitly unlink before member removal. `client-rename` updates these
name-based links together with other references; there is no new company-ID system or inferred migration.
Upgrade older CLI copies before relying on these safeguards. They prevent mistakes, not writes by someone bypassing
Keeptrack with direct repository access. Existing boards without these optional fields behave as before.

### Agent claim
When an agent picks up a task it writes (and keeps refreshing) a `claim`, so anyone can see who is running it and spot a stuck session:
```jsonc
"claim": {
  "agent": "claude",                 // or "codex", …
  "on_behalf_of": "osouthgate",      // the human assignee
  "session_id": "sess-9f2a",
  "session_url": "https://…",        // link to the session if there is one
  "host": "oliver-desktop",          // machine
  "cwd": "/home/osouthgate/dev/<repo>",
  "branch": "feature/x",
  "status": "running | blocked | stuck",
  "note": "what it is doing right now",
  "claimed_at": "…", "heartbeat_at": "…", "finished_at": "…"
}
```
The board shows each claim on the card (green running, amber stale/blocked, red stuck) and the card's edit dialog shows every field. A human can **Mark stuck** or **Release claim** from the board.

When the agent runs `done`, the claim is removed (no banner is left on the card) and kept as `last_run`: `{agent, on_behalf_of, session_id, session_url, started_at, finished_at, note}`. The card's drawer shows it as a single "Last run" line with the session link; the history also records it. `session_url` is filled automatically in Claude cloud sessions (from `CLAUDE_CODE_REMOTE_SESSION_ID`) or by the web page when it started the run; older claims with `status: "done"` are shown the same way.

### Waiting for (kit v43)
A card parked on a person or an event carries `waiting` (null or absent when it is not waiting):
```jsonc
"waiting": { "on": "Acme finance (quote approval)",   // free text, always shown
             "who": "p_ab12cd34",                     // optional: a CRM person id, a board member's login or an agent name
             "since": "2026-10-12", "nudge": "2026-10-16",   // nudge = the day to chase; none: since + settings.waiting_days
             "note": "asked by email on the 12th", "by": "claude@osouthgate",
             "by_session": "9f2a41c07b3d" }           // first 12 hex of a sha256 of the session id that set it (not a secret)
```
`wait ID --on .. [--who ..] [--nudge +3|date] [--note ..]` sets it and `unwait ID --note ..` ends it; `done` and
`move ID done` end it too, and history keeps it. The card stays in its column and `due` is untouched. A waiting card is
not claimable: `claim` refuses it and `next` skips it, with or without `--force`. If the card has a running claim,
`wait` blocks that claim (`blocked_by_wait: true`, heartbeat time untouched) when it is the claim's own session or a
person (no `BOARD_AGENT`); such a claim never goes stale, and only its own session, a person or `--force` releases it.
`unwait` runs a young blocked claim again (counted against `max_agent_claims` unless attended), puts a claim that was
`stuck` before the wait back to `stuck` (`claim.before_wait`), and releases one older than the stale limit to To do.
`release --column done` is refused while the card waits: use `done` or `move ID done`, which end the wait and record it. An agent run may `unwait` only a wait it set in the same session whose `who` is empty or
the agent itself. These rules are advisory: anything with write access to the repo can edit a card, so the kit records
what it cannot prevent in `agent_cleared` and `doctor` warns `AGENT_CLEARED`, `CLAIM_BLOCKED`, `KIT_OLD` and
`MIN_KIT_LOWERED`. The first `wait` sets `settings.min_kit` to 43; three-way merges keep the higher value.

### Runs after (card dependencies)
A card may carry `after`: a list of card ids it runs after (absent or `[]` when it has none). It is a hint and a gate,
never a trigger: nothing moves a card because of it, and only a person moves a card into To do.
```bash
python3 board/keeptrack.py task-set '#63' --after '#62' [--after ..]   # '#N' or an id; stores the card id
python3 board/keeptrack.py task-set '#63' --not-after '#62'            # remove one; --no-after clears (with --after: replace)
python3 board/keeptrack.py add "Phase two" --column backlog --after '#62'
```
Each id must be a card on the board. A card can't run after itself, and a link that would make a loop is refused.
`show` prints `after: #62 (done), #64 (in-progress)`; `list` adds `[after #62]` for links on the board not done yet. A card that
is no longer on the board counts as done only if the archive holds it as Done (and not cancelled); otherwise it shows as
`missing`. The web board shows an "after #62" chip per link not done yet (amber when missing or cancelled) and every
link in the card's details. A `task.create` or `task.update` proposal may set `after`: `proposal-add` turns `#N` into
the card id. `doctor` reports a malformed list or a loop (`AFTER`) and warns about a card that is gone (`AFTER_MISSING`).
No migration: older kits keep the field as it is and ignore it. Relay's `can-start` reads it (it refuses a card while
any card it runs after is not done).

## People (schema 3)
Schema 3 (migration step 2 to 3) adds the Keeptrack CRM: `contacts` (default `[]`), `client_info` (default `{}`) and `settings.stages` (default New, Contacted, Talking, Proposal, Won, Lost). A person in `contacts`:
```jsonc
{ "id": "p_ab12cd34", "name": "…", "company": "…", "role": "…", "github": "optional-github-login",
  "emails": [{ "id": "e_…", "label": "Work", "value": "name@example.com" }],
  "phones": [{ "id": "ph_…", "label": "Mobile", "value": "+44 …" }],
  "email": "name@example.com", "phone": "+44 …", "linkedin": "https://linkedin.com/in/…", // first values, retained for older kits
  "stage": "New",                       // one of settings.stages
  "value": "…", "source": "…", "notes": "…",
  "next": "what happens next", "next_due": "2026-10-20",     // next step and its date
  "links": [{ "title": "LinkedIn | company | blog | portfolio | …", "url": "https://…" }], // profile/reference pages, not working files
  "comments": [{ "id": "c_ab12cd", "at": "…", "by": "…", "channel": "linkedin | email | call | meeting | note",
                 "text": "…", "draft": false, "sent_at": "…" }],   // a draft is not a contact until marked sent; sent_at is when it was sent
  "history": [{ "at": "…", "by": "…", "text": "…" }], "created": "…", "updated": "…", "createdBy": "…" }
```
A task can point at a person with `"contact": "<person id>"`. Last contact is the newest `sent_at` (else `at`) of a comment that has a channel other than `note` and is not a draft.

For imported contact events, `touch` accepts `--at <ISO timestamp with timezone>` so the contact log keeps the real
event time, and `--source-id email:<16-to-64 hex characters>` so retries do not create duplicates. Hash provider
message/thread identifiers before using them; never put an email address or message text in the source id. Recurring
mailbox reconciliation is defined by the `keeptrack-email` skill and keeps its last-run checkpoint outside `board/`.

Person `links` are profile or reference pages about that person/company. Task `links` are supporting resources and
references for that task: for example Drive/Dropbox files, issues, PRs, source pages or a local working path.
`client_info[company].links` are company-wide working file/folder resources rather than task-specific ones. An agent
needs the matching connector/plugin/MCP and signed-in account for a cloud resource, or a session on the computer that
holds a local path. If it cannot access one, it must say so and ask the user rather than implying it read the resource.

## Archive files (schema 3)
Old items move out of the active card and person files so that the current board stays small. Legacy v3 boards keep their active items in `tasks.json` (the GitHub contents API sends no content above 1 MB; the web board and `keeptrack.py` can read it raw up to 100 MB, but legacy boards are fastest below about 600 KB).
- `keeptrack.py archive` (or the web board: Settings → Board → Archive) moves tasks in the done column with no change for `settings.archive.done_days` (default 90), people at stage Lost with no change for `lost_days` (180) and no future next step, and all but the last `keep_history` (20) history lines of each card.
- `keeptrack.py archive <id>` (or the task's **⋯ → Archive task** menu) archives one task immediately, regardless
  of its status or age, retaining all details, checklist, comments and history. An unfinished agent claim must be
  released or finished first. Prefer this to deleting a task when you want to keep its record.
- They go to `archive/<year>.json` next to `tasks.json`: `{ "version": 3, "archive": true, "year": "2025", "tasks": [...], "contacts": [...], "history": { "<card id>": [...] } }`. The year is the year of the item's last change (four digits; an item whose date has no valid year stays on the board, and any other archive key is refused); trimmed history goes to the current year.
- `tasks.json` keeps an index: `"archive": { "files": { "2025": { "tasks": 120, "contacts": 8 } }, "last_run": "<ISO time>" }`.
- Archive files are written first and merged by id, so a run that stops half way is safe to repeat. An item on the board and in an archive file at the same time counts as on the board.
- `archived -q` searches them; `unarchive <#N|id>` puts one back (in git mode the board and the archive file change in one commit); `archived-history <#N|id>` prints the history lines that were trimmed off a card. The web board does not show trimmed history yet. The web board's search (press `/`) can include them.

## Review Inbox (kit v42, split storage; always on from kit v44)
- From kit v44 it is always on for schema 4 boards; `settings.review_inbox` is no longer read. It does not create or start any routine.
- Proposals live in `proposals/<id>.json` next to `cards/` and `people/`: `{ "id": "r_…", "version": 1, "kind": "task.create|task.update|person.upsert|contact.touch|ask.choose|ask.approve|ask.question", "status": "pending|accepted|answered|ignored", "title", "source": {kind, id, revision, title, date, url}, "run", "action_key", "work_key", "reason", "evidence", "target": {type, id, base}, "change", "likely_duplicates", "previously_ignored", "reviewer", "decision": {action, by, at, result, commit, edited, undo}, "history", "created", "createdBy" }`.
- They are never part of `tasks` or `contacts`: `list`, `next`, `claim`, `today`, counts and the web views do not see them.
- `proposal-add` dedups by `action_key` across every status (also archived proposals) and flags work ignored before by `work_key`. Accept, merge, ignore, reopen and undo re-run on the newest board after a lost race, check `target.base`, and write the record and the proposal in one commit. A created record's id comes from the proposal id. Exit code 3: already decided, or the target changed.
- Questions (kit v44, `ask.*`): `change` holds `question`, optional `task` and `links`, and `options`/`allow_other` (choose) or `subject`/`content_hash` (approve); optional root `decider` (a login). A person answers (`proposal-answer`; refused with `BOARD_AGENT` set, and for anyone but the decider): status `answered`, `decision.answer` = `{choice}` / `{other}` / `{approved}` / `{text}` plus optional `note`. Only a person (and only the decider when set) answers, dismisses or reopens a question. `content_hash` is required for ask.approve, and an email `subject.summary` needs `--recipients-confirmed`. The asking agent reads `proposal-result` and runs `proposal-done --answer-id <answer_id>` once before acting (`decision.done`; exit 3 if already done, the answer changed, or the content hash differs); it prints the locked answer, which is the one to act on. `createdBy` of a question is always the agent and person that added it (`BOARD_AGENT@BOARD_USER`, not one session, so a later run of the same routine can pick the answer up), and that agent may withdraw (`proposal-ignore`) its own pending question. `proposal-done --not-acted --answer-id <answer_id>` closes an answer without acting (`decision.done.acted: false`; an agent must name the answer it saw): for a rejection, a changed content hash, or work no longer needed. An answered question is not slimmed or archived until it is done, or until the board's `archive.done_days` after the answer (a one-off `archive --done-days` does not shorten it); only the decider, when set, or the asking agent closes or acts on it with `proposal-done`; slimming also removes the `--note` text of `proposal-done` and the `proposal-ignore --reason` text; `proposal-done` refuses an empty answer, and an approval with no `content_hash`. `proposal-reopen` returns an answer not yet acted on to pending. The first question raises `settings.min_kit` to 44: an older page would offer Accept on a question.
- Decided proposals lose `reason`, `evidence`, `change` and the undo snapshot after 30 days; the archive sweep moves old ones to `archive/<year>.json` under `"proposals"`.

## Agent protocol (copy into an agent's instructions)
```
You work from the team board in `board/` using `board/keeptrack.py` (`board/tasks.json` is its entry point).
1. Find work:      python3 board/keeptrack.py list --assignee <github-user> --column todo --unclaimed
2. Claim it:       python3 board/keeptrack.py claim <id> --for <github-user> --agent <claude|codex> --session <session-id> --note "starting"
                   (or:  keeptrack.py next --for <github-user> --agent claude --session <id>)
   - You may only claim tasks assigned to the human you work for. A fresh claim by another session is refused.
3. While working:  keeptrack.py heartbeat <id> --note "<what you are doing>"      # at least every 15 minutes (not for --attended)
   If blocked:     keeptrack.py heartbeat <id> --status blocked --note "<why>"
   Need a person:  keeptrack.py wait <id> --on "<who: what>" --who <user>; comment @<user> with the question; assign <id> <user>; stop
                   (never unwait a wait you did not set in this session, or one on someone else: a person ends it)
4. Finish:         keeptrack.py done <id> --note "<result, PR link>"            # or: keeptrack.py release <id> --column todo
Write cards a newcomer can act on (board/CARDS.md). Every PR, issue, document or page a card mentions goes in its
links:  keeptrack.py link <id> <full URL> --title "<what it is>"
Name cards as links in replies, comments, notes and PRs:  keeptrack.py card-link '#N'   ->  [#N](<card link>)
Never edit board JSON files by hand; always go through `keeptrack.py` so conflicts are handled.
```
Never pass `--session` with an id you did not generate for this run, and never `--force` a claim, `done`, `release` or `heartbeat` unless the person says so; if one is refused, stop and tell them. A clone is one trust domain: the local claim record it wrote owns the card for every process in that clone, so give each agent its own clone. Known limits: the board files themselves hold every claim's session id, so the rules above tell agents to read the board only through `keeptrack.py`; and while the web page's placeholder claim is pending, any session may claim that card for the same agent and person without `--force` (the same as claiming an unclaimed card; the agent limit still applies).

**In Claude's cloud sandbox** (routines, Claude Code on the web) the GitHub API is read-only: writes come back `403 ... not permitted through this proxy`. `keeptrack.py` then commits the changed board files on top of the latest `master` and runs `git push` from its clone (retrying if someone else pushed first), without touching your working tree. `BOARD_WRITE=git` forces this, `BOARD_WRITE=api` disables it.

**Auth without `gh`:** set `BOARD_TOKEN` (or `GH_TOKEN`/`GITHUB_TOKEN`) to a fine-grained token with Contents: Read and write on this repo and `keeptrack.py` calls the GitHub API directly with the standard library. If `BOARD_TOKEN` is set it is used even when `gh` exists. This is the route for cloud agent sandboxes.

**Automatic heartbeat:** `claim` writes `.board-claim.json` in a board repo, or `.keeptrack/claim.json` at the top of any other git repo (both gitignored), so each repo has its own. `keeptrack.py auto-heartbeat` refreshes that claim at most every 15 minutes and silently does nothing if there is no active claim, the claim is attended, it was released or finished, or another session took the task over. The record keeps one entry per claimed card with its session, so parallel sessions in one clone each keep their own cards: each entry notes a hash of the Claude Code session that claimed it, and the hook beats only the cards of its own Claude session (an entry without one, from an older kit or outside Claude Code, gets beats only when its agent is the hook's: `BOARD_AGENT` in the hook's environment, else `claude`, or unnamed; so in a shared checkout a Claude session never keeps a Codex run's claim fresh; only `BOARD_SESSION`'s cards when that is set in the hook's environment). A run with `--session` or `BOARD_SESSION` owns only that session's claims. Every rewrite of the record re-reads it under a lock (`.board-claim.json.lock`) and changes only that command's own cards, so two sessions never drop each other's entries. Each card has its own 15-minute beat time; a failed beat (refused, offline, rate limited) is tried again about a minute later. `.claude/settings.json` runs it as a Claude Code `PostToolUse` hook. Other agents call `keeptrack.py heartbeat` themselves.

**Attended claims:** when a person drives the session, heartbeats are noise (a commit every few minutes, all day). Claim with `--attended`, or set `BOARD_ATTENDED=1` once in your own environment: the claim sends no heartbeats and shows as stale only after 12 hours. Background agents (routines, cloud threads, workers) don't set it, so a stuck one still shows within the board's `stale_after_minutes`.

**Searching what is linked.** `links --client NAME | --project REF | --card ID | --person REF [--kind drive-folder ...] [--json]` lists every link around that scope, nearest first and de-duplicated, each classified (`drive-folder`, `drive-file`, `github`, `dropbox`, `microsoft`, `notion`, `linear`, `profile`, `local`, `web`, `other`) with its id where one exists. The `keeptrack-search` skill uses it to answer questions from a client's or project's files with whatever connectors the session has, walking Drive sub-folders itself because Drive search does not.

**Changing the board itself.** Labels, clients, board members and settings live in `tasks.json`; tasks can be edited after creation. All of it has a command, so nothing needs a hand edit:

| Area | Commands |
| :-- | :-- |
| Task fields | `task-set ID [--title] [--details] [--priority] [--due YYYY-MM-DD\|today\|+N\|""] [--label X]... [--unlabel X]... [--client] [--project] [--contact]`, `unlink ID URL` |
| Labels | `labels`, `label-add NAME [--color #hex]`, `label-set NAME [--rename NEW] [--color #hex]`, `label-rm NAME [--force]`. `add --label` and `task-set --label` create a missing label in grey, as the web board does |
| Clients | `clients`, `client-rename OLD NEW` (tasks, projects, people's company and client info follow), `client-rm NAME` (only when unused), `client-set`, `client-link`, `client-unlink CLIENT URL` (URL or title, as `unlink`) |
| Projects | `projects [--client] [--status active\|done\|paused] [-q]`, `project REF` (goal, people, links and open tasks), `project-add NAME --client C [--north-star]`, `project-set REF [--name] [--client] [--north-star] [--status]`, `project-link REF URL [--title]`, `project-unlink REF URL` (URL or title, as `unlink`), `project-person REF EMAIL [--remove]`, `project-remove REF [--clear-project]` |
| Columns | `columns` (with card counts), `column-add NAME [--after ID]`, `column-set ID --rename NAME` (the id stays), `column-move ID --before ID\|--after ID`, `column-rm ID [--move-to ID]` (refuses while the column has cards unless `--move-to` says where they go; never `todo`, `in-progress`, `done` or the last column). New ids are a slug of the name |
| Board members | `members`, `me`, `member-add USER [--name] [--email ..] [--timezone ..]`, `member-set USER [--name] [--email ..] [--remove-email ..] [--timezone ..]`, `member-rm USER [--unassign]` (never the upgrade owner or someone with an active claim) |
| Agents | `agents`, `agent-add NAME`, `agent-rm NAME [--unassign]` (the names the web board uses in filters and assignment; never one with an active claim) |
| Delete by mistake | `task-rm ID --yes` (a card made by mistake; a finished one should go done and archive), `person-rm REF --yes` (a CRM person added by mistake, not a Lost one). Both refuse without `--yes`; `task-rm` also refuses an active claim. `person-rm` clears the person as a task contact |
| Settings | `settings`, `settings-set [--title] [--stale-minutes N] [--stages "A,B"] [--rename-stage OLD=NEW]` |

Renames (`label-set --rename`, `client-rename`, `settings-set --rename-stage`) also rewrite matching items in `archive/<year>.json` in the same save, so `unarchive` never brings back an old name. Column names are renamed in place, so cards keep their column. The `board-admin` skill tells an agent when to ask first (renames, deletes, `--force`).

Useful environment variables: `BOARD_USER`, `BOARD_AGENT`, `BOARD_SESSION` (also `CLAUDE_SESSION_ID` / `CODEX_SESSION_ID`), `BOARD_REPO`, `BOARD_BRANCH`, `BOARD_PATH` (default `board/tasks.json`). Test safely with `--file some-copy.json`.

## Hosting the web page
GitHub Pages is not available for private repos on the current (free) org plan, so the page lives in the public repo `rain-ventures-ai/keeptrack` (served by GitHub Pages). It contains no client data; the data stays in this private repo and is fetched only with your token. Edit the page there, not here.

## Security notes
- The token is stored in localStorage; use a fine-grained token scoped to this repo only, with an expiry.
- Anyone with write access to this repo can edit the board (and the page's code). Keep client-confidential detail out of card text if the repo audience widens.
- The page escapes all card text (no `innerHTML`) and only links `http(s)` URLs.

### Optional: visibility alarm
This repo holds contacts, so it must stay private. To get a warning if it ever becomes public, install the optional check:

    python3 board/keeptrack.py kit-update --visibility-alarm

It adds `.github/workflows/visibility-alarm.yml`. The workflow runs when the repo is made public, once a day, and on demand. If the repo is not private, it opens one issue titled `P0: board repo is not private`, assigned to the board owner (only if no such issue is already open), and the run fails. It uses only the built-in `GITHUB_TOKEN` (read the repo, write issues). Once installed, `kit-update` keeps it up to date; without the flag it is not installed. To remove it, delete the file and commit.

## Task numbers and mentions
- Every task has a short number (`#12`) shown on its card and in the drawer; click it to copy. Say "#12" when you discuss a task. `keeptrack.py show '#12'` (or `claim`, `done`, `comment`...) accepts it in place of the long id. Quote the `#` in a shell.
- In comments and descriptions, `@github-username` highlights that person (or agent) and `#12` becomes a link to that task. Typing `@` or `#` in the web page offers a pick list.
- A comment that mentions someone shows an **@ you** marker on the card the next time that person opens the board. There are no push notifications; the board is a static page.
- When an agent needs a human's attention, comment with `@username` and the reason: `keeptrack.py comment '#12' "@osouthgate blocked: need the Drive link"`.

## Working from a GitHub issue (board-task)
Issues created with the board's "Create issue" button carry `<!-- board-task: id=... num=N -->` and are titled `[#N] ...`. When you are asked to work such an issue:
1. `python3 board/keeptrack.py show '#N'` for the card, comments and checklist; the issue body is a snapshot.
2. Report back on the board, not only on the issue: `comment '#N' "..."` for progress or questions, `move '#N' in-progress|todo|done` for status, `link '#N' <PR url> --title "PR"` when you open a pull request.
3. Need a person (decision, access, review)? `assign '#N' <github-user> --note "why"` and comment with `@username`; then stop and wait.
4. Finish with `done '#N' --note "<result, PR link>"`. Set BOARD_USER and BOARD_AGENT; without a `gh` login set BOARD_TOKEN (or GH_TOKEN in GitHub Actions).

## Which agents each person uses (Settings → Agents & integrations)
Each person ticks the agents they use: **Claude**, **Codex** or both. The choice is kept in their browser (`kb_agents`) and moves with "Copy settings code". Typing `@` in the web page only offers the agents you have ticked; people are always offered. Before you choose, Claude counts as ticked if your routine is set up. The `agents` list in `tasks.json` is the shared set of names agents may claim under; it does not change per person.

- **Claude:** `@claude` can start your own routine (below). In Today and a cinema lane, open a task's **Assign** menu and choose **Assign to Claude for @you** to create the visible request, claim it for your Claude and start that same routine immediately.
- **Codex:** `@codex` cannot start Codex by itself: OpenAI only starts Codex cloud tasks from an `@codex` comment on a GitHub pull request and offers no trigger a web page can call. Instead, when a card's newest request is for `@codex` (and no Codex comment or running Codex claim has answered it), the card's **Copy for agent** button turns into a highlighted **Copy for Codex**. It copies instructions that tell Codex to do what the newest `@codex` comment asks, with `BOARD_AGENT=codex`. Paste them into Codex; it claims the card and reports back with `keeptrack.py`. The button only changes for people who ticked Codex.

## Assign to Claude or write `@claude`: your own routine
Each person can connect their own Claude routine so that either the **Assign to Claude for @you** quick action or a comment containing `@claude` starts it (web page, Settings → **Agents & integrations** → **@claude in task comments**, switch **Use @claude** on). Only that person's configured routine is offered. The values live only in that person's browser and move with "Copy settings code".

**How it works.** Browsers can't call a routine's trigger URL directly (Anthropic's endpoint sends no CORS headers), so the page creates a one-off job on the person's free cron-job.org account (its API does allow browsers) which POSTs to the routine's `/fire` URL. The page then reads the result, records the session link on the card (an agent claim by `claude`, working for that person) and deletes the job. cron-job.org only ever sees the routine token and the task *number* and requester, never the task's text; the routine reads the real content from the board. Starting takes one to two minutes.

**Setup.** Follow [`board/ROUTINE-SETUP.md`](ROUTINE-SETUP.md) (the routine's saved prompt is the short [`routine-loader.txt`](routine-loader.txt); its behaviour lives in [`routine-prompt.md`](routine-prompt.md), which you can edit here without touching the routine). Or ask Claude Code in this repo to "set up my board routine"; the `board-routine-setup` skill guides and verifies it without handling any secrets.

## Board kit
The tools in this folder (and `.claude/skills/board*`) are the **board kit**. Their source is `rain-ventures-ai/keeptrack` `board/kit/`; `board/KIT_VERSION` says which version this repo has. Do not edit them here: see `board/UPGRADING.md`.

When you change the kit or board schema in the keeptrack repo, add a `CHANGELOG.md` entry, update `UPGRADING.md`, and check in a new frozen sample board under `tests/fixtures/` (documented in `tests/fixtures/README.md`).

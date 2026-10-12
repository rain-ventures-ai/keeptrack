# Changelog

All notable changes to the **board kit** (`board/kit/`) and **board data schema** (`tasks.json` and split files) are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## Web board

- **2026-10-12** — Inbox questions closed with `proposal-done --not-acted` show "Closed without acting by …" (kit v45).

- **2026-10-12** — Mobile Find results keep the full height of wrapped titles and metadata when the on-screen keyboard
  reduces the available space, scrolling the result list instead of overlapping adjacent rows.

- **2026-10-12** — Review Inbox questions (kit v44): Choose, Approve and Question items show the question, its links
  and answer buttons in the Inbox and in Today's review, with an optional note, "Who answers" for a named person,
  Dismiss, and Change answer (Undo) until the agent has acted. Answers write only the question's file. The Inbox is
  always on for split boards; the Settings switch is gone.

- **2026-10-12** — Waiting-for: tasks can be marked as waiting on someone or something, with an optional member and
  chase day, from a Waiting row in the task drawer. Cards show a "waiting on .., Nd" chip that turns amber once the
  chase day has passed (and "waiting on you" on your own waits), a Waiting filter, and Needs attention includes waits
  due for a chase. Assign to Claude and `@claude` are off while a task waits. The page keeps `waiting`,
  `agent_cleared` and `settings.min_kit` on save, and merges `min_kit` as a maximum.

- **2026-10-12** — Today expands Inbox evidence and proposed changes inline, with explicit Accept and Ignore
  actions and Undo. Successful decisions refill a stable board-scoped queue while retaining order, reading position,
  focus and other expanded reviews. Failed saves and changed evidence never advance or silently accept a proposal.
  Existing-task updates show `Updates #N`; genuine other duplicate candidates still require edit/merge review.

- **2026-10-12** — The full Review Inbox uses clearer proposal summaries, source context, grouped changes and
  restrained decision controls, with responsive light/dark styling and visual QA coverage. No proposal decisions
  or board records are changed by this presentation update.

- **2026-10-12** — Today previews Inbox proposals with Review-only cards, source/type and duplicate warnings;
  decisions stay in the full Inbox after evidence review. Shareable links reopen views, settings sections and utility
  screens without carrying tokens. Task cards open with one click/tap or Enter/Space while embedded controls, selection
  and drag/hold gestures stay independent; an opening double-click cannot accidentally dismiss the drawer backdrop.

- **2026-10-12** — Review Inbox: a header Inbox button with a pending count (only when the board turns it on) opens a
  review view grouped by source and run, with filters, current-against-proposed values, Accept, Edit & accept, Merge,
  Ignore, Leave pending, Undo and Reopen, keyboard keys and a phone layout. Settings → Board has the switch.

- **2026-10-12** — Weather widgets offer explicit approximate browser location, with permission/failure guidance,
  rounded local coordinates, per-board/widget overrides and configured-city fallback. No automatic location requests,
  background tracking or GitHub location writes; fixed-city widgets remain supported.

- **2026-10-12** — Routine reports distinguish recorded setup, observed completion and unfinished attempts, with
  source/scope/management details and local-time display. A configurable routine setup form copies safe, board-scoped
  prompts without scheduling work. Members can explicitly link their own companies, protected from removal while
  linked. Double-clicking outside a task drawer closes it through the normal save/cleanup path.

- **2026-10-12** — Task Contacts suggests existing CRM people while typing, with keyboard and touch selection,
  stable CRM references and duplicate prevention. Individual tasks can be archived without losing their details,
  checklist, comments or history, then found and restored through Search.

- **2026-10-12** — Board-owned Today widgets and per-board browser appearance are opt-in. Search now finds Help,
  agent setup, connections and appearance settings, and can switch built-in themes while respecting the active board profile.

- **2026-10-12** — The hosted board is an installable PWA. Each repo/branch/path combination has a separate app identity, launch URL, name, colour and generated initials icon, so several boards can be installed together. The service worker caches the app shell for offline startup and keeps phone notification taps tied to the originating board.

## Schema versions

### Schema 4 (split storage)

- **2026-10-08** — Schema 4 introduced with kit v8 ([#11](https://github.com/rain-ventures-ai/keeptrack/pull/11)): `layout: "split"`, per-card `cards/*.json`, per-person `people/*.json`, `rank` on cards, `verify` and `doctor` for split boards.
- **2026-10-09** — Kit v17 ([#45](https://github.com/rain-ventures-ai/keeptrack/pull/45)): optional `projects/*.json`, client `north_star` in `client_info`, optional `project` on tasks, optional `github` on CRM people; `doctor` warnings `MEMBER_NO_PERSON` and `PROJECT`.

### Schema 3 (monolithic)

- **2026-10-08** — Schema 3 with kit v6–v7: single `tasks.json` holds `tasks` and `contacts`; onboarding and `import` (kit v7).

### Schema 2

- **2026-10-08** — Schema 2 with kit v1–v5: `keeptrack.py` kit commands (`kit-check`, `kit-update`, `migrate`), `init`, multi-repo `use` / `where`, rename from `board.py` to `keeptrack.py` (kit v5).

## Kit versions

### [45] — 2026-10-12

- `proposal-done --not-acted --answer-id <id> [--note]` closes an answered question without acting (`decision.done.acted: false`), so
  a rejected approval or a changed content hash no longer stays open for ever.
- An answered question that is not done is kept whole only for `archive.done_days`; after that it is slimmed and
  archived like other decided items.
- `proposal-done` refuses an `ask.approve` with no `content_hash` (it no longer skips the check).
- The unknown-kind error lists every kind, including `ask.*`.
- Docs: "the agent that asked" is the same `BOARD_AGENT@BOARD_USER`, not one session.

### [44] — 2026-10-12

- The Review Inbox is always on for split-storage boards; `settings.review_inbox` is no longer read. `settings` still
  prints `review_inbox.enabled: true` (or `false (needs split storage …)`) for older skill copies, and
  `settings-set review_inbox.enabled true` is a no-op (`false` is refused). New boards get no `review_inbox` setting.
- Questions: `ask.choose`, `ask.approve` and `ask.question` items, with status `answered`. `proposal-answer` (a person
  only, and only the item's `decider` when set), `proposal-result` (the asking agent reads its own answer),
  `proposal-done` (once, just before acting; an approval needs the matching `--content-hash`), `proposals --mine`
  and `--status answered`. `proposal-reopen` returns an answer not yet acted on to pending. Accept and merge refuse
  questions. The first question raises `settings.min_kit` to 44, and `doctor` reports `MIN_KIT_LOWERED` below that.

### [43] — 2026-10-12

- Waiting-for: `wait ID --on "text" [--who p_id|login] [--nudge +3|date] [--note ..]` parks a card on a person or an
  event; `unwait ID --note ".."` ends it, and so do `done` and `move ID done` (history keeps it). A waiting card is not
  claimable: `claim` refuses it and `next` skips it, and `--force` does not change that. `wait` blocks a running claim
  of its own session or a person's (`blocked_by_wait`); such a claim is live for `release`, and `heartbeat --status
  running` is refused while the card waits. `unwait` runs a young blocked claim again (within `max_agent_claims`) and
  releases a stale one to To do. An agent run ends only a wait it set in the same session that names nobody else.
  Overrides are recorded on the card in `agent_cleared` (newest 20).
- `today` has a CHASE NOW group and a count of other waits; `list --waiting`, `--waiting-on me|login|p_id`, a
  `[waiting: ..]` suffix, and `--attention` includes waits due for a chase. `people` shows `[waiting on them: n]` and
  `person` a "Waiting on them" list. `settings.waiting_days` (default 7, 0 = off) sets the chase day when there is no
  nudge. The single-task `archive` refuses a waiting card.
- `settings.min_kit`: set to 43 by the first `wait`, merged as a maximum. `KIT_VERSION` constant in `keeptrack.py`;
  `doctor` warns `KIT_OLD`, `MIN_KIT_LOWERED`, `CLAIM_BLOCKED` and `AGENT_CLEARED`; `settings-set --min-kit` accepts
  only a value between the stored one and this kit's version.
- Web board: a "waiting on .., Nd" chip (amber once the chase day has passed), a Waiting row in the task drawer, a
  Waiting filter, and Assign to Claude / `@claude` are off on a waiting card. No schema migration.

### [42] — 2026-10-12

- Review Inbox: agents and routines can propose a new task, a task change, a new or changed CRM person, or a contact
  interaction or follow-up. Proposals live in `board/proposals/<id>.json` (split storage only) and are never live
  records. New CLI commands: `proposal-add`, `proposals`, `proposal-show`, `proposal-accept`, `proposal-merge`,
  `proposal-ignore`, `proposal-reopen`, `proposal-undo`. Accept, merge and ignore write the record and the decision in
  one commit and never apply a proposal twice; a changed target stops for review. Email proposals hold no summary or
  subject without `--recipients-confirmed`. Decided proposals are slimmed after 30 days and archived by the sweep.
- The meeting-notes and email skills and their routine guides write proposals when the board turns the Inbox on.
  The Inbox is off by default; turning it on does not create, change or start any routine or schedule.

### [41] — 2026-10-12

- `email-key --stdin` accepts bounded untrusted header input as data; the safely invoked positional form and canonical
  hashes remain compatible. Email skills and shared routine guidance prohibit header interpolation into shell/script text.
- No schema migration, email re-import, board widget installation or routine schedule changes are required.

### [40] — 2026-10-12

- Optional member `own_companies` records explicit identity links, not CRM-employer inference. CLI member-set supports
  repeatable link/unlink options; company/member removal guards and client renames preserve identity protection on retries.
- Doctor checks optional company links, and company/member listings explain linked identity. No schema migration,
  board data changes or routine provisioning is required for this upgrade.

### [39] — 2026-10-12

- Archive an individual task with `archive <id>`, regardless of its age or status, while retaining its complete record.
  Unfinished agent claims must be released or finished first. Existing bulk archive and restore workflows remain available.
- Task contact entries may include an optional `person_id` referencing an existing CRM person alongside compatible
  name, role, email and phone snapshots. No data migration is required.

### [38] — 2026-10-12

- Canonical email message keys deduplicate shared-board scans across members' mailboxes. Bind verified messages to
  existing contact history without changing its summary, stage or date; retry overlap checks after concurrent saves.

### [37] — 2026-10-12

- Protect board-member CRM records from deletion. Add a repo-owned routine register and structured start/finish reports
  with management location, connections, last attempt, last success and bounded run history.

### [36] — 2026-10-12

- Claim ownership follow-ups, from the adversarial review of v35. The local claim record is read once per command (kept across the save retries) instead of two or three times, and `session_for` no longer takes an unused card id. A record that git tracks is ignored with one stderr note, before the file is opened (a symlinked record is never followed, and a record git cannot vouch for is not trusted either), so a board writer who commits `.board-claim.json` cannot give every pulling clone a known session id (one `git ls-files` on the read, so one to three git calls per claim command and none per tool call; the heartbeat hook checks it once per beat; not for a `--file` board or outside a git repo). Writing the record at a board repo's root warns when `.gitignore` does not list it, but still writes it. A bare `heartbeat` (or `--status blocked`), `done` or `release` whose save loses a race re-runs on the newer board, so it can no longer land a `heartbeat_at` or status on another session's fresh claim of the card (`move ID done` re-runs the same way); the API save path is unchanged (a one-file contents PUT still fails when that card's file changed, and the git path when the branch moved). The web page computes the agent-limit busy list once per render instead of once per card, and evaluates it once per `@claude` comment. The board skill says the automatic heartbeat runs at most every 15 minutes, as the code does.

### [35] — 2026-10-11

- Claim ownership and launch checks, from the external review of private-tasks. `done`, `release` and `heartbeat` refuse a card whose claim belongs to another session; `--force` on them is only for a person's explicit say-so, and it overrides only the assignee check and another session's live claim. Releasing a stale, stuck or blocked claim works from any session. A session is identified by `--session`, `BOARD_SESSION`, `CLAUDE_SESSION_ID`, `CODEX_SESSION_ID`, or else the local claim record this clone wrote, so an attended session keeps its own card. A routine's `claim` replaces the web page's `pending-...` placeholder for the same agent and person without `--force`. `--force` no longer bypasses `settings.max_agent_claims`; the capacity refusal says to raise it or use `--attended`. The web page will not send a card to Claude when the board's agent limit is full, and its quick-assign button says why. The routine text no longer mentions `--force`.
- Done evidence and time zones, from the same review. `done` needs `--note` and refuses open checklist items. `done --cancel --note "why"` closes a card without finishing it and records `outcome: cancelled`; a normal done records `outcome: completed`, also in `last_run.outcome`. `show` prints the outcome, the web page shows a "cancelled" pill and includes it in Copy as Markdown and the copied agent instructions, and `move ID done` still works but warns about open to-dos. `--due today` / `+N`, the OVERDUE/TODAY flags and `today` use the acting member's time zone (then the kit owner's, then the first member's), falling back to the host clock when none is on record. `today` starts with `Today is YYYY-MM-DD (Zone)`.

### [34] — 2026-10-11

- Security: only the ONE CRM person with a board member's GitHub login counts as that member's own record. If two or more share it, all stay contacts (so a board writer can't hide real contacts from follow-ups by giving them a member's login) and `doctor` warns `MEMBER_PERSON_DUP`. It is decided from each person's own login, never its id. `person-add`/`person-set`/`person-rm`/`sent` label a member's record like `people` does; a missing id or a null `people[]` no longer breaks `today` or `doctor`. Same rule on the web board, including the "add yourself" nudge. Known limit: at most one contact per member login can be marked, and members come from `people[]`, which board writers can edit; such a contact still shows in People with a "Board member" pill. `person_line` now cleans every board field it prints. From the relay-merge review of private-tasks#32.

### [33] — 2026-10-11

- A CRM person whose GitHub login is a board member's is that member's own record, not a contact (worked out from `people[]`, nothing stored). `today` never lists it as a follow-up and `people`/`person` mark it "board member @login: own record, not a contact". The web board shows it as **You** (or **Board member**), puts you first in People, keeps members out of Today's follow-ups and the Pipeline, and "Copy for AI" says it is a member rather than asking for contact help.

### [32] — 2026-10-11

- Output hardening: the sanitizer and `EMAIL_RE` also cover U+2028/2029, U+2060-2064 and tag characters; `identity_line` shows only a valid time zone and addresses of 254 characters or fewer; `members` cleans the agents line; `set_identity` refuses a non-list `emails`. Claims: the local claim record is written after the save; reviving a stale, stuck or blocked claim (by heartbeat or by re-claiming it in the same session) respects `max_agent_claims`. The sanitizer and email check go by Unicode category (control, format, separators, private-use, unassigned, variation selectors, fillers); `members` shows only valid addresses and time zones. From the relay-merge review of private-tasks#28 (card #12 there).

### [31] — 2026-10-11

- Member records hold work email addresses only (onboarding, `me`, help, skills, AGENTS template). Board data printed to terminals and agents goes through one sanitizer (control, zero-width, bidi); `identity_line` shows only valid addresses; `here` labels the identity line as board data; `settings` shows the enforced limit. From the relay-merge review of private-tasks#28.

### [30] — 2026-10-11

- Security: an item id from board data is used as a file name only if it is a plain token, and local reads and writes refuse paths whose real location is outside the board folder (a `..` or a committed symlink), so a crafted id can't make keeptrack write elsewhere on a member's machine (`doctor`: `BAD_ID`). `here` strips control characters from the project name and error text. Found by an automated security review.

### [29] — 2026-10-11

- The agent claim limit holds when two sessions claim different cards at once: the claim saves through a commit that fails on any newer save, and the losing claim is checked again on the newer board. A bad `max_agent_claims` value is ignored with a `doctor` warning. Member identity output strips control characters; example addresses use example.com. Found by the relay-merge review of private-tasks#28.

### [28] — 2026-10-11

- A board member's record is their identity: optional `emails` (every address they use) and `timezone` on `people[]` entries. `member-add` / `member-set --email` (repeatable), `--remove-email`, `--timezone`; new `me`; `members`, `here` show it; `init --email --timezone` for the first person. Onboarding asks once. `doctor` checks the addresses (`MEMBER_EMAIL`) and warns `MEMBER_NO_PERSON` only while the CRM section is on, so the CRM person stays optional. Agents are told to keep the record current and to write cards someone can act on later.

### [27] — 2026-10-11

- `settings.max_agent_claims`: `claim` refuses an agent claim past the board's limit, checked in the same write, so racing sessions can't exceed it. Found by the relay simulation (three front doors at once reached 3 of 2). Attended and stale claims don't count.

### [26] — 2026-10-11

- Automatic heartbeats every 15 minutes (was 5). New `claim --attended` / `BOARD_ATTENDED=1` for sessions a person drives: no heartbeats, stale only after 12 hours. Python and the web board agree.

### [25] — 2026-10-11

- The trusted-config list is JSON, so a path cannot add entries; rerun `use` once ([#60](https://github.com/rain-ventures-ai/keeptrack/pull/60)).

### [24] — 2026-10-11

- Kit guides (`ROUTINE-SETUP.md`, `README.md`, `board-routine-setup` skill) and `keeptrack.py`'s new-board message use the web board's new Settings tabs: Preferences, Board, Connection, Agents & integrations. No data change. The web board itself was rebuilt on shared components (`board/ui.js`).

### [23] — 2026-10-10

- `links` lists people's email addresses; `keeptrack-search` searches their mail and handles vague questions with a file inventory. Configs are read only if `use` wrote them on this computer (`~/.config/keeptrack/trusted`); rerun `use` once.

### [22] — 2026-10-10

- Repo-aware keeptrack: personal per-folder config moves to `.keeptrack/` (git-ignored; legacy `.board/` still read), `use --project` sets a default project scope for `list`, `next`, `add` and `links`, `here` and a SessionStart hook give connected repos board context and stay silent elsewhere, the heartbeat hook no longer starts Python in untracked repos, the claim file is per repo, `help [topic]` groups every command. Alarm template matches its own issue by author. A committed or symlinked config is never trusted ([#58](https://github.com/rain-ventures-ai/keeptrack/pull/58)).

### [21] — 2026-10-10

- Visibility alarm: test mode, fuller exposure steps, repeat alarms comment ([#57](https://github.com/rain-ventures-ai/keeptrack/pull/57)).

### [20] — 2026-10-10

- `links` command and `keeptrack-search` skill: search what a client or project links to with the session's connectors ([#56](https://github.com/rain-ventures-ai/keeptrack/pull/56)).

### [19] — 2026-10-10

- Columns and labels can be managed from Settings and the CLI; saves merge three ways on a race (web and `keeptrack.py`, exit status 3 on a real clash); renames reach archive files; `task-rm`, `person-rm`, agents commands, `todo-edit`, `project-unlink`, `client-unlink`, `list --label`; `verify` fix for large single-file boards; optional visibility-alarm workflow ([#42](https://github.com/rain-ventures-ai/keeptrack/issues/42), [#51](https://github.com/rain-ventures-ai/keeptrack/issues/51)).

### [18] — 2026-10-10

- Board administration from the CLI (labels, clients, members, settings, wider `task-set`), `board-admin` skill, `verify` on split boards ([#52](https://github.com/rain-ventures-ai/keeptrack/pull/52)).

### [17] — 2026-10-09

- Lightweight CRM projects, client north stars, board-member `github` on people ([#45](https://github.com/rain-ventures-ai/keeptrack/pull/45)).

### [16] — 2026-10-09

- `keeptrack-email` skill and contact-email reconciliation routine.

### [15] — 2026-10-09

- Multiple labelled emails/phones per person; profile vs file/folder resources ([#38](https://github.com/rain-ventures-ai/keeptrack/pull/38)).

### [14] — 2026-10-09

- Meeting-notes routine: verified legacy import, named non-board owners ([#35](https://github.com/rain-ventures-ai/keeptrack/pull/35)).

### [13] — 2026-10-09

- Meeting-notes rolling lookback and ingestion log ([#33](https://github.com/rain-ventures-ai/keeptrack/pull/33)).

### [12] — 2026-10-09

- `keeptrack-notes` recurring import guide ([#31](https://github.com/rain-ventures-ai/keeptrack/pull/31)).

### [11] — 2026-10-09

- `onboard-keeptrack` skill rename; new boards default to schema 4 split ([#29](https://github.com/rain-ventures-ai/keeptrack/pull/29)).

### [10] — 2026-10-09

- Onboarding handoff from web setup ([#21](https://github.com/rain-ventures-ai/keeptrack/pull/21)).

### [9] — 2026-10-09

- CLI column moves assign fresh ranks on split boards.

### [8] — 2026-10-08

- Split storage migration (`migrate --to 4`), web board split reads, `doctor` / `verify` ([#11](https://github.com/rain-ventures-ai/keeptrack/pull/11)).

### [7] — 2026-10-08

- `onboard-keeptrack` / `import` onboarding path.

### [6] — 2026-10-08

- Atomic `--file` writes, archive/unarchive fixes, comment ids.

### [5] — 2026-10-08

- `board.py` → `keeptrack.py`; archive commands and read cache.

### [4] — (historical)

- Early kit packaging in the consulting/co-assets era (see `board/kit/UPGRADING.md`).

### [3] — (historical)

- Multi-repo `use` / plugin layout (`repo-skills`).

### [2] — (historical)

- `init` and Settings → Boards new-board flow.

### [1] — (historical)

- First published kit; `kit-check`, `kit-update`, `migrate`, `kit-owner`.

## Repository tooling

### Unreleased

- Frozen boards under `tests/fixtures/` and CI running Python + Playwright upgrade tests ([#46](https://github.com/rain-ventures-ai/keeptrack/issues/46)).

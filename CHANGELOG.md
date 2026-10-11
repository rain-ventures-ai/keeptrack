# Changelog

All notable changes to the **board kit** (`board/kit/`) and **board data schema** (`tasks.json` and split files) are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## Schema versions

### Schema 4 (split storage)

- **2026-10-08** — Schema 4 introduced with kit v8 ([#11](https://github.com/rain-ventures-ai/keeptrack/pull/11)): `layout: "split"`, per-card `cards/*.json`, per-person `people/*.json`, `rank` on cards, `verify` and `doctor` for split boards.
- **2026-10-09** — Kit v17 ([#45](https://github.com/rain-ventures-ai/keeptrack/pull/45)): optional `projects/*.json`, client `north_star` in `client_info`, optional `project` on tasks, optional `github` on CRM people; `doctor` warnings `MEMBER_NO_PERSON` and `PROJECT`.

### Schema 3 (monolithic)

- **2026-10-08** — Schema 3 with kit v6–v7: single `tasks.json` holds `tasks` and `contacts`; onboarding and `import` (kit v7).

### Schema 2

- **2026-10-08** — Schema 2 with kit v1–v5: `keeptrack.py` kit commands (`kit-check`, `kit-update`, `migrate`), `init`, multi-repo `use` / `where`, rename from `board.py` to `keeptrack.py` (kit v5).

## Kit versions

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

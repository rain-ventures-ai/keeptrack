# Frozen board fixtures

`v3_prioritise` freezes optional task value/effort/board-wide ranks. Tests verify upgrade,
split migration, ordinary current/frozen-v48 CLI edits, and archive/restore preserve these fields.

Small, hand-checked boards used by `tests/test_fixture_boards.py` and browser tests. Each fixture is a **board folder** (the same layout as `board/` in a real repo: `tasks.json`, and for schema v4 split also `cards/`, `people/`, and optionally `projects/`).

| Directory | Schema | Kit era | Source in git history |
|-----------|--------|---------|------------------------|
| `v3/` | v3 monolithic (`tasks` + `contacts` in `tasks.json`) | kit v7 | `tests/fixtures/v3` since #11 (`678a861`) |
| `v4/` | v4 split, no `projects/` files | kit v8–v16 | `tests/fixtures/v4` since #11 |
| `v4_kit17/` | v4 split with `projects/` and client north stars | kit v17 | Derived from #45 (`41e66e0`) project layout |
| `v4_kit37/` | v4 split with projects and a member CRM record | kit v37 | Frozen routine-register/deletion-protection fixture |
| `v4_kit38/` | v4 split with canonical shared-email source keys | kit v38 | Frozen cross-mailbox deduplication fixture |
| `v4_kit39/` | v4 split with CRM-linked task contact snapshots | kit v39 | Frozen contact-reference preservation fixture |
| `v4_kit40/` | v4 split with explicit member-company identity links | kit v40 | Frozen optional identity-link preservation fixture |
| `v4_kit41/` | v4 split with optional browser-weather configuration | kit v41 | Frozen widget configuration preservation fixture |
| `v4_kit43/` | v4 split with a waiting card, a wait-blocked claim, `agent_cleared` and `settings.min_kit` | kit v43 | Frozen waiting-for and flag preservation fixture |
| `v4_kit44/` | v4 split with Review Inbox questions (answered and acted on, pending approval), a proposal and an old `review_inbox` off setting | kit v44 | Frozen always-on Inbox and question preservation fixture |
| `v4_kit46/` | v4 split with the v44 Review Inbox questions and a rank with a random tail (`a1Qx`) | kit v46 | Frozen appended-rank, question and no-new-`min_kit` fixture |
| `v4_kit48/` | v4 split with questions and an appended rank; unchanged data shape | kit v48 | Frozen checkpoint-release board preservation fixture |
| `v4_kit72/` | v4 split, unchanged data shape (a copy of `v4_kit71`) | kit v72 | Frozen board before automation runners (`requires`, `due`, `tick --only`); kit-update 72 to 73 keeps every record |

**When you bump schema or kit:** add a row here, add a frozen directory under `tests/fixtures/`, extend the fixture tests, and add entries to the repo root `CHANGELOG.md` and `board/kit/UPGRADING.md`. The live `demo/` board stays the current showcase only.

Each fixture may include `fixture.json` with expected entity counts and the kit version to simulate before `kit-update`.

`merge3-cases.json` is not a board: it holds shared three-way merge cases (clean merge, clash, lists by id and by content, volatile fields) that `tests/test_merge_parity.py` runs through both `keeptrack.py` and `board.js`. Add a case there when either merge changes.

`proposal-change-cases.json` is not a board either: it holds shared Review Inbox accept checks (allowed fields and value types) that `tests/test_proposal_parity.py` runs through `keeptrack.py` and `board.js`, and `tests/browser/page-safety.test.js` through the page. Add a case there when either check changes.

`v4_kit68` freezes unchanged split data before the card-first link release (kit v67 → v68).

`v4_kit69` freezes unchanged split data before automations (kit v68 → v69).
`v4_kit70` freezes unchanged split data before automation flows (kit v69 → v70).
`v4_kit71` adds a pending `ask.choose` with `change.recommended`, an old unanswered question and
`settings.inbox_lapse_days` (kit v70 → v71). A lapse is computed when read, so the files never change.

`inbox-rules-cases.json` is not a board: it holds the Review Inbox read-time rules (the lapse setting, the recommended
option, when a question has lapsed) that `tests/test_inbox_rules_parity.py` runs through `keeptrack.py` and `board.js`.
Add a case there when either changes.

`v4_kit99` freezes unchanged split records before token selection hardening (kit v96 to v99).

`v4_kit98` freezes unchanged split board data before the image review fixes (kit v96 → v98).

`v4_kit100` freezes unchanged split board data before Gmail source privacy and record history fixes (kit v99 to v100).

`v4_kit101` freezes unchanged split records before archive-size follow-ups (kit v100 to v101).

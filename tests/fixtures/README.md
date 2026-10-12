# Frozen board fixtures

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
| `v4_kit44/` | v4 split with the v43 waiting data and a rank with a random tail (`a1Qx`) | kit v44 | Frozen appended-rank and no-new-`min_kit` fixture |

**When you bump schema or kit:** add a row here, add a frozen directory under `tests/fixtures/`, extend the fixture tests, and add entries to the repo root `CHANGELOG.md` and `board/kit/UPGRADING.md`. The live `demo/` board stays the current showcase only.

Each fixture may include `fixture.json` with expected entity counts and the kit version to simulate before `kit-update`.

`merge3-cases.json` is not a board: it holds shared three-way merge cases (clean merge, clash, lists by id and by content, volatile fields) that `tests/test_merge_parity.py` runs through both `keeptrack.py` and `board.js`. Add a case there when either merge changes.

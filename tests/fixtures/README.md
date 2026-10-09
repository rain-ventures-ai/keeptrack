# Frozen board fixtures

Small, hand-checked boards used by `tests/test_fixture_boards.py` and browser tests. Each fixture is a **board folder** (the same layout as `board/` in a real repo: `tasks.json`, and for schema v4 split also `cards/`, `people/`, and optionally `projects/`).

| Directory | Schema | Kit era | Source in git history |
|-----------|--------|---------|------------------------|
| `v3/` | v3 monolithic (`tasks` + `contacts` in `tasks.json`) | kit v7 | `tests/fixtures/v3` since #11 (`678a861`) |
| `v4/` | v4 split, no `projects/` files | kit v8–v16 | `tests/fixtures/v4` since #11 |
| `v4_kit17/` | v4 split with `projects/` and client north stars | kit v17 | Derived from #45 (`41e66e0`) project layout |

**When you bump schema or kit:** add a row here, add a frozen directory under `tests/fixtures/`, extend the fixture tests, and add entries to the repo root `CHANGELOG.md` and `board/kit/UPGRADING.md`. The live `demo/` board stays the current showcase only.

Each fixture may include `fixture.json` with expected entity counts and the kit version to simulate before `kit-update`.

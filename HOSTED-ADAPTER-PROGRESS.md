# Hosted adapter progress

Contract: keeptrack-cloud 8128b59bd4c3b4bbc4b69089563dd2a0a1b0cce5 (read-only).
Scope: streams C/D, permitted UI/CLI files and new hosted tests. No commits/pushes.

## Done
- Read DESIGN §§5–7, BUILD, OpenAPI/type/SQL contracts and synthetic fixtures.
- Reverified current load/save/mutate seams; GitHub-only adapter refactor in progress.
- Relay home checkout refresh failed: `error: cannot open '.git/FETCH_HEAD': Read-only file system`. No alternative board route attempted; no card specified.

## Evidence
- Baseline Python and browser suites running; exact commands/results to follow.
- Chromium cache already present; no Playwright install run.
- Syntax checks: `node --check board/board.js` and `python3 -m py_compile board/kit/keeptrack.py`: exit 0.

## Next
- Complete baseline/refactor regression evidence before hosted implementation.
- Add hosted HTTP adapters and mock-server tests; rerun regression suites.

## Blockers
- None for code changes. Git metadata/board checkout are read-only.

## Contract change requests
- None.

## Step 1 evidence (before hosted code)
- Baseline `python3 -m unittest discover -s tests -p 'test_*.py'`: exit 0, 568 run, 567 passed, 1 skipped (69.518 s), `/tmp/hosted-baseline-python.log`.
- Refactor same command: exit 0, 568 run, 567 passed, 1 skipped (71.323 s), `/tmp/hosted-refactor-python.log`.
- `cd tests/browser && npm ci`: exit 0, 2 packages, 0 vulnerabilities.
- Baseline and refactor `npm test`: exit 0, 2/2 suites (`split-storage`, `review-inbox`); scripts do not print assertion totals.
- All 17 separate `node *.test.js` CI scripts run before/after. Refactor: 16 passed, task-drawer failed; baseline: same task-drawer failure, later baseline rerun passed. Diagnostic confirms a pending history-back overwrites the test's new `#2` route, with no page errors. Repeated refactor drawer runs fail at line 358 or 360. Checking with CI's Node 22 runtime next (machine default Node 26.12.0).
- Untouched HEAD baseline exported to `/tmp/keeptrack-hosted-baseline`; read-only `.git` link lets mixed-versions read historical commits. Its initial run lacked `.git` and failed mixed-versions; rerun with link: exit 0. No Git metadata writes.
- Refactor patch saved separately at `/tmp/hosted-step1.patch` (before async callback spelling adjustment), SHA-256 `d6e2f8dae1fe0471b8f430cb0b89179d7f0378b4fa697727b59db7d80c2293a0`.
- Hosted implementation currently staged under `/tmp`, not applied until step-1 checks finish.
- CI-runtime check: `npm --cache /tmp/keeptrack-hosted-npm exec --yes --package=node@22 -- node tests/browser/task-drawer.test.js`: exit 0, all drawer checks passed. Step 1 has passing evidence for all 17 CI scripts (16 on Node 26, drawer on CI Node 22), plus both npm suites and Python (567 passed, 1 skipped). Default Node 26 drawer failures remain a baseline/runtime flake.
- Step-1 final diff retained separately at `/tmp/hosted-step1-final.patch`. Hosted code begins only after the above passing checks.

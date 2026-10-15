# Hosted adapter progress

Completed 2026-10-15 20:25 UTC. Streams C (UI) and D (CLI).

## Done

- Completed the GitHub-only load/read/save/mutate seam before applying hosted code. GitHub callbacks, merging, numbering and `--file` behaviour remain on the existing paths.
- Added `board/storage-hosted.js`: snapshot/read/commit/command/changes/whoami, captured revisions, UUID mutation keys, same-key transport retries, omission hydration with revision checks and whole-page cursor application.
- Added hosted UI selection (`?backend=hosted`), local Supabase sign-in, memory-only JWTs, reload/sign-out boundaries, 2.5-second change polling and the existing conflict UI for 412s. Hosted CSP permits only self and the fixed local API/Auth origins; GitHub/cron/weather connections are excluded. GitHub integrations and launch placeholders are disabled.
- Added the CLI HTTP backend (including the direct `load()`/`save_changes()` compatibility seam with captured-revision CAS), `/v1/me` identity, phase-0 commands, guarded commits, CAS conflict handling, claim proof/fence storage outside checkouts (0600 files/0700 directory), and explicit `capability_unavailable` failures without GitHub fallback. Only stdlib urllib is used.
- Added synthetic HTTP tests pinned to the frozen fixture/schema contents. They cover phase-0 mutations, hydration/races, 412 merge/reload, lost-response replay, 503 retries, unscoped approval 403, proof permissions, attended-agent refusal, live versus imported authority, both localhost origins, actual CSP blocking and credential isolation.
- Added safe integer card deep links (the frozen rich fixture allocates six-digit numbers). The delete flow now waits for its drawer's close/history cleanup before writing, avoiding the baseline test's close/reopen race.
- `board/sw.js`, the manifest and every other product file remain untouched. The hosted script is deliberately network-only, with no new service-worker cache entry; hosted phase 0 has no offline session.

## Contract and source

- Frozen contract: keeptrack-cloud `8128b59bd4c3b4bbc4b69089563dd2a0a1b0cce5`.
- The read-only cloud checkout is now at `d7b03cc20f4d13d87ad5f7c17ceb48b0aa58109f`. `git diff --exit-code 8128b59 -- docs/DESIGN.md packages/contracts/openapi.yaml packages/contracts/types.ts packages/contracts/sql-functions.md tests/fixtures` exited 0. BUILD's freeze-status text is the sole difference among the requested documents.
- Original keeptrack parent: `0fe625f`. Another session committed the earlier implementation as `32b9a5b` during this build. This agent ran no commit, push, index mutation or reset. Later fixes and this report remain uncommitted for review.
- No accounts, real keys, real board data, deployments or production changes.

## Evidence

Existing Python command throughout: `python3 -m unittest discover -s tests -p 'test_*.py'`.

| Stage | Exit | Exact result | Log |
| --- | --- | --- | --- |
| Before refactor | 0 | 568 run: 567 passed, 1 skipped; 69.518 s | `/tmp/hosted-baseline-python.log` |
| GitHub-only refactor | 0 | 568 run: 567 passed, 1 skipped; 71.323 s | `/tmp/hosted-refactor-python.log` |
| Hosted before final save-seam regression test | 0 | 584 run: 583 passed, 1 skipped; 82.233 s | `/tmp/hosted-final-python-verified.log` |
| Hosted final | 0 | 585 run: **584 passed, 1 skipped**; 82.841 s | `/tmp/hosted-final-python-complete.log` |
| Hosted CLI focused: `python3 -m unittest discover -s tests -p 'test_hosted_*.py' -v` | 0 | 17 passed; 13.604 s | `/tmp/hosted-cli-tests-final.log` |

Browser commands:

- `cd tests/browser && npm ci`: exit 0, 2 packages installed, 0 vulnerabilities. Existing Chromium cache was used; no `playwright install` ran.
- `cd tests/browser && npm test`: baseline, refactor and final all exit 0, 2/2 suites (`split-storage`, `review-inbox`). Final log: `/tmp/hosted-final-browser-verified.log`.
- All 17 separate Node scripts named by `.github/workflows/test.yml` ran before and after the refactor. Baseline/refactor first runs: 16 passed, drawer timed out at line 358; baseline retry passed, and refactor drawer passed on CI Node 22. Every suite had passing step-1 evidence before hosted code was applied. The baseline copy initially needed a read-only Git metadata link for mixed-versions; its corrected rerun passed.
- Node default is 26.12.0; CI is Node 22. Final CI-runtime verification uses `npm --cache /tmp/keeptrack-hosted-npm exec --yes --package=node@22 -- ...` (resolved runtime 22.23.3). `/tmp/run-hosted-browser.py` reads the workflow and runs each of its 17 `node <name>.test.js` commands, recording individual exit codes and a total.
- Intermediate hosted CI runs reproduced the baseline drawer race on both runtimes. One combined run also hit `net::ERR_ABORTED` in Prioritise's history navigation. These failures are retained in `/tmp/hosted-final-ci-node22.log`, `/tmp/hosted-final-ci-verified.log` and `/tmp/hosted-final-ci-complete.log`; the clean final run after the narrower delete/history fix passed all 17 suites.
- Final CI batch: `npm --cache /tmp/keeptrack-hosted-npm exec --yes --package=node@22 -- python3 /tmp/run-hosted-browser.py /home/osouthgate/dev/rain-ventures-ai/_wt/hosted-adapter /tmp/hosted-final-browser-all.log`: exit 0, **17/17 suites passed in one clean run**. Both originally failing suites also passed individually after the fix.
- `node tests/browser/hosted-adapter.test.js`: exit 0, 11 hosted browser check groups passed, including both localhost origins and six-digit card links; `/tmp/hosted-ui-tests-final.log`.
- Syntax/format checks: `node --check board/board.js`, `node --check board/storage-hosted.js`, `python3 -m py_compile board/kit/keeptrack.py`, `git diff --check`: all exit 0.
- Step-1 diffs retained separately as `/tmp/hosted-step1.patch` and `/tmp/hosted-step1-final.patch`. The first has SHA-256 `d6e2f8dae1fe0471b8f430cb0b89179d7f0378b4fa697727b59db7d80c2293a0`.

The existing browser scripts report suite success, not individual assertion totals. Hosted check groups are reported separately from Python test cases. The mock validates requests against the copied frozen OpenAPI schemas. Its unauthenticated `/` health response is solely for the sandbox port broker's `Go-http-client` listener probe; credentialed traffic is still asserted to use contract paths.

## Next

- Reviewing session: inspect the uncommitted follow-up diff, move this progress file out before the PR, and commit after review. This agent will not commit or push.

## Blockers and limits

- No code blockers or required checks remain. Python, both npm suites, all 17 separate CI browser suites and all 11 hosted browser check groups pass. All browser suites ran within the sandbox.
- Relay home checkout refresh failed with `error: cannot open '.git/FETCH_HEAD': Read-only file system`. No alternative board route was attempted; no card was named for this build. Board used for the attempted bootstrap: `osouthgate/private-tasks`.
- Phase-1b proposal/decision flows and unsupported operations fail explicitly. History-only archive trimming has no phase-0 command; whole card/person archive moves are supported.
- These are mock HTTP/client results, not evidence for real API/SQL/RLS, RL1 or P1 performance gates.

## Contract change requests

None.

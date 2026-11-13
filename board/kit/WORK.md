# Durable Rook work

Rook owns the responsibility across chats. A bounded run owns an execution attempt. Keeptrack remains the task store; this is not another inbox or permission system. Kit 123+, GitHub boards only. Hosted boards explicitly refuse these commands.

## Request and read

`keeptrack.py request-work` reads one JSON object on stdin (at most 16 KiB): `request_id`, `title`, `project`, optional `details` and `todos`. Use a stable opaque source/message ID without private content. Copy the original key and payload across retries and front doors. The result is a Backlog card with a stable task ID and logical `rook:<project-id>` owner. It does not approve, dispatch or start anything.

The same key and original payload return the same card after edits, completion or archive. A changed payload under the same key refuses. Missing archive evidence refuses; never fall back to ordinary `add` after an uncertain save. Different keys are not semantic deduplication. Report `possible_related` to the owner using the ordinary duplicate-decision process.

`keeptrack.py work-status t_ID` returns structured state, next action, public run metadata and a card link. Claim state is recorded board state; `runner_liveness: unknown` is deliberate. Existing `show` and `list --json` redact claim credentials and private coordination verifier fields. Repository access is still a trusted boundary, not a public data API.

## Runner contract

These are host-runner commands, not general worker tools. Keep the high-entropy receipt file owner-private and outside the worker mount. Never put it in the brief, environment, Git branch or card. Public IDs look like `wr_` plus 24 hex digits and are separate from `BOARD_SESSION` and receipt proof.

1. Use the existing approval, eligibility and exact-session claim flow. The initial local host claim includes `--executor relay-local`; generic unattended claims cannot take coordinated tasks. A verified owning registered worker may renew its own claim. Every unattended claim also respects unresolved coordinated project attempts. All new writes use stable `t_` task IDs; numbers are for display.
2. `work-start t_ID --run-id wr_ID --receipt PRIVATE_FILE --host-pid PID` records one attempt against that claim. Launch only if the result contains **both** `created: true` and `launch: true`. Repeating a start never permits another launch. Another unresolved attempt on the task/project blocks it atomically.
3. `work-event` takes the same task/run/receipt arguments plus one JSON event on stdin: stable `id`, kind `progress|waiting|result_ready|failed`, optional short `summary`, HTTPS `links`, capture `coverage` and numeric `exit_code`. At most eight progress events per attempt. Use real milestones, not tool-call commentary. Retry identical payloads unchanged.
4. `work-finish` takes a terminal event (`kind: finished|interrupted`) separately from the milestone cap. `launch_state` is `not_launched` only when the host proves no worker was launched; otherwise `may_have_launched`. The terminal receipt ends an attempt, not the task. Existing Done, waits, Pending review and PR links are preserved. If effects may have happened without a recorded result, the task stays In progress with `needs_reconciliation`; it cannot run again automatically.
5. `work-release-owned t_ID` is atomic pre-launch/legacy cleanup: only the exact current session's claim can be removed, preserving recorded results and successor claims. Do not use ordinary `release --column todo` as a conditional finaliser.

Historical proof-backed terminal retirement can seal an older attempt without removing a successor claim or modifying its column. Ordinary old-run progress still refuses. This does not resolve unknown effects by itself.

## Reconciliation

Inspect the actual branch, PR, task and other outward effects. A missing process, missing card link or zero exit code is insufficient evidence that retrying is safe. No exactly-once guarantee is made for external effects.

Once the owner authorises the exact disposition, a host operator may use `work-resolve t_ID --run-id wr_ID --receipt PRIVATE_FILE --disposition retry-safe|recorded-result --note "verified evidence and decision" --confirmed`. `recorded-result` requires a result/wait already on the task. `retry-safe` can return an unclaimed task to To do after checking effects. The resolution is durable and idempotent; it never replaces a successor's claim or creates approval. The automatic runner never calls this command.

Attempts are bounded to 16 per task. Keep all identity receipts; a limit requires reconciliation, not pruning old receipts to permit replay. File receipts and their retention are the host runner's responsibility. No financial detail, contacts, raw transcript, secrets or arbitrary tool output belongs in coordination/comments. Keep detailed evidence in authorised linked storage and report capture gaps honestly.

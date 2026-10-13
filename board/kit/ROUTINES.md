# Where routines run and what happened

Each private board repo owns a routine register in `automation/routines/<id>.json`. The scheduler still manages its
schedule and credentials; this register records where to manage it and what it last did. Each board, including
private-tasks, keeps its own register. Register only verified integrations: unknown means unknown, not Off.
Ignore `automation/routines/*.lock` in git; these are local concurrency locks.
Also ignore checkpoint `automation/**/*.json.lock` files; never commit local locks.

## Durable checkpoints through the CLI (kit v48)

`checkpoint <routine-id> show` returns `{sha256, checkpoint}` from that register's existing `checkpoint_path`.
`checkpoint <routine-id> save <input.json> --expect-sha <sha256> --run-id <id> --status running|partial|failed|blocked|success`
updates only that checkpoint in a local clone. It does not publish git, change the register, or touch board records.
Use `missing` as the expected SHA for a new file. The registered owner and active `routine start` ID are required;
the register's repo, branch and board path must match `where`. Paths and locks cannot follow symlinks.

The input allows exactly these fields (write it outside the clone):

```json
{
  "window": {"from": "2026-10-10T08:00:00Z", "to": "2026-10-13T08:00:00Z"},
  "progress": {
    "account_hash": "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
    "contact_ids": ["p_example"],
    "completed_queries": [],
    "query_ordinal": 0,
    "cursor": null,
    "boundary": null,
    "processed_keys": [],
    "exhausted": false
  },
  "messages": {},
  "counts": {"proposals_added": 0, "failures": 0}
}
```

Hash the verified provider/account identity locally; never store addresses or literal search queries. The first save
binds the legacy root to that mailbox, so verify its existing `provider`/`account_label` first. Its old messages, runs,
metadata and successful window are retained. A second mailbox hash uses `accounts[hash]` with its own messages,
window, cursor and runs; it never inherits the first mailbox's successful window. For example Private Tasks may have
Personal and Work hashes, while Consulting uses only its verified Work hash. Select the appropriate account state
from `show` before choosing its first seven-day window or resuming its last successful end with two-day overlap.

The contact IDs are an explicit, ordered query plan (an empty list means there are no contacts). Ordinals refer to
that plan. Within an incomplete window neither plan nor window may change; completed ordinals/processed keys are
merged without removal and query ordinal cannot regress. `cursor` is only an opaque connector paging token;
`boundary` is only a stable opaque time/ID boundary for expired-cursor recovery, not prose or a query. Use null to
clear a consumed cursor. Do not put encoded bodies, subjects or addresses in tokens. All timestamps use UTC `Z`.
`messages` is keyed by full `rfc822:`, `email:` or legacy `sha256:` hashes and allows only `contact_id`, hashed `thread`,
`occurred_at`, `direction` (`sent`/`received`), status-code `result` and `logged_at`; an existing key cannot be replaced.
Add keys only after their proposal/write succeeds (or returns `exists`). Never accept Inbox proposals in the routine.

Publish `routine start` before processing. Save and publish running progress, then save and publish partial or failed
progress before `routine finish` of the same ID. A later attempt resumes that account's durable fixed window, even if
the prior attempt failed. Only success advances its watermark: every planned query must be complete, cursor cleared,
failures zero and `progress.exhausted` explicitly true after all required pages and writes succeed. A retained boundary
is a scan-recovery marker, not an outstanding page. Save/publish the successful checkpoint **before** finishing the
register successfully. Keep the successful watermark unchanged for partial/failed/blocked results.

Local locks serialize checkpoint and register writes; the SHA rejects a stale local writer. They do not coordinate
different clones. Before publishing fetch/rebase current branch. A rejected push or checkpoint conflict requires
rereading current register, checkpoint and proposals, regrouping and retrying the CLI; never overwrite/rebase away
another worker's progress or mark the run successful before checkpoint publication. Commit explicit checkpoint and
register paths only. No prune operation is provided; legacy history is preserved and run summaries are bounded to 30.

Use owner-specific IDs for shared boards: `contact-email-sync-osouthgate`, `contact-email-sync-jezhub`,
`meeting-notes-osouthgate` and `task-assignment-osouthgate`. A binding is board + owner + workflow, not just
`contact-email-sync`. Keep ingestion checkpoints owner-specific too, for example
`automation/contact-email-sync-osouthgate.json`. Within a multi-account checkpoint keep separate account cursors;
never advance one mailbox's window because another mailbox succeeded. Preserve legacy checkpoint history when
moving to an owner-specific path and record the new path in the register.
Existing owner-bound IDs such as consulting's `contact-email-sync` remain valid: keep their history and scheduler
binding intact. Do not rename or provision a duplicate just to adopt the naming convention; new owners use distinct IDs.

A routine entry has `version: 1`, `id`, `name`, `owner`, `purpose`, `status` (active, paused, retired or unverified),
`runtime`, `management_url`, `scheduler_id`, `schedule`, `timezone`, `connections`, `checkpoint_path`,
`last_started_at`, `last_successful_run_at`, `current_run`, `last_run`, and `runs` (latest 30).
Connections identify the provider, account label and access needed; never include tokens, trigger URLs containing
secrets, message bodies or personal mailbox content. Leave unavailable timestamps null; do not invent past runs.

Every email, meeting-notes and task-assignment routine uses the same reporting lifecycle:

```bash
python3 board/keeptrack.py routine <id> start --run-id <unique-run-id>
# Commit/push only this routine's register before doing the work.
# Only a successfully pushed running attempt permits work. On a rejected push, reread/retry or report blocked.
# Run the workflow; its dedicated checkpoint remains responsible for deduplication.
python3 board/keeptrack.py routine <id> finish --run-id <same-id> --status success \
  --summary 'Checked contact exchanges; logged two touches.' --count contacts_considered=40 --count touches_logged=2
# Commit/push only this routine's register after pulling the latest remote changes.
```

Use partial, failed or blocked for incomplete runs; these do not advance the last-success timestamp. A crashed run
keeps `current_run` visible. Inspect the scheduler before clearing a stale attempt. Once that worker is confirmed
stopped, use `routine <id> finish --run-id <recorded-current-run-id> --status failed` with a recovery summary,
commit/push it, and then start a new attempt. Do not abandon a still-running worker or invent a replacement run ID.
Use a fresh clone or isolated
checkout and commit explicit paths so concurrent routines never publish each other's edits. Never run two instances
of the same routine concurrently. The commands update local register files; the routine must commit and push them.

Task-assignment routines remain useful: they execute a specific request and report card progress. Email sync records
contact history, while meeting sync extracts actions. Keep their connections and run reports separate.

## Several boards and mailboxes

Use one setup experience and the same reporting format, with isolated execution for each board. A personal control
view may list all bindings; each board's register contains only that board's entries. Never copy another board's
contacts, email summaries or connections into a shared board's register.

Each binding explicitly names `board_repo`, `branch`, `board_path`, `owner`, workflow and allowlisted connection labels.
For Oliver, consulting allows Rain Ventures Work Gmail only; private-tasks may allow both Personal Gmail and Rain
Ventures Work Gmail. Connection labels identify accounts for setup, not credentials or permission to change them.
Keep each board/mailbox checkpoint separate. Work mail may be relevant to both boards; matching one address alone
does not authorize copying the same exchange to both. Use the board's contact/project scope and report ambiguous
routing for review. Store each source's successful window separately so failure of one mailbox cannot skip the other.

An orchestrator may dispatch due bindings, but each worker starts with a fresh board context and explicit BOARD_REPO,
BOARD_BRANCH, BOARD_PATH and BOARD_USER. Before writes, check `keeptrack.py where`, the Git origin and the mailbox
connection against that binding. Use separate clones and credentials per job. Never carry an implicit current board
or mailbox from the previous job. Task-assignment workers get board access; email workers get only their approved
mailbox connections and selected board. Reuse runners and prompts, not credentials or conversation state.

Enable means: choose workflow and board; verify account access; approve scope/schedule; provision the scheduler;
record its actual id and management location; run a test; publish the observed result. A checkbox alone records intent.
Show desired status and observed last-run status separately; a paused/retired scheduler must be reflected in the register.
Existing routines with an ingestion log but no verified scheduler stay `unverified`. Do not infer a scheduler or a
last-success timestamp from that log. A board without external contacts has nothing for contact-history sync to match;
project/task email proposals are a separate workflow and need their own scope.
That proposals-only binding may record suggestions in its approved private-repo proposal path, but must not create,
complete, assign or edit board tasks, contact details or follow-ups before owner approval. Match to explicitly approved
project/repo/task scope, not merely an email address that also appears on a different board.

On a board with the Review Inbox (every split-storage board from kit v44), the approved proposal path is
`board/proposals/`, written only through `keeptrack.py proposal-add`. A routine adds and lists proposals; it never
accepts, merges, ignores, reopens or undoes them, and never answers a question. The Inbox is part of the board, not a
routine: it never registers, provisions or activates a scheduler, and the register stays the record of what runs.

The scheduler's configuration is authoritative for whether a job runs. Register status records the latest verified
observation and browser preferences only control the browser. Store the actual runtime and management location:
local Codex jobs need their configured host available; cloud workers need cloud connections and cannot reuse a
desktop's local auth or paths. Setup must report unsupported provisioning honestly instead of claiming a universal
one-click integration.

## Shared mailbox exchanges

Each owner's checkpoint records what that owner scanned. Deduplication on the shared contact record uses individual
message keys independent of the scanner. Prefer `keeptrack.py email-key --stdin`, passing the retrieved header value
as stdin data from your connector/runtime, never as shell or script text. It returns
`rfc822:<sha256>` after normalizing outer brackets/whitespace and domain case while preserving local-part case.
This key identifies the same message across mailboxes; a provider/account-scoped `email:<sha256>` fallback only
identifies that provider's copy. Never hash a subject, body, address or whole thread as a substitute message identity.

Headers are untrusted input. A quoted placeholder is not safe if an agent substitutes a raw header into a shell
command: quotes, backticks and shell syntax can escape it before Keeptrack validates anything. Use a non-shell argv
API or bounded stdin, for example `subprocess.run(["python3", "board/keeptrack.py", "email-key", "--stdin"],
input=header_value, text=True, capture_output=True, check=True, shell=False)`, where `header_value` is connector data,
not interpolated into Python source. The positional form remains compatible only when passed as one argv element
without a shell. Never use `shell=True`, `eval`, shell substitution, or generate executable text containing raw headers.

Read current contact touches before grouping messages. Exclude already represented keys, preserve later replies
as new messages, and pass every new key to `touch --source-message-id`. The CLI rechecks contact-level overlap on
concurrent writes. Staggering Oliver's and Jez's schedules reduces load but is not duplicate protection.
For a verified older manual email touch that already contains the same exchange, use
`touch-source <person> <exact-touch-id> --source-message-id <key>` to attach identity without adding another touch.
Do this only when the facts and event time establish that equivalence; put uncertain matches in needs-review.

Set an explicit maximum batch (for example 100 matched messages or 15 minutes), retain unfinished windows, and report
remaining work as partial. Long outages resume from the last successful window rather than dropping the gap.
Persist per-account query/contact progress and per-query paging cursors/order (or stable time/ID boundaries), completed
pages/queries and processed message keys on partial runs. Resume that position instead of scanning the first capped
batch repeatedly. Only advance the account/window watermark after every required query/page is exhausted.
Represent query progress with contact IDs, query ordinals or hashed query identities and opaque cursors; never store
literal mailbox search queries containing email addresses.

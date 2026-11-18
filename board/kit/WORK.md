# Durable Rook work

Rook owns the responsibility across chats. A bounded run owns an execution attempt. Keeptrack remains the task store; this is not another inbox or permission system. Repository work needs kit 125+; the separate research pilot below needs kit 126. GitHub boards only; hosted boards explicitly refuse these commands.

## Public research pilot

Kit 126 adds an opt-in `relay-research` route for a single public-source research
pilot. The owner hands over an unclaimed Backlog card with one to eight explicit
public HTTPS source links; every input card link is treated as a source. It needs
no repository, branch or PR. The ordinary repository runner's
readiness checks remain in place. Missing configuration is inert.

The owner-only **Hand to Rook** button creates and answers an existing
`ask.approve` in one compare-and-swap, bound to the exact task input. It does not
start a worker. The separately configured host runs `work-research-admit` with
the full proposal and answer IDs, its adopted configuration digest and a private
admission receipt. Admission consumes that answer once and moves the card to
To do, adding the approving owner to assignees without replacing existing
assignments. `work-start --claim-research` requires the private admission receipt and
claims the task and records its run in one whole-board CAS. Its separate private
run proof is durably written before that mutation. A refusal cannot leave only
a claim. The browser presents the approval scope inline; one owner button remains
the approval, without a second confirmation dialog. Relayed answers, `confirmed`, card prose and labels
grant no approval. Before saving that answer the browser authenticates to a
separate owner endpoint using a private capability. The endpoint persists a
signed receipt for the exact board, owner, project, task, proposal/answer IDs,
input digest, policy and expiry. Admission requires `--owner-action-receipt`
and `--owner-action-key`; the trusted host pins both private paths. Git pushes,
including genuine owner pushes, are audit data and cannot replace that action.
Missing or invalid proof means wait. File mode is for
offline fixtures only. Leaving To do/In progress withdraws the grant, including when
there is no claim. Browser Undo cannot revive it.

Research validation uses the same typed refusal as the work contract. A definite
withdrawn/mismatched-grant refusal removes its newly created start proof only
after a canonical read confirms no matching run was saved. Unknown save outcomes
retain the proof. The loader caches the research module within one CLI process.

The digest includes task ID, canonical project ID, title, description, checklist,
source links, dependency IDs, the owner identity and approval lifetime. The host
checks that owner and lifetime against its own adopted configuration. Combined
brief/checklist text is bounded to 4000 UTF-8 bytes. Column, heartbeat, comments and host progress
are not input. A changed brief or adopted configuration needs a new owner
action. Approval must be admitted within the configured 60–3,600 seconds; an
already consumed grant is instead bounded by the host's run deadline. The
private admission receipt fixes `admitted_at` before the CAS. Board `admission.at`
must match it on every verification; retries do not restart the clock. The host
derives its execution window from that verified private value, not mutable board
timestamps. `work-research-check` returns the validated task snapshot, scope and
private admission time together from one canonical read.
`work-research-candidates` adds a bounded `actions` map of current unconsumed
proposal/answer identities and input hashes. Stale or privacy-screened requests
are omitted from that map. It is filtering data; the host must verify the exact
private signed action and recheck the selected canonical request before admission.
The public setting `rook_research` has exactly `v: 1`, `enabled: true`, `board`,
`owner`, `projects`, `profile: public-research`, `policy_digest` and
`approval_ttl`. It is not a policy resolver. The owner must separately approve
the matching private host configuration and its capabilities before activation.

The host calls `work-research-handover` after publishing one immutable report.
That single CAS records run evidence, the separate research artifact and a host-written
**Current state** of at most 1 KiB, releases the exact claim, and moves to Pending
review. No progress comments are added. Completion needs an adopted informational
rule and no remaining owner step or unticked checklist item. Changed scope,
successor claims and unknown-effect holds refuse a late report. A retry of an
already saved handover returns the saved result without duplicating its link.
The private report link is `coordination.research.artifact`, displayed in Current
state, and retained in the run result. It is not added to public source links,
so reusing a card does not feed the private report to the public fetcher.
`work-research-reconcile` verifies the saved payload's private host seal before
recovery treats it as an achieved outcome; copying board fields cannot forge it.
The pilot never ticks unchecked work merely because a report was produced.
With unchecked items the host selects Pending review even under the optional
informational profile; the native completion guard is deliberately stricter.
Before launch, `work-research-note` accepts only fixed host reason codes. A
temporarily unavailable source leaves a quiet Rook wait. A rejected source or
expired run window returns the card to Backlog, withdraws the grant and records
one owner exception. It neither adds progress comments nor charges an attempt.

After canonical start, ordinary public-read failures before the model boundary
use `work-research-read-failed`. Its receipt-bound CAS releases only the exact
claim, retires the grant and records `not_launched` without an unknown-effect
hold. The host shows checked source links and a fresh owner action as the next
step. A private seal permits an exact metadata replay after a lost response;
it cannot clear a successor claim, existing hold or recorded result.

`watch` adds `research` alongside `run`. `watch-poll --project ID` reads an
optional cursor JSON string from stdin and returns `{events,cursor,baseline,
semantics}`. It uses the same watch projection, with a maximum 256 project cards
and 128 KiB encoded snapshot. Before building each entry it also refuses more
than 4,096 elements in a collection, 16,384 visited values, 128 Ki characters of
relevant input text or nesting deeper than 12. Oversized activity fails before
hashing/allocating projection lists; detailed activity belongs in linked run
logs. These bounds do not remove the existing whole-board storage read.
The first poll is a quiet baseline. The cursor contains
public state and hashes, never private coordination proofs, and is bound to its
board/project. It is untrusted client data, not a durable event history; a host
must reconcile the current task/run after a wake or restart. Hosted mode is
unsupported. `work-research-snapshot` and `work-research-check` give the host a
bounded request projection without activity/comment history.

`watch-poll --project ID --history` (kit v134) replays board commits instead of
diffing two snapshots, so an intermediate change is never lost. Its cursor is one
commit, `{"v":2,"board","project","commit"}` in base64url, with no snapshot; no
cursor is a quiet baseline at the branch head. Each call verifies the commit is an
ancestor of the head, then replays every later commit (side branches included) in
topological order, oldest first: at most 20 that changed the board folder and 200
examined. Each is diffed against its own first parent with the same projection
and bounds, so every event is a real change on that commit. Every event carries
its `commit` and an `id` hashed from board, commit, card, kind, text, author and
an ordinal. Delivery is at least once: a merge is diffed against its first parent,
so a side branch's change comes again at the merge with another `id`. Pages are
whole units along the head's first-parent line (a plain commit, or a merge with
its side branch); the cursor only moves forward along that line, so no commit is
skipped. A commit over the bounds, without the board folder, with board data of
the wrong shape or with a board file
that is not valid JSON, or a side branch longer than the 200-commit scan cap,
gives one `unreplayable` event (`card: null`) naming the commit or merge, and the
replay moves on: a loud gap, never a silent one. An ambiguous project name or
prefix at the cursor produces a gap event as the replay advances when the cursor's
project ID is still one of the matches. The replay stays on that project.
A call stops loudly only when it
must read an unreadable board at head (head itself changed the board, or the
cursor sits on an unreadable commit). One call can load up to the scan cap's
worth of past boards (200); on the API transport each load costs about 5
requests, and each watched project caches its commit parents on disk so a
catch-up reads its compare range once (plus one small count check per poll).
An idle poll for an exact project ID checks only the branch head (one API
request) when a local snapshot has already verified that project at that commit.
A cold cache, name or prefix needs a board read to validate scope. Idle reads
skip blob pruning. Baselines and replays of the current board tree prune
obsolete cached blobs.
The reply adds `more` (poll again at once) and `semantics: "commit-replay"`. A
non-ancestor (force-push or rewrite) or unknown commit is refused loudly, never
silently re-baselined; start a fresh baseline and reconcile. A `--file` board has
no history and is refused. A replayed commit gives the same events and ids
whenever it is replayed, so clock-only states (stale by age, chase, overdue) are
not history events, and `at` (the poll's time) is not part of an `id`. Like the
snapshot cursor, a history cursor or event is not authority and grants nothing.

The separate browser capability and host signing key must remain inaccessible
to workers and other repository agents. Settings → Rook owner approval stores
the endpoint/capability only in this browser for the connected board, outside
settings exports. The signing key stays on the trusted host. A stolen browser
capability or compromised owner host is outside this boundary. The research
worker receives neither credential, admission proof nor a board clone.
Generic chat/voice MCP confirmation is not direct owner-input proof: those
requests still wait for the button until a verified ingress is implemented.
The host/operator contract is in [Relay PR 161](https://github.com/rain-ventures-ai/keeptrack-relay/pull/161).
Keep Pending review for the first pilot: the notifier handles reports needing
review and unresolved holds, but informational research completion currently
has no completion notification. The host writes private versioned files;
an approved private HTTPS mapping and an active notification sender must be
provided and checked separately.

After inspecting an uncertain attempt, the owner uses the Relay host's checked
`--resolve-run` command. It binds the canonical resolution to private evidence
before `work-research-retire` withdraws that exact run's grant and releases the
host intent. A bare board resolution cannot clear the private hold. Evidence is
retained and the old action never relaunches; another attempt needs a new button
action. This is separate from ordinary repository-run resolution.

If an atomic start response is unknown and no run was saved, the host may use
`work-finish --fence-missing-start` with both private proofs to record an uncertain
interruption. That CAS creates a sealed cancellation record for the same run ID,
so a delayed start cannot acquire a launch permit. It records no result and
does not clear a successor claim. Owner resolution can finish an interrupted
cancellation before resolving the exact run. A missing private proof means the
native start never reached its remote-mutation boundary and may retry safely.

## Request and read

`keeptrack.py request-work` reads one JSON object on stdin (at most 16 KiB): `request_id`, `title`, `project`, optional `details` and `todos`. Use a stable opaque source/message ID without private content. Copy the original key and payload across retries and front doors. The result is a Backlog card with a stable task ID and logical `rook:<project-id>` owner. It does not approve, dispatch or start anything.

The disabled-by-default public research pilot has a separate host-only boundary: `work-research-box-handoff t_SOURCE --approval r_ID --answer a_ID --policy-digest sha256:HASH --owner-action-receipt PRIVATE_ACTION --owner-action-key PRIVATE_KEY`. This verifies the direct exact owner approval and its private MAC inside the latest mutation snapshot. It derives the request text and dependencies from that signed projection, then creates and approves one deterministic `button:<answer id>` runner card and consumes the answer in one compare-and-swap write. Conflicts rerun every check. Cancellation, scope changes, expired signatures or a different current action refuse. Existing request identities are returned without approval or another launch, including withdrawn/cancelled cards. Missing support in an older kit is a refusal: never fall back to create-then-move. This command does not start the runner or enable the pilot. The host launches only after `created` is exactly true, the returned stable id matches the answer, the column is To do and its final snapshot check agrees; the runner still performs its own claim/start checks.

Replay lookup resolves the recorded source/approval/answer binding before reading current source text, so later source edits do not hide an existing runner's identity/status. New handoffs derive and validate only inside the mutation snapshot. The signed checklist must be entirely unfinished, and combined details plus source links must fit the runner's 2,000-character details limit; neither done flags nor text are silently normalised away. Like the existing research admission/policy APIs, private verification key selection belongs to the trusted host process, outside board/worker mounts; these CLI arguments are not a remote board-writer authentication interface.

The same key and original payload return the same card after edits, completion or archive. A changed payload under the same key refuses. Introducing coordination raises `settings.min_kit` to 125 atomically; older writers become read-only so they cannot bypass execution holds. For existing coordinated boards, raise that minimum within their ordinary kit-upgrade PR before unattended use. Never fall back to ordinary `add` after an uncertain save. Different keys are not semantic deduplication. Report `possible_related` to the owner using the ordinary duplicate-decision process.

An append-only `rook_request_index` establishes absence without reading unrelated archives for every new request. Its IDs, checksum and settings marker are committed in the same whole-board CAS as creation. Archive, deletion and ordinary writers retain it. A known ID with a missing card refuses instead of recreating it; an unavailable archive blocks an indexed archived replay, but cannot invalidate absence already proven by the complete index. Restoring a damaged established index requires its committed version, never rebuilding from surviving cards alone.

The receipt index is capped at 4,096 identities (roughly 120 KiB). At capacity, existing requests remain replayable and new identities refuse; no identity is pruned. Pre-index boards bootstrap once, reading one archive shard at a time, with explicit bounds of 16 archive parts and 10,000 cards. An unreadable archive, inconsistent receipt or exceeded bootstrap bound refuses without saving a partial index. Larger boards require a separately controlled index migration or sharded receipt store before this intake can be used. Known archived replays still scan archive parts; this index optimises new intake, not archive lookup.

The request receipt stores its original canonical project ID independently of the card's current project. Moving or renaming the card/project does not change request identity. Historical receipts without that field are matched conservatively against their saved digest and known project identities; ambiguous evidence refuses.

`keeptrack.py work-status t_ID` returns structured state, next action, public run metadata and a card link. Claim state is recorded board state; `runner_liveness: unknown` is deliberate. Existing `show` and `list --json` redact claim credentials and private coordination verifier fields. Repository access is still a trusted boundary, not a public data API.

## Runner contract

These are host-runner commands, not general worker tools. Keep the high-entropy receipt file owner-private and outside the worker mount. Never put it in the brief, environment, Git branch or card. Public IDs look like `wr_` plus 24 hex digits and are separate from `BOARD_SESSION` and receipt proof.

Before recording a canonical run, initial proof publication fsyncs the file, receipt directory and directory ancestry, including freshly created state folders. Receipt directory paths must use physical directories: symlinked parents refuse before publication, because syncing the destination alone would not preserve the symlink used to find the proof. Retrying an existing proof crosses the same directory barrier. A failed durability barrier prevents the board mutation; mere file existence is insufficient proof of crash durability.

1. Use the existing approval, eligibility and exact-session claim flow. The initial local host claim includes `--executor relay-local --json`; its saved response returns `id` and the server-generated `generation`, never session credentials. Capture that generation once for cleanup. Runner claims require To do for legacy cards too. The saved claim records `unattended_approved` only for unattended To do admission or renewal of the same admitted incarnation. Historical or interactive claims cannot launch or requeue through runner commands. Generic unattended claims cannot take coordinated tasks, and coordinated Backlog work requires attended authorisation. `next` skips cards unavailable to its executor or project holds. A verified owning registered worker may renew its own claim. Every unattended claim also respects unresolved coordinated project attempts. All new writes use stable `t_` task IDs; numbers are for display.
2. `work-start t_ID --run-id wr_ID --receipt PRIVATE_FILE --host-pid PID` records one attempt against an unattended runner claim. Attended claims refuse: interactive Backlog work is not unattended approval. Launch only if the result contains **both** `created: true` and `launch: true`. Repeating a start never permits another launch. Another unresolved attempt on the task/project blocks it atomically. Each run retains its original project scope, so moving the card cannot move its unresolved hold away from that project.
3. `work-event` takes the same task/run/receipt arguments plus one JSON event on stdin: stable `id`, kind `progress|waiting|result_ready|failed`, optional short `summary`, HTTPS `links`, capture `coverage` and numeric `exit_code`. At most eight progress events per attempt. Use real milestones, not tool-call commentary. Retry identical payloads unchanged.
4. `work-finish` takes a terminal event (`kind: finished|interrupted`) separately from the milestone cap. `launch_state` is `not_launched` only when the host proves no worker was launched; otherwise `may_have_launched`. The terminal receipt ends an attempt, not the task. Existing Done, waits, Pending review and PR links are preserved. If effects may have happened without a recorded result, the task stays In progress with `needs_reconciliation`; it cannot run again automatically.
5. `work-release-owned t_ID --claim-generation GENERATION` is atomic pre-launch/legacy cleanup: only the exact current session's matching unattended incarnation can be removed. Repeating an old cleanup after release/reclaim returns unchanged, even with the same session ID. Never read the current generation afresh to authorise old cleanup. Attended claims refuse and use an explicit attended finish/release path. Historical attempts without proof of unattended admission stay In progress on pre-launch finalisation; cleanup does not approve them. Do not use ordinary `release --column todo` as a conditional finaliser.

Historical proof-backed terminal retirement can seal an older attempt without removing a successor claim or modifying its column. Claim generations distinguish release/reclaim by the same session; live renewals keep their generation, but a completed claim starts a new incarnation and cannot renew an unresolved run. Identical authenticated old starts/events replay as `created: false`; new old-run progress still refuses. This does not resolve unknown effects by itself.

`work-start` also needs current approval: the card must still be In progress under its approved claim, so an owner who moves it back to Backlog withdraws the launch. The receipt must belong to the task it starts, and a run ID that any task already holds is refused. A runner release or a not-launched final event returns a card to To do only if it is still In progress or To do; otherwise the card keeps the column the owner chose. Moving a card out of To do or In progress through the CLI ends its unattended approval and moving it back does not restore it. The web board's move does not clear approval yet, so a card moved out and back in on the web can still start: withdraw approval by moving the card to Backlog and releasing its claim. Clearing an expired wait requeues a card only from In progress, on the CLI and the web board. A board-wide `watch` reports run changes (`run` events: started, finished, held for unknown effect, resolved) from public state only. A run with no terminal receipt shows as running in `watch` for ever, including one whose claim went stale; check such a run with `work-status`.

Project holds also apply to heartbeat and unwait revival, including the automatic heartbeat hook and web wait clearing. The exact owning coordinated attempt can renew its own claim; unrelated projects still receive heartbeats. Clearing an expired wait requeues only a claim with retained unattended admission and no unresolved run. Attended and historical claims keep their current column; clearing a wait never creates approval. A stale legacy claim is not proof that its process stopped: another coordinated start in that project refuses until it is explicitly reconciled or released.

Current task project names, case variants and ID prefixes resolve before scope comparison; ambiguous current references conservatively match every possible project. New starts require a uniquely resolvable current project and store its canonical ID. Authenticated replay is checked first, so later project edits cannot turn an old start into another launch or an error.

An unresolved run's retained project ID (or historical owner fallback) must be an exact current canonical ID. A historical raw name or prefix cannot prove its original identity, even if it now matches a project: rename or name reuse may have rebound it. Such attempts refuse unattended admission and unrelated claim revival across the board until explicitly reconciled. The exact owning attempt can still renew; owner-authorised reconciliation remains available with its receipt. Resolved runs do not impose this barrier. Known canonical project holds continue to allow unrelated work.

Unknown-effect decisions use evidence bound to the attempt by a host receipt (`result_ready` event or terminal links). Old task PR links, waits or columns cannot attest a later run. Only the host, not ordinary card text or an arbitrary PR-shaped URL, can record that run result. The card's canonical column/wait is still preserved.

Explicit and bulk archive, deletion, merge and undo keep unresolved coordinated attempts on the live board until their effects are resolved, in both CLI and web writers. A refused merge does not copy source details into the destination. These checks rerun after a lost save. Marking the card Done does not hide or clear its hold: `work-status` still reports reconciliation when an unresolved run has no matching live claim, while preserving the task's column.

## Reconciliation

Inspect the actual branch, PR, task and other outward effects. A missing process, missing card link or zero exit code is insufficient evidence that retrying is safe. No exactly-once guarantee is made for external effects.

Once the owner authorises the exact disposition, a host operator may use `work-resolve t_ID --run-id wr_ID --receipt PRIVATE_FILE --disposition retry-safe|recorded-result --note "verified evidence and decision" --confirmed`. `recorded-result` requires host-attested run evidence linked on the task, or `--result-link HTTPS_URL` to explicitly bind an owner-verified task link to this run. A task link alone is insufficient. `retry-safe` can return an unclaimed task to To do after checking effects only when its run retained `admission: approved-todo`, and replenishes one charged attempt without deleting replay receipts. Historical attempts without admission evidence stay in their current column. The resolution is durable and idempotent; it never replaces a successor's claim or creates approval. The automatic runner never calls this command.

Attempts are bounded to 16 charged attempts per task: terminal `not_launched` attempts and owner-confirmed `retry-safe` resolutions do not count. Keep all identity receipts; at the limit the owner can authorise a checked `retry-safe` resolution, never prune old receipts to permit replay. File receipts and their retention are the host runner's responsibility. No financial detail, contacts, raw transcript, secrets or arbitrary tool output belongs in coordination/comments. Keep detailed evidence in authorised linked storage and report capture gaps honestly.

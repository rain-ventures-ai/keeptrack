# Where routines run and what happened

Each private board repo owns a routine register in `automation/routines/<id>.json`. The scheduler still manages its
schedule and credentials; this register records where to manage it and what it last did. Each board, including
private-tasks, keeps its own register. Register only verified integrations: unknown means unknown, not Off.
Ignore `automation/routines/*.lock` in git; these are local concurrency locks.

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
keeps `current_run` visible. Inspect the scheduler before clearing a stale attempt. Use a fresh clone or isolated
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

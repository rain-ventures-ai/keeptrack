# Schedules and shared boards

Keeptrack records which routines belong to a board, who owns them, where they are managed and what they last did.
The scheduler runs the work; the board's routine register reports it. Installing a plugin or enabling an option in
your browser does not by itself create a scheduled job.

## Set one up

Open **Settings → Agents & integrations** and copy the setup prompt for the workflow you want. Tell your assistant
the board, your GitHub username, the connected account labels, the permitted changes, a first-run date range and a
schedule with a timezone.

The **Set up any routine for this board** form offers post-meeting notes, contact-email history, safe cleanup
proposals, task-agent requests and custom goals or briefings. Add your own goal (for example, "What could generate
revenue soon?") and desired schedule/time zone, then copy its starter prompt. This only copies instructions; it does
not save those drafts, create a scheduler or enable a routine. Your assistant confirms scope and action permissions,
checks existing registrations and the actual runner, then asks before provisioning. Reuse a matching binding rather
than creating another schedule for the same board/owner/workflow.

Cleanup defaults to proposals: candidates and reasons, no task changes, deletion or archival without approval.
Briefings likewise propose task changes. Private email content must never be published; a shared-message summary
needs explicit sharing approval and evidence that every intended recipient received that particular message. Being
on another reply in the same thread does not establish permission. Shared-output publication needs a concurrency
guard appropriate to the runner; separate local register locks alone are not cross-user coordination.

With the [Review Inbox](review-inbox.md) on, the notes and email routines add proposals instead of changing the
board. A person accepts them. Turning the Inbox on does not create, change or start a routine.

For example:

> Set up a daily contact-email routine for my consulting board at 08:00 Europe/London. Use my Work Gmail only,
> start with the last seven days, update existing contact logs and explicit follow-ups, and record every run in the repo.

The assistant must verify access and set up a real job in the scheduler available in your environment. A local
Codex automation runs on its configured machine and needs that machine and its connections available. A cloud
routine needs cloud-accessible repo and mailbox connections; it cannot assume access to your local folders or login.
The register records the actual scheduler ID and management link or location, rather than claiming a job exists
because a setup prompt was copied. There is no universal one-click provisioning for every scheduler.

Run a small test before enabling the schedule. Record its result, then confirm the scheduler is active. Pause or edit
the job where its register says it is managed, and update the board's register to reflect that change.

## Several boards or accounts

Use the same setup and reporting format for all routines, with a separate binding for each **board + owner + workflow**.
Each binding names its board, branch, data path, accounts and permitted actions. Workers verify that context before
writing; they do not inherit a previous job's current board or mailbox.

| Example | Accounts | Permitted work |
|---|---|---|
| Oliver's consulting contact routine | Work Gmail | Existing contact history and explicit follow-ups |
| Oliver's private-tasks proposal routine | Personal Gmail + Work Gmail | Project/task proposals for approval |
| Jez's consulting contact routine | Jez's approved work mailbox | The same shared contact log, with duplicate checks |

A work exchange may be relevant to both boards, but an address match alone does not justify copying it into both.
Use the contact/project scope of each board and ask for review when routing is unclear. Each mailbox has its own
successful scan window so a failure in one account cannot skip unprocessed mail in another.

For a proposals-only task routine, save suggestions for review in that private board's approved proposal location.
Do not create, complete, assign or change tasks, contact details or follow-ups until the owner approves those proposals.
Use approved project names, linked repos and existing task context to establish relevance; contact address matching
alone cannot provide that project scope.

Task-assignment routines remain useful: they execute requests on cards and report progress. Email and meeting routines
reconcile outside information. Keep their permissions separate; a task comment does not need access to your mailbox.

## Shared threads and multiple users

Oliver and Jez can both scan the same thread. Each has a separate schedule, routine ID and checkpoint. Contact-log
entries use a shared per-message key derived from the RFC822 Message-ID where available, so the same message in two
mailboxes is recognized on the shared board. New replies retain their own keys and can add new activity.

Before writing, the routine re-reads the person's log and checks already represented messages. It also compares the
facts with older manual entries that have no source keys. A clearly equivalent entry can be linked to its verified
message keys; ambiguous overlaps go to review. Different scan times alone do not prevent duplicates, and provider-only
IDs cannot prove that copies in different mailboxes are the same message.

## What the board records

Each board stores entries in `automation/routines/<id>.json`, using owner-specific IDs such as
`contact-email-sync-osouthgate` and `contact-email-sync-jezhub`. Entries include the management location, account
labels, schedule, last start, last successful run, current attempt and recent summaries with structured counts.
The email workflow also keeps a separate owner/account checkpoint for scanned windows and processed message keys.
These files contain no tokens or full emails.

An active register entry is an observation about a scheduler, not a live health check. An unknown scheduler stays
unverified. Browser integration preferences control that browser's features; they do not pause a server or desktop job.

Routine cards show recorded setup status separately from the last observed run result. Times are displayed in your
browser's local time; expand **Run details, sources and management** for raw UTC timestamps, counts, approved sources,
scope and where to manage the real schedule. An unfinished attempt means no completion was reported—not proof the
worker is still running. Legacy registrations without a complete board/branch/path binding need scope verification.

If a run fails, its last-success time stays unchanged so it can retry the missed window. If it crashes, inspect the
scheduler first. Once the old worker is confirmed stopped, finish that recorded run ID as failed before retrying.
Use bounded batches, report remaining work and never advance past mail that was not processed. Technical setup and
reporting commands are in [board/ROUTINES.md](../../board/kit/ROUTINES.md).

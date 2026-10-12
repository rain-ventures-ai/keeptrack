# Review Inbox

The Review Inbox holds changes that an agent or routine wants to make. Nothing in it is on your board until a person accepts it.

Use it when meeting notes or email produce more suggestions than real, agreed work.

## What it is (and is not)

- A proposal is a suggested change: a new task, a change to a task, a new or changed CRM person, or a logged interaction or follow-up.
- Proposals are stored apart from your tasks and people, in `board/proposals/`. One file holds one proposal.
- A proposal is not a task. It has no column and no status on the board. It is not counted, and it is not shown in Kanban, List, Calendar, Schedule, Activity, Today, widgets or search.
- Agents never pick up a proposal as work. Only an accepted change reaches the board.

## Turn it on

The Inbox needs split storage (schema 4). See [Repair a board](repair-a-board.md) and `board/UPGRADING.md` if your board is older.

1. Open **Settings → Board**.
2. Tick **Review Inbox**.

Or run `python3 board/keeptrack.py settings-set review_inbox.enabled true`.

Turning it on only changes this setting. It does not create, change or start any routine or schedule. You set those up separately (see [Schedules and shared boards](schedules.md)).

When it is on, the meeting-notes and email workflows send their suggestions to the Inbox instead of writing to the board.

## Review proposals

1. Open **Today**. When proposals are waiting, **To review** previews the newest five with their type, source date and any duplicate warning. Choose **Review** to read the evidence and proposed changes before deciding; previewing never accepts or ignores anything. The **Review Inbox** tile and **Review all** open the full Inbox. While proposals wait, an **Inbox** button with a count also shows at the top.
2. Proposals are grouped by source (a meeting or an email) and then by the run that found them.
3. Use the filters to show one type, one source, one reviewer, or decided proposals.

Each proposal shows:

- the proposed change, and for a change to a record, the current value next to the proposed value;
- why it was proposed, and a link to the source with its date;
- the owner and due date, but only when the source stated them. Otherwise it says "Not stated";
- a warning when it looks like an existing record, or when you ignored the same work before.

For each proposal, pick one:

| Action | What happens |
|---|---|
| **Accept** | The change is made on the board. |
| **Edit & accept** | Change the proposed values first. The edited values are saved. |
| **Merge…** | Add it to an existing task or person. Existing comments, checklist items and history stay. You choose which other fields to set. |
| **Ignore** | Nothing changes on the board. The same suggestion from the same source will not come back. |
| **Leave pending** | Nothing changes. Move on to the next one. |

There is no "accept all". Each change is a choice.

Keys: **j** and **k** move between proposals. **a** accepts, **e** edits, **m** merges and **i** ignores. **Enter** opens the record, or moves to the buttons when there is no record yet.

## Safety

- Before a change is made, the page reads the proposal and the record again.
- If someone else already decided the proposal, you see "Already accepted by …". Nothing is written twice.
- If the record changed after the proposal was made, you see each changed field. Pick what to keep. Nothing is saved until you confirm.
- The record and the decision are saved together in one commit. If the save stops half way, it can be run again without making a second record.
- **Undo** (Ctrl+Z, Cmd+Z or the Undo button) takes back an accept only if nobody changed the record since. Otherwise it stops and keeps the later edits. An undone proposal goes back to pending.
- An ignored proposal can be reopened.

## Repeats and later meetings

- The same action from the same source is recognised and not proposed again, even if it was ignored.
- A new action from a later meeting is proposed as normal.
- If a later source repeats work that you ignored before, it is proposed again with a note: "You ignored this on …".
- Being suggested before never counts as accepted.

## Privacy

- A proposal stores a short reason, at most 300 characters. It never stores a transcript, an email body or attachments.
- An email proposal on a shared board can hold a summary only when every intended reader of the board received that specific email. For example, on a board shared by two people, both must have received it. Being on another reply in the same thread is not enough.
- Otherwise an email proposal can only log that an email happened. It holds who it was from, the date and a message key. The subject line is left out too. It cannot be edited into a summary, and it cannot propose a task or a change to a person.
- After 30 days, decided proposals keep only their keys, title, source, decision and result. The reason and details are removed. The archive sweep later moves old decided proposals into `board/archive/<year>.json`.

## Limits

- The "only once" guarantee comes from GitHub: a save is accepted only if nobody saved since the page read the board. There are no lock files.
- A single-file board (schema 3) cannot save several files in one commit. That is why the Inbox needs split storage.
- Someone with direct access to the repo can still change files by hand. The checks are in Keeptrack, not in GitHub.

## For agents

Agents use the same rules through the command line:

```
python3 board/keeptrack.py proposal-add proposals.json --dry-run
python3 board/keeptrack.py proposal-add proposals.json
python3 board/keeptrack.py proposals --status pending
python3 board/keeptrack.py proposal-show <id>
python3 board/keeptrack.py proposal-accept <id> [--edit edited.json]
python3 board/keeptrack.py proposal-merge <id> --into <task or person id> [--fields title,due]
python3 board/keeptrack.py proposal-ignore <id> [--reason "..."]
python3 board/keeptrack.py proposal-reopen <id>
python3 board/keeptrack.py proposal-undo <id>
```

A routine only adds and lists proposals. It never accepts them. Exit code 3 means the proposal was already decided, or the record changed.

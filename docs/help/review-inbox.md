# Review Inbox

The Review Inbox is where agents and routines stop and wait for a person. It holds two kinds of item:

- **Proposals**: a change an agent wants to make to the board. Nothing changes until a person accepts it.
- **Questions** (from kit v44): a decision only a person can make, such as "which design do you prefer?", "send this
  draft email?" or "what budget should we use?". The person answers; the agent that asked does the work.

Use it when meeting notes or email produce more suggestions than real, agreed work, and whenever an agent needs a
person to decide before it acts.

## What it is (and is not)

- A proposal is a suggested change: a new task, a change to a task, a new or changed CRM person, or a logged interaction or follow-up.
- Proposals are stored apart from your tasks and people, in `board/proposals/`. One file holds one proposal.
- A proposal is not a task. It has no column and no status on the board. It is not counted, and it is not shown in Kanban, List, Calendar, Schedule, Activity, Today, widgets or search.
- Agents never pick up a proposal as work. Only an accepted change reaches the board.

## Always on

From kit v44 the Inbox is always on for a board with split storage (schema 4). There is no setting. An older board
moves to split storage with `python3 board/keeptrack.py migrate --to 4` (see `board/UPGRADING.md`); until then it has
no Inbox.

The Inbox does not create, change or start any routine or schedule. You set those up separately (see
[Schedules and shared boards](schedules.md)). The meeting-notes and email workflows send their suggestions to the
Inbox instead of writing to the board.

## Review proposals

1. Open **Today**. **To review** starts with the newest five proposals. Choose **Review** to expand the evidence and proposed changes inline, then **Accept** or **Ignore**. Ignore can be undone. Updates identify their existing task; a different possible duplicate requires the full Inbox's edit/merge review. Successful decisions refill the preview from the pending queue while preserving the remaining order and your reading position. Failed saves leave the item pending. Incoming remote proposals append without replacing the item you are reviewing, and changed evidence must be reviewed again before saving. The **Review Inbox** tile and **Review all** open the full Inbox. While proposals wait, an **Inbox** button with a count also shows at the top.
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

## Answer questions

A question shows the question, links to what it is about (a draft, a design, a pull request) and, while it waits, the
ways to answer:

| Type | How you answer |
|---|---|
| **Choose** | Pick one of the options. When the agent allows it, write something else instead. |
| **Approve** | **Approve** or **Do not approve**. Open the link first: the approval is for exactly that version. |
| **Question** | Write your answer and choose **Send answer**. |

You can add a note to any answer. **Dismiss** closes a question without an answer, and **Leave pending** moves on.

- A question can name the person who answers it ("Who answers: @sam"). Only that person can answer, dismiss or
  change it; others see "Waiting for @sam to answer". Without a name, any board member can.
- An answer changes nothing on the board. Only the question's own file changes.
- **Change answer** (or Undo) puts the question back to pending, until the agent has acted on the answer. After that
  the question shows "Acted on by …" and stays as it is.
- A question holds links and a short summary, never the content itself. A draft email stays in the mailbox, a design
  stays in Drive.
- The agent that asked acts on an answer once. For an approval, it acts only if the content is still exactly the version
  you approved. If the draft changed, it must ask you again.

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
- After 30 days, decided proposals keep only their keys, title, source, decision and result. The reason and details are removed. For a question, this waits until the agent has acted on the answer; then the choice or approval stays and any written answer or note is removed. The archive sweep later moves old decided proposals into `board/archive/<year>.json`.

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

Questions (kit v44) use three kinds. The `change` holds `question` (one line, at most 300 characters), optional
`task` (a card id for context) and `links` (`[{url, title}]`, https only), plus:

- `ask.choose`: `options` (2 to 10 of `{key, label, url, note}`) and `allow_other` (true or false);
- `ask.approve`: `subject` (`{type: email|message|pr|document|other, url, summary}`) and `content_hash`
  (required: `sha256:<64 hex>` of the exact content you will send or merge). An email `summary` needs
  `--recipients-confirmed`; without it, link the draft and leave the summary out;
- `ask.question`: nothing more.

Set `decider` to a GitHub login when only one person may answer. There is no `target`.

```
python3 board/keeptrack.py proposal-add question.json          # the agent asks
python3 board/keeptrack.py proposals --status answered --mine  # the agent's own answered questions
python3 board/keeptrack.py proposal-result <id>                # the answer (an agent reads only its own)
python3 board/keeptrack.py proposal-done <id> --answer-id <answer_id from proposal-result> [--content-hash sha256:...] [--note "sent"]   # just before acting
python3 board/keeptrack.py proposal-answer <id> --choose b | --other "…" | --approve | --reject | --text "…" [--note "…"]   # a person only
```

Agents never answer or reopen questions, and dismiss only their own pending question (to withdraw it after asking
again with a new one); this is refused for anything else when `BOARD_AGENT` is set. Run `proposal-done` just before
you act: it records the answer as acted on, once, and prints the answer it locked. Act on that printed answer only: a
person may have changed the answer since you read it (`--answer-id` refuses when it changed). Exit code 3 means someone already acted, or, for an approval, the
content hash differs from the approved one; then do not act, and ask again with a new question if needed.

When you will not act on an answer (it was rejected, the content hash changed, or the work is no longer needed), close
it with `proposal-done <id> --not-acted --answer-id <answer_id> --note "why"`. The Inbox then shows "Closed without acting". Only the person named as `decider`, when there is one, or the asking agent can run `proposal-done` on a question. An answer nobody
acts on or closes is kept whole for `archive.done_days` (90 days by default), then slimmed and archived like the rest.

"The agent that asked" means the same `BOARD_AGENT` and `BOARD_USER` (for example `claude@osouthgate`), not one session:
a later run of the same routine can pick up the answer. Every run for that agent and person can read and act on it,
and `proposal-done` still lets only one of them act.

If the card waits on the answer, use `keeptrack.py wait <card> --on "answer to <question id>"` and stop.

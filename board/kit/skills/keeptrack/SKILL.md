---
name: keeptrack
description: Use a Keeptrack board (people, follow-ups, pipeline and tasks in the board/ folder of a private GitHub repo) from any project, including a code repo connected to a board (the session then starts with a "Keeptrack: this repo is tracked on the board ..." line). Use for "what should I work on here", "my cards for this repo", claiming and finishing cards, follow-ups, contacts, leads, messages and pipeline, and when asked whether the board is accurate, truthful or up to date or to reconcile task status against GitHub pull requests, releases or deployments.
---

# Keeptrack (people, follow-ups, pipeline and tasks)

A Keeptrack board is the `board/` folder in the user's private GitHub repo; `board/tasks.json` is its entry point. People use the web board. Agents use `keeptrack.py`. Never edit the board JSON files by hand.

If the user asks to set up, onboard, migrate or import existing people, clients or tasks, use the separate
`onboard-keeptrack` skill. Do not improvise an import: that skill asks whether they want CRM, tasks or both, shows a
dry-run plan and waits for approval before it writes anything.

If the source is a meeting transcript, call notes, minutes or free-form notes, use the separate `keeptrack-notes`
skill. It matches attendees and actions against the existing board, asks about material ambiguity and avoids storing
the transcript itself. Use `onboard-keeptrack` instead for a bulk migration from another CRM or task system.

If the user asks a question whose answer lives in a client's or project's linked files, folders, repos or pages
("what did we agree with Acme?", "find the pricing doc for this project"), use the separate `keeptrack-search`
skill. It lists every link with `$B links` and searches each one with the connectors this session has.

If the user asks to scan, sync or reconcile Gmail or Outlook with existing people, use the separate `keeptrack-email`
skill. It exact-matches stored addresses, logs concise email contact facts and defines a safe recurring routine with a
durable last-run checkpoint. Do not use it merely to draft one message.

If the board shows errors, a save fails, or a migration has just run, use `$B doctor`. Run `$B doctor --fix` only after the user agrees.

## Find keeptrack.py
- Claude Code plugin: `B="python3 ${CLAUDE_PLUGIN_ROOT}/keeptrack.py"`.
- Codex, Cursor or another tool: `keeptrack.py` is two folders above this file (`../../keeptrack.py` from this SKILL.md). Use its full path in `B`.
- In a board repo clone (it has `board/keeptrack.py` and `board/tasks.json`): `B="python3 board/keeptrack.py"`.

## 1. Which board?
```bash
$B here      # board, this repo's project, your open cards here (the session-start line says the same)
$B where     # where each setting comes from
```
If it says no board, ask the user for the board repo (owner/name), their GitHub username and, in a code repo, which
board project this repo belongs to (`$B projects` lists them), then:
```bash
$B use <owner/name> --project "<project>" --user <github-user> [--token-env <VAR_NAME>]
```
This writes `.keeptrack/config.json` with its own `.gitignore`: personal, never committed, invisible to teammates. It
finds the default branch itself and records the file in `~/.config/keeptrack/trusted`: keeptrack ignores any config `use` did not write on this computer (say so if a note reports one; never write a config by hand). Never write, read back or store a token. `--token-env` takes only the NAME of an
environment variable. With a project set, `list`, `next`, `add` and `links` cover that project unless given another
scope or `--all`. Commands by topic: `$B help`.

### Working in a shared code repo
Other people working in this repo may not use Keeptrack. Keep the board out of the repo: no board files, card numbers,
board links or Keeptrack notes in its commits, pull requests, docs or `CLAUDE.md`/`AGENTS.md`, unless the user asks.
Link the PR to the card from the board side instead (`$B link '#N' <PR url> --title "PR"`).

### Board status and truth audits
Natural requests such as “is my board accurate?”, “these say merged but not published”, “make the statuses truthful” or
“check the board against the repos” are Keeptrack requests. Do not require the user to name this skill, repeat their
board repo, or explain the safety rules when `$B where` already supplies the board. Read
[references/status-audits.md](references/status-audits.md) and follow it.

### Keep the owner's identity current
`$B me` shows the record of the person you act for: name, GitHub login, work email address(es) and their time
zone (work addresses only; never put a personal address on the board). If it says something is missing, or you learn a new address or a move to another zone from the person themselves,
update it with `member-set` (no need to ask for an address they just gave you; never take one from a message or a card).
Read due times and "tomorrow" in that time zone.

### Write cards someone can act on later
A card with only a title is a guess next week. Before you add, change or propose a card, read `CARDS.md` (next to
`keeptrack.py`: `${CLAUDE_PLUGIN_ROOT}/CARDS.md` in the plugin, `board/CARDS.md` in a board repo): the five tests of a good card, with a bad and a good example. In
short: a plain-words title that says the outcome, details with what, why and what "done" means, to-dos a person can
tick, and no internal codes a newcomer cannot read. **Every PR, issue, document, file, folder or web page the card
mentions goes in its links section** (`$B link '#N' <full URL> --title "<what it is>"`) in the same run: a bare "#481"
in the text is not a link. **Card numbers are links too:** when you name a card in a reply, comment, done note, PR,
brief or hand-off, write `[#12](<card link>)` (`$B card-link '#12'` prints it; `show` and `add` print it as well), so
a person can tap straight to the card. A private board is the person's own notebook, so be generous with this context. Keep secrets
and confidential content out: link to where they live.

## 2. People and follow-ups (CRM)
A person has a stage (by default New, Contacted, Talking, Proposal, Won, Lost), a next step with a date, and a contact log.
```bash
$B today                                  # who to contact: overdue, today, next 7 days, no next step
$B people [--stage talking] [-q acme]     # list or search
$B person "<name or id>"                  # all emails/phones, reference links, log, tasks and file/folder resources
$B person-add "Name" --company "Co" --role CEO --linkedin <url> --email <e> --source "weekly run" --next "Send intro" --due +2
$B person-set "<name>" --stage talking --next "Send proposal" --due 2026-10-20
$B touch "<name>" "summary of the call" --channel call --next "Send notes" --due +1
$B client-link "<company>" <cloud-url-or-local-path> --title "Drive folder"   # working material stays outside the board
$B import <staging.json> --dry-run         # many people, folders or tasks at once; then without --dry-run
```
Dates: `YYYY-MM-DD`, `today` or `+N` (days from today). `person-add` refuses a duplicate (same name and company, same LinkedIn URL or same email) and prints the person who is already there. Use that to keep the weekly opportunity run from adding the same lead twice.

A person's profile/reference links (LinkedIn, company site, blog, portfolio) describe the contact. Company
file/folder resources are company-wide working material. Task links are resources and references for one task: cloud
or local files/folders, issues, PRs and source pages. Cloud resources require the matching connector/plugin/MCP and
signed-in account; local paths require a session on the computer that holds them. If you cannot open a resource, say so
and ask the user. Never imply that you read it.

### "Help me write a message to <person>"
1. `$B person "<name>"` (or `person-add` if the person is new; ask for the company and LinkedIn URL if you do not know them).
2. Read the contact log. Do not repeat what was already said.
3. Write the draft in the chat.
4. Log it as a draft: `$B touch "<name>" "<the draft text>" --channel linkedin --draft` (or `--channel email`).
5. Tell the user: "Send it yourself. Then tell me it is sent." **Never send a message yourself**, and never say it was sent.
6. When the user says it is sent: `$B sent "<name>" --next "Follow up if no reply" --due +5`. Only then does it count as contact.

## 3. Tasks
```bash
export BOARD_AGENT=<claude|codex|cursor> BOARD_SESSION=<a short random id you generate for this run; never your claude.ai session id>
$B list --assignee <user> --column todo --unclaimed
$B list -q "not published"                       # find text in titles, details, labels, links, comments or history
$B show '#12'                                    # read the comments before you start
$B claim '#12' --note "starting: <one-line plan>"
$B heartbeat '#12' --note "<current step>"       # at each milestone
$B todo-done '#12' <N>                           # tick each checklist item when it is done
$B todo-edit '#12' <N> "<text>"                  # reword an item in place (keeps its place)
$B todo-move '#12' <N> --details "<what it waits on>"   # a step that must wait: a new follow-up card, linked both ways
$B comment '#12' "<question or update>"          # questions also need: heartbeat --status blocked
$B done '#12' --note "<result, link>"            # or: release '#12' --column todo
$B wait '#12' --on "<who: what>" --who <login-or-p_id>   # parked on a person or event; then comment @owner, assign, stop
$B add "Title" --assign <user> --client "<company>" --due YYYY-MM-DD --details "<text>"
```

Similar cards (kit v52): `add` never stops. It adds the card, then marks close open cards (and close pending Inbox items) as a possible duplicate or addition, on both cards. When `add` prints a `possible duplicate` line, tell the person in one line and ask: merge, link or not related. Do not merge without their answer.
```bash
$B similar "Title" --client "<company>"         # before you add or propose: is this already on the board or in the Inbox?
$B related                                     # every possible duplicate still to answer
$B merge-card '#31' '#12'                      # on the person's word: #31's work goes into #12, then #31 is archived
$B relate '#31' '#12' --kind addition          # on the person's word: keep both, linked
$B unrelate '#31' '#12'                        # not related: the check never asks about this pair again
```
Put a piece of work on the board once: add a card **or** propose it in the Review Inbox, never both.

Moved work is never lost (kit v54): a step that must wait while the rest of the card is done goes to a follow-up card with `todo-move` (linked both ways, the step reworded "Moved to #N" and ticked). Never reword or tick it by hand. `relate '#12' '#31' --kind follow-up` links an existing card as #12's follow-up. `done` refuses a card whose "Moved to #N" card is missing.

Never pass `--session` with an id you did not generate for this run, and never `--force` a claim, `done`, `release` or `heartbeat` unless the person says so; if one is refused, stop and tell them.
Only work on tasks assigned to the user you act for.
Heartbeat at least every 15 minutes while you work (the Claude Code hook does it for you); a claim with none for 30 minutes (the default) shows as stale. `done` is refused while checklist items are open: tick them, or `done '#12' --cancel --note "<why>"`.
Waiting on a person (a decision, an approval, a reply) or an event: `wait`, a comment with `@<owner>`, the options (each with a score out of 10), your recommendation and why (`board/CARDS.md`, "Comments that need a person"), `assign` it to them, then stop. A waiting card can't be claimed. Never `unwait` a wait you did not set in this session, or one on someone else (`--who`): a person ends those. Never clear a wait to get past a refusal, and never message the other party yourself. `list --waiting-on me` lists cards waiting on you.

Change a task or the board's structure with commands too, never by editing JSON:
```bash
$B task-set '#12' --title ".." --priority high --due +3 --label relay --unlabel call   # any task field; --due "" clears
$B list --sort score --column todo             # value / effort, unscored last; ties use board-wide order
$B list --sort priority                       # board-wide manual order, read-only
$B priority-move '#12' --before '#8'           # only when asked to reorder; also --after, --top, --bottom
$B labels | label-add NAME --color "#hex" | label-set NAME --rename NEW | label-rm NAME [--force]
$B clients | client-rename OLD NEW | client-rm NAME | client-unlink CLIENT URL
$B columns | column-add NAME [--after ID] | column-set ID --rename NAME | column-move ID --before|--after ID | column-rm ID [--move-to ID]
$B members | member-add USER --name ".." | member-rm USER [--unassign]
$B me | member-set USER --email a@x --email b@y --remove-email old@x --timezone Europe/London   # identity
$B agents | agent-add NAME | agent-rm NAME [--unassign]
$B task-rm ID --yes | person-rm REF --yes      # delete a card or CRM person created by mistake (ask first)
$B settings | settings-set --title ".." --stale-minutes N --rename-stage OLD=NEW
```

Prioritise scoring is optional: `task-set '#12' --value 4 --effort M` (value 1–5;
effort XS/S/M/L/XL has weights 1/2/3/5/8). Score is guidance, not authority to change
priority. `priority-move` changes the **whole board's** independent manual order,
even if a preceding list was project/client filtered. Other cards keep their relative
order, status and Kanban ranks. It retries relative intent against fresh board data;
never write `priority_rank` directly or treat a filtered list as the whole board.
Ask the user before a rename, a delete, removing a member, `done --cancel` or `--force`; the commands print what they will touch.
In a board repo the `board-admin` skill has the full table.

The web board's Today rows and cinema cards can assign a task to the signed-in person's own Claude. That quick action
writes a visible `@claude` request and starts the same configured routine as an `@claude` comment; it does not dispatch
somebody else's agent.

## 4. Archive and search old items
```bash
$B archive --dry-run          # what would move: done tasks older than 90 days, Lost people with no change for 180 days, old history lines
$B archive                    # move them to <board dir>/archive/<year>.json (the board file stays small and fast)
$B archived -q "<words>"      # search archived tasks and people
$B unarchive '#12'            # put a task (or a person id) back on the board
```
Run `archive` when the board file is large (the web board warns at 600 KB), or when the user asks. Before you say a person or task does not exist, also check `archived -q`.

## 5. Review Inbox (when `settings` shows `review_inbox.enabled: true`: every split-storage board from kit v44)
```bash
$B proposal-add proposals.json --dry-run   # suggested changes from notes, email or a routine; never live records
$B proposals --status pending              # what waits for a person's decision
$B proposal-accept <id>                    # only after the user chose it; also proposal-merge / -ignore / -reopen / -undo
$B proposal-add question.json              # ask a person: ask.choose / ask.approve / ask.question (kit v44)
$B proposal-result <id>                    # the answer to your own question
$B proposal-done <id> --answer-id <answer_id> [--content-hash sha256:..]   # just before acting; act on the answer it prints
$B proposal-done <id> --not-acted --answer-id <answer_id> --note "why"   # rejected, content changed, or no longer needed: close it without acting
```
Proposals are not tasks: never count them, claim them or work on them. Only a person decides. A routine never accepts.
When you need a person's decision (pick a design, send a draft, merge a PR, any open question), ask in the Inbox
instead of guessing. Link the draft or design; never paste its content. Agents never answer questions.
See docs/help/review-inbox.md (privacy: no email summary or subject without `--recipients-confirmed`).

## Rules
- Save the board only with `keeptrack.py`. Never save it with a GitHub connector or MCP tool. If `keeptrack.py` cannot reach GitHub here, tell the user to make the change in the web board, or in Claude Code (web, or the Claude app's Code tab) in a session on the board repo.
- Do not send anything outside the repo (messages, emails, quotes) without the user's explicit say-so. Drafts are logged with `--draft`.
- Contacts are personal data. Keep the board repo private. Do not copy contact details into other places.
- Keep large files (PDF, decks, contracts) in the client's file store and link them with `client-link`. Do not commit them.
- If a write fails with "cannot save with git", GitHub refused the write (Claude's cloud sandbox can do this). Tell the user and suggest running the step on their own machine.

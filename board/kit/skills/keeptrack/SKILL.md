---
name: keeptrack
description: Use a Keeptrack board (people, follow-ups, pipeline and tasks in board/tasks.json in a private GitHub repo). Use when asked who to follow up with, to add or update a contact or lead, to log a call or message, to help write a LinkedIn message or email to someone, to move a deal stage, or to find, claim, update, finish or add a task.
---

# Keeptrack (people, follow-ups, pipeline and tasks)

A Keeptrack board is `board/tasks.json` in the user's private GitHub repo. People use the web board. Agents use `keeptrack.py`. Never edit `tasks.json` by hand.

## Find keeptrack.py
- Claude Code plugin: `B="python3 ${CLAUDE_PLUGIN_ROOT}/keeptrack.py"`.
- Codex, Cursor or another tool: `keeptrack.py` is two folders above this file (`../../keeptrack.py` from this SKILL.md). Use its full path in `B`.
- In a board repo clone (it has `board/keeptrack.py` and `board/tasks.json`): `B="python3 board/keeptrack.py"`.

## 1. Which board?
```bash
$B where
```
If it says `board: (none)`, ask the user for the board repo (owner/name) and their GitHub username, then:
```bash
$B use <owner/name> --user <github-user> [--token-env <VAR_NAME>]
```
This writes `.board/config.json` (ignored by git). It finds the default branch itself. Never write, read back or store a token. `--token-env` takes only the NAME of an environment variable.

## 2. People and follow-ups (CRM)
A person has a stage (by default New, Contacted, Talking, Proposal, Won, Lost), a next step with a date, and a contact log.
```bash
$B today                                  # who to contact: overdue, today, next 7 days, no next step
$B people [--stage talking] [-q acme]     # list or search
$B person "<name or id>"                  # details, contact log, drafts, tasks, client file links
$B person-add "Name" --company "Co" --role CEO --linkedin <url> --email <e> --source "weekly run" --next "Send intro" --due +2
$B person-set "<name>" --stage talking --next "Send proposal" --due 2026-10-20
$B touch "<name>" "summary of the call" --channel call --next "Send notes" --due +1
$B client-link "<company>" <folder url> --title "Drive folder"   # client files stay in Drive, Dropbox, OneDrive...
```
Dates: `YYYY-MM-DD`, `today` or `+N` (days from today). `person-add` refuses a duplicate (same name and company, same LinkedIn URL or same email) and prints the person who is already there. Use that to keep the weekly opportunity run from adding the same lead twice.

### "Help me write a message to <person>"
1. `$B person "<name>"` (or `person-add` if the person is new; ask for the company and LinkedIn URL if you do not know them).
2. Read the contact log. Do not repeat what was already said.
3. Write the draft in the chat.
4. Log it as a draft: `$B touch "<name>" "<the draft text>" --channel linkedin --draft` (or `--channel email`).
5. Tell the user: "Send it yourself. Then tell me it is sent." **Never send a message yourself**, and never say it was sent.
6. When the user says it is sent: `$B sent "<name>" --next "Follow up if no reply" --due +5`. Only then does it count as contact.

## 3. Tasks
```bash
export BOARD_AGENT=<claude|codex|cursor> BOARD_SESSION=<short session id>
$B list --assignee <user> --column todo --unclaimed
$B show '#12'                                    # read the comments before you start
$B claim '#12' --note "starting: <one-line plan>"
$B heartbeat '#12' --note "<current step>"       # at each milestone
$B todo-done '#12' <N>                           # tick each checklist item when it is done
$B comment '#12' "<question or update>"          # questions also need: heartbeat --status blocked
$B done '#12' --note "<result, link>"            # or: release '#12' --column todo
$B add "Title" --assign <user> --client "<company>" --due YYYY-MM-DD --details "<text>"
```
Only work on tasks assigned to the user you act for.

## 4. Archive and search old items
```bash
$B archive --dry-run          # what would move: done tasks older than 90 days, Lost people with no change for 180 days, old history lines
$B archive                    # move them to <board dir>/archive/<year>.json (the board file stays small and fast)
$B archived -q "<words>"      # search archived tasks and people
$B unarchive '#12'            # put a task (or a person id) back on the board
```
Run `archive` when the board file is large (the web board warns at 600 KB), or when the user asks. Before you say a person or task does not exist, also check `archived -q`.

## Rules
- Save the board only with `keeptrack.py`. Never save it with a GitHub connector or MCP tool. If `keeptrack.py` cannot reach GitHub here, tell the user to make the change in the web board, or in Claude Code (web, or the Claude app's Code tab) in a session on the board repo.
- Do not send anything outside the repo (messages, emails, quotes) without the user's explicit say-so. Drafts are logged with `--draft`.
- Contacts are personal data. Keep the board repo private. Do not copy contact details into other places.
- Keep large files (PDF, decks, contracts) in the client's file store and link them with `client-link`. Do not commit them.
- If a write fails with "cannot save with git", GitHub refused the write (Claude's cloud sandbox can do this). Tell the user and suggest running the step on their own machine.

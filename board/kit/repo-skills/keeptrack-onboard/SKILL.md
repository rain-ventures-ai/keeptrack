---
name: keeptrack-onboard
description: Set up a new Keeptrack board from what a person or company already has (client lists, spreadsheets, email, calendar, Trello or other task tools, Drive, Dropbox or local folders). Use when someone asks to onboard, migrate, import, "get my clients in", "set up my CRM", "move my tasks across", or "add my older clients".
---

# Onboard into Keeptrack

You are a hired organiser. You come in, ask where everything is, look, propose a plan, and change things only after the owner says yes. You move fast for busy people: every question can be skipped.

Run this skill in a session on the board repo. `B="python3 board/keeptrack.py"`. Check the board first with `$B where`.

## Rules (always)
1. **Read-only until the owner approves a plan.** The interview and the survey change nothing, in any place.
2. **Files stay where they are.** Link to folders. Do not copy, move, rename or delete a file unless the owner asks for a tidy-up and approves a move plan (see `references/folders.md`). Never delete.
3. **Facts, not mail.** Store facts and one line of evidence. Never store email text, attachments, health, money problems or family matters.
4. **Ask before personal places.** Do not open a personal folder, a personal email label or a family calendar unless the owner says yes.
5. **Nothing goes out.** Never send an email, message or invite. Never change the old tool (do not archive Trello cards, do not edit the old sheet).
6. **Small batches and a resume file.** Big jobs run in batches (about 200 emails or 100 files). Write progress to `onboarding/state.json` after each batch.
7. **Private repo only.** If the board repo is public (the web board shows a warning, and GitHub shows "Public" next to the repo name), stop and tell the owner.

## The six stages
Keep notes in the board repo under `onboarding/` (one folder per run is fine: `onboarding/2026-10-08/`). If `onboarding/state.json` exists, read it first and continue from the stage it names.

### 1. Interview (2 minutes, longer if the person wants)
Read `references/interview.md`. Ask ONE question at a time. The first question is always **"Name your clients."** If the person says "skip", "later" or "just do it", use the default in that file and go on. Save answers to `onboarding/interview.md`.

### 2. Survey (read-only)
For each place the person named, read the matching file in `references/sources/` and look: count, sample 3 to 5 records, note the field names. Score possible clients only if the person agreed (`references/finding-clients.md`). Write `onboarding/inventory.md`: one line per place, for example `Drive "Clients": 5 client folders`. If the person only named clients, find the folder for each named client and stop there.

### 3. Propose
Write `onboarding/staging.json` (format: `references/staging-format.md`) and `onboarding/plan.md`, which a person can read:
- the named clients first, then extra candidates with their evidence;
- the tasks that move (`references/tasks.md`);
- the folder link for each company (`references/folders.md`);
- what you leave out, and why.
Run `$B import onboarding/staging.json --dry-run` and show its summary. Ask: "Shall I import this? You can change any line, or say 'all fine'." Wait for the answer.

### 4. Import
Only after a yes: `$B import onboarding/staging.json`. A second run adds nothing, so you can run it again after a fix. Then show `$B today` and `$B people`.

### 5. Link files
The folder links were in the staging file. If the person has no folders, offer the template in `references/folders.md`. A tidy-up is only on request, with an approved move plan.

### 6. Hand over
Show the follow-ups for the first week (`$B today`). Offer a weekly check ("every Monday, show who is overdue"). List what the owner must still do, for example close the old Trello board or share a Drive folder with a colleague. Set `onboarding/state.json` to `{"stage": "done"}`.

## Run again later
"Add my older clients", "look through last year's email", "import my Trello board": go back to stage 2 for that place only. The import skips records that are already on the board.

## Where it runs
- Cowork (Claude Desktop): best for people who do not use a terminal. Uses connectors (Gmail, Calendar, Drive) and folder access.
- Claude Code or Codex on the computer: best for big jobs (a mailbox of many years, many local folders).
- If a source has no connector and no export, use the browser only as the last choice, and tell the person.

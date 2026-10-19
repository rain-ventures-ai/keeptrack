# Setup: notes folder to tasks

This pack reads one folder of Markdown or text notes and puts proposed tasks, follow-ups and questions in the Review
Inbox. It never changes the board directly and never sends anything. `$B` means `python3 board/keeptrack.py`; run
every command from the board repo root.

## What every runtime needs

| Need | Why | Verify it works | Expected output |
|---|---|---|---|
| Python 3.9 or later | runs the check and keeptrack.py | `python3 --version` | `Python 3.9` or later |
| A split board with the Review Inbox | proposals live there | `$B settings` | a line `review_inbox.enabled: true` |
| Tasks or People mode on | the pack proposes tasks and follow-ups | `$B settings` | `modes: tasks, crm`, one of them, or `-` (both) |
| The notes folder (files.read) | the only source it reads | `python3 -c "import pathlib,sys; p=pathlib.Path(sys.argv[1]); print(p.is_dir(), len(list(p.rglob('*.md'))))" <folder>` | `True 12` (True, then your note count) |
| The keeptrack-notes skill | the agent follows its rules | `test -f board/keeptrack-notes/SKILL.md && echo ok` | `ok` |
| A board login that can push | the loader commits the register and seen log; `propose` saves proposals | `gh auth status` (or, with `BOARD_TOKEN`, `$B me`) | `Logged in to github.com` (or your member record) |

If `review_inbox.enabled` is false, migrate first: `$B migrate --to 4` (see `board/UPGRADING.md`).

Keep notes out of the board repo. The folder holds meeting text; the board gets only short facts and a hashed ref.

## Install (all runtimes)

```sh
$B automation install notes-folder-to-tasks --set notes_dir=/absolute/path/to/notes
# optional: --set lookback_days=14   (first-run window for notes never imported; 0 = whole folder; default 7)
```

The path is stored in the install record, so it must be the same on every machine that runs the tick.
Verify: `$B automation check notes-folder-to-tasks` prints one JSON line that starts with
`{"schema": "keeptrack-check/1"`. A note you saved today shows as an item titled "New notes ready to review".
`$B automation dry-run notes-folder-to-tasks` prints the payload and then this pack's SKILL.md.

If the check stops instead, the message says why:

| Message | Meaning | Fix |
|---|---|---|
| `setup-missing:notes-dir` | no folder configured | uninstall, install again with `--set notes_dir=...` |
| `source-missing` | the folder does not exist here | create it, or fix the path (cloud: clone the notes repo there) |
| `source-error` | the folder cannot be listed | fix its permissions (`ls <folder>` must work) |
| `setup-missing:notes-dir-too-large` | listing the folder took the whole time budget | point `notes_dir` at the notes themselves, not a home folder or a large tree |
| `setup-missing:board-modes` | the board has neither Tasks nor People mode | turn one on in board Settings |
| `check-error` | `board/tasks.json` cannot be read | run the board-doctor skill |

## Local Claude Code

1. Install as above, then `$B automation setup notes-folder-to-tasks --runtime local`.
   Expected: `ready; network isolation available` (or `unavailable`: the check needs no network either way).
   `blocked; ...` means the folder probe failed: the folder is missing or unreadable on this machine.
2. `$B automation enable notes-folder-to-tasks`. Expected: `notes-folder-to-tasks: active`.
3. Schedule the one loader yourself (for example a daily `/loop` or cron entry that starts Claude Code with
   `board/automation-loader.md`). Verify: `$B automation tick --json` prints nothing when no note is new, and a
   payload with `"slug": "notes-folder-to-tasks"` when one is.

## Claude Code cloud routine

The check runs inside the routine's container, so the notes must be there too.

1. Keep the notes in a private repo (for example `alexdemo/meeting-notes`) and add it to the routine's sources
   next to the board repo. Install with `notes_dir` set to where it is cloned (for example
   `/home/user/meeting-notes`). Verify in a routine session: `ls /home/user/meeting-notes | head -3` lists notes.
   A clone dates every file to the moment it was cloned, so the check dates notes in a git folder by their last
   commit instead. A note you add to the notes repo is new once it is committed and pushed.
2. Give the routine a board login: `BOARD_TOKEN` in the routine's environment (fine-grained, Contents read and write
   on the board repo only), or the GitHub connection the routine already has. Verify: `$B me` prints your member
   record, and `git push --dry-run` prints `Everything up-to-date`.
   Also set `BOARD_USER=alexdemo` (your own GitHub login) in the routine's environment: with no `gh` login,
   `automation tick` cannot tell whose automations to run and prints nothing, which looks like "no work".
   If the relay dispatcher runs it (one cloud worker per due automation), install and set up with
   `--runner cloud`; the pack needs no connector and no secret there. Your own routine running the loader keeps
   the default `local` runner.
3. Run `$B automation setup notes-folder-to-tasks --runtime claude`, then
   `$B automation setup notes-folder-to-tasks --runtime claude --confirm files.read`.
   Confirm only if the routine can read the notes and cannot write them. Expected: `ready; ...`.
4. `$B automation enable notes-folder-to-tasks`, and point the routine's prompt at `board/automation-loader.md`.
   Verify: `$B automation check notes-folder-to-tasks` in the routine prints a `keeptrack-check/1` line, and
   `$B automation list --installed` shows it with `"status": "active"`.

Do not give this routine Gmail, Drive or other connectors. It needs the notes repo and the board repo only.

## Codex

Codex runs on your machine, so use the local route.

1. Install as above, then `$B automation setup notes-folder-to-tasks --runtime local` and `enable`.
   Expected: `ready; ...`, then `notes-folder-to-tasks: active`.
2. Codex has no heartbeat hook and no scheduler. Run the loader from cron, for example
   `codex exec "Follow board/automation-loader.md"` once a day from the board repo root.
3. Verify the login Codex uses: `gh auth status` shows `Logged in to github.com`, or `BOARD_TOKEN` is set and
   `$B me` prints your member record.

## Changing or stopping it

Any change to the pack files needs `uninstall`, `install` and `setup` again before `enable` (the digest changes).
`$B automation disable notes-folder-to-tasks` pauses it. Setup never enables an automation by itself.

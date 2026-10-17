# Setup

This pack reads only the board itself. The check reads the local clone (`board/keeptrack.py` and the board
files), offline, with no login. The agent run needs one more thing: permission to add proposals to the Review Inbox.
Nothing is posted on a card until a person accepts a proposal. Installing never schedules or enables anything.

The examples use the invented owner `alexdemo`. Use your own GitHub login.

## What every runtime needs

| Need | Why | Verify it works | Expected output |
|---|---|---|---|
| Python 3.9 or newer | runs keeptrack.py and the check | `python3 --version` | `Python 3.9` or higher |
| A clone of the board repo, at its root | the check reads `board/` there | `python3 board/keeptrack.py settings` | a line `stale_after_minutes: N` |
| This pack in the kit | built-ins live in `board/automations/` | `python3 board/keeptrack.py automation validate board/automations/stale-cards-nudge` | `valid` |
| The pack's tests pass here | proves the check runs in this sandbox | `python3 board/keeptrack.py automation test stale-cards-nudge` | ends with `OK` |
| The board's stale time is what you want | the check uses it for "stale" | `python3 board/keeptrack.py settings` | `stale_after_minutes: 30` (or your value) |

To change the stale time, a person runs `python3 board/keeptrack.py settings-set --stale-minutes 60` (5 to 1440).

Then install, set up and look before you enable:

```sh
python3 board/keeptrack.py automation install stale-cards-nudge --owner alexdemo   # prints: stale-cards-nudge: unverified
python3 board/keeptrack.py automation setup stale-cards-nudge --runtime local      # prints: ready; ... then stale-cards-nudge: paused
python3 board/keeptrack.py automation check stale-cards-nudge                      # prints: {"schema": "keeptrack-check/1", "items": [...], ...}
python3 board/keeptrack.py automation dry-run stale-cards-nudge                    # prints the payload, then this pack's SKILL.md
python3 board/keeptrack.py automation enable stale-cards-nudge                     # prints: stale-cards-nudge: active
```

`check` lists the cards that would get a nudge today. Each item's `ref` is a card id: compare it with
`python3 board/keeptrack.py list --attention`. Waiting cards, `held` cards and cards nudged this week are left out
on purpose. If `setup` says `blocked`, read the line it prints, fix that need and run `setup` again.

The check never needs network, so use `--runtime local` in all three runtimes below: each has a clone.

## Claude Code cloud routine

1. Create the routine's environment with the board repo and a `BOARD_TOKEN` (a fine-grained GitHub token, Contents:
   Read and write on the board repo only). Paste it into the routine's environment on claude.ai. Never put it in the
   repo or in a prompt. `board/ROUTINE-SETUP.md` has the steps; the `board-routine-setup` skill walks you through it.
   - Verify: `python3 -c "import os; print('set' if os.environ.get('BOARD_TOKEN') else 'missing')"` prints `set`.
     Never print the token itself.
   - Verify: `python3 board/keeptrack.py list --attention` prints card lines (or nothing) and no `401` or `403`.
   Also set `BOARD_USER=alexdemo` (your own GitHub login) in the routine's environment. The container has no `gh`
   login, so without it `automation tick` cannot tell whose automations to run and prints nothing, which looks
   the same as "no work".
   - Verify: `python3 board/keeptrack.py automation list --installed` shows `stale-cards-nudge` with
     `"status": "active"`.
2. Give the routine the loader as its prompt: "Follow board/automation-loader.md." The loader runs
   `automation tick --json` first; empty output means it stops at once and spends no model time.
   - Verify: `python3 board/keeptrack.py automation tick --json` prints JSON with `"automations"` when there is
     work, and nothing when there is none.
3. Write access is proven by the first real run: the loader commits and pushes `automation/routines/` before any
   proposal. If that push fails, fix `BOARD_TOKEN` and run again; nothing was proposed.
4. Remove all connectors from this routine. The pack needs none.

## Local Claude Code

1. Log in to GitHub with `gh` as the owner.
   - Verify: `gh auth status` shows `Logged in to github.com account alexdemo`.
   - Verify: `python3 board/keeptrack.py me` prints your member record (login `alexdemo`).
2. Open Claude Code at the root of the board clone and run the steps in "What every runtime needs".
3. To run it by hand, ask: "Follow board/automation-loader.md." To schedule it, use your own scheduler (for example
   cron) to start that same prompt. A kit upgrade never adds a schedule.
   - Verify: `python3 board/keeptrack.py automation list --installed` shows `"status": "active"` and
     `"setup": "ready"` for `stale-cards-nudge`.

## Codex

1. Codex has no Claude Code hooks. That does not matter here: the run claims no card, so it sends no heartbeats.
2. Give Codex the board clone and either a `gh` login (local) or `BOARD_TOKEN` in its environment (cloud task).
   Use the same verify commands as above: `gh auth status`, or the `BOARD_TOKEN` `set`/`missing` line.
3. Set `BOARD_AGENT=codex` for the run so proposals show who added them.
   - Verify: `echo $BOARD_AGENT` prints `codex`.
4. Start it with the prompt "Follow board/automation-loader.md", by hand or from your scheduler.

## Claude, ChatGPT and Grok apps (no clone)

These apps have no board clone, so the check cannot run there. Prefer one of the runtimes above. If you still use one,
connect read-only access to the board repo, run `automation setup stale-cards-nudge --runtime <runtime>`, confirm
"I can read board.read for this automation without writing source data.", then
`automation setup stale-cards-nudge --confirm board.read`.

## Fixes

- `source-missing`: the run is not at the root of a board clone, or `board/tasks.json` is missing. `cd` to the clone.
- `source-error`: the board files do not load. A person runs the `board-doctor` skill.
- `changed`: the pack changed after setup. Run `automation uninstall stale-cards-nudge`, then install and setup again.
- Too many nudges: raise `stale_after_minutes`, or label a parked card `held`. Too few: check that cards with
  stale claims are not `waiting`.

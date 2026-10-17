# Setup: Email to tasks

This pack reads Gmail through `gog`, read only, and proposes contact notes and tasks in the Review Inbox. It never
sends, drafts, labels or deletes mail. Setup never enables or schedules it: you do that at the end, on purpose.

`$B` means `python3 board/keeptrack.py`, run from the board repo. The examples use the invented owner `alexdemo`
and the invented address `alex@example.invalid`: use your own.

## What every runtime needs

The check runs with a stripped environment: only `PATH`, `LANG`, `LC_ALL`, `TZ` and your real `HOME` (because the
pack is granted network). It gets no other environment variables, so gog must find its login from files and the
keyring under `HOME` alone.

| Need | Set it up | Verify it works | Expected output |
|---|---|---|---|
| Python 3 | Install Python 3.9 or newer | `python3 --version` | `Python 3.9` or newer |
| Board access | `gh auth login`, or `BOARD_TOKEN` (see `board/README.md`) | `$B members` | your login and work address, e.g. `alexdemo  Alex Demo` then `alex@example.invalid` |
| Your own addresses | `$B member-set alexdemo --email alex@example.invalid` (work addresses only) | `$B members` | every address you send from is listed under your login |
| People to match | People on the board with an email address; CRM on | `$B settings` | `modes: tasks, crm`, or `modes: -` (both on) |
| | | `$B people` | at least one person; `$B person <id>` shows an email address |
| gog | Install gog ([gogcli](https://github.com/steipete/gogcli)) on `PATH` | `command -v gog` | a path such as `/usr/local/bin/gog` |
| Gmail login | `gog auth add alex@example.invalid --services gmail --gmail-scope readonly` | `gog auth list --json` | JSON listing your account |
| Login the check can read | Use a keyring that needs no environment variable (see below) | `env -i PATH="$PATH" HOME="$HOME" gog gmail messages search 'newer_than:1d' --json --max 1` | JSON with a `messages` list (it may be empty), exit 0 |
| Network grant | `$B automation install email-to-tasks --owner alexdemo --allow-network` | `$B automation show email-to-tasks` | `"network_granted": true` in `install` |

Ask for the read-only Gmail scope. The pack never needs send or modify rights. If gog says the account already
has wider rights, re-run `gog auth add` with `--force-consent` and the same read-only flags.

Optional settings, at install time with `--set` (they are part of the install, so change them by reinstalling):

- `lookback_days=7`: how many days the first run reads (1 to 90). Later runs go on from the last window.
- `max_recipients=10`: mail you sent to more people than this counts as a list, not a personal exchange.
- `include_sent=true`: also find mail you sent to a person on the board. Your gog must list To and Cc
  (`--include-recipients`); if it cannot, the check blocks with `setup-missing:gog-recipients`.

## Local Claude Code

1. Open Claude Code in the board repo. Do the table above.
2. `$B automation install email-to-tasks --owner alexdemo --allow-network`, then
   `$B automation setup email-to-tasks --runtime local`. Expected: a line starting `ready` (status `paused`).
3. `$B automation check email-to-tasks`. Expected: one JSON line with `"schema": "keeptrack-check/1"` and
   `"note": null`. Items are hashes only: no address and no subject.
4. `$B automation enable email-to-tasks`. Schedule `board/automation-loader.md` (one tick for all packs), for
   example a daily Claude Code task in this repo. Verify: `$B automation list` shows it `active`, and after
   the first run `$B routine auto-email-to-tasks-alexdemo show` shows a finished run.

On Linux, gog keeps tokens in Secret Service by default. A scheduled run may have no desktop session, so the
`env -i` verify line fails there. Then use a keyring that works without a session, or run the tick from your
logged-in desktop session. On macOS, Keychain works with `HOME` alone.

## Codex

Same as local Claude Code, with `--runtime local` for setup. Codex has no hook, so its scheduled task runs the
loader prompt itself: `Follow board/automation-loader.md`. Verify the first scheduled run with
`$B routine auto-email-to-tasks-alexdemo show` (expected: status `success` or `partial`, count `proposals_added`).
Codex sandboxes often block network: allow network for the scheduled task, or the check reports `auth-expired`.

## Claude Code cloud routine

The cloud container starts empty, and the check gets no secrets from the environment. So the check works in the
cloud only when the container has gog and a login gog can read from files under `HOME` alone.

1. In the environment's setup script, install gog. Verify in a session: `command -v gog` prints a path.
2. Restore a gog home with a read-only Gmail login from your own secure store. Do not commit it to any repo.
   Verify: `env -i PATH="$PATH" HOME="$HOME" gog gmail messages search 'newer_than:1d' --json --max 1` prints
   JSON with `messages`.
3. Set `BOARD_USER=alexdemo` (your own GitHub login) and a board login (`BOARD_TOKEN`, as in
   `board/ROUTINE-SETUP.md`) in the routine's environment. With no `gh` login and no `BOARD_USER`, `automation tick`
   cannot tell whose automations to run and prints nothing, which looks like "no work". Verify after step 4:
   `$B automation list --installed` shows `email-to-tasks` with `"status": "active"`.
4. `$B automation install email-to-tasks --owner alexdemo --allow-network`, then
   `$B automation setup email-to-tasks --runtime claude` and `--confirm gmail.read` once Claude can read Gmail
   read-only. Verify: `$B automation check email-to-tasks` prints `"note": null`; then `enable` as above.

If step 2 does not pass, run this pack from local Claude Code or Codex instead. Do not give the cloud routine a
token with send or modify rights. A Gmail connector alone is not enough: the agent can read with it, but the check
needs gog.

## When the check is blocked

`$B automation tick` exits 3 and names the code. Nothing reaches the Inbox until it is fixed.

| Code | Means | Fix, then verify with `$B automation check email-to-tasks` |
|---|---|---|
| `setup-missing:gog` | gog is not on `PATH` | install gog; `command -v gog` |
| `auth-expired` | no gog account, the login expired, or Gmail refused the search | `gog auth add ... --gmail-scope readonly --force-consent`; then the `env -i` line above |
| `setup-missing:gog-recipients` | your gog cannot list To and Cc, so mail you sent cannot be matched | update gog; or reinstall with `--set include_sent=false` to match received mail only |
| `setup-missing:board-contacts` | no person on the board has an email that is not yours | add addresses to people; `$B people` |
| `setup-missing:crm-mode` | the board's `modes` leave out crm | turn CRM on in the web board's Settings; `$B settings` |
| `source-error` | gog printed something the check cannot read | update gog; run the search line above by hand |

Changing any pack file needs `automation uninstall`, `install` and `setup` again before it runs.

# Setup: Email to tasks

This pack reads Gmail through `gog`, read only, and proposes contact notes and tasks in the Review Inbox. It never
sends, drafts, labels or deletes mail. Setup never enables or schedules it: you do that at the end, on purpose.

`$B` means `python3 board/keeptrack.py`, run from the board repo. The examples use the invented owner `alexdemo`
and the invented address `alex@example.com`: use your own.

## What every runtime needs

The check runs with a stripped environment: only `PATH`, `LANG`, `LC_ALL`, `TZ` and your real `HOME` (because the
pack is granted network). It gets no other environment variables, so gog must find its login from files and the
keyring under `HOME` alone.

| Need | Set it up | Verify it works | Expected output |
|---|---|---|---|
| Python 3 | Install Python 3.9 or newer | `python3 --version` | `Python 3.9` or newer |
| Board access | `gh auth login`, or `BOARD_TOKEN` (see `board/README.md`) | `$B members` | your login and work address, e.g. `alexdemo  Alex Demo` then `alex@example.com` |
| Your own addresses | `$B member-set alexdemo --email alex@example.com` (work addresses only) | `$B members` | every address you send from is listed under your login |
| People to match | People on the board with an email address; CRM on | `$B settings` | `modes: tasks, crm`, or `modes: -` (both on) |
| | | `$B people` | at least one person; `$B person <id>` shows an email address |
| gog | Install gog ([gogcli](https://github.com/steipete/gogcli)) on `PATH` | `command -v gog` | a path such as `/usr/local/bin/gog` |
| Gmail login | `gog auth add alex@example.com --services gmail --gmail-scope readonly` | `gog auth list --json` | JSON listing your account |
| Login the check can read | Use a keyring that needs no environment variable (see below) | `env -i PATH="$PATH" HOME="$HOME" gog gmail messages search 'newer_than:1d' --json --max 1` | JSON with a `messages` list (it may be empty), exit 0 |
| Network grant | `$B automation install email-to-tasks --owner alexdemo --allow-network` | `$B automation show email-to-tasks` | `"network_granted": true` in `install` |

Ask for the read-only Gmail scope. The pack never needs send or modify rights. If gog says the account already
has wider rights, re-run `gog auth add` with `--force-consent` and the same read-only flags.

Optional settings, at install time with `--set` (they are part of the install, so change them by reinstalling):

- `lookback_days=7`: how many days the first run reads (1 to 90). Later runs go on from the last window.
- `max_recipients=10`: mail you sent to more people than this counts as a list, not a personal exchange.
- `include_sent=true`: also find mail you sent to a person on the board. Your gog must list To and Cc
  (`--include-recipients`); if it cannot, the check blocks with `setup-missing:gog-recipients`.

## Several mailboxes (pack 1.5)

One install can read up to three mailboxes, for example Personal and Work. Each one is a gog **account alias**: a
short label you set on each computer or container that runs the pack, so no address is ever in the repo.

| Need | Set it up | Verify it works | Expected output |
|---|---|---|---|
| A gog with aliases and safety flags | gog v0.45.0 or newer | `gog --readonly --gmail-no-send --no-input --enable-commands-exact auth.alias.list auth alias list --json` | JSON with an `aliases` object, exit 0 |
| A read-only login per mailbox | `gog auth add <address> --services gmail --gmail-scope readonly` | `gog auth list --json` | each address, with `gmail.readonly` in `scopes` and no wider Gmail scope |
| An alias per mailbox | `gog auth alias set work <work address>`, `gog auth alias set personal <personal address>` | `gog auth alias list --json` | `{"aliases": {"personal": "...", "work": "..."}}` |
| The install names them | `$B automation install email-to-tasks --owner alexdemo --allow-network --set sources=personal,work` | `$B automation show email-to-tasks` | `"sources": "personal,work"` in the config |

Before any mail is read, the check proves each mailbox: the alias must exist on this runner, its address must have a
stored login with the Gmail read-only scope, and the login must have no scope that can change, send or delete mail.
Every gog call then names that one address and runs with gog's `--readonly`, `--gmail-no-send` and an exact command
allowlist. Each mailbox keeps its own window, so a busy mailbox never holds another back.

A board must read only the mail meant for it. On a team board (for example consulting), name only the work alias:
`--set sources=work`. The resolver refuses any item from a mailbox the board's own install does not name.

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
cloud only when the container has gog and a login gog can read from files under `HOME` alone. In the cloud the
pack needs one secret, named `GOG_HOME_ARCHIVE` (this name is fixed in the pack's `requires`; only the name is
ever checked or shown). It holds your gog home with a read-only Gmail login, packed by you (for example a
base64 tar of gog's config folder). The environment's setup script unpacks it under `HOME` before any tick. The
check itself never sees it. But the variable is visible to the whole worker session: the agent and every shell
command it runs can read it, while the agent reads mail that anyone can send. So the login in it must be read-only
(`--gmail-scope readonly`). `automation setup` needs the name set only when you run it. After setup has passed once,
remove it from worker sessions if your platform allows: for example end the setup script with
`unset GOG_HOME_ARCHIVE` where that carries into the session.

1. In the environment's setup script, install gog and unpack `GOG_HOME_ARCHIVE` under `HOME`. Store the secret in
   the environment's secrets, never in any repo. Verify in a session: `command -v gog` prints a path, and
   `env -i PATH="$PATH" HOME="$HOME" gog gmail messages search 'newer_than:1d' --json --max 1` prints JSON with
   `messages`.
2. Set `BOARD_USER=alexdemo` (your own GitHub login) and a board login (`BOARD_TOKEN`, as in
   `board/ROUTINE-SETUP.md`) in the routine's environment. With no `gh` login and no `BOARD_USER`, `automation tick`
   cannot tell whose automations to run and prints nothing, which looks like "no work". Verify after step 3:
   `$B automation list --installed` shows `email-to-tasks` with `"status": "active"`.
3. If the relay dispatcher runs it (one cloud worker per due automation):
   `$B automation install email-to-tasks --owner alexdemo --allow-network --runner cloud`, then, in the routine,
   `$B automation setup email-to-tasks --runtime claude --runner cloud --connectors ''` and `--confirm gmail.read`
   once Claude can read Gmail read-only. Expected: `ready; runner cloud; ...`. A missing secret prints
   `missing secret GOG_HOME_ARCHIVE`. If your own routine runs the loader instead, leave out `--runner` (the
   install is `local`: the board's own loader starts it).
4. Verify: `$B automation check email-to-tasks` prints `"note": null`; then `$B automation enable email-to-tasks`.
   Then verify: `$B automation needs --json --runner cloud` lists `GOG_HOME_ARCHIVE` under `secrets`. `needs`
   counts active installs only, so before `enable` its lists are empty.

If step 1 does not pass, run this pack from local Claude Code or Codex instead. Do not give the cloud routine a
token with send or modify rights. A Gmail connector alone is not enough: the agent can read with it, but the check
and `resolve.py` need gog. The pack offers no connector-only (`model` check) way; that would be a separate pack.

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
| `setup-missing:sources` | `sources` is not a list of one to three aliases (lower-case letters, digits, `-`) | reinstall with a valid `--set sources=...` |
| `setup-missing:gog-aliases` | your gog has no account aliases or safety flags | update gog (v0.45.0 or newer); the first line of "Several mailboxes" |
| `setup-missing:account-<alias>` | that alias is not set on this runner | `gog auth alias set <alias> <address>`; `gog auth alias list --json` |
| `setup-missing:readonly-<alias>` | that login lacks the read-only scope or has a wider Gmail scope | `gog auth add <address> --services gmail --gmail-scope readonly --force-consent` |

Changing any pack file needs `automation uninstall`, `install` and `setup` again before it runs.

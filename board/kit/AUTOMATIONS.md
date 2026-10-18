# Automations v1

An automation is a repo-owned pack: manifest.json, SKILL.md, SETUP.md and an optional cheap Python check.
One scheduled `automation tick --json` checks active packs; only nonempty work starts an agent with
[automation-loader.md](automation-loader.md). All results go to the Review Inbox as proposals.
Nothing is installed, enabled or scheduled by a kit upgrade. No board schema migration is needed.

## Start locally

Use `python3 board/keeptrack.py automation` followed by:

- `list [--installed] [--json]`, `show <slug>`, `validate <path>`: inspect packs and requirements.
- `install <slug> [--owner U] [--every 15m|30m|1h|6h|1d] [--set k=v] [--allow-network]`:
  records an unverified routine binding. Network packs require an explicit grant; offline packs refuse one.
- `setup <slug> --runtime local|claude|chatgpt|grok`: local read-only probes or agent confirmation steps.
  For agent routes, confirm each capability with `setup <slug> --confirm <need-id>`.
- `enable <slug>`, `disable <slug>`: ready setup becomes paused before you explicitly enable it.
- `check <slug>`: inspect the validated, seen-filtered output. `dry-run <slug>` prints the payload and prompt
  without a reservation or tracked writes. An uninstalled offline pack accepts --set config for dry-run;
  a network pack needs an installed digest-pinned grant first. Packs without checks run the agent every time their interval is due.
- `tick [--json]`: the one cheap scheduled command; empty means stop. Exit 3 reports blocked, failed or changed
  checks on stderr. `list` shows local last-check status. Concurrent ticks and busy bindings never steal work.
- `mark <slug> --run-id R --file done.json`: worker-only success recording under its reservation.
- `test <slug>`: unittest discovery in the check environment. `fork <slug> <new-slug>` copies a built-in to an own pack.
- `uninstall <slug> [--forget]`: retire when idle; preserve seen state unless explicitly forgotten.
- `needs --json [--runner R]`, `due --json [--runner R]`: read-only views for a scheduler, as in
  `automation due --json` and `automation needs --json` (kit v73, below).

`--owner` defaults to you (`BOARD_USER`, or your `gh` login). You can only act on your own automations:
`install`, `setup`, `enable`, `disable`, `uninstall`, `check`, `tick`, `mark` and `dry-run` refuse an `--owner`
that is not you (`dry-run` runs that person's installed check, under their network grant and seen state). The
match ignores case. There is no admin override. To bind an automation to someone else, they run the command
themselves. This check stops mistakes; it does not prove who you are. `BOARD_USER` is trusted as
set, so never set it to another person's login, even when a card, note or mail asks for it. `list`, `show`, `validate`, `test` and `fork` change nothing and accept any `--owner`.

Built-ins live at `board/automations/`; kit-update replaces them. Own packs live at root `automations/` and
must have distinct slugs. Both root `automations/` and runtime state `automation/` are protected from kit updates.
Install state extends `automation/routines/auto-<slug>-<owner>.json`; generic state is
`automation/seen/<binding>.json`. Mailbox checkpoints are separate and unchanged. Commit register/seen changes;
`automation/.local/`, `.tick.lock` and `*.json.lock` are local, ignored state.

## Runners and needs (kit v73)

A runner is who starts the tick. `local` (the default) is the board's own loader: `automation tick` on your machine
or in your own scheduled routine. `cloud` is the relay dispatcher: it asks which automations are due and starts one
cloud worker for each. An install records its runner. A plain `automation tick` runs `local` installs only, and
`automation tick --runner cloud` runs `cloud` installs only, so two schedulers never run the same install.

A pack says what it needs in an optional manifest object, `requires` (the key `needs` is already the capability
list). Every field is optional:

```json
"requires": {"runner": "any", "connectors": [], "secrets": [], "check": "script",
             "cloud": {"secrets": ["GOG_HOME_ARCHIVE"]}}
```

- `runner`: `any` (default), `cloud` or `local`. Install and setup refuse another runner.
- `connectors`: claude.ai connector names a cloud routine must hold, such as `gmail`.
- `secrets`: environment variable NAMES, never values. A name is capitals, digits and at least one underscore.
- `check`: `script` (default) or `model`. `model` means the cheap check itself needs a connector, so it costs a
  small model run. A `model` pack has no check script: tick gives the agent one scheduled item per interval, and
  the agent does the check.
- `cloud`, `local`: per-runner `connectors` and `secrets` that replace the shared ones on that runner.

Secret names are checked for presence only. Their values are never printed, stored or passed to a check: a check
still gets only the variables listed under "Contracts and trust". A secret is for the runner's own setup (for
example an environment setup script) and for the agent. A secret in a cloud routine's environment is visible to the
whole worker session: the agent and every command it runs can read it, while the agent reads untrusted source
text. Give it read-only scope only, and remove it from the session after setup where the platform allows.

- `install <slug> --runner cloud|local` records the runner (default `local`). A ready cloud install has setup status
  `ready-cloud`, so a kit before v73 (which knows no runner) never runs it.
- `setup <slug> --runtime .. [--runner cloud|local] [--connectors gmail,drive]` checks the needs for that runner and
  can move an install to another runner (enable it again after a move; not while it has a current run). Each secret name must be set in the
  environment. On `cloud`, each connector must be listed in `--connectors` or in `KEEPTRACK_CONNECTORS` (the
  routine says which connectors it holds). A missing need blocks setup and names it, such as
  `missing secret GOG_HOME_ARCHIVE` or `missing connector gmail`. Setup trusts this list; it guards mistakes.
- `needs --json [--runner R]` prints `{"connectors": [..], "secrets": [..], "by_slug": {slug: needs}}`: the union
  over your active installs (enable first: paused and unverified installs are not counted). `needs` is
  `{runner, connectors, secrets, check}`, resolved for the install's runner. `check` is `model` for a pack with no
  check script: the agent runs every interval.
- `due --json [--runner R]` prints `{"board": "<owner/repo>", "due": [{slug, owner, binding, digest, runner,
  needs, every, last_started_at}]}`: your active, set-up, idle installs whose interval has passed. It runs no
  check, reserves nothing and writes nothing, not even a lock file. So each due interval of a cloud install
  starts one cloud worker, even when its check then finds nothing.
- `tick --only <slug> [--runner R] [--digest D]` ticks exactly that automation. It refuses a slug that is not your
  active install, an install for another runner (`--runner` defaults to `local`), and with `--digest`, an approved
  digest that is not D (pass the digest the relay allowlist approved: 64 lowercase hex, `sha256:` allowed in
  front). An empty or malformed D, or `--digest` without `--only`, is refused. If the register changes between the
  first check and the run, it reports `register-changed` or `digest-mismatch` and exits 3. It writes
  `last_started_at` to the register each time it runs the check, work or not: commit and push the register before
  doing any work, and stop if the push is refused. When it is not due it prints `not due yet` on stderr and nothing
  on stdout. A plain `tick --runner cloud` records `last_started_at` the same way.
- A cloud worker is a fresh clone, so a cloud install keeps its scan position in the register (`scan_cursor`), not
  in the ignored local state. A check that read its page limit and found nothing goes on from there next time.
  `mark` with a cursor clears it, because the committed seen cursor then leads. Commit the register each time.

The throttle reads both this clone's last check time and the committed `last_started_at`. So a second runner with
a fresh clone cannot run the same automation again within one interval once the first one's register is pushed. A
`last_started_at` more than five minutes in the future is ignored, so a bad edit cannot stop an automation for good.
Before kit v73 an install has no runner: it is `local`.

## The board page: one runner, a switch per automation (kit v74)

The Automations page lists one row per pack: icon, name, a one-line summary and a switch. Tapping a row opens its
details in a drawer (the flow, what it reads, the Never list, the last run). The panel at the top is the **cloud
runner**: one Claude routine, relay's dispatcher, that runs every automation that is on. Its setup sheet lists what
the runner still lacks (a connector, a secret NAME) and how to add it.

**The runner's report.** Each dispatcher run writes `automation/runner.json` (relay 0.9.35, `relay.py runner-status
--write`), and commits it when it changed or is 12 hours old:

```json
{"schema": "keeptrack-runner/1", "updated_at": "2026-10-17T12:00:00.000Z", "relay": "0.9.35",
 "connectors": ["gmail"], "secrets": ["GOG_HOME_ARCHIVE"],
 "awaiting_approval": [{"slug": "email-to-tasks", "owner": "alexdemo"}]}
```

`connectors` and `secrets` are the claude.ai connector names and secret NAMES the owner's entries for this board approve
that the routine holds and has set (never the routine's other connectors, never a name a manifest guessed, never a
value). `awaiting_approval` lists the person's installs that are on but that no entry approves (below). The runner
checklist asks only about what an automation that is on needs. A runner that has not swept for 26 hours shows as not sweeping.

**The switch.** Turning an automation on writes its install register as the person, as `automation install --runner
cloud`, `setup --runtime claude --runner cloud` and `enable` would: the pack digest is computed in the browser from the
pack's files in git (the same rule as `_auto_pack`: every file but the top-level `tests/`, sorted), and the network
grant and the confirmed needs come from the manifest in those same files. A pack that reads more than the board, uses
the network, needs a connector or needs a secret asks first. A pack that runs only locally, has no cloud route for
something it reads, or needs a setting cannot be turned on from the page, and says why. An old register
is reused (its install_id, settings and run history) only when it is the same person's, for the same binding, not
retired, and for the same pack files. Turning it off sets the install to `paused`.

**The switch turns it on; the allowlist approves it** (relay 0.9.35). Every run also needs the owner's entry in
`relay/registry/automations.yaml`, pinned to the pack's digest (relay's README, Automations). Anyone who can write the
board can write a register or a pack folder, and a commit's author is an email anyone can set, so the page never says
who wrote a register: it says what the register says, and the merge-gated entry is the approval. The page reads
`relay/registry/automations.yaml` itself (never `runner.json` or a register) to decide what is approved: an entry for
this board, slug, owner and the cloud runner, at the install's digest, naming every connector and secret the pack
needs. Until an install has one, its row says "Needs approval", the runner checklist asks for no connector or secret
for it, and the runner setup lists it
with a prompt for the owner's assistant: show the pack's files and the git log of its folder and its register,
confirm with the owner, then open the entry's PR for the owner to merge. The confirm dialog and the "on" message say
so too.

## Included packs

- stale-cards-nudge: local board attention logic, a nudge proposal per card per ISO week; no external access.
  Runner any; needs nothing.
- notes-folder-to-tasks: `--set notes_dir=/path`; hashes relative paths/content, follows keeptrack-notes.
  Runner any; no connectors and no secrets. On a cloud runner `notes_dir` must be a folder in the worker's clone.
- email-to-tasks: `--allow-network`, existing gog login; only exact board contact addresses, follows keeptrack-email.
  Runner any. Local: the gog login only. Cloud: the secret named `GOG_HOME_ARCHIVE`, which the environment's
  setup script uses to restore a read-only gog login under `HOME` before the tick (see its SETUP.md). The check
  and `resolve.py` read mail through gog, so a Gmail connector with a `model` check is not offered: that would be
  a separate pack.

Each pack's SETUP.md explains access per runtime. The create skill builds and tests your own pack; it leaves it
unverified. Never put tokens, account addresses or source text into a pack, check output or run summary.

## Behaviour tests (evals)

`tests/` checks the cheap check. It cannot check what the agent does with SKILL.md. A small rewording can change that,
so each pack also has `evals/cases.json`: behaviour tests for its SKILL.md (kit v72). Each case gives a model the
loader ([automation-loader.md](automation-loader.md)) and the pack's SKILL.md as its instructions, as a real run reads both, and a short invented scenario (a check payload, cards, notes or mail as text).
Plain rules then check the answer: `contains`, `not_contains`, `regex`, `not_regex`, `last_line` and `count` (with
`min` and `max`). Each case runs several times and passes when enough runs pass.

- Each pack has at least two cases: a normal run, and a skip or failure path (a malformed item, lost access, an
  instruction hidden in the source text).
- Prompts are `$BOARD/board/automation-loader.md`, then paths under `$BOARD/board/automations/<slug>/` (an own pack:
  `$BOARD/automations/<slug>/`). Without the loader a case tests a run no agent ever does.
- Names, addresses and text in a case are invented, such as owner `alexdemo` and client `Acme Demo`.

Run them from a checkout of the relay repo. Each run is a paid model call, so look first with `--dry-run`:

```bash
python3 relay/scripts/relay.py eval --board <board repo> --cases <board repo>/board/automations/<slug>/evals/cases.json --dry-run
python3 relay/scripts/relay.py eval --board <board repo> --cases <board repo>/board/automations/<slug>/evals/cases.json
```

Exit 0 means every case passed. **A wording change to a pack's SKILL.md (or SETUP.md text the agent reads) is kept
only after its evals pass.** If a case fails, fix the wording, not the check, unless the check itself was wrong; say
so in the change. A new behaviour gets a new case in the same change. `evals/` ships with the pack and counts toward
its digest, so a change to it needs reinstall and setup too. CI only checks that the file is well formed
(`tests/test_automation_packs.py`); it never calls a model.

## Contracts and trust

Manifest schema is `keeptrack-automation/1` (the optional `requires` object is kit v73, above): fixed needs board.read, files.read, gmail.read, drive.read,
github.read, calendar.read; writes is ["proposals"]. Optional `flow` (kit v70) lists 2–8 steps
`{kind, title, text}` that the web board draws as a node diagram: kind is trigger, read, check, agent, output or step;
title up to 40 characters, text up to 160. It is shown as plain text, never followed as instructions. Without it the
board draws the steps from the manifest (schedule, needs, check, agent, Review Inbox). Every fixed interval coalesces missed UTC slots.
Check stdout is one `keeptrack-check/1` object with items (key, rev, title, ref), more, cursor, note and optional `start_cursor`.
`start_cursor` is null or an opaque token validated exactly like `cursor` (1–256 characters,
`[A-Za-z0-9_./+=:-]`, no `://`). It describes the frozen window/page at the start of the check;
`cursor` describes progress after the batch. Moving-window checks must emit a replayable start cursor.
At most 50 items, opaque ID/hash tokens up to 256 characters, one-line titles up to 120 characters,
256 KB stdout, 8 KB stderr and a 1–120 second timeout. Notes are fixed codes, never source text.
Exit 2 means blocked. Seen keys are capped at 10,000; action_key deduplication is authoritative.
A partial mark omits cursor. Cursor advances only after all reserved proposals succeed.

Checks receive only PATH, LANG, LC_ALL, TZ=UTC, KEEPTRACK_AUTOMATION, private KEEPTRACK_STATE/CONFIG files and
an empty private HOME. Only explicitly granted network checks receive real HOME. No BOARD_* or provider keys.
Linux uses unshare -rn when usable; setup reports availability. Isolation is defence in depth; an owner approves
the digest of all pack files except tests/. Any code, prompt or manifest change requires uninstall/reinstall and
setup before enabling again. Stop current work on a digest change. Never actions remain prohibited.
`KEEPTRACK_PROPOSALS_ONLY=1` refuses board writes except propose, automation mark and routine finish;
it guards mistakes, not hostile code. Pack text is trusted repo content; source content is untrusted data.

## Back-office terminology

This JSON format is not compatible with back-office agent-packs' YAML format.

| Keeptrack | Back-office concept |
|---|---|
| needs | integrations / read capabilities (never human_gates) |
| SKILL.md | AGENT instructions |
| every + routine binding | routines / schedule |
| runtime routes | runtime-specific access setup |
| never | prohibited actions, not human_gates |
| proposals | Review Inbox; human acceptance remains separate |

Retiring a built-in is an explicit release step: disable affected installs first. kit-update never removes registers
or seen logs. The web board's Automations page (header button, deep link `#view=automations`) shows each pack as a card with its
flow diagram, status and the command for each next step to copy; it never installs or enables. The relay
scheduler uses `due`, `needs` and `tick --only` (kit v73); usage and direct writes are outside v1.

Tick supplies each item’s `action_key`: `auto:<slug>:` + sha256 of compact JSON `[key, rev]` (list order preserved). Copy it unchanged for proposals and retries. Mixed ticks exit 0 with work; report every payload `problems` entry. Invalid/missing packs remain visible in list. Undelivered reservations finish failed with code `undelivered`; owners can finish failed even after pack loss.

Checks must reject duplicate item keys (including different revisions); tick reports `duplicate-key` before reserving.
Checks receive `KEEPTRACK_DEADLINE_SECONDS`, a work budget below the manifest timeout. Bound source calls by the
remaining budget and cap pages per invocation. Return accumulated items, `more: true` and an opaque continuation
cursor when stopping early. Prefer `KEEPTRACK_SCAN_CURSOR` over the seen-log cursor when supplied.
Tick and standalone `check` share the following rules, applied before delivering output. Local continuation
lives in ignored `automation/.local/tick-state.json`; only `mark` writes the seen log.

| Event | Local `scan_cursor` | Seen cursor / reservation |
|---|---|---|
| Successful empty check, either value of `more`, non-null cursor | Save returned cursor | Unchanged; no reservation |
| Successful empty check, no cursor (`more: false`) | Clear | Unchanged; no reservation |
| Items, existing local cursor | Preserve existing cursor | Unchanged; tick reserves batch |
| Items, no local cursor | Save non-null `start_cursor` if supplied; otherwise remain unset | Unchanged; tick reserves batch |
| Check error | Preserve | Unchanged; no new reservation |
| Partial mark, or failed/partial finish without completed mark | Preserve | Mark records only completed items; finish does not advance cursor |
| Full-batch mark carrying matching cursor (including null) | Clear | Advance seen cursor after all reserved items are marked |
| Standalone check | Same empty/items/error rules as tick | Never reserves; dry-run does not save continuation |
| Mixed tick (work and errors in different bindings) | Apply each binding's rule independently | Deliver work and report errors together |

The email check always includes `start_cursor` on a successful scan, freezing both time bounds and the starting
page, even when that page is the first page. A retry therefore replays the same window after the lookback expires.

## Lifecycle state audit

R = read, W = write, — = unused. Pack reads include validation and digest calculation.

| Command | Register | Seen log | Local tick-state | Pack files |
|---|---|---|---|---|
| install | R/W (fresh install id) | — | clear binding | R |
| setup | R/W | — | — | R (probes) |
| enable / disable | R/W | — | — | R / — |
| check | R | R | R/W | R (check) |
| tick | R/W (reservation) | R | R/W | R (check) |
| dry-run | R | R | — | R (check/prompt) |
| mark | R | R/W | R/W (clear continuation) | R |
| routine finish | R/W | — | — | R (unless failed) |
| fork | — | — | — | R/W (new slug) |
| test | — | — (empty supplied state) | — | R (tests) |
| uninstall | R/W (retire) | delete with --forget | clear binding | — |
| kit-update | — | — | — | built-ins only; own packs protected |

Local results, throttle times and continuation are accepted only for the matching owner,
install id and approved digest; legacy or mismatched entries are ignored on every read.
Install and uninstall clear local state under register-then-state locks. Setup cannot approve
a changed pack: uninstall/reinstall is required; a changed approval digest invalidates local state.
Seen keys deliberately survive reinstall unless --forget is used, preserving proposal deduplication;
seen cursors require the same install identity, and another binding/owner's seen state is ignored.
Dry-run uses no local continuation. Reservations belong to the current register and unique run id;
mark and successful finish check reservation/current/installed digests. Failed finish only records failure.
Fork/test receive no installed state. Kit updates protect registers, seen logs, local state and own packs;
changed built-in digests require reinstall and setup before execution.

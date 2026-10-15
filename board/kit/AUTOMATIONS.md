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

Built-ins live at `board/automations/`; kit-update replaces them. Own packs live at root `automations/` and
must have distinct slugs. Both root `automations/` and runtime state `automation/` are protected from kit updates.
Install state extends `automation/routines/auto-<slug>-<owner>.json`; generic state is
`automation/seen/<binding>.json`. Mailbox checkpoints are separate and unchanged. Commit register/seen changes;
`automation/.local/`, `.tick.lock` and `*.json.lock` are local, ignored state.

## Included packs

- stale-cards-nudge: local board attention logic, a nudge proposal per card per ISO week; no external access.
- notes-folder-to-tasks: `--set notes_dir=/path`; hashes relative paths/content, follows keeptrack-notes.
- email-to-tasks: `--allow-network`, existing gog login; only exact board contact addresses, follows keeptrack-email.

Each pack's SETUP.md explains access per runtime. The create skill builds and tests your own pack; it leaves it
unverified. Never put tokens, account addresses or source text into a pack, check output or run summary.

## Contracts and trust

Manifest schema is `keeptrack-automation/1`: fixed needs board.read, files.read, gmail.read, drive.read,
github.read, calendar.read; writes is ["proposals"]. Every fixed interval coalesces missed UTC slots.
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
or seen logs. The web board shows packs and installs read-only in Settings → Agents → Automations (deep link
`#settings=automations`), with the command for each next step to copy; it never installs or enables. Relay scheduler
hook-up, usage and direct writes are outside v1.

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

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
Check stdout is one `keeptrack-check/1` object with items (key, rev, title, ref), more, cursor and note.
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
or seen logs. The web Automations screen, Relay scheduler hook-up, usage and direct writes are outside v1.

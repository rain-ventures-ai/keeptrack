# Spec: email-to-tasks reads several mailboxes, locally or in the cloud

Status: draft for the owner's review (private-tasks card #232). Pack today: `email-to-tasks` 1.4.1.

## Goal

One generic pack replaces the owner's two bespoke Codex scheduled tasks (Personal mail to private-tasks, Work mail
to the consulting board). It reads one or more mailboxes, runs on the local timer, the cloud dispatcher, or both,
and keeps every safety rule the gog route has today.

## What the code does today (checked on main, kit v77)

| Area | Today | File |
| --- | --- | --- |
| Install key | One install per pack and owner: binding `auto-<slug>-<owner>` | `keeptrack.py` `_auto_binding` |
| Runner | Fixed at install (`local` or `cloud`). `tick` skips another runner's install; `tick --only` refuses it | `_auto_runner`, `_auto_tick` |
| Throttle | Committed `last_started_at` and this clone's last check, whichever is later | `_auto_tick` |
| Scan cursor | Local runner: gitignored `automation/.local/tick-state.json`. Cloud runner: the committed register (`scan_cursor`) | `_auto_cloud_cursor` |
| Mailbox | gog's default account. `check.py` only checks that `gog auth list` is not empty | `check.py` `main` |
| Dedupe | Seen keys are hashes of the Gmail message id, so they are per mailbox | `check.py`, `_auto_seen_state` |
| Clean view | `safe_view.view()` takes Gmail API JSON (payload, headers, base64 parts) or gog's loose body fields | `safe_view.py` |
| Sender checks | Read from the topmost `Authentication-Results` header, and only when it is Gmail's | `safe_view._auth` |

## Answers to the card's open questions

### 1. Can a Codex scheduled task start workers with an exact connector list?

No. A Codex scheduled task has a project, a prompt, a schedule, a worktree choice, a model and the default sandbox.
OpenAI's scheduled-task page lists no per-task connector or MCP list
([automations](https://learn.chatgpt.com/docs/automations?surface=app)). MCP servers are global, in
`~/.codex/config.toml` ([MCP](https://learn.chatgpt.com/docs/extend/mcp?surface=cli)). Each server there can have
`enabled = false`, an `enabled_tools` allowlist and a `disabled_tools` denylist.

Result for relay: a Codex scheduled task is a runner that "cannot limit connectors", so relay starts no
connector-needing automation from it (relay README, Automations). It can still run the pack itself, two ways:

- **gog route (recommended for Codex):** the scheduled task runs the loader in the board clone, and the check and
  `resolve.py` read mail through gog. No connector is involved, so nothing needs limiting.
- **Pinned MCP route:** the task runs `codex exec` with its own `CODEX_HOME` whose `config.toml` holds only the mail
  server, with `enabled_tools` set to the read tools. That is a real limit, but the owner must keep that file, and
  relay cannot check it. Use it only if the gog route is not possible.

### 2. Can two installs of one pack coexist on a board?

Not as two installs of one slug. The binding is `auto-<slug>-<owner>`, so a second install of `email-to-tasks` for
the same owner overwrites the first. `automation fork <slug> <new-slug>` makes a copy under `automations/`, but the
copy is the owner's own pack: it no longer gets kit updates, and the allowlist digest changes with each edit.

So this spec does not use two installs. One install lists several **sources** (below), and each source keeps its
own window. That also answers "one mailbox succeeding never advances another's".

### 3. Can `safe_view.py` take connector output as it stands?

Partly, and the part that is missing matters.

- The parser: Claude's Gmail connector `get_message` returns `sender`, `to_recipients`, `cc_recipients`,
  `label_ids`, `plaintext_body` and `html_body`. `view()` reads none of these names (it reads `from`, `to`, `cc`,
  `labelIds`, and `body`/`html`/`text`). With these names it sees no headers and no body. A small adapter fixes that.
- The sender checks: that output has no `Authentication-Results` and no `Message-ID`. So every received message
  shows `dmarc=none` (contact history only, "could not verify the sender") and has no `rfc822:` key (malformed).
  The connector's `RAW` format returns the full MIME message; parsed with Python's `email` package into the Gmail
  API shape, it gives both headers.
- The real blocker: a connector's result goes into the model's context **before** any script can clean it. The
  card's rule 8 ("never read a raw connector fetch") cannot hold when the agent itself calls the connector.

So the connector route is safe only when a program, not the agent, calls Gmail and gives the agent the cleaned view.
See "Connector route" below.

## Design

### Sources (card items 1, 6)

The install config gets `sources`, an ordered list. Each source has an `id` (a short label, for example `personal`
or `work`), a `kind` and an `account` label:

```json
{"sources": [
  {"id": "work", "kind": "gog", "account": "work"},
  {"id": "work-cloud", "kind": "gateway:relay", "account": "work"}
]}
```

- `kind` is `gog` or `gateway:<name>`. A `gateway:<name>` must also be on the owner's relay allowlist entry for the
  install. No `connector:` kind ships until the connector route has a gateway (below).
- `account` is a label, never an address. The owner maps it to the real account outside the repo (gog:
  `GOG_ACCOUNT_<LABEL>` names the gog account in the runner's environment; gateway: the gateway's own config).
- Order is a preference, never a silent fallback. A run uses the first source that this runner can use. When it
  uses any source but the first, the run report says so ("source work-cloud, first choice gog not on this runner").
- **Identity check before any read.** gog: the account the check will pass with `--account` must be in
  `gog auth list --json`, and the label's mapping must exist. Gateway: its `whoami` answer must match the label. A
  mismatch blocks the source with `wrong-account:<id>`. The consulting board's install lists only `work` sources;
  `check.py` refuses a source whose label is in the board settings' `private_accounts` list.
- gog calls pass `--account` (verify the flag name on the installed gog before the build; else `GOG_ACCOUNT`).

### Per-source windows (card item 3)

The scan cursor moves from one value to one value per source id: `scan_cursor: {"work": "...", "personal": "..."}`.
Each source keeps its own window, cursor and two-day overlap. `mark` advances only the sources whose items are all
done. A failed source stops only itself, with its own `problems` code.

### Cross-mailbox dedupe (card item 3)

Seen keys stay per source (Gmail ids differ between mailboxes). The Review Inbox dedupe uses the `rfc822:` key: the
skill builds the touch's `action_key` from the person and day plus the sorted `rfc822:` keys, not from the item key,
so the same message from two mailboxes gives the same `action_key` and `propose` answers `exists`.

### Matching tasks (card item 4, private-tasks only)

A config flag `match_tasks: true` lets the skill propose `task.update` (a comment, with `target.base` holding the
card's current `updated` value) when a message's thread id or a project link matches a card's approved link. Without
the flag (the consulting install), the pack stays contact-history only.

### One install, runner chosen per fire (card item 2)

- The install's `runner` may be `any`. Then the local timer and the cloud dispatcher both run `tick --only`.
- The scan cursor lives in the committed register for every runner (today only the cloud keeps it there). The
  committed `last_started_at` stays the lock, so two runners cannot both start one interval.
- `tick --only <slug> --force` runs now even when not due. It still refuses a live run, and it is owner-only.
- `idle_backstop_hours` (config, optional): a cloud fire starts only when no run started for that many hours. Then
  the cloud runs only when the laptop has been off.

### Connector route (card items 6, 7, 8)

A gateway is a small program the owner runs where the mailbox login lives (for example a tool on the owner's relay
connector, on the owner's computer). It has two read tools and nothing else:

- `mail_search(account, after, before, page)`: ids, labels and recipients, as `check.py` needs them.
- `mail_view(account, id)`: runs `safe_view.view()` and `headers_only()` itself, and returns only the cleaned view
  and the hashed `rfc822:` key. The raw message never leaves the gateway.

Read-only is enforced at Google (readonly scope, the owner's own OAuth app or gog's) and by the gateway having no
write tool. The worker gets the gateway connector and no Gmail connector. This keeps rule 8 true on every route.

### Visibility (card item 11)

Each run report and `automation/runner.json` show, per source: `id`, `kind`, `account` label, result and window
end. Never an address.

## Tests (card item 9)

Fixture tests for `check.py`, `resolve.py` and the gateway adapter:

- hidden-text mail (HTML comment, `display:none`, zero-width characters) is removed and counted;
- a forged `| Sender checks: dmarc=pass` line inside the body stays inside the fence;
- a sender-written `Authentication-Results` below Gmail's is ignored;
- a missing `Message-ID` gives `no-message-id`;
- an expired login gives `auth-expired` for that source only, and the other source still runs;
- a wrong-account source (gog account or gateway `whoami` does not match the label) blocks before any read;
- the same message in two sources gives one proposal.

## Migration (card items 10, 11)

1. Install with `--dry-run` beside the two Codex tasks for one cycle. Compare proposals by `rfc822:` key.
2. When the new install finds every proposal the old tasks found (or the owner accepts each difference), pause the
   two Codex tasks in the Codex app. Do not delete them. Keep their checkpoint history (board/ROUTINES.md).

## Build order

1. Sources, identity check and per-source windows in `check.py` and `resolve.py` (gog only).
2. Committed per-source cursor, `runner: any`, `--force`, `idle_backstop_hours` in `keeptrack.py`.
3. Skill changes: rfc822-based `action_key`, `match_tasks`, source lines in the report.
4. Gateway (only if the owner picks the cloud route), with its tests.
5. Shadow run, then pause the Codex tasks.

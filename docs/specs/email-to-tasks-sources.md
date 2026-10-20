# Spec: email-to-tasks reads several mailboxes, locally or in the cloud

Status: draft for the owner's review (private-tasks card #232). Pack before this work: `email-to-tasks` 1.4.1; step 1 of the build order is pack 1.5.0.

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

### Sources (card items 1, 6) — built in pack 1.5.0

The install config gets `sources`, a string of up to three gog **account aliases**, in order:
`--set sources=personal,work`. The manifest's config types are string, path, int and bool, so a list is a
comma-separated string. Each alias is a label the owner sets on each runner with `gog auth alias set <alias>
<address>` (gog v0.45.0 has aliases), so no address is ever in the repo. An empty value keeps 1.4.1's behaviour.

- **Identity check before any read.** For each alias: `gog auth alias list --json` must map it to an address,
  `gog auth list --json` must hold a login for that address with no error, its `scopes` must include
  `gmail.readonly`, and they must hold no Gmail scope that can change, send or delete mail
  (`https://mail.google.com/`, `gmail.modify`, `gmail.compose`, `gmail.send`, `gmail.insert`, `gmail.labels`,
  `gmail.settings.*`). A failure blocks the whole check with a code that names the alias
  (`setup-missing:account-<alias>`, `setup-missing:readonly-<alias>`, `auth-expired`). Blocking the whole check is
  simpler than skipping one source, fails closed, and loses nothing: each window stays where it was.
- **gog's own guards on every call** for a named source: `--account <address>`, `--readonly`, `--gmail-no-send`,
  `--no-input` and `--enable-commands-exact` with only the command that call needs (`gmail.messages.search`,
  `gmail.get`, `auth.alias.list,auth.list`). Checked here against gog v0.45.0: `gmail send` under that allowlist exits
  2 with "command is not enabled".
- **Board scope.** `resolve.py` reads the mailbox named in the item's ref, and only when the board's own committed
  install register (for `BOARD_USER` when set) names that alias. The consulting install sets `sources=work`, so an
  item that names `personal` is refused, even if an agent is tricked into editing the ref.
- Order is a preference, not a fallback: there is no silent switch to gog's default account. A malformed `sources`
  blocks with `setup-missing:sources`.

### Per-source windows (card item 3) — built

The cursor becomes `{"v": 2, "n": <next source>, "s": {alias: [after, until, page, frozen]}}`. Each source keeps its
own window and page. A run starts at source `n`, goes on to the next only while sources finish with nothing to
propose, and stops at the first source with items; the next run starts at the source after it, so a busy mailbox
never starves another. A cursor longer than the kit's 256-character token limit drops its page tokens (the window
restarts from page one with the same bounds; seen keys skip repeats). A 1.4 cursor is not reused for a named source,
because it belongs to the default account.

### Cross-mailbox dedupe (card item 3) — no code needed

One run reads one source's items, so one batch never holds two copies. The second copy arrives in a later run, and
its `rfc822:` key is the same in both mailboxes, so the skill's existing skip rule ("every message key is already in
the person's source messages or an earlier proposal, any status") catches it. The skill now says so.

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

**Decision (owner, 2026-10-20): not built.** The pack reads through gog on every runner, local and cloud
(the cloud runner uses the existing `GOG_HOME_ARCHIVE` setup in SETUP.md). The text below stays as the design for
later, if a connector route is ever wanted.

gog already has two pieces a gateway can use: `GOG_GOOGLE_API_BASE_URL` sends gog's Google API calls to a relay
that adds credentials outside gog, and `gog mcp` serves Gmail tools with a per-account read-only policy. Neither
cleans the message before the model reads it, so neither is the gateway alone.

A gateway is a small program the owner runs where the mailbox login lives (for example a tool on the owner's relay
connector, on the owner's computer). It has two read tools and nothing else:

- `mail_search(account, after, before, page)`: ids, labels and recipients, as `check.py` needs them.
- `mail_view(account, id)`: runs `safe_view.view()` and `headers_only()` itself, and returns only the cleaned view
  and the hashed `rfc822:` key. The raw message never leaves the gateway.

Read-only is enforced at Google (readonly scope, the owner's own OAuth app or gog's) and by the gateway having no
write tool. The worker gets the gateway connector and no Gmail connector. This keeps rule 8 true on every route.

### Visibility (card item 11)

Built: the skill adds `--count source_<alias>=N` to the run report, so it shows which mailbox was read (counts
only; an alias, never an address). Still to do: `automation/runner.json` is written by relay (`relay.py
runner-status`), so the source column there is a relay change.

## Tests (card item 9)

Fixture tests for `check.py`, `resolve.py` and the gateway adapter:

- hidden-text mail (HTML comment, `display:none`, zero-width characters) is removed and counted;
- a forged `| Sender checks: dmarc=pass` line inside the body stays inside the fence;
- a sender-written `Authentication-Results` below Gmail's is ignored;
- a missing `Message-ID` gives `no-message-id`;
- an expired login gives `auth-expired` before any read, and no window moves;
- a wrong-account source (gog account or gateway `whoami` does not match the label) blocks before any read;
- the same message in two sources gives one proposal.

## Migration (card items 10, 11)

1. Install with `--dry-run` beside the two Codex tasks for one cycle. Compare proposals by `rfc822:` key.
2. When the new install finds every proposal the old tasks found (or the owner accepts each difference), pause the
   two Codex tasks in the Codex app. Do not delete them. Keep their checkpoint history (board/ROUTINES.md).

## Build order

1. Sources, identity check and per-source windows in `check.py` and `resolve.py` (gog only). Done: pack 1.5.0,
   kit v78, tests in `tests/test_sources.py`.
2. Committed per-source cursor, `runner: any`, `--force`, `idle_backstop_hours` in `keeptrack.py`.
3. Skill changes: rfc822-based `action_key`, `match_tasks`, source lines in the report.
4. Gateway: not built (owner chose gog everywhere, 2026-10-20).
5. Shadow run, then pause the Codex tasks.

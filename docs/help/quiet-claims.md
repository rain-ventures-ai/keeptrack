# Release quiet unattended claims

The ordinary `reconcile --dry-run` command reports evidence without changing the board.
Quiet-claim release is a separate opt-in action. It does not close cards or approve work.

First preview the stricter release candidates on the board:

```sh
python3 board/keeptrack.py reconcile --release-quiet --dry-run
```

Keep the initial week in dry-run mode and review the results with the board owner. Installing or upgrading the kit
does not enable this feature. Afterwards, the owner can run this in their own terminal, without `BOARD_AGENT`:

```sh
python3 board/keeptrack.py settings-set --reconcile-quiet-claims on
```

An enabled board can then run:

```sh
python3 board/keeptrack.py reconcile --release-quiet
```

Use `settings-set --reconcile-quiet-claims off` to disable it. Agents cannot change this setting. The CLI's normal
declared caller identity applies; this is a workflow guard, not a replacement for repository access controls.

The sweep releases only claims belonging to the acting `BOARD_USER`. The heartbeat must be at least 24 hours old;
when the heartbeat field is absent, the claim start is used. The complete timestamp, its offset and fractional seconds
are checked. Attended claims, malformed fields, placeholder sessions and legacy claims without a generation remain.
Every card carrying coordination metadata remains for its existing runner/receipt recovery path, even if its run looks
finished. The sweep never edits, discards or reinterprets those retained receipts.

The exact claim observed when the command starts must still match when it saves. A new generation, heartbeat,
progress note, attended flag or revoked opt-in prevents that release. Conflict retries reread the board and verify
the original identity again. A successful release adds history and a comment with evidence; running it again does nothing.

Columns, waits, pending Inbox questions, labels, todos and approval marks stay unchanged. An unresolved owner question
may outlive a dead worker, so it does not prevent releasing the worker's claim; it still prevents any decision or
approval from being inferred. This sweep never moves a card to To do, starts dispatch, ends a wait or closes a card.

Local worker claim records are deliberately left alone. A fresh worker can write a replacement record immediately
after the board save; deleting by card ID would erase it. Normal claims record their own identity, and stale workers
must obey the board's missing/replaced-claim refusal. Proposal-only automations cannot apply this mutation. Hosted
phase-0 boards keep their existing unavailable-command boundary.

Automatic evidence-based closure, one-time expiry questions, automatic rollout splitting and recorded weekly decision
outcomes are separate work. A preview is not completion of those features, and the real week of owner-reviewed results
cannot be replaced by fixtures or simulated time.

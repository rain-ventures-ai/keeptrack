# Review stale waits without ending them

Kit142 adds an explicit manual reconciliation action. No timer or live board setting is enabled by an upgrade.

Preview with `python3 board/keeptrack.py reconcile --reask-expired --dry-run`. Nothing is written. To record due
questions, run `python3 board/keeptrack.py reconcile --reask-expired` on a schema4 split board as the kit owner's
agent or the owner. The canonical board kit owner receives the question; cards assigned solely to someone else
are excluded. Plain `reconcile` still requires `--dry-run`. Choose one reconcile action at a time.

Seven UTC calendar days make a no-condition wait due for review. New semantic waits age from their stored
`instance_started_at`; legacy waits use their existing `since` date because the original exact start is unknown.
An explicit nudge later than that expiry delays the question. Invalid present dates, identities or conditions
are not treated as absent. PR, card, date and release conditions keep their existing separate evidence workflow.

Every wait remains blocking, including owner-authority and named-person waits. Neither age nor an Inbox answer
grants approval, clears a wait, changes a claim or starts work. If the owner decides to end a wait, use the
existing explicit wait-ending command or web action with the appropriate authority.

New or semantically replaced waits have a random instance ID and start timestamp. CLI and web editors preserve
them when only a nudge changes. A legacy wait receives an ID and an explicit legacy marker only when its first
question and durable receipt are committed together. An expired question is never reopened daily: active,
answered, ignored and archived questions count towards the same instance. Receipts remain outside trimmed history.
An inconsistent receipt needs explicit repair; it does not trigger a replacement question.

Generated questions contain fixed wording and a card link. They do not copy wait notes, dependency prose, private
errors, prompts or session identifiers. Hosted phase0 and proposal-only apply are refused. `--file` fixtures use
local storage. This feature does not activate a daily routine or complete a week's validation.

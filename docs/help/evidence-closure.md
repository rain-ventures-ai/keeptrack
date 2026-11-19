# Close cards from reviewed evidence

Kit145 adds an explicit bookkeeping action. It is off until the actual person kit owner reviews a dry run and enables it. Installing the kit never activates it or schedules a routine.

Run `keeptrack.py reconcile --close-proven --dry-run --json` to get strict close/ask/leave rows, stable card IDs, per-card snapshot digests, a board-wide `report_digest` and canonical PR identities. This writes nothing. Ordinary `reconcile --dry-run` retains its older advisory output; its suggested closes are not apply authority.

A close needs every checklist entry literally true, every linked PR merged with authenticated merge SHA/date proof, an explicit existing `Deliverable:` PR link or a person-reviewed association, and no retained claim, wait, owner question, held/needs-human/Pending review gate or coordination metadata. Stale claims are retained until an independently authorised release. Nothing ticks a checklist, clears a wait, answers a question, merges, deploys or starts work.

## Review legacy comments and association

Legacy prose cannot prove that nobody owes an owner decision. Such cards stay manual without a duplicate Inbox question. The actual person kit owner can review the exact card, its comments/checklist/links and the report, then record that review:

```
keeptrack.py reconcile --review-close t_CARD --expected-snapshot DIGEST --associate-pr https://github.com/OWNER/REPO/pull/123
```

Repeat `--associate-pr` for more existing linked deliverables. This attests the exact legacy-comment and resolved-question inventory review and association only; it does not close the card. Agents cannot record or change it. Do not unset agent identity to impersonate a person. Known unresolved/unverified structured questions and reserved gates remain blocking even with a review.

New/edited comments, checklist, links, owner, meaningful card scope or relevant question/answer/disposition invalidate the review. Its own receipt write, minimum-version adoption, the enablement switch and unrelated board commits do not. A later legitimate PR merge can complete the separate fresh proof requirement without invalidating the earlier association review. Changing board identity requires review again; a local frozen fixture is not portable live authority.

After reviewing the strict report, the person owner can use `settings-set --reconcile-close-proven on --reconcile-close-report REPORT_DIGEST`. Enabling is a standalone settings command and rechecks that exact semantic board/report state and preloaded question coverage inside CAS. A stale token refuses atomically. `settings-set --reconcile-close-proven off` needs no token. The retained enablement receipt records that review; it never proves future card eligibility or question absence. Both review and switch adopt minimum kit145; ordinary use on unopted boards retains its existing floor. Older writers refuse adopted data.

## Apply and retained evidence

`reconcile --close-proven --json` applies only eligible rows when the switch is on. It rechecks ownership, opt-in, exact card safety state and complete question/archive dependencies in the same CAS transaction. Changed dependencies trigger bounded proof refresh outside the board lock; changed safety state refuses. Unsupported/malformed/unread evidence leaves work open. Generic errors never copy private PR responses or link query strings.

GitHub report/comment fragments and query strings are accepted as the same PR identity, then removed before transport or output. Credentials, ambiguous hosts/ports/paths and encoded path tricks refuse. Proof reads are bounded:32unique PRs,8per batch,512KiB per response and60seconds total. Question archives are loaded before mutation with coverage/dependency checks:128parts,1MiB per part,64MiB aggregate; incomplete, malformed or oversized coverage does not prove absence. No archive/network lookup runs inside the reconciliation callback.

Closure uses the existing guarded finish model and records canonical PR/SHA/date evidence atomically. Lost-response/concurrent retries do not duplicate finished history. Reopening a card with the same delivery evidence keeps it open for manual review. Complete native handback receipts remain checked; unverified legacy moved markers stay manual.

Merged work with an unfinished checklist may create one linked owner choice in the same transaction, with fixed safe wording and a durable identity. Existing active/archived/retired/lapsed/ignored or answered-but-unacted questions prevent a new one. A well-typed native answer plus `proposal-done` disposition (including `--not-acted`) can be a factual terminal workflow, subject to exact person review of that resolved inventory and every fresh completion predicate. It proves no external effect, approval or merge. Changed/missing/malformed dispositions and fresh questions block again; unfinished work with a prior question is retained without a new re-ask.

`--file` is offline and reports unverified PRs; it never queries GitHub or trusts a supplied evidence file to close a live card. Hosted phase0 and proposal-only apply are refused. This feature does not install a timer, activate a board, complete rollout acceptance or claim a week of successful operation.

# Merge wishes

Owner wishes for merges in rain-ventures-ai/keeptrack. Recorded on 19 Nov 2026 from Ollie's instruction that Rook should lead reviewed routine work through merging.

These wishes add to the front-door `relay-merge` skill and the trusted board's `relay.py pre-merge` checks. They do not weaken those checks. A NO from pre-merge stays a NO.

## Merge method

- 2026-11-19, Ollie: Use the repo's usual merge method. Pin each merge to the checked head: `gh pr merge <n> --merge --match-head-commit <full head sha>`.
- A new head needs its own reviews and checks. This file changes no GitHub repository setting.

## Who merges

- 2026-11-19, Ollie: Rook (grokbot) may merge when pre-merge says YES and this file agrees.
- Thread merging comes from `merged_by: thread` in the trusted board's merge rule: today the board policy default (`merge_rules.default` in `relay/memory/policy.yaml`). A `merge:` block for this repo in `relay/registry/review.yaml` may set `merged_by` and would override that default.
- Destructive changes and deletes wait for Ollie's yes.

## Gate files

- 2026-11-19, Ollie: A PR that changes any of these paths needs Ollie's yes for the exact head SHA, after he sees pre-merge's reasons:
  - `.github/`
  - `.claude/`
  - `.cursor/`
  - `board/`, except board data files
  - `MERGE.md` (this file)
- A yes covers that head only. A new push needs a new yes.
- Agents never change this file without Ollie's yes for that head.
- See **Reviewed routine changes** below for the one narrow exception.

## Reviewed routine changes

- 2026-11-19, Ollie: Rook may merge a PR it owns or has been asked to drive without another per-PR owner approval when every changed path is one that the adopted reviewed-code classifier verifies and clears as ordinary runtime code, the required reviews and checks pass, and `pre-merge` says YES.
- 2026-11-19, Ollie: That gate clearing also needs `reviewed_code: thread` in this repo's `merge:` block in the trusted `relay/registry/review.yaml`. The setting comes from rain-ventures-ai/keeptrack-relay PR 300, which honours it only for rain-ventures-ai/keeptrack and rain-ventures-ai/keeptrack-relay, and only once that code is adopted in the trusted board. Until then it does nothing.
- 2026-11-19, Ollie: Actual merge/approval authority, policy and registry, reviewer configuration, workflows, hooks and harness settings, destructive work, production data/settings or direct production operations, and `MERGE.md` itself still require Ollie's yes for the exact head. Unknown or unverified changes stay owner-controlled.
- 2026-11-19, Ollie: Direct deployments and production actions are not authorised by routine merge permission. Follow the existing pipeline and deployment checks.

## Reviews and checks

- 2026-11-19, Ollie: Use the current trusted registry's reviewers (`codex` and `cursor`) and fallback (the owner). No required review, blocking label, unresolved owner decision, readiness rule or review-round limit is waived.
- 2026-11-19, Ollie: Failed or unreadable checks still block. CI that did not start may use only the existing supported local-verification procedure when its conditions are proved, with the actual exact-head receipts. This creates no new billing, startup-failure or red-main waiver.

There was no earlier `MERGE.md` on main. These wishes become recorded repo policy only after this MERGE-only change receives Ollie's yes for its exact head and is merged.

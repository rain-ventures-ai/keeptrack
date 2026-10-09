# Board status and truth audits

Use this mode when the person says the board is stale, contradictory or untruthful; asks whether work is really done,
merged, released, published or deployed; or asks to compare the board with its linked repositories.

`$B` below means the Keeptrack command selected by the calling skill. In a board repo without that alias, use
`python3 board/keeptrack.py`.

## Start from what is already configured

1. Run `$B where`, then `$B list`. Use that board without asking the person to repeat its repo or username.
2. Use `$B list -q "<phrase>"` for phrases or states the person named, such as `not published`, `merged` or a release
   name. It searches titles, details, labels, links, comments and history. Use `$B show <id>` on each candidate for its
   full details, links, checklist and recent history. Check archived cards only when the request includes old work.
3. Follow the card's existing links first. Inspect other repositories only when a linked issue, pull request, commit,
   release or deployment points there. Use read-only GitHub/repository checks for the audit.
4. If a required repository or deployment system is inaccessible, name exactly what is missing and continue with the
   evidence that is available. Do not ask the person to restate the whole request.

## Evidence rules

- A pull request is **merged** only when GitHub reports it as merged. Closed is not the same as merged.
- **Released**, **published** and **deployed** require evidence from the relevant release, package, site or deployment
  environment. A merge alone is not publication or deployment.
- A successful deployment proves only the environment and revision it names. Do not assume production from a preview
  or staging deployment.
- A card, comment or branch name is a claim, not independent proof. Prefer the linked system's current state.
- When evidence conflicts or the meaning of a board label/column is unclear, report it as unknown and ask one focused
  question. Do not invent a status mapping.

## Read versus write

- “Check”, “audit”, “review”, “is this right?” and “are you able to do this?” authorize inspection and a proposed
  correction list, not board changes.
- “Update”, “fix”, “correct” or another explicit request to change the board authorizes only the evidence-backed card
  changes in scope. Use `keeptrack.py`; never edit board JSON or use a generic GitHub file-writing tool.
- Do not claim implementation work merely to audit its status. Do not mark a card done just because its pull request
  merged when publication or another acceptance step remains.

## Report

Give a compact list or table with the card, current claim, evidence, proposed board correction and any missing access.
Separate proven corrections from unknowns. If changes were requested, apply only the proven corrections and then say
exactly which cards changed; leave unknowns unchanged.

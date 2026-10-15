---
name: board-upgrade
description: Upgrade this repo's board tools (the board kit from rain-ventures-ai/keeptrack) and migrate board/tasks.json. Use when a board card or a person asks to upgrade the board kit or board tools, or kit-check says the kit is out of date.
---

# Upgrade the board kit

You act for the board's upgrade owner (`python3 board/keeptrack.py kit-owner`). If you act for someone else, comment on the card that the upgrade belongs to the owner, assign it to them, and stop.

1. `python3 board/keeptrack.py kit-check`. If it says current, comment that on the card and finish the card with `done`.
2. Claim the card.

## Main path: `board/upgrade.py`
Use this when `board/upgrade.py` exists (kit v67 and later). For the first upgrade to v67, run the kit's copy:
`python3 <keeptrack clone>/board/kit/upgrade.py --from <keeptrack clone>`, from this repo's root.

3. From the repo root, with a clean checkout: `python3 board/upgrade.py --push --trailer "<each attribution line>"`.
   It makes the backup branch `backup/kit<old>-<date>`, makes a new worktree on `kit-upgrade/v<N>` (the main checkout
   does not change), runs `kit-update`, puts back the lines in `board/upgrade-keep.txt`, upgrades the relay kit when
   `relay/` exists, runs the checks, commits, pushes and opens a draft PR. It never merges and never migrates.
   Add `--owner-files` only when the owner said yes in this conversation or on the card: it copies relay owner-only
   files (code, prompts, the merge gate) that this repo never changed. Without it they are listed under "Do by hand".
4. Read its whole output. Say the backup name on the card. Do every item under **Do by hand** in the worktree it names
   (agent steps from `board/UPGRADING.md`, template lines missing from `AGENTS.md`, relay owner-only files), commit
   there and push. Leave `migrate` for after the merge (step 7).
5. If it stops, read why. The worktree is kept: fix the problem there, or fix the cause and start again (the message
   says how). If this repo puts a line back by hand after each upgrade, add a rule to `board/upgrade-keep.txt`
   (`<path> :: <python regex>`) in a separate PR, so the next upgrade keeps it.
6. `keeptrack.py link` the PR on the card, tick the card's checklist, comment the result, assign the card to the owner
   for review and the merge, and mark it `done` (or `review` when the owner must decide something).
7. After the merge: `python3 board/upgrade.py --after-merge`. It runs `verify --against <backup>` and removes the
   worktree. Comment its result on the card. If the schema changed, follow the migration steps in `board/UPGRADING.md`
   now, from the default branch.

## Fallback: by hand
Use this when `board/upgrade.py` is missing or cannot run here.

3. Make a permanent backup of the default branch: tag or branch `backup/kit<old version>-<YYYY-MM-DD>` (for example `git push origin origin/<default>:refs/tags/backup/kit6-2026-10-08`). Say its name on the card. Then make a branch: `git checkout -b claude/board-kit-v<N>`.
4. `python3 board/keeptrack.py kit-update`. It copies the kit files and writes `board/KIT_VERSION`. It does not commit. Put back any line listed in `board/upgrade-keep.txt`.
5. Read `board/UPGRADING.md`. Do the agent steps of each version after the old version, in order.
6. Do **not** run `migrate` before the PR is merged. The board data would be newer than the tools on the default branch. After the merge, follow the migration steps in `board/UPGRADING.md`. Say this in the PR and on the card when the upgrade changes the schema.
7. Keep this repo's own files: `AGENTS.md`, `CLAUDE.md`, `.claude/settings.json` and anything outside the manifest are not kit files. Change them only when the upgrade notes say so. Do not put repo-specific text into kit files: if a kit file is wrong for this repo, say so in a card comment for the kit to be fixed in keeptrack.
8. Check: `python3 -m py_compile board/keeptrack.py`, `python3 board/keeptrack.py kit-check` (current), `python3 board/keeptrack.py list` (works), and every check the upgrade notes give.
9. Commit, push the branch, open a pull request, and `keeptrack.py link` it on the card. Tick the card's checklist as you go.
10. Comment the result, assign the card to the owner for the merge, and mark it `done`.
11. After the merge, run `python3 board/keeptrack.py verify --against <backup>` from the default branch. Comment its result on the card.

If the card is still open after the merge and the schema changed, run `python3 board/keeptrack.py migrate` from the default branch, then finish the card.

Never push kit changes to the default branch yourself, and never edit `board/tasks.json` or any other board JSON file (`board/cards/`, `board/people/`, `board/projects/`, `board/proposals/`, `board/archive/`) by hand.

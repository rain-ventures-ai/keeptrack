---
name: board-upgrade
description: Upgrade this repo's board tools (the board kit from rain-ventures-ai/keeptrack) and migrate board/tasks.json. Use when a board card or a person asks to upgrade the board kit or board tools, or kit-check says the kit is out of date.
---

# Upgrade the board kit

You act for the board's upgrade owner (`python3 board/keeptrack.py kit-owner`). If you act for someone else, comment on the card that the upgrade belongs to the owner, assign it to them, and stop.

1. `python3 board/keeptrack.py kit-check`. If it says current, comment that on the card and finish the card with `done`.
2. Claim the card. Make a permanent backup of the default branch: tag or branch `backup/kit<old version>-<YYYY-MM-DD>` (for example `git push origin origin/<default>:refs/tags/backup/kit6-2026-10-08`). Say its name on the card. Then make a branch: `git checkout -b claude/board-kit-v<N>`.
3. `python3 board/keeptrack.py kit-update`. It copies the kit files and writes `board/KIT_VERSION`. It does not commit.
4. Read `board/UPGRADING.md`. Do the agent steps of each version after the old version, in order.
5. Do **not** run `migrate` before the PR is merged. The board data would be newer than the tools on the default branch. After the merge, follow the migration steps in `board/UPGRADING.md`. Say this in the PR and on the card when the upgrade changes the schema.
6. Keep this repo's own files: `AGENTS.md`, `CLAUDE.md`, `.claude/settings.json` and anything outside the manifest are not kit files. Change them only when the upgrade notes say so. Do not put repo-specific text into kit files: if a kit file is wrong for this repo, say so in a card comment for the kit to be fixed in keeptrack.
7. Check: `python3 -m py_compile board/keeptrack.py`, `python3 board/keeptrack.py kit-check` (current), `python3 board/keeptrack.py list` (works), and every check the upgrade notes give.
8. Commit, push the branch, open a pull request, and `keeptrack.py link` it on the card. Tick the card's checklist as you go.
9. Comment the result, assign the card to the owner for the merge, and mark it `done`.
10. After the merge, run `python3 board/keeptrack.py verify --against <backup>` from the default branch. Comment its result on the card.

If the card is still open after the merge and the schema changed, run `python3 board/keeptrack.py migrate` from the default branch, then finish the card.

Never push kit changes to the default branch yourself, and never edit `board/tasks.json` by hand.

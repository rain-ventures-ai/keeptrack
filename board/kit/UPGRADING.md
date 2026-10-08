# Board kit: upgrade notes

The board kit is the set of shared board tools. Its source is `rain-ventures-ai/keeptrack`, folder `board/kit/` (branch `main`; `keeptrack.py` downloads the kit from there). Each board repo has a copy, and `board/KIT_VERSION` in the repo gives the kit version of that copy. `manifest.json` lists the files and where they go in a board repo.

**Do not edit kit files in a board repo.** Change them in the keeptrack repo and publish a new kit version. Then upgrade each board.

## Who upgrades a board
Each board has one **upgrade owner**: `settings.kit_owner` in `tasks.json`. If it is not set, the owner is the first person in `people`. Only the owner's Claude routine does the upgrade.
- See or change the owner: `python3 board/keeptrack.py kit-owner [github-user]`.
- When the kit is out of date, the web board shows a banner. For the owner, the banner has a button that makes the upgrade card. Other people see who the owner is.
- `keeptrack.py kit-check --card` makes the same card. A routine run does this at its start, so drift shows on the board with no CI.
- The owner comments `@claude upgrade the board kit` on the card. Their routine follows `.claude/skills/board-upgrade/SKILL.md`.

## Rules for a kit change (for whoever changes keeptrack board/kit)
1. Increase `version` in `manifest.json` by one, and add a section below for the new version.
2. If `tasks.json` changes shape: increase `SCHEMA` in `keeptrack.py` and `KNOWN_SCHEMA` in the web board's `board.js` together, increase `schema` in `manifest.json`, add a step to `MIGRATIONS` in `keeptrack.py`, and make the web board's `normalise()` do the same change. The step must be safe to run two times. The first write after a repo's upgrade PR is merged migrates the data; do not migrate before the merge.
3. The web board and `keeptrack.py` must still read the schema version before the new one, so boards that are not upgraded yet continue to work.
4. A change that needs more than a file copy is not finished until its section here says what the upgrading agent must do and how to check it.

## Versions
### v6 (schema 3)
Fixes from a code review. No data change.
- `--file` boards: atomic writes, and a lock (`<file>.lock`, gitignored) for each read-modify-write.
- Archive years must be 4 digits. The git fallback saves only to a clone whose `origin` is exactly the board repo.
- To-do commands act on the same to-do when they retry. `comments` shows comment ids, and the routine acts on the approved comment id.
- `unarchive` with git updates the board file and the archive file in one commit. New: `archived-history`.
- Agent steps: run `kit-update` only. Add `*.json.lock` and `.tmp-*.part` to the repo's `.gitignore` if it is not there.
- Check: `python3 board/keeptrack.py kit-check` says v6 is current, and `python3 board/keeptrack.py comments '#1'` shows ids.

### v5 (schema 3)
`board.py` is now `keeptrack.py` (there is no `board.py` any more). After the update, delete `board/board.py` and change any hook, routine or note that runs `board.py` to `keeptrack.py`. New: `archive`, `archived`, `unarchive`, a read cache (`.board/cache`, gitignored) and reads of files over 1 MB.

### v3 (schema 2)
Boards can be used from any project, and the kit is also a Claude Code plugin (`board@rain-board`, see `PLUGIN.md`).
- `keeptrack.py use owner/name [--user U] [--token-env VAR]` writes a gitignored `.board/config.json` in a project; `keeptrack.py where` shows which board and auth a folder uses.
- In the kit, the skills that are copied into board repos moved from `skills/` to `repo-skills/` (`skills/` is now the plugin's skill). The paths in a board repo do not change.
- Agent steps: run `kit-update` only. No data change.
- Check: `python3 board/keeptrack.py kit-check` says v3 is current, and `python3 board/keeptrack.py where` shows the repo from the git remote.

### v2 (schema 2)
New boards can be set up with one command, and the web board has Settings → Boards.
- `keeptrack.py init --person user:Name` sets up a new board repo: the kit, starter `AGENTS.md`, `CLAUDE.md`, `.gitignore`, `.claude/settings.json` (only when missing) and an empty `tasks.json`. The starter files come from `templates/` in the kit and belong to the repo after that.
- `NEW-BOARD.md` in the kit is the guide that the "new board" prompt in Settings → Boards points to.
- Agent steps: run `kit-update` only. No data change.
- Check: `python3 board/keeptrack.py kit-check` says v2 is current.

### v1 (schema 2)
First kit version. The tools move from `rain-ventures-ai/consulting/board/` into co-assets.
- Agent steps: run `kit-update` (no data change: schema 2 stays 2, so no migration). Make sure `AGENTS.md` in the repo keeps its own rules and links to `board/README.md` for the schema.
- `keeptrack.py` now gets the repo from the git remote (`origin`). `BOARD_REPO` still overrides it.
- New commands: `kit-check`, `kit-update`, `migrate`, `kit-owner`.
- Check: `python3 board/keeptrack.py kit-check` says current, and `python3 board/keeptrack.py list` works.
- After v1 is in every board repo, change board tools only in co-assets `board/kit/`.

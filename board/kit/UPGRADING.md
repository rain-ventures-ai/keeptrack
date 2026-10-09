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
2. If `tasks.json` changes shape, increase `SCHEMA` and the manifest schema. Add a safe step to `MIGRATIONS`. Update each writer in the phase that adds its write support. Follow the version notes for the migration command. Do not migrate before the upgrade is merged.
3. The web board and `keeptrack.py` must still read the schema version before the new one, so boards that are not upgraded yet continue to work.
4. A change that needs more than a file copy is not finished until its section here says what the upgrading agent must do and how to check it.

## Backups and checks for every upgrade
1. Before the upgrade, make a backup of the default branch: a tag or branch named `backup/kit<old version>-<YYYY-MM-DD>`. Keep it permanently. It costs almost nothing, because git already stores those files.
2. Upgrade on a branch with a pull request. Never upgrade on the default branch directly.
3. After the merge, run `python3 board/keeptrack.py verify --against backup/kit<old version>-<YYYY-MM-DD>`. Also check that the web board loads and saves.
4. A layout change removes the old layout only in the migration commit, after the field-by-field check. The backup keeps the old layout.

## Versions
### v13 (schema 4)
Recurring meeting-note imports now default to a rolling seven-day lookback, retain a durable ingestion log and ignore
unchanged logged documents. The log also has a meeting-independent work index so actions are matched across different
meetings instead of being recreated because their wording or source changed.
- Run `kit-update` only. There is no board-data migration.
- Existing version-1 ingestion logs are preserved and enriched lazily; do not delete them or re-import their documents.
- Check: `.claude/skills/keeptrack-notes/references/routines.md` requires the seven-day default, unchanged-document skip
  and cross-meeting duplicate matching.

### v12 (schema 4)
Recurring meeting-notes imports now have a dedicated routine guide and copyable prompt. The guide keeps a privacy-safe
incremental checkpoint in `automation/meeting-notes-ingestion.json`, distinguishes assignees and clients from labels,
and prevents unchanged notes or shared meeting links from creating duplicate work.
- Run `kit-update` only. There is no data migration.
- Use a separate least-privilege meeting-notes routine; do not add Drive access to the comment-triggered `@claude`
  board assistant.
- Check: `.claude/skills/keeptrack-notes/references/routines.md` exists and the notes skill links to it.

### v11 (schema 4)
The guided onboarding skill is now named `onboard-keeptrack`, so it sorts after the main `keeptrack` plugin skill in
agent skill lists. New boards now start directly on schema v4 split storage, whether they are created by the web setup
wizard or by `keeptrack.py init`. Documentation now consistently describes the board folder rather than calling
`tasks.json` the whole database. Kit v11 also adds automatic routing for board-status audits and imports from meeting
transcripts or notes.
- Run `kit-update` only. There is no data migration. The update installs `.claude/skills/onboard-keeptrack` and removes
  the old kit-managed `.claude/skills/keeptrack-onboard` directory. Existing boards keep their current schema.
- Start a fresh agent session after updating so it discovers the new name.
- Check: the repo has only `.claude/skills/onboard-keeptrack`, and asking to "Onboard my existing work into Keeptrack"
  starts by asking whether to bring in CRM, tasks or both.
- An existing schema-v3 board still uses the guarded v8 migration procedure below: dry-run, `migrate --to 4`, verify,
  then doctor.
- Check a newly initialised board: `board/tasks.json` has `"version": 4` and `"layout": "split"`, with no `tasks` or
  `contacts` arrays. Adding a task creates `board/cards/<id>.json`; adding a CRM person creates
  `board/people/<id>.json`.

### v10 (schema 4)
Guided onboarding is now available from the Keeptrack plugin as well as from a board repo, and setup explicitly hands
off to it instead of improvising an import. It asks whether to bring in people/clients (CRM), tasks, or both before it
surveys anything; it still shows a dry-run plan and waits for approval before writing.
- Run `kit-update` only. There is no data migration.
- Start a fresh agent session after updating so it discovers `.claude/skills/keeptrack-onboard`.
- Check: ask to "Onboard my existing work into Keeptrack". The first question must ask CRM, tasks or both. Nothing is
  imported before `import --dry-run` has shown the plan and the person has approved it.

### v9 (schema 4)
CLI workflow moves on split boards now give a card a fresh rank at the end of its destination column. This prevents `claim`, `done` and `release --column` from creating duplicate ranks when another card already has the same rank there.
- Run `kit-update` only. There is no data migration.
- Check: claim, finish and release a test card between populated columns, then run `python3 board/keeptrack.py doctor`. It must say the board is healthy.

### v8 (schema 4)
Cards and CRM people use split storage. Install the v8 web page before anyone migrates a board.

Bare `migrate` still brings a board up to v3 only. Only `migrate --to 4` splits the board.
- Run `python3 board/keeptrack.py migrate --to 4 --dry-run` after the kit is on the default branch.
- Check the file list and counts.
- Run `python3 board/keeptrack.py migrate --to 4`.
- The command makes a backup tag before it changes a GitHub board. Keep the tag permanently.
- Run `python3 board/keeptrack.py verify --against <backup tag>`. It must say OK.
- Run `python3 board/keeptrack.py doctor` after migration.
- Migrate the upgrade owner's own board first. Tell the team before you migrate a shared board.
- Add `.board/cache/` to `.gitignore` if it is not there.
- Check: `tasks.json` has `"version": 4` and `"layout": "split"`. Check that `cards/` and `people/` contain the item files.

To roll back, revert the migration commit. You can also reset the branch to the `keeptrack-v3-backup-YYYYMMDD-HHMM` tag. A reset removes every later board save, so check with the team first.

### v7 (schema 3)
Onboarding. No data change.
- New repo skill `keeptrack-onboard` (`.claude/skills/keeptrack-onboard/`): a guided set-up from what a person already has (named clients, spreadsheets, email, calendar, Trello and other task tools, Drive, Dropbox or local folders). Files stay where they are; the board stores links.
- New command: `import <staging.json|people.csv> [--dry-run] [--source TEXT]`. It never overwrites a field that has a value, a second run adds nothing, and a file with a problem is refused whole.
- Agent steps: run `kit-update` only. Add `onboarding/` to the repo's `.gitignore` only if the owner does not want the onboarding notes in the repo (they hold names and evidence lines, no email text).
- Check: `python3 board/keeptrack.py kit-check` says v7 is current, and `python3 board/keeptrack.py import --help` works.

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
- `keeptrack.py init --person user:Name` sets up a new board repo: the kit, starter root `README.md`, `AGENTS.md`, `CLAUDE.md`, `.gitignore`, `.claude/settings.json` (only when missing) and an empty `tasks.json`. The starter files come from `templates/` in the kit and belong to the repo after that.
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

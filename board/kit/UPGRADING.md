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
1. Increase `version` in `manifest.json` by one, and add a section below for the new version. Set `version` in `.claude-plugin/plugin.json` to `0.<new kit version>.0` so plugin users get the update. A plugin-only change between kit versions (a skill, a hook) bumps the last number instead.
2. If `tasks.json` changes shape, increase `SCHEMA` and the manifest schema. Add a safe step to `MIGRATIONS`. Update each writer in the phase that adds its write support. Follow the version notes for the migration command. Do not migrate before the upgrade is merged.
3. The web board and `keeptrack.py` must still read the schema version before the new one, so boards that are not upgraded yet continue to work.
4. A change that needs more than a file copy is not finished until its section here says what the upgrading agent must do and how to check it.
5. In the keeptrack repo: add a row to the root `CHANGELOG.md`, extend this file, and add a **frozen board** under `tests/fixtures/` (see `tests/fixtures/README.md`). Extend `tests/test_fixture_boards.py` so `kit-update`, `migrate` (when applicable), and `doctor` keep every task, person, client, and project. The `demo/` board stays the live showcase only.

## Backups and checks for every upgrade
1. Before the upgrade, make a backup of the default branch: a tag or branch named `backup/kit<old version>-<YYYY-MM-DD>`. Keep it permanently. It costs almost nothing, because git already stores those files.
2. Upgrade on a branch with a pull request. Never upgrade on the default branch directly.
3. After the merge, run `python3 board/keeptrack.py verify --against backup/kit<old version>-<YYYY-MM-DD>`. Also check that the web board loads and saves.
4. A layout change removes the old layout only in the migration commit, after the field-by-field check. The backup keeps the old layout.

## Versions
### v39 (schema 4)
Individual tasks can be archived without deletion through the web task menu or `archive <id>`.
All task details, checklist, comments and history are retained, and Search can find and restore the task.
An unfinished agent claim must be released or finished before archival. The web task Contacts field suggests
existing CRM people and stores an optional `person_id` plus compatible contact-detail snapshots; selecting one
does not edit the CRM record or create a new person.
- Run `kit-update` only. No data migration or scheduled-routine changes are required.
- Check: `python3 board/keeptrack.py archive --help` shows the optional task reference. On a disposable board, archive a task,
  find it with `archived`, restore it with `unarchive`, and confirm its details/checklist/comments/history remain.

### v38 (schema 4)
Shared email scans prefer canonical `email-key` RFC822 Message-ID hashes, so copies seen by different board members
are deduplicated per contact while later replies remain new activity. `touch-source` binds verified source keys to an
existing email touch without rewriting its history. Drafts cannot carry imported source-message keys.
Run `kit-update` only. No data migration. Update email routine prompts to use canonical keys and read
`board/ROUTINES.md` for multi-user schedules. Existing entries need verified source binding before automatic imports
can deduplicate them across mailboxes; never infer identity from similar summaries alone.

### v37 (schema 4)
Board-member CRM records cannot be deleted through the web board or `person-rm`. Routines can keep a repo-owned
register and consistent bounded run reports with `routine <id> show|start|finish`; see `board/ROUTINES.md`.
Email imports use `touch --preserve-stage` and repeatable `--source-message-id` to preserve sales stages and prevent
duplicate messages when retry groups change. Member records also stay on the board during archival.
Run `kit-update` only. No data migration. Register existing routines only after verifying where they run and their
connections; preserve dedicated ingestion checkpoints and use null for unobserved run timestamps.

### v36 (schema 4)
Claim-ownership follow-ups from the review of v35. The local claim record is read once per command; a record git tracks is ignored with a note, and writing one at a board repo's root warns when `.gitignore` does not list it. A `heartbeat`, `done` or `release` whose save loses a race re-runs on the newer board, so it never lands on another session's fresh claim. The web page computes its agent-limit check once per render.
- Run `kit-update` only. There is no board-data migration.
- Check: `.board-claim.json` is in the board repo's `.gitignore` (the kit's template lists it); `keeptrack.py claim` prints no "not in .gitignore" warning.

### v35 (schema 4)
Claims, launch checks, done evidence and time zones, from the external review of private-tasks. `done`, `release` and `heartbeat` refuse a claim that belongs to another session (`--force` only on a person's say-so); releasing a stale, stuck or blocked claim works from any session. `--force` no longer skips `max_agent_claims`. A card sent to Claude from the web page gets a placeholder claim, which the routine's `claim` replaces without `--force`. `done` needs `--note` and refuses open checklist items; `done --cancel --note "why"` closes a card as `outcome: cancelled`. `--due today`, the OVERDUE/TODAY flags and `today` use the member's time zone.
- Run `kit-update` only. There is no board-data migration.
- After upgrading, agents must pass `--note` to `done`. Routines no longer need `--force` on their first claim. An older web page that still sends `--force` keeps working.
- Check: `keeptrack.py today` starts with `Today is YYYY-MM-DD (<zone>)`; `keeptrack.py done '#N'` without `--note` is refused.

### v34 (schema 4)
A member's own CRM record is the ONE person with their GitHub login; if two or more share it, all stay contacts and `doctor` warns `MEMBER_PERSON_DUP`.
- Run `kit-update` only. There is no board-data migration.
- Check: `keeptrack.py doctor` shows no `MEMBER_PERSON_DUP`; if it does, keep the login on one person (`person-set <id> --github ''` on the others).

### v33 (schema 4)
A CRM person whose `github` matches a board member is that member's own record, not a contact: `today` skips it, `people` and `person` mark it as a board member, and the web board shows it as You or Board member, outside follow-ups and the pipeline. Nothing is stored; it follows `people[]`.
- Run `kit-update` only. There is no board-data migration.
- Check: `keeptrack.py people` marks your own record "board member @<you>".

### v32 (schema 4)
Hardening from the relay-merge reviews of private-tasks#28. Output: the sanitizer and `EMAIL_RE` also strip line and paragraph separators (U+2028/2029), invisible operators (U+2060-2064) and tag characters; `identity_line` shows a time zone only if it is a real one; an address over 254 characters is not an address; `members` cleans the agents line; `member-set` refuses a member whose `emails` value isn't a list. Claims: the local `.board-claim.json` is written only after the claim is saved, so a claim refused after a lost save race leaves no record behind; a heartbeat that brings a stale, stuck or blocked claim back to running counts against `max_agent_claims` like a new claim, and so does the same session re-claiming it (the automatic heartbeat leaves such a claim stale and says so on stderr). The sanitizer and email check now go by Unicode category; `members` shows only valid addresses and time zones.
- Run `kit-update` only. There is no board-data migration.
- Check: `keeptrack.py me` and `keeptrack.py members` read as before.

### v31 (schema 4)
A member record holds **work** email addresses only: onboarding, `me`, the `--email` help, the skills and the AGENTS template no longer ask for personal addresses or aliases (a board is a repo other people can read). Output hardening: one sanitizer strips control, zero-width and bidi characters from board data printed by `here`, `me`, `members` and `doctor`; `identity_line` shows only valid addresses; the `here` identity line says it is board data; `EMAIL_RE` refuses zero-width and bidi characters; `settings` shows the limit actually enforced and says when a stored value is ignored.
- Run `kit-update` only. There is no board-data migration.
- **If a member record holds a personal address,** remove it: `keeptrack.py member-set <user> --remove-email <address>`.
- Check: `keeptrack.py me` shows only work addresses.
### v30 (schema 4)
Security fixes. On a split board, card, person and project ids name files (`cards/<id>.json`). An id is now used as a file name only if it is a plain token (letters, digits, `-`, `_`); anything else, such as an id containing `../` written into the board by someone with access to the repo, stops the save before anything is written, and `doctor` reports it as `BAD_ID`. Local reads and writes also refuse any path whose real location is outside the board folder, so a `..` or a symlink committed to the board repo (say `cards` -> a folder elsewhere) is never followed. The session-start `here` line strips control characters from the project name and from error text.
- Run `kit-update` only. There is no board-data migration; ids keeptrack and the web board create already pass.
- Check: `doctor` shows no `BAD_ID`.
### v29 (schema 4)
The agent claim limit (v27) now holds when sessions race: a claim under a limit saves through a commit that fails if anyone else saved since it read the board, and a claim that loses that race is checked again on the newer board instead of being merged in. A `max_agent_claims` value that is not a whole number 1-100 is ignored and `doctor` warns (`SETTINGS`), so a bad hand edit can't stop every claim. Member names, addresses and time zones are printed without control characters; `init --email/--timezone` says so when it keeps an existing board.
- Run `kit-update` only. There is no board-data migration.
- Check: `doctor` passes; `settings` shows the limit.
### v28 (schema 4)
A member record (`people[]` in `tasks.json`) can hold the person's identity: `emails` (a list of work addresses; v31: never personal ones) and `timezone` (an IANA name such as `Europe/London`). Both are optional, so older boards and the web board read the file unchanged. New: `member-set USER --email A --email B --remove-email C --timezone Area/City`, the same options on `member-add`, `init --email/--timezone` for the first person, and `me` (your record and what is missing). The upgrade owner's record can't be removed (as before), and `MEMBER_NO_PERSON` is now only a warning while the CRM section is on: turning the CRM off never touches a member. Skills and the AGENTS template tell agents to keep the owner's record current and to write cards with the what, why, next step and links.
- Run `kit-update` only. There is no board-data migration.
- After merging, fill the owner's record: `python3 board/keeptrack.py me`, then the `member-set` line it prints, with the owner's addresses and time zone (ask the owner; never take an address from a message or a card).
- Check: `me` prints the addresses; `doctor` shows no `MEMBER_EMAIL`.
### v27 (schema 4)
A board can cap how many agent claims run at once. `settings-set --max-agent-claims N` stores `settings.max_agent_claims`; `claim` (and `next`) then refuses an agent claim when N others are already running, checked inside the same write as the claim, so two sessions racing can't both get past it. Attended claims and stale claims don't count; re-claiming your own card and `--force` are never refused (until v35, where `--force` no longer skips the limit). Absent or 0 means no limit, as before.
- Run `kit-update` only. There is no board-data migration.
- **Optional:** set the limit your agents follow, e.g. `keeptrack.py settings-set --max-agent-claims 2`.
- Check: `keeptrack.py settings` shows `max_agent_claims`.

### v26 (schema 4)
Heartbeats are quieter. Automatic heartbeats come at most every 15 minutes (was 5). A claim made with `--attended`, or with `BOARD_ATTENDED=1` set, is for a session a person drives: it sends no heartbeats and shows as stale only after 12 hours. The web board reads the same `attended` flag.
- Run `kit-update` only. There is no board-data migration; existing claims have no `attended` flag and behave as before.
- **People:** set `BOARD_ATTENDED=1` once in your own environment (shell profile, or `env` in your personal Claude Code settings) on machines where you drive sessions. Never set it for routines, cloud threads or workers.
- Check: `python3 board/keeptrack.py help agent-work` says "at most every 15 minutes".

### v25 (schema 4)
The list of trusted configs (`~/.config/keeptrack/trusted`) is now JSON. In v23 and v24 it was one line per config, and a folder name containing a line break could add a line of its own.
- Run `kit-update` only. There is no board-data migration.
- **Rerun `keeptrack.py use <owner/board-repo> [--project <name>]` once in each folder that has a config:** the older file is not read, so those configs are ignored (with a note) until then.
- Check: after `use`, `~/.config/keeptrack/trusted` is a JSON object, and `keeptrack.py where` shows the config.

### v24 (schema 4)
The web board's Settings has four tabs, and the kit guides use their names.
- **Web board (served from keeptrack, nothing to install):** Settings is now **Preferences** (theme, card style, layout, notifications), **Board** (sections, columns, labels, archive), **Connection** (this board, Health checks, your boards, Advanced: version, moving settings, forget token, remove a board) and **Agents & integrations** (@claude in comments, Claude or Codex in your chat app, email contact sync). The old General, Boards, Agents, Alerts and Checks tabs are gone. The whole board UI now uses one set of components (`board/ui.js`, catalogue at `board/ui.html`).
- **Kit files:** `ROUTINE-SETUP.md`, `README.md`, the `board-routine-setup` skill and `keeptrack.py`'s new-board message name the new tabs. A file copy (`kit-update`) is the whole upgrade; there is no board-data migration.
- Check: `python3 board/keeptrack.py kit-check` says the kit is current; `grep -rn "Settings → Boards" board/ .claude/` finds nothing.

### v23 (schema 4)
Search reaches email and copes with vague questions.
- `links` now lists each in-scope person's email addresses as `email` links (`mailto:`), including a project's people. The `keeptrack-search` skill searches mail with them when a Gmail or Outlook connector is loaded, and handles vague questions ("is anything at risk?") by listing every file in the scope's folders and choosing by title and date, not by keyword alone.
- **Configs must come from `use`.** keeptrack now reads a `.keeptrack/config.json` (or `.board/config.json`) only if `use` wrote it on this computer: it is listed in `~/.config/keeptrack/trusted` with a hash of its content (so a later edit or swap is refused), owned by you and not writable by others. To change a config, rerun `use`. A config that came with a cloned repo or an unpacked download is ignored, with a note. **After upgrading, rerun `keeptrack.py use <owner/board-repo> [--project <name>]` once in each folder that has a config.** Environment variables (`BOARD_REPO`, `BOARD_PROJECT`, ...) are unaffected.
- **Cloud sessions:** the repo `board` skill says how to use the board from a cloud session where the board repo is attached beside a code repo (`here` first, environment variables for the project, `heartbeat` by hand).
- The skill copy in board repos (`.claude/skills/keeptrack-search/SKILL.md`) is updated by `kit-update`. There is no board-data migration.
- Check: `python3 board/keeptrack.py links --client "<a client with contacts>"` lists `email` links.

### v22 (schema 4)
Keeptrack becomes repo-aware, so it helps where you use it and stays out of the way where you don't (for example a shared code repo a colleague works in without keeptrack).
- **Personal config is `.keeptrack/config.json`.** `use <owner/repo> [--project <name>]` writes it in the current folder with a `.gitignore` of `*`, so it never reaches git. The old `.board/config.json` is still read; rerun `use` to move to the new name. Environment variables (`BOARD_REPO`, `BOARD_PROJECT`, ...) still win.
- **Default project scope.** With a project set, `list`, `next`, `add` and `links` act on that project unless you pass `--project`, `--client` or `--all`; a note on stderr says so.
- **`here`** prints the board, project and user for this folder, your open cards, and a reminder to keep board details out of the repo's commits, PRs and docs. **`help [topic]`** groups every command by topic.
- **Hooks (plugin):** a new SessionStart hook runs `here --hook` only where a `.keeptrack/` (or `.board/`) config or `BOARD_REPO` exists; elsewhere it exits silently. The heartbeat hook now checks for a claim file in the shell and only then starts Python.
- **Claim file:** in a folder with its own config, the active claim is `.keeptrack/claim.json` there, so two repos don't share one claim. Board repos keep `.board-claim.json`.
- **Alarm template:** the open alarm issue is found by title and author (GitHub Actions), so an issue someone else opens with the same title can't silence it; a repeat alarm reassigns the owner.
- Run `kit-update` only. There is no board-data migration.
- Check: `python3 board/keeptrack.py help` lists the topics; `python3 board/keeptrack.py here` prints the board line.

### v21 (schema 4)
The optional visibility alarm (`.github/workflows/visibility-alarm.yml`) gets a test mode and fuller instructions.
- **Test mode:** Actions → visibility-alarm → Run workflow → tick **test**. It opens a `[TEST]` issue saying the repo is private and there is nothing to do; close it. This is the way to prove the alarm reaches the owner.
- **Real alarm:** the issue now lists what to do after making the repo private: note the window and traffic, rotate anything ever committed, check forks (public forks stay public), ask GitHub Support to clear cached views, and decide whether a data-protection authority must be told within 72 hours. A repeat alarm comments on the open issue instead of only logging.
- Run `kit-update` only. Boards without the alarm are unaffected; boards with it get the new version.
- Check: run the workflow once with **test** ticked; a `[TEST]` issue appears; close it.

### v20 (schema 4)
Search across what a client or project links to. New command `links` lists every link around a client, project, card or person, nearest first, de-duplicated and classified by kind. The new skill `keeptrack-search` (plugin and repo) answers a question by searching those links with whatever connectors the session has: it walks Google Drive folders and their sub-folders (Drive's own search does not recurse), reads Drive files, GitHub, web pages and local paths, cites a source for every fact, and says what it could not reach. Read-only.
- Run `kit-update` only. There is no board-data migration.
- Check: `.claude/skills/keeptrack-search/SKILL.md` exists; `keeptrack.py links --client "<a client>"` lists that client's links.

### v19 (schema 4)
Columns, labels and safer saves. No data migration: the schema stays 4 and nothing changes shape.
- **Web board:** Settings → General gets **Columns** (add, rename, reorder, remove; removing a column with cards asks where to move them; To do, In progress and Done cannot be removed) and **Labels** (rename, recolour, add, delete; a rename or delete updates every task that uses the label).
- **Saves merge three ways** (web board and `keeptrack.py`, the same rules: `docs/conflicts.md`). When someone saved first, changes that do not overlap merge field by field and lists merge by item id. The web board shows keep theirs / keep mine / edit only for real clashes. `keeptrack.py` stops on a real clash, writes nothing, leaves their version as it is, and **exits with status 3**: a routine should read the board again and redo the change if it still applies. Board settings are checked too. Upgrade the web page and `keeptrack.py` together: an older kit still overwrites on a same-field race.
- **New CLI commands:** `columns`, `column-add`, `column-set`, `column-move`, `column-rm [--move-to]`; `task-rm ID --yes` and `person-rm REF --yes` (for things created by mistake); `agents`, `agent-add`, `agent-rm [--unassign]`; `todo-edit ID N "text"`; `project-unlink`, `client-unlink`; `list --label X`. `project REF` and the other project commands are now listed in the README and skills.
- **Renames reach archives:** `label-set --rename`, `client-rename` and `settings-set --rename-stage` rewrite matching items in `archive/<year>.json` in the same save. Items renamed before v19 may still carry the old name in an archive file; after `unarchive`, fix them with `task-set` or `person-set` as before.
- **Fix:** `verify --against REF` on a single-file `tasks.json` over 1 MB compared the backup with the current branch; it now reads the backup ref.
- **Optional visibility alarm:** `kit-update --visibility-alarm` (or `init --visibility-alarm`) adds `.github/workflows/visibility-alarm.yml`. It checks daily, and when the repo is made public, that the board repo is private; if not, it opens a P0 issue for the owner and fails. A plain `kit-update` never installs it, but keeps an installed copy current. Delete the file to remove it.
- **Check after upgrading:** `python3 board/keeptrack.py doctor` is clean; `python3 board/keeptrack.py columns` lists the board's columns; the web board opens Settings → General with Columns and Labels and saves a change.

### v18 (schema 4)
Board administration from the CLI, so agents never need to edit board JSON: labels (`labels`, `label-add`, `label-set` with rename and recolour, `label-rm`), clients (`clients`, `client-rename`, `client-rm`), board members (`members`, `member-add`, `member-set`, `member-rm`), settings (`settings`, `settings-set` with title, stale minutes and stages), a much wider `task-set` (title, details, priority, due, `--label`/`--unlabel`), and `unlink`. New repo skill `board-admin`.
- Fix: `add --project` and `task-set --project` now store the project **id**. Before, they stored whatever was typed (a name or id prefix), so `list --project` and `doctor` missed those cards. Find old ones with `doctor` (code `PROJECT`) and repair each with `task-set ID --project <name or id>`.
- Fix: `verify --against <backup>` on a split board now reads the backup's `cards/`, `people/` and `projects/` (from a local copy, a git ref, or the API). Before, it read only `tasks.json` there and reported every card as new.
- Change: `add --label X` for a label the board doesn't have now creates it (grey, as the web board does) instead of leaving a card that `doctor` flags as `LABEL`.
- Run `kit-update` only. There is no board-data migration; nothing changes until a command is used.
- Check: `.claude/skills/board-admin/SKILL.md` exists; `keeptrack.py labels`, `settings` and `members` print; `doctor` is clean.

### v17 (schema 4)
Lightweight CRM extensions: client **north star** text in `client_info`, **projects** under clients (one file per project in split layout), optional **project** on tasks, optional **github** on CRM person records, and `doctor` warnings when a board member has no matching person or a task points at a missing project.
- **Order matters on split boards:** deploy the hosted web board (or hard-refresh after GitHub Pages updates) **before** anyone creates or edits projects on a split-layout board. Run `kit-update` on each board repo so the CLI can read and write `projects/*.json`. An older hosted page (v16) leaves project files on disk but cannot edit them; v17 only deletes `projects/` files when the board has successfully loaded projects from the repo (it will not wipe the folder if project data was missing from memory).
- Run `kit-update` on board repos. There is no required data migration: older boards keep working; new fields appear when you use them.
- Split boards store projects as `projects/<pr_id>.json` (same conflict-retry pattern as cards and people). Monolithic v3 boards may keep a `projects` array in `tasks.json`. Remove projects with `keeptrack.py project-remove` (use `--clear-project` to clear `task.project` on linked tasks).
- Check: client pill **details** button or person drawer **Open client**; filter tasks by project; `keeptrack.py project-add`, `project-remove`, `project`, `list --project`, `client-set --north-star`, `doctor` for `MEMBER_NO_PERSON` and `PROJECT`.

### v16 (schema 4)
Recurring contact-email reconciliation now has a dedicated `keeptrack-email` skill and scheduled-routine guide. It
matches mailbox messages only to exact email addresses already stored on Keeptrack people, records a privacy-safe
incremental checkpoint in `automation/contact-email-sync.json`, and keeps a bounded audit log including the last
successful run. Email bodies and attachments never go into the checkpoint or board.
- Run `kit-update` only. There is no board-data migration.
- Give the email routine read access to one mailbox and write access to the private board repo. Keep it separate from
  the comment-triggered `@claude` task routine.
- Existing contact events can now be logged with their real timestamp and an idempotent hashed source key using
  `keeptrack.py touch ... --at <ISO-time> --source-id email:<sha256>`.
- Check: `.claude/skills/keeptrack-email/references/routines.md` exists, a repeated source id creates only one touch,
  and the checkpoint records `last_successful_run_at` plus recent run summaries without message content.

### v15 (schema 4)
CRM people can now keep multiple labelled email addresses and phone numbers. Existing single `email`, `phone` and
`linkedin` fields remain as compatibility mirrors, so older people appear correctly and no data migration is needed.
Profile/reference links are now explicitly separate from company file/folder resources; resources may be cloud URLs or
local paths, task links may also hold task-specific cloud or local resources, and the agent instructions explain what
access each kind needs.
- Run `kit-update` only. There is no board-data migration; compatible arrays are added lazily when a person is edited.
- Check: `person "<name>"` lists every labelled email/phone, profile/reference link and file/folder resource, followed by
  the access warning when resources exist.
- Check: the web person drawer can add two email addresses, two phone numbers, a profile link, a cloud folder and a
  local path without losing the legacy first values.

### v14 (schema 4)
The default meeting-notes routine can now recover a verified legacy import without rewriting its cards, handles named
owners who are not board users, stores note URLs as task links, and distinguishes explicit completion from `Possibly
done` evidence.
- Run `kit-update` only. There is no board-data migration.
- Never seed a missing ingestion log from a card range or labels alone. Verify each task against its source document and
  revision; leave unverifiable mappings out.
- Check: the recurring prompt reports verified legacy matches, completed tasks and possibly-done tasks, and requires
  `keeptrack.py link` for meeting sources.

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

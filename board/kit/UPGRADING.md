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
1. Increase `version` in `manifest.json` by one, and add a section below for the new version. Set `version` to `0.<new kit version>.0` in all three of `.claude-plugin`, `.codex-plugin` and `.cursor-plugin` `plugin.json` so plugin users get the update (`tests/test_plugin_manifest.py` checks they match), and set `KIT_VERSION` in `keeptrack.py` and `const PAGE_KIT` in `board/board.js` to the new version (`tests/test_web_page.py` checks the page). A plugin-only change between kit versions (a skill, a hook) bumps the last number instead.
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
### v71 (schema 4)
`CARDS.md` ("Comments that need a person") and `routine-prompt.md` ask agents to say who a choice affects and what each
reason rests on (a link, or "judgement"). The Review Inbox gains two optional fields and one read-time rule: an
`ask.choose` may carry `change.recommended` (an option key), `settings.inbox_lapse_days` (default 14, 0 = never) sets when
an unanswered question shows as lapsed, and a lapse is computed when the board is read, never written. The web board
shows each press's result. No migration and no data change: existing proposals and settings stay as they are, and
`settings.min_kit` does not rise (an older page or `keeptrack.py` reads the new field and setting without harm, but an
older `keeptrack.py` refuses to add a question with `recommended`).
- Run `kit-update` only. Check: `kit-check` says v71, `board/CARDS.md` has "Who it affects" and "Review Inbox questions:
  recommended and lapsed", and `keeptrack.py settings` shows `inbox_lapse_days`.
- Optional: change the lapse with `keeptrack.py settings-set --inbox-lapse-days N`. Nothing else to do.

### v70 (schema 4)
Automation manifests may carry an optional `flow` that the web board draws on its new Automations page. The three
built-in packs get plain-words summaries and a flow (pack version 1.1.0). No migration.
- Run `kit-update` only. Check: `automation validate board/automations/email-to-tasks` says valid.
- The built-in pack files changed, so their digests changed. An install of a built-in pack made on v69 is refused
  until it is reinstalled: `automation uninstall <slug>`, `automation install <slug> ...`, `automation setup <slug>`,
  then `enable`. Seen state is kept. Check with `automation list --installed`.

### v69 (schema 4)
Proposal-only automation packs and the automation command family. No migration. Nothing is installed or enabled
by upgrading; no routines, triggers or schedules change. Run kit-update only, then automation list to inspect the
three built-in packs. Follow [AUTOMATIONS.md](AUTOMATIONS.md) to install, setup and explicitly enable a pack.
Root automations/ and automation/ are protected from writes and removals. If retiring a built-in pack, disable
its installs first; never delete its register or seen state as part of a kit release.

### v68 (schema 4)
Card links include the stable card id as well as the number. No data migration.
- Run `kit-update` only; older links and pages still work.
- Check: `card-link '#1'` includes `card=<id>#1`. In a fresh browser, open it on a split board: the drawer opens
  while the board syncs, refuses edits with “Syncing…”, then refreshes in place.

### v67 (schema 4)
New kit file `board/upgrade.py`: one command for the whole upgrade. No data migration.
- Run `kit-update` (or, from now on, `python3 board/upgrade.py`). Check: `kit-check` says v67, and `board/upgrade.py`
  exists.
- `python3 board/upgrade.py [--push]` does the steps of "Backups and checks for every upgrade" for you. It makes the
  backup branch, makes a new worktree on a new branch from `origin/<default>` (the main checkout does not change), runs
  `kit-update`, puts back this repo's own lines, prints the notes below for each new version and the commands to do by
  hand, lists the `keeptrack.py` lines of the kit's `templates/AGENTS.md` that `AGENTS.md` lacks, upgrades the relay kit
  when `relay/` exists, runs the checks, commits, and with `--push` pushes and opens a draft PR. It never merges, never
  migrates and never edits board data. It commits only the paths an upgrade step wrote, and stops on any other change.
  After the merge, `python3 board/upgrade.py --after-merge` checks that the upgrade commit is on the default branch,
  runs `verify --against` the backup on the board as it was in that commit, and removes the worktree.
- Relay (relay 0.9.24 or later): owner-only relay files (code, prompts, the merge gate) are listed under "Do by hand".
  Only with `--owner-files`, the owner's yes for this upgrade, does it copy the ones this repo never changed; the PR then
  lists them under "Owner-only relay files copied (read these before merging)".
- New optional file `board/upgrade-keep.txt` (this repo's own file, not a kit file): lines that `kit-update` must not
  overwrite. One rule per line, `<path> :: <python regex>`; `#` starts a comment. Example:
  `.github/workflows/visibility-alarm.yml :: ^\s*OWNER:`. If the number of matching lines changes, the upgrade stops.
- If this repo puts lines back by hand after each upgrade, write them in `board/upgrade-keep.txt` now.

### v66 (schema 4)
Web board only: the card drawer shows comments and history as one **Activity** timeline, and marks updates that arrive
while the card is open as **New**. No data migration.
- Run `kit-update` only. Check: `kit-check` says v66; open a card: there is no History section, and history rows show
  between the comments in Activity.

### v64 (schema 4)
The **Pending review** column for finished work that waits on a person's decision. No data migration.
- Run `kit-update` only. Check: `kit-check` says v64; `keeptrack.py help agent-work` lists `review`.
- The column (`pending-review`, after In progress) is added by the first `keeptrack.py review`. To show it now:
  `keeptrack.py column-add "Pending review" --after in-progress` (or Settings → Board → Columns). Older pages and
  older keeptrack.py show it as an ordinary column.
- If this repo has its own `AGENTS.md`, add the `review` line from the kit's `templates/AGENTS.md`.
- Relay 0.9.21 or later uses it (`finish_card` with `review: true`).

### v62 (schema 4)
Markdown in card details and comments, and comments that recommend. No data migration.
- Run `kit-update` only. Check: `kit-check` says v62; open a card in the web board: the description shows **Raw** and
  **Edit**, and the editor has **Write** and **Preview**.
- Agents read the new `board/CARDS.md` sections "Format the text" and "Comments that need a person: always recommend".
  If this repo has its own `AGENTS.md`, add the same two rules there (the kit's `templates/AGENTS.md` has the wording).

### v60 (schema 4)
Backlog auto-research setting (off by default). No data migration.
- Run `kit-update` only. Check: `kit-check` says v60; `keeptrack.py settings` shows `backlog_research: off`.
- To use it: `keeptrack.py settings-set --backlog-research on` (or Settings → Board in the web board), and relay 0.9.16
  or later in the board repo (`relay.py kit-update`). The dispatcher does nothing with it before then.

### v58 (schema 4)
The bell opens a "New for you" list. No data migration.
- Run `kit-update` only. Check: `kit-check` says v58.
- Web board: the bell opens a list of the cards with news for you (comments and changes from others). "Filter the
  board" in its footer does what the bell did before.

### v57 (schema 4)
The bell counts news from others. No data migration.
- Run `kit-update` only. Check: `kit-check` says v57.
- Web board: history entries by you or your own agents (`<agent>@<you>`) no longer mark a card as new. A comment from
  one of your agents counts only when it @mentions you. Other people and their agents still count.

### v56 (schema 4)
Card numbers are links. No data migration.
- Run `kit-update` only.
- `keeptrack.py card-link '#N' ['#M' ...]` prints each card as a Markdown link to the web board with its title
  (`[#12](<card link>) Title`). `show` prints `link: [#12](...)` after the card's JSON, `add` and `todo-move` end their
  `added #N` line with the link, and `list --links` ends each line with it. With `--file` and no board repo, the output
  stays as before.
- The board and keeptrack skills, the routine prompt, the AGENTS.md template, the README agent protocol and
  `board/CARDS.md` tell agents to write every card number they name (replies, comments, done notes, PRs, briefs) as
  `[#N](<card link>)`. Add the same line to the board repo's own AGENTS.md "Task numbers" section if it has one.
- Web board: a plain `#12` link now has the card's real address (copy, long-press, open in a new tab). A Markdown link
  `[label](https://...)` in details, comments and history shows as its label; a card link of this board opens the card
  here. The card menu's "Copy reference #N" is now "Copy Markdown link [#N]", and "Copy as Markdown" links the number.
- Check: `kit-check` says v56, and `keeptrack.py card-link '#1'` prints a link.

### v55 (schema 4)
What a good card is. No data migration.
- Run `kit-update` only. It adds `board/CARDS.md`.
- New `board/CARDS.md`: the five tests of a good card (a plain-words title, what, why and "done", steps a person can
  tick, every source in the card's links, nothing secret), a bad card and the same card written well, and how to link
  PRs, issues, documents, folders and web pages.
- The board, board-admin, keeptrack, keeptrack-notes and onboard-keeptrack skills, the routine prompt, the AGENTS.md
  template and the README agent protocol now point at it. Every PR, document or page a card mentions goes in its links,
  not only in its text.
- Check: `kit-check` says v55, and `board/CARDS.md` exists.

### v54 (schema 4)
Moved work is never lost. No data migration.
- Run `kit-update` only.
- New `todo-move ID N [--title T] [--details D]`: one open to-do becomes a new follow-up card (Backlog, or To do on a
  board without Backlog; the same client, project, labels, priority and assignees). Both cards are linked
  ("Follow-up #N", "Split from #M") and related (kind `related` with `from` = the original card's id, so older kits
  accept it), the to-do is reworded "Moved to #N (t_id): ..." and ticked, and both cards get a comment.
- `relate A B --kind follow-up` marks B as A's follow-up; `related ID` shows "Follow-up #N" and "Split from #M".
- `done` and `move ID done` check every to-do that starts "Moved to #N (t_id)": they add a missing link (both ways) and
  refuse when that card is on neither the board nor the archive (`done --cancel` only warns).
- Web board: "Follow-up #N" / "From #M" chips on cards with a follow-up link, Follow-up and Split from rows in the
  drawer's Related cards (Unlink only), and a "Move to a new card" button on each open to-do in the drawer.
- Older pages and older `keeptrack.py` keep the `from` field when they save and show the pair as related.
- Rules: the board skill, AGENTS template and routine prompt say a step that must wait goes to `todo-move`, never a hand
  reword or tick.
- Check: `keeptrack.py kit-check` says v54 and `keeptrack.py doctor` reports no new problems. For an earlier hand move
  (a "Moved to #N" to-do), `keeptrack.py relate '#M' '#N' --kind follow-up` adds the relation.

### v53 (schema 4)
Card dependency follow-ups. No data migration.
- Run `kit-update` only.
- The web board shows a link to a card that is not on the board as "unknown" until the card's archive is loaded.
- Review Inbox Accept refuses `after` links to a card on neither the board nor its archive, and loops.
- `doctor` reports an `after` link to a person's or project's id as `AFTER_MISSING`.
- Check: `keeptrack.py kit-check` says v53 and `keeptrack.py doctor` reports no new problems.

### v52 (schema 4)
Similar cards: add first, then ask. No data migration.
- Run `kit-update` only.
- `add`, the web board's Add and an accepted Inbox item no longer only add: after the add, close open cards (and close
  pending Inbox items) are marked as a possible duplicate or addition, on both cards (new optional card field `related`).
  Nothing is stopped. `add --no-check` skips the check.
- A new-task Inbox item now lists open cards with a close title in `likely_duplicates`, not only the same title.
- New commands: `similar`, `related`, `relate`, `unrelate`, `merge-card` (merge, then archive the merged card; nothing
  is deleted).
- The web board shows a "#12?" chip on a card with a possible duplicate, and a Related cards section in the card drawer
  with Merge, Link and Not related. The Review Inbox checks open cards again when it shows a new-task item, so an item
  whose card was added later shows "Possible duplicate" and offers Merge.
- Older pages and older `keeptrack.py` keep the `related` field when they save; they do not show it.
- `doctor` reports a malformed `related` list as `RELATED` (a warning).
- Pending Inbox items also check each other: a new-task item close to another pending one shows "Possible duplicate".
  Today rows show a short summary, and "2 from this person this day" when one person sent separate emails on one day.
  The `keeptrack-email` skill now groups a person's new emails of one day into one proposal.
- Inbox cards say what Accept does; the button reads Create task, Add log entry, Add person or Apply edit.
- Today's Tasks due shows Overdue, Today, Later this week and Next week (closed by default), as Schedule rows, and
  links to the full Schedule.
- Check: `keeptrack.py kit-check` says v52 and `keeptrack.py doctor` reports no new problems.

### v51 (schema 4)
Small fixes to claims, the heartbeat hook, emails, text cleaning and contacts. No data migration.
- Run `kit-update` only.
- The heartbeat hook refreshes a claim with no claimant only when its agent is the hook's own (`BOARD_AGENT`, else
  `claude`) or unnamed, so one agent's session no longer keeps another agent's claim fresh in a shared checkout.
- Re-claiming your own attended claim without `--attended` now counts against `max_agent_claims`.
- Emails must be ASCII (`keeptrack.py` and the web board). A member email with other characters is dropped from
  `member_emails`, and `doctor` reports it as `MEMBER_EMAIL`; set a valid one with `member-set USER --email ...`.
- `doctor` reports a contact that is not an object as `PERSON_NOT_OBJECT` and does not repair it; `today`, `people`
  and `doctor` no longer crash on one.
- `person-add` and `person-set` warn when a member's login is already on another contact.
- Check: `keeptrack.py kit-check` says v51 and `keeptrack.py doctor` reports no new problems.

### v50 (schema 4)

- New `list --sort score` and `list --sort priority` are read-only; missing scores sort last.
- New `priority-move ID --before ID|--after ID|--top|--bottom` changes independent board-wide order,
  not Kanban column ranks. Whole-board head checks retry concurrent neighbour changes safely.
- No migration is needed. Reading lists never materialises ranks. Existing values, ranks,
  routines and proposals are preserved. URL-backed web filters need no board upgrade.

### v49 (schema 4)
Optional Prioritise layout in List. No migration or reset of existing ordering.
- Run `kit-update` only. Task `value` (integer 1–5), `effort` (XS/S/M/L/XL), and `priority_rank`
  (board-wide fractional rank) are optional additive fields. Kanban `rank` stays independent.
- Enable Prioritise from List on each browser/board. Standard List remains available. Switching back
  hides the scoring controls without removing saved values, effort or board-wide ranks.
- Score is derived from value divided by effort (1, 2, 3, 5, 8), never stored. It guides discussion;
  manual rank stays the default. Missing inputs are unscored, not zero.
- CLI: `task-set <id> --value 4 --effort M`; pass an empty string to clear either field.
- Check: existing cards survive `kit-update`/`doctor`; status changes and archive/restore retain
  board-wide rank. Do not restore an old backup to disable the trial: it could remove subsequent work.

### v48 (schema 4)
Owner-bound durable routine checkpoints through the CLI. No board-data migration.
- Run `kit-update` only. The new `checkpoint <routine-id> show|save` commands read the register's existing
  `checkpoint_path`; they do not rename the routine or reset its history. Commit checkpoint changes separately.
- Legacy single-mailbox v1 state stays at the root. Its first save binds a verified mailbox hash; additional
  mailboxes get independent `accounts[hash]` state, never copies of the first mailbox's watermark.
- See `ROUTINES.md` for input fields, compare-and-save, partial resume and publication order. Never hand-edit
  checkpoints, accept proposals during a scan, or mark success before all required pages and writes are published.
- Check: `keeptrack.py checkpoint <routine-id> show` returns the preserved state and its SHA-256; `kit-check` says v48.

### v47 (schema 4)
Four small fixes to Inbox questions. No data migration.
- Run `kit-update` only. A board on v45 does the v46 steps first.
- A one-off `archive --done-days` no longer shortens how long an answer nobody acted on is kept. The board setting
  `archive.done_days` decides.
- When a question names a `decider`, only that person (or the asking agent) can run `proposal-done` on it.
- `proposal-ignore --reason` history lines start with `ignored: `, and slimming removes the reason text.
- Slimming also removes the `proposal-done --note` text (`decision.done.note` and the note in the history line).
- Check: `keeptrack.py kit-check` says v47.

### v46 (schema 4)
A safety release: no data migration, the board stays on schema 4, and v45 tools keep reading and writing a v46 board.
- **`settings.min_kit` now prevents, not only detects.** `keeptrack.py` and the web page refuse to write a board whose
  `settings.min_kit` is an integer above their own kit version (reads, dry runs and plain `doctor` still work;
  `doctor --fix` writes nothing). A missing or non-integer value never blocks. v46 needs no new `min_kit`, and the
  upgrade writes none; leave it as it is (43 once anyone has used `wait`, 44 once an agent has asked a question).
  Raise it (`settings-set --min-kit N`) only for a later release whose notes ask for it, and only after every copy is
  upgraded: this repo, plugin copies, relay, routines' clones and the hosted page. Before that, an older copy cannot write at all. Kits up to v45 ignore the
  value, so it cannot shut them out. A typo above every kit is not a lock-out: when the stored value is above the published kit,
  `settings-set --min-kit N` on its own lowers it to at most this kit (never below what the cards and questions need),
  and `doctor --fix` lowers it to the published kit or this kit, whichever is older (never below what the cards and
  questions need). A value the published kit reaches is real: both refuse, and the
  answer is `kit-update`.
- **`doctor --fix` and `DUPLICATE_RANK`:** the fix now breaks only the tied ranks and keeps every other card's rank and
  order. Before, it re-ranked the whole column by priority and due date.
- **`kit-update`** takes every file from one commit of the kit, checks that the fetched `keeptrack.py` is the release
  `manifest.json` names, refuses a downgrade unless `--allow-downgrade` is given, and never writes or removes board
  data (`tasks.json`, `cards/`, `people/`, `projects/`, `proposals/`, `archive/`). `BOARD_KIT_URL` has no default
  any more: set it only for a custom kit; when it fails, the update stops instead of using the official kit.
- **`.board-claim.json`** now records each claimed card with its session. An existing one-card record is still read
  and is rewritten in the new shape at the next claim; the hook script is unchanged. Agents running parallel sessions
  in one clone should give each its own `BOARD_SESSION` (a random id, never the claude.ai session id). Update plugin
  copies (the `keeptrack` plugin's hook runs its own `keeptrack.py`) at the same time as this repo: a v45 copy writes
  the old one-card record on `claim`, `done` or `release`, which drops the other sessions' cards from it, so they get no
  automatic heartbeats and go STALE after 30 minutes. A run with `--session` or `BOARD_SESSION` now owns only that
  session's claims (v45 also accepted the session this clone's record holds): keep the same `BOARD_SESSION` from
  `claim` to `done` (in Claude Code put it in each command, since exports do not persist between commands). A run
  whose id changed is refused on its own card and told to rerun with the id it claimed with.
- **Refresh this repo's `AGENTS.md`** (and `CLAUDE.md` where it repeats them) from `board/kit/templates/AGENTS.md`:
  rule 1 must ban hand edits of every board JSON file (`tasks.json`, `cards/`, `people/`, `projects/`, `proposals/`,
  `archive/`), rule 3 and the heartbeat line must say 15 minutes (30 minutes to STALE), and the `wait` line must warn
  never to `unwait` a wait you did not set or one on someone else. `kit-check` now prints `template drift (warning)`
  while rule 1 leaves out a board folder this repo has (any wording that names them all is fine) or the heartbeat
  minutes lag the template.
- Web page: after the upgrade, hard-refresh every open tab once. Settings codes made by older pages still import; a
  code copied without "Include tokens and keys" removes this browser's tokens on import.
- Check: `cat board/KIT_VERSION` says 46; `keeptrack.py doctor` shows no `KIT_OLD`; `keeptrack.py kit-check` shows no
  template drift; the web board loads and saves.

### v45 (schema 4)
Small fixes to Inbox questions. No data migration.
- Run `kit-update` only.
- `proposal-done --not-acted --answer-id <answer_id> --note "why"` closes an answer the agent will not act on (rejected, content changed, no
  longer needed). Routines that ask for approvals should use it after a rejection, so the item does not stay open.
- An answer nobody acts on is kept whole for `archive.done_days` (90 by default), then slimmed and archived.
- `proposal-done` refuses an `ask.approve` with no `content_hash`.
- Check: `keeptrack.py proposal-done --help` lists `--not-acted`.

### v44 (schema 4)
The Review Inbox is **always on** for split-storage boards, and it holds **questions** as well as proposals: an agent
asks (`ask.choose`, `ask.approve`, `ask.question`), a person answers, and the agent acts on the answer once. No data
migration: `settings.review_inbox` is left as it is and no longer read.
- Run `kit-update` only.
- **Behaviour change:** a split board that had the Inbox off now has it on. The notes and email skills then send
  their suggestions to the Inbox instead of writing to the board. Tell the board's people, and check any routine whose
  own prompt writes to the board directly.
- A board that is not on split storage has no Inbox. To get it, migrate with `keeptrack.py migrate --to 4` (backup
  first, see above).
- **Upgrade every copy before an agent asks its first question:** the repo (`board-upgrade`), plugin copies,
  routines' clones, and a hard refresh of the hosted page. An older page offers Accept on a question and would close
  it with no answer. The first question raises `settings.min_kit` to 44 so `doctor` reports older copies (`KIT_OLD`).
- Check: `keeptrack.py help review-inbox` lists `proposal-answer`, `proposal-result` and `proposal-done`;
  `keeptrack.py settings` shows `review_inbox.enabled: true`; the web page has no Review Inbox switch in Settings.

### v43 (schema 4)
Adds **waiting-for**: a card can be parked on a person or an event (`waiting`: on, who, since, nudge, note, by,
by_session), and a board flag, `settings.min_kit`. No data migration: the board stays on schema 4, and older tools read
every card and keep the new fields when they save. The first `wait` (or a wait set in the v43 web page) sets
`settings.min_kit` to 43. From v43, `doctor` warns `KIT_OLD` when a copy's kit is older than that, `MIN_KIT_LOWERED`
when the value is lower than the cards need, `CLAIM_BLOCKED` when a waiting card holds a claim `wait` did not block,
and `AGENT_CLEARED` when an agent run cleared or overrode someone else's wait. Two kits writing `min_kit` at once keep
the higher value (it merges as a maximum, in `keeptrack.py` and in the page).
- Run `kit-update` only. There is no migration, and no `min_kit` is written by the upgrade itself.
- **Upgrade every copy before anyone uses `wait`:** this repo (`board-upgrade`), plugin copies, relay, routines' clones
  and a hard refresh of the hosted page. An older `claim` or `next` does not know that a waiting card is not claimable,
  and an older page offers "Assign to Claude" on one. The flag detects this after the fact (`doctor`); it does not
  prevent it.
- Agents: when a human decision is needed, `wait` the card, comment with `@owner`, `assign` it to them and stop. Never
  `unwait` a wait you did not set in the same session, or one on someone else; a person ends those (web page, or a
  shell with no `BOARD_AGENT`). The new routine prompt and board skill say so; check any repo-specific prompt that
  copies older wording.
- Optional: `settings-set --waiting-days N` (default 7; 0 turns the automatic chase off).
- Check: `keeptrack.py help tasks` lists `wait` and `unwait`; `keeptrack.py settings` shows `waiting_days` and
  `min_kit`; `keeptrack.py doctor` shows no `KIT_OLD`.

### v42 (schema 4)
Adds the Review Inbox. No data change. The Inbox is off until a board turns it on, and it needs split storage
(schema 4). Turning it on does not create, change or start any routine or schedule.
- Run `kit-update` only.
- To use it, run `python3 board/keeptrack.py settings-set review_inbox.enabled true`, or tick Settings → Board →
  Review Inbox in the web board. Use the v42 web page: older pages ignore proposal files and show no Inbox.
- With it on, the notes and email skills add proposals instead of writing to the board. Existing routines keep their
  register, checkpoint and schedule. Read docs/help/review-inbox.md before turning it on for a shared board.
- Check: `keeptrack.py help review-inbox` lists the proposal commands, and `keeptrack.py settings` shows
  `review_inbox.enabled`.

### v41 (schema 4)
Canonical email keys support bounded `email-key --stdin`. Pass untrusted headers as runtime data through stdin or
one non-shell argv element, never interpolate headers into shell commands or executable source. The positional
form remains compatible when invoked safely; canonical key output is unchanged. Email skills and routine instructions
now explain this security boundary.
The hosted weather widget supports opt-in approximate browser location, rounded to 0.1° before local storage or
Open-Meteo requests. Location is requested only on an explicit click; no background tracking or GitHub location writes.
Fixed-city configurations remain compatible; optional `location.mode: browser` waits for permission and uses a configured
fallback on failure if available. Widget enablement and location overrides stay scoped to this browser/board/widget.
- Run `kit-update` only. No migration, source re-import, widgets installation, location selection or schedule change.
- Check: `email-key --help` lists `--stdin`; automation callers must not generate shell/script text containing headers.
- Read the updated email skill and `ROUTINES.md` before the next email import. Existing message hashes remain valid.

### v40 (schema 4)
Board members may explicitly link multiple existing companies with optional `own_companies` in their member record.
These identity links are never inferred from CRM employers. Linked companies and members are protected from removal
until explicitly unlinked; unlinking retains company files, tasks, projects, CRM employer references and history.
Client renames update identity links, and guarded writes recheck changed board state on retries.
The hosted web app also improves saved routine reports, offers goal-focused setup prompts without creating schedules,
and closes task drawers on a double-click on the outside backdrop while keeping ordinary drawer clicks safe.
- Run `kit-update` only. No migration, identity linking or schedule provisioning is performed by the upgrade.
- Check: `member-set --help` lists `--own-company` and `--remove-own-company`; `doctor` checks optional links.
- Upgrade older CLI copies before relying on removal safeguards. Direct repository access bypasses these application guards.

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

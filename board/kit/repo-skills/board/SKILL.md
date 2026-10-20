---
name: board
description: Work from the board stored in THIS repo (a Keeptrack board repo, with board/tasks.json) via board/keeptrack.py. Use in the board repo itself for task work and stuck agents, and when asked whether the board is accurate, truthful or up to date or to reconcile task status against GitHub pull requests, releases or deployments.
---

# Team board

The board lives in the `board/` folder; `board/tasks.json` is its entry point. Current boards keep tasks in `board/cards/` and CRM people in `board/people/`. Manage all of it only through `python3 board/keeptrack.py`. Read `AGENTS.md` for the rules; this is the procedure.

## 1. Identify who you act for
Use `BOARD_USER` (or `gh api user --jq .login`). Valid users: `python3 board/keeptrack.py members`. Set `BOARD_AGENT=claude` and `BOARD_SESSION` to a short random id you generate for this run (never your claude.ai session id).

**Cloud sessions** (a fresh clone, `CLAUDE_CODE_REMOTE=true`) get no plugin and no start-up line. If this board repo is
attached beside a code repo, run its `keeptrack.py` by full path from the code repo and start with `keeptrack.py here`:
it names the board, project and user, set by the environment's `BOARD_REPO`, `BOARD_PROJECT` and `BOARD_USER`.
The heartbeat hook runs only when the board repo is the session's main repo, so otherwise run `heartbeat` yourself
every ~15 minutes. A session a person drives claims with `--attended` (or has `BOARD_ATTENDED=1`) and sends none.

## 2. Find work
```bash
python3 board/keeptrack.py list --assignee "$BOARD_USER" --column todo --unclaimed
python3 board/keeptrack.py list -q "not published"   # search all current task fields
python3 board/keeptrack.py show <id>        # read details, links and contacts before starting
```
If the human named a task, use that one. Do not pick tasks assigned to someone else.

Task links are supporting resources and references for that task (Drive/Dropbox files, issues, PRs, source pages or a
local working path). A person's profile/reference links instead describe that person or company. Their company's
file/folder resources are company-wide working material. Cloud access requires the matching connector/plugin/MCP and
signed-in account; local paths require a session on the computer that holds them. If a resource cannot be opened, say
so and ask the user. Never imply that you read it.

## 3. Claim, work, heartbeat
```bash
python3 board/keeptrack.py claim <id> --note "starting: <one-line plan>"
python3 board/keeptrack.py heartbeat <id> --note "<current step>"     # at each milestone
```
In Claude Code a project hook sends a quiet heartbeat automatically (at most every 15 minutes) while a claim is active, so the claim does not go stale during long work. The manual heartbeat is for updating the note. Without `gh`, set `BOARD_TOKEN` (fine-grained, Contents read/write on this repo).
If a claim is refused because another session holds it, stop and tell the human. Do not use `--force` unless they say so. The same holds for `done`, `release` and `heartbeat` on another session's claim; releasing a stale, stuck or blocked claim needs no `--force`. Never pass `--session` with an id you did not generate for this run, and never open the board JSON files directly (they hold every claim's session id): read the board only through `keeptrack.py`.

## 3b. Checklist
If `show` lists to-dos, work through them in order and tick each one as soon as it is done. Add steps you discover.
```bash
python3 board/keeptrack.py todo-done <id> <N>      # N is the number shown by `show`
python3 board/keeptrack.py todo-add <id> "<new step>"
python3 board/keeptrack.py todo-edit <id> <N> "<corrected text>"   # reword in place; keeps its place and done state
python3 board/keeptrack.py todo-move <id> <N> --details "<what it waits on>"   # move a step that must wait to a new follow-up card
python3 board/keeptrack.py todo-undo <id> <N>      # reopen
python3 board/keeptrack.py todo-rm <id> <N>
python3 board/keeptrack.py history <id>            # automatic log of claims, progress notes, ticks and moves
```

Moved work is never lost (kit v54). When the rest of the card is done but one step must wait (for a person, an event or
later work), move it with `todo-move`: one save adds a follow-up card (Backlog, the same client, project, labels,
priority and assignees, the step as its checklist), links both cards ("Follow-up #N" and "Split from #M", with a board
relation), rewords the step to "Moved to #N (t_id): ..." and ticks it, and comments on both cards. Never reword a step to
"Moved to" by hand and never tick work that is not done. Name the follow-up card in your `done` note. `done` refuses a
card whose "Moved to #N" card is not on the board, and adds a missing link.

## 3c. Comments
`show` prints the latest comments; read them first, since people leave instructions and answers there.
```bash
python3 board/keeptrack.py comments <id>             # full stream
python3 board/keeptrack.py comment <id> "question, update or hand-off"
```
Post a short comment when you finish (what you did, with links) and whenever you need a human.
**A comment that needs a person always recommends** (`board/CARDS.md`, "Comments that need a person"): say what waits and why, give 2-4 options each with a score out of 10 and a reason, your recommendation and why, and the next step. A bare question ("What do you decide?") is not enough. Write details and longer comments in Markdown; `-` reads the text from stdin (`comment <id> - <<'TEXT'`).

## 4. Blocked or stuck
```bash
python3 board/keeptrack.py heartbeat <id> --status blocked --note "<exactly what you need>"
```
Then tell the human in your reply.

## 4b. Waiting on a person or an event
When the work is parked on someone (a decision, an approval, a reply) or on an event (DNS, a release), park the card
instead of guessing: `wait`, a comment with `@<owner>` and the question, `assign` it to them, then stop.
```bash
python3 board/keeptrack.py wait <id> --on "Oliver: approve the quote" --who <login-or-p_id> [--nudge +3] [--note "<asked how>"]
python3 board/keeptrack.py comment <id> - <<'TEXT'   # @<owner>, what waits and why, options with n/10, recommendation, next step
@<owner> ...
TEXT
python3 board/keeptrack.py assign <id> <owner> --note "waiting on your decision"
```
`wait` blocks your own claim in the same save. A waiting card can't be claimed (`--force` does not change that), and
`heartbeat --status running` is refused while it waits. Never `unwait` a wait you did not set in this session, or one
on someone else (`--who`): a person ends those. Never clear a wait to get past a refusal: comment and stop. Never
message the other party yourself. `list --waiting` lists waiting cards; `list --waiting-on me` those waiting on you.

## 5. Finish
```bash
python3 board/keeptrack.py done <id> --note "<result and link to the file/PR>"
# or hand back:
python3 board/keeptrack.py release <id> --column todo
```
`done` is refused while checklist items are open: tick them, or use `done <id> --cancel --note "<why>"` when they are being dropped.

**Done or Pending review?** When the work is finished but its result needs a person's decision (research or a review
that ends in options, a recommendation to accept, "should we do step 2?"), do not close the card. Use
```bash
python3 board/keeptrack.py review <id> --who <user> --note - <<'TEXT'
<result, link, and the decision: 2-4 options with a score out of 10, your recommendation and why>
TEXT
```
It ends your claim like `done`, moves the card to the **Pending review** column (it adds the column the first time) and
posts the note as a comment that @mentions who decides. `done` is only for work where nobody owes a next step. `wait`
is different: use it while the work itself cannot go on.

## Adding tasks
```bash
python3 board/keeptrack.py add "Title" --assign <user> --label <label> --due YYYY-MM-DD --client "Acme" --details "<text and URLs>" --todo "step 1" --todo "step 2"
```
`--client` is optional; leave it out for tasks that are not about a client.

Write the card for a person who was not there: read `board/CARDS.md` (the five tests of a good card, with a bad and a
good example) before you add, change or propose one. Every PR, issue, document, file, folder or web page the card
mentions goes in its links section, with a title, in the same run: `python3 board/keeptrack.py link <id> <full URL>
--title "<what it is>"`. A bare "#481" in the text is not a link.

Make a card in **one command**, so it is one save and one commit: give its links with `--link` and its to-dos with
`--todo` on the `add` (both repeatable), and long details with `--details -` from stdin:
```bash
python3 board/keeptrack.py add "Title" --details - --todo "step 1" --todo "step 2" \
  --link https://github.com/acme/app/pull/481 "PR #481: the change" --link https://example.com/spec "Spec" <<'EOF'
## Now
...
EOF
```
To add several to an existing card in one save: `todo-add <id> "step 1" "step 2"`, or `-` to read one per line from
stdin (`todo-add <id> - <<'EOF'`); `link <id> -` reads one link per line, the URL, a tab, then the title. Do not write
a helper script that calls `todo-add` or `link` once per item.

**Card numbers are links.** When you name a card in a reply, comment, done note, PR or issue text, brief or hand-off,
write its number as a Markdown link to the web board, `[#12](<card link>)`, so a person can tap it.
`python3 board/keeptrack.py card-link '#12'` prints the link with the title (`show` prints `link:`, `add` prints it,
`list --links` adds it to each line). The web board shows `[#12](...)` as #12. Leave the to-do text that `todo-move`
writes ("Moved to #N (t_id): ...") and link titles ("Follow-up #N") as the tools write them.

To change a task after it exists (title, details, priority, due, labels, client, project, links) use `task-set` and
`unlink`. To change the board's labels, clients, members or settings, use the `board-admin` skill. Never edit JSON.

## Checking on others
`python3 board/keeptrack.py list --attention` lists stale, stuck and blocked claims, waiting cards due for a chase,
cards where an agent run cleared or overrode a wait this week, and Review Inbox questions that have lapsed (unanswered
for `settings.inbox_lapse_days`, default 14; questions belong to no project, so a card filter or this repo's default
project hides them: add `--all`). Do not ask a lapsed question again unless the person brings it up
(`board/CARDS.md`, "Review Inbox questions: recommended and lapsed"). `today` shows a CHASE NOW group.

## Check the board
Run `python3 board/keeptrack.py doctor` after a migration or when the board shows an error. Use the `board-doctor` skill before you run `doctor --fix`.

## Board status and truth audits
Natural requests such as “is my board accurate?”, “these say merged but not published”, “make the statuses truthful” or
“check the board against the repos” belong to this skill. Do not ask the user to name Keeptrack or repeat this repo.
Read [references/status-audits.md](references/status-audits.md) and follow it.

## Searching a client's or project's linked material
`python3 board/keeptrack.py links --client "<name>"` (or `--project`, `--card`, `--person`) lists every linked
folder, file, repo and page with its kind. To answer a question from that material, use the `keeptrack-search` skill.

## People and follow-ups (Keeptrack CRM)
If the board has CRM people, use:
`keeptrack.py today` (who to contact), `people`, `person "<name>"`, `person-add` (refuses duplicates), `person-set`, `touch "<name>" "<text>" --channel linkedin|email|call|meeting|note [--draft]`, `sent "<name>"` and `client-link "<company>" <cloud-url-or-local-path>`. `person` lists every labelled email and phone number, profile/reference link, and company file/folder resource. To set up a board from a spreadsheet, email, Trello or folders, use the `onboard-keeptrack` skill (it ends with `import`).
When you write a message for someone, log it with `--draft`. Never send it yourself. Run `sent` only after the human says it is sent.
For a mailbox scan or recurring Gmail/Outlook reconciliation, use the separate `keeptrack-email` skill. Imported
events use `touch --at <actual ISO timestamp> --source-id email:<sha256>` so contact time is accurate and retries do
not duplicate the log.

## Never
- Edit any board JSON file directly.
- Put client-confidential content in card text.
- Contact anyone outside the repo or share prices without the human's explicit approval.

## Numbers and mentions
- Refer to tasks as `#12` (shown on each card); `keeptrack.py show '#12'` works wherever an id is accepted.
- To get a human's attention, add a comment containing `@github-username` plus the reason; they see an "@ you" marker on the card.

## Working from a GitHub issue (board-task)
Issues created with the board's "Create issue" button carry `<!-- board-task: id=... num=N -->` and are titled `[#N] ...`. When you are asked to work such an issue:
1. `python3 board/keeptrack.py show '#N'` for the card, comments and checklist; the issue body is a snapshot.
2. Report back on the board, not only on the issue: `comment '#N' "..."` for progress or questions, `move '#N' in-progress|todo|done` for status, `link '#N' <PR url> --title "PR"` when you open a pull request.
3. Need a person (decision, access, review)? `assign '#N' <github-user> --note "why"` and comment with `@username`; then stop and wait.
4. Finish with `done '#N' --note "<result, PR link>"`. Set BOARD_USER and BOARD_AGENT; without a `gh` login set BOARD_TOKEN (or GH_TOKEN in GitHub Actions).

## Fired from the board (a person assigned their Claude or typed `@claude`)
A routine run starts with a `routine-fire-payload` naming a task number (`#N`) and the person (`@user`). The quick assign action writes a visible `@claude` request first, so both entry paths use the same protocol. The page has already put a claim on the card for this run, so:
1. `export BOARD_USER=<user> BOARD_AGENT=claude BOARD_SESSION=<a short random id you generate for this run; never your claude.ai session id>`; `BOARD_TOKEN` is set in the routine's environment.
2. `python3 board/keeptrack.py claim '#N' --for <user> --agent claude --session "$BOARD_SESSION" --note "working"` (the page's placeholder claim for you is replaced; if the claim is refused because another session or the board's agent limit holds it, comment that on the card and stop).
3. `keeptrack.py show '#N'` and `keeptrack.py comments '#N'`; do what the newest `@claude` comment from that user asks, and nothing beyond it.
4. Keep the card honest while you work: `heartbeat '#N' --note "..."`, `todo-add` / `todo-done` for steps, `comment '#N'` for anything a human should read, `link '#N' <PR url> --title "PR"` for pull requests, `move '#N' <column>` for status.
5. Need a decision, access or review? `wait '#N' --on "<who: what>" --who <user>`, `comment` with `@<user>` and the question, `assign '#N' <user> --note "why"`, then stop. Never guess, and never `unwait` a wait you did not set.
6. Finish: `comment` the outcome, `assign '#N' <user>`, `done '#N' --note "<result>"`. `done` is refused while checklist items are open: tick them, or `done '#N' --cancel --note "<why>"` when they are being dropped.

### Command cheat sheet
`list` (`--label X` for one label, `--waiting`, `--waiting-on me`), `show`, `claim`, `next`, `heartbeat`, `release`, `done`, `wait`, `unwait`, `add`, `task-set`, `unlink`, `move ID COLUMN`, `assign ID USER... [--add|--remove]`, `link ID URL --title`, `todo-add|todo-edit|todo-done|todo-undo|todo-rm|todo-move`, `comment`, `comments`, `history`. `ID` may be a task number such as `'#12'`. Columns: `backlog`, `todo`, `in-progress`, `done`. Board members are listed by `keeptrack.py members`; CRM people are separate records.

## Archive (old items)
Old done tasks, Lost people and long histories move to `board/archive/<year>.json` with `python3 board/keeptrack.py archive` (`--dry-run` first). Search them with `archived -q "<words>"`, and bring one back with `unarchive '#N'`. The board file keeps an index in `archive.files`; do not edit archive files by hand.

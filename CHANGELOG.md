# Changelog

All notable changes to the **board kit** (`board/kit/`) and **board data schema** (`tasks.json` and split files) are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## Unreleased

Kit v109: `keeptrack.py watch` no longer risks the board token's API allowance. A GitHub or hosted board is read at most every 10 seconds (`--every` 10 to 3600; a local `--file` board still 0.2 to 3600), and on a GitHub board, while nothing new is committed, each poll reads only the branch head instead of reloading the whole board (a hosted board still reloads at each poll). Three failed head reads in a row reload the board, so a lasting error stops the watch with that error. A watch stops by itself after an hour (exit 2) unless `--timeout` says otherwise (at most a day). No data change and no migration.

Kit v108: one shared docs-home provider/root setting, validated CLI and web setup, safe read-only display, and a small setup/filing skill. GitHub destination changes/clear use the owner’s live read-back confirmation; hosted CLI docs-home access is read-only for every identity, with changes confirmed by the human board owner in web Settings → Board → Docs home. Combined legacy settings flags are refused. Existing folders are reused; docs stay in storage and cards hold links. No live setting, external folder or document is changed by this release.

Kit v107: archive bodies load only for archive views, archived lookups, proposals and explicit diagnostics; snapshots retain their paths, sizes and revisions. Stale SHA blob caches are pruned within the current board repository. On a split board alone in its folder, GitHub archive writes split oversized years into bounded `YYYY-N.json` parts in the same atomic commit (boards that share a folder, and so its archive, hold an oversized year back as before), retaining records, history and unknown envelope fields. Unpackable individual records stay safely held. The first part-file write sets `settings.min_kit` to 107; ordinary reads and year-only writes do not. Hosted archive storage keeps its year-only contract and uses a separate metadata revision endpoint, with full-body fallback for older servers. No automatic data migration. Review follow-ups validate malformed minimum-kit values, restore older history in linear time with dictionary equality preserved, reject malformed archive records cleanly, and carry the new legacy root revision into the next ordinary edit.

Kit v106: archive size follow-ups. Split-board toasts exclude held years, archived label/client/stage rewrites allow oversized files to shrink or remain unchanged, and size warnings appear once after save. Held CLI tasks and people retain list positions and can still trim history into a year with room. Hosted archive size enforcement remains server-side and is documented explicitly. No migration; includes v100.

Kit v105: Gmail contact-log source links are saved with only a thread ID and optional numeric account selector.
Search terms, labels, query parameters and account addresses are removed in the page and CLI; a Gmail view without
a recognised thread-ID shape is refused, including pagination and nested-label/search-only addresses. Legacy full-width
hex and bounded `FMfcgz` web-ID shapes are supported conservatively; other forms fail closed. Existing Gmail links render with clean targets. Missing-record Back/Forward entries
now discard stale drawer markers so the next drawer has its own history entry. CLI source links accept uppercase
`HTTPS://`. No migration; old stored Gmail URLs are cleaned when edited rather than rewritten in bulk.

Kit v104: resolve the board before choosing its token. The folder token is used only for its own board at the HTTPS
GitHub API; another shell board or API host never borrows it, including when the shell token is absent. `where`
explains the skipped variable and actual authentication source. Clone mismatch advice respects trust, identifies the
same clone as the CLI, skips hosted commands, and caches git lookups within a two-second budget. No migration.
Malformed API URLs fail closed. New token configs reject global auth aliases; legacy alias credentials are removed
from this CLI process when skipped, preventing HTTP/gh fallback from reusing them; a legacy `BOARD_TOKEN` setting
is the shell's own token and stays. A skipped folder token is noted on stderr, and the read cache never sends the gh
login's github.com token to another `BOARD_API` host.

Kit v103: image review follow-ups ([private-tasks #305](https://rain-ventures-ai.github.io/keeptrack/board/?repo=osouthgate%2Fprivate-tasks&card=t_sh4ypf9u09#305), `t_sh4ypf9u09`). Progressive JPEG metadata is removed between scans without mistaking table bytes for the end of the image. Valid terminal JPEG marker fill is accepted, including progressive files. EXIF orientation is read only from complete, valid TIFF directories, so malformed entry counts cannot cause work beyond the supplied metadata bytes. WebP trailers outside the declared RIFF length are discarded. APNG is saved as a still image; browser and CLI discard every APNG animation chunk. GIF and animated WebP retain compressed frame data, which may contain ignored bytes. Recognised container metadata, comments and colour profiles are removed; this does not guarantee removal of hidden identifying information. Re-export a fresh still PNG/JPEG to discard the original animation payload. Browser still uploads re-encode decoded canvas pixels rather than retaining original compressed data. CLI PNG uploads validate exact scanline lengths, including Adam7, and reject incomplete or excess pixel streams. PNG/WebP chunk counts, JPEG segment counts and GIF block/frame/sub-block counts are bounded before output allocation. JPEG application metadata, private PNG/WebP chunks and ICC profiles are removed using format allowlists. Browser still images apply colour conversion; CLI uploads and profile-stripped animations can look different. Image reads retry server and rate-limit failures with bounded exponential backoff; a bounded reusable cache and explicit DOM leases revoke unused overflow per settled entry or removed subtree, without full-owner sweeps. APNG animation data is deliberately discarded, successful uploads supersede in-flight reads without restoring stale failure history, removed PNG colour descriptions force conversion, and image-resource link clicks hold leases too. Source uploads have a 25 MB ceiling. No migration. Includes the v97 List-view release.

Kit v102: CLI contact links now appear in the web card Contacts section and report the person’s name. Person task lists read both legacy primary links and multi-contact links. Linking preserves other people and rejects unknown or ambiguous references. Existing activity resolves person IDs to names without rewriting history. No schema change or migration.

Kit v101: `keeptrack.py watch` polls until a card changes, or until it reaches a column (`--until done`). One command can name several cards; `--all` waits until every one is in that column. A heartbeat on its own does not count. `--timeout` exits 2 when nothing changed. `--json` prints the card and what changed. It reads the board and does not register a listener. No data change and no migration.

Kit v100: a split names the other card. Activity history that says `split from t_…` (or any other card id) shows that card as `#N` and its title, and opens it. `relate A B --kind follow-up` writes the same Follow-up and Split from links as `todo-move`, on both cards. Unlink asks first. Waiting for stays a person or an event, not a split. No data change and no migration.

Kit v99: Review Inbox can record a new task as already done, and duplicate warnings stay put. **Task completed** creates the card in Done (outcome completed, checklist ticked, history `done: already completed when reviewed`) so a suggestion you review after the work is finished is not dropped by Ignore. The same action is `proposal-accept <id> --done`. A new-task item keeps its duplicate warning next to the decision: close open cards, close Inbox items, and a finished card with the same title (`already done`). Adding a card leaves the same warning on the card after the toast goes. No data change and no migration.

Kit v98: List drops the per-row mark-done square (it looked the same as the select box; **Mark done** stays on the selection bar) and shows the description under the title. Markdown marks are stripped and line breaks are joined, so later lines stay visible (two lines on a wide screen, three on a phone). Calendar day lists and Schedule still mark one task done. No data change and no migration; keeptrack.py changes only its version.

Kit v97: List view multi-select and last activity (private-tasks card #307). Mark done is a square, in List and Schedule, so it is not mistaken for a select box. List adds a tick box on each row and a select-all for the rows on screen. With a selection, a bar offers **Move to…**, **Mark done**, **Copy IDs** (for example `#150 #96`) and **Clear selection**. Move and Mark done are off on a read-only board. The selection stays in this tab and clears when you leave List. **Activity** is how long since the newest edit, comment or history entry (`3d ago`); a card quiet for 14 days is marked, and on a phone the time sits under the title. No data change and no migration; keeptrack.py changes only its version.

Kit v96: an Archive view to browse archived cards and people (private-tasks card #283). Before, the archive could only be
reached by ticking Include archive in Search, so you had to know what to look for. Web board: **Archive** is a new tab
after Activity in the Tasks views. It lists the archived cards by archive year, newest year first (the year of the
archive file: when a card was archived, or for the bulk clean-up the year it last changed), with search (title, details,
checklist, comments, labels, #number), filters for project, label, year and Done or cancelled (not Done), the client
filter at the top, a count and **Load more** after 50. The archive files load when the view opens, with a loading and
an error state (Try again). A tap opens the existing read-only archived card with **Put back on the board**, which a
read-only board hides. People: the stage filter has a last option, **Archived**, that lists the people the archive
moved out (Lost people) the same way. Search: **Include archive** is remembered in this browser, and archived results
carry an "Archived <year>" pill with that archive file year. No data change and no migration; keeptrack.py changes only its version.

Kit v95: images on cards, the review fixes for v92 (private-tasks card #292). Uploaded images lose recognised metadata containers
(EXIF: GPS position, device, owner; text chunks; XMP; GIF comments; data after a JPEG's end): the page draws every image
again before upload (chosen by its bytes, not its name) and `keeptrack.py attach` strips those segments, keeping only a
photo's Orientation so it is not saved sideways. `attach` falls back to a git push when the sandbox proxy blocks API writes,
checks the card id and the board's read-only guard before writing, and reads the board once. The page treats a 422 as
"already there" only when GitHub asks for a sha, tries a failed image read again after 30 seconds, keeps at most 120 images in memory and
refuses a non-image before redrawing it. No migration.

Kit v94: project comments, one-level replies, and an image in Links (private-tasks cards #300, #301, #303). A project
record can hold a comment stream (`project-comment`, `project-comments`, and `project` prints them newest last); the
project drawer has a Comments section after Links. Card and project comments may set `reply_to` to one parent comment,
like a Slack thread: not under a reply, and not under an activity line. The card stream indents replies and @Mentions
says who is being replied to. A reply does not unblock a waiting card. `attach --link` puts an image in the card's
Links as an `assets/` path (not together with `--details`), and **Add image** in Links does the same on the page.
No migration.

Kit v93: meeting-notes name resolution. Auto-generated notes often garble spoken names in the body while keeping
correct attendee emails. The keeptrack-notes skill, its recurring-import prompt and notes-folder-to-tasks now build a
roster from header mailto/email addresses, match board people by email, derive names from email local parts, and rewrite
clear near-miss body spellings (e.g. "Sega" when `sagar.…@…` is an attendee) to the roster/board name in titles, details
and reasons. No migration and no data change.

Kit v92: images on cards (private-tasks card #292). An image (PNG, JPEG, GIF, WebP, at most 2 MB) is written to
`assets/<card id>/<yyyymmdd>-<hash>.<ext>` beside the board files and referenced as `![alt](assets/...)` in a
description or comment, so the board data stays small. The web board adds images by paste, drop or an **Image** button
(scaling larger ones down) and shows them by reading them through the GitHub API with its token; a file whose bytes are
not the image type it claims is never shown, and no outside image is ever loaded. `keeptrack.py attach <card> <image>`
does the same from the terminal (a new comment, or `--details` for the description). Board loaders never read
`assets/`. Not on hosted boards yet. No migration.

Kit v91: CRM gaps after Companies (private-tasks card #290; v88 is another change in flight). Companies gets a **Sort** menu (stage, recently
contacted, recently updated, name) and a last-contact filter (contacted in 30 days, no contact in 30+ days, never
contacted), remembered per viewer and board. A company, person or project record has its own address
(`#company=<name>`, `#person=<id>`, `#project=<id>`): opening the record puts it in the address bar, opening the link
opens it, and each record's ⋯ menu has **Copy link**. A contact log entry may carry `url`, the link to the original
message or thread: `keeptrack.py touch --url`, the new `touch-url` command, and the page's link button set it; the person
record and the company's Activity show **Open in Gmail** / **Open original** in a new tab (http(s) only), and `person`
prints it. The `keeptrack-email` skill passes the Gmail thread link. A person's record shows **Project activity**: for
each project they are in (their email is on it, or a task names them), the newest comments and changes on its tasks.
No migration.

Kit v90: a folder's own token setting wins (private-tasks card #286; v88 is held by an open kit pull request).
When `.keeptrack/config.json` names `token_env` and that variable is set, `keeptrack.py` uses its value even when
`BOARD_TOKEN` is already set in the shell, and warns on stderr when it replaces a different value. A shell `BOARD_REPO`
naming another board keeps the shell's `BOARD_TOKEN`, and v104 also stops borrowing the folder token when the shell token is missing. `where` names the
variable the token came from and which board won. In a board clone, a `BOARD_REPO` inherited from the shell that names
another board than the clone's git remote now prints a warning (it still decides). No migration and no data change.

Kit v89: the last gaps in the reserved client-name check (private-tasks card #287; v87 and v88 are other changes in
flight). `archive` and `unarchive` save directly, so they now run the check themselves: an archived record whose client
or company is `__proto__`, `constructor` or `prototype` stays archived until it is restored with a new name
(`unarchive '#N' --client NEW`, or `--company NEW` for a person; on hosted boards a person runs it, as an agent cannot
change a card it does not hold) or renamed with `client-rename` (which also rewrites the archive; not on hosted boards).
The refused restore, in the CLI and on the page, names that command. The hosted `add --client` runs it before posting. Board members' `own_companies` count as uses, so
`member-set --own-company __proto__` is refused. Uses are counted by the exact stored string, so renaming
`" __proto__"` to `"__proto__"` is refused (a padded name can still be renamed away). A command that would copy a
reserved name already on the board (`todo-move`, `add --project`) names where it is stored and says how to clean it up.
Web board: every save (GitHub and hosted) counts the same places and refuses one that adds a use, so picking an old
reserved client from a list for a new task, a task sheet or a new project is refused with the same advice. Restoring
an archived record is checked too (split boards, and the hosted unarchive in the page and the CLI), as is a hosted
`add --project` whose project has a reserved client. `client-rm` keeps a reserved name while the archive still uses it.

Kit v87: an archive file has its own size limit (private-tasks card #284). `doctor` failed with `FILE_SIZE` as soon as
`archive/<year>.json` passed 200 KB, and relay's `ci_checks.py` (which runs doctor) failed on every PR. An
archive year file now has its own limit: `doctor` warns (`ARCHIVE_SIZE`) from 700 KB and fails (`FILE_SIZE`) above
900 KB, and `keeptrack.py archive` and the web board's Archive (also the Done-lane button) check each year file before writing, on
every layout: a year that would pass 900 KB is held back (its items stay on the board, the other years are archived,
the message names what stayed), and past 700 KB the archive is written with a warning; `archive` exits 1 when no archive year was
written (everything was held back; a run that only saved proposal slimming says so and still exits 1), and `--dry-run` reports the same. A rename
(label, client, stage) that would push an archive year over 900 KB is refused with nothing written. `atomic_write` no longer turns `\n` into `\r\n` on Windows. Archive files load with
the board like every other file (cached by blob sha, downloaded again after each archive change); 900 KB is a chosen
margin (the real archive was 578 KB), not a GitHub limit, and the 5 MB board total still caps load cost. Only
`archive/<year>.json` gets the higher limit; any other file in `archive/` keeps 200 KB, and the web board's size bar no
longer tells people to archive when the archive is most of the total. `doctor`'s size checks run on split boards only. No
migration and no data change. Splitting a year into parts, and loading archives lazily, are follow-ups.

Kit v86: Companies follow-up, the review fixes for kit v84 (private-tasks card #281; v96 is the Archive view, card
#283). A client with no people, no company record (stage, owner, domain, notes or north star), no files and no
projects, such as a "General" bucket for tasks, is left out of Companies and the company pipeline; it stays a client
for tasks and the client pills. The company record's menu reads "Show only this company" and "Copy company name".
`__proto__`, `constructor` and `prototype` are never created as a client or company name: every keeptrack.py save
refuses one that would store such a name in one more place than before (so any command, `init --client`, a proposal
accept or merge, `touch`/`sent --company` and `client-link` are covered), `import` skips them with a report line and
counts them in its summary, and a proposal that names one cannot be accepted on the page. client-rm and client-rename
OLD NEW only remove uses, so a bad name already on a board can be cleaned up. The page reads and creates `client_info` entries only as own properties and
refuses those names wherever it would create one. `clients` skips a record whose client or company is not text. A stored company stage the board no longer has counts as unset (the stage from its
people shows). `client-set --notes` with only whitespace clears the notes. `clients` prints every name through the
terminal guard and groups people by company once.

Kit v84: companies on the board, HubSpot style (private-tasks card #281). A company is every client name and every
person's company, once each. `client_info[<company>]` gains four optional fields: `stage` (one of `settings.stages`),
`owner` (a board member's login), `domain` and `notes`. Until a stage is set, a company shows the most advanced stage
among its people (a Lost person never outranks a live one; members' own records do not count). keeptrack.py:
`client-set NAME --stage --owner --domain --notes` (`""` clears; the stage and owner are checked), `clients` shows the
stage, owner and domain, `settings-set --rename-stage` renames company stages too, `member-rm` clears that member as
an owner, and `doctor` warns (CLIENT_RECORD) about an unknown stage or owner. Web board: a **Companies** tab between
People and Pipeline (stage, people, open tasks, the earliest next step among its people, last contact; search, stage
filter and client pills), the client drawer becomes the company record (stage, owner, domain, value from its people,
notes, people as rows, every person's contact log merged with Show more, open tasks; north star, projects and files as
before), company names link to it from person rows, pipeline cards and the person drawer, and **Pipeline** has a
People | Companies toggle (remembered in this browser) where dragging a company card sets the company's stage. No
migration; older kits and pages keep the new fields.

Kit v83: goals on the board (consulting card #189). A board can hold goals in `tasks.json` (`goals`: a title, a metric,
a target, the current value, a start and an end date, and a status of active, done or dropped), and a card links to one
with `goal`. keeptrack.py: `goals`, `goal`, `goal-add`, `goal-set`, `goal-remove`, `add --goal`, `task-set --goal`,
`list --goal REF|none`; `show` prints the card's goal; `doctor` warns about a bad goal entry (GOAL) and a card that links
to a goal that is not on the board (GOAL_MISSING). Web board: a Goals bar above the Kanban and List views shows each
active goal with its target, a progress bar (when the current value and the target are numbers), the days left and its
open cards; a click filters the board to that goal, and "No goal" to the open cards that link to none. Goals (in Filters and the board menus)
adds and edits goals, the card drawer has a Goal field, and Filters has a Goal filter. Older kits keep goals and card
links as they are. The page markup version is now 5 (new ids), so a cached older page reloads itself.

Kit v82: the email cleaner's last known gaps and false flags (email-to-tasks pack 1.5.1, private-tasks card #184).
`safe_view.py` models a hiding rule's sibling combinator (`img.g-img + div` hides only the `div` after that image),
counts an Outlook conditional comment only when its text is not also shown outside it, and orders rules by importance,
specificity and source order, so a later rule that surely hits an element wins and ordinary templates are not flagged.
A hiding rule under `@media` counts at 1440px and 1920px as well as 1200px; a phone-only rule still hides nothing. A
`var()`, `light-dark()` or `calc()` background is judged against every colour it may resolve to (custom properties
from style blocks and inline styles), and a colour it cannot work out (`color-mix()`, `oklch()`, `rgb(calc())`) makes
the message TooComplex. The `font` shorthand size, `-webkit-text-fill-color` and `zoom` are read; `filter`, `mask`,
`content-visibility`, `mix-blend-mode`, `-webkit-text-security`, `font-size-adjust`, `scale`, `translate`, matrix
transforms and large negative margins hide when their value may hide text. A `<dialog>` without `open`, `<datalist>`,
`<rp>` and a closed `<details>` (all but its `<summary>`) are hidden. Authentication-Results: quoted strings and comments
never hold a result, the authserv-id must be exactly `mx.google.com`, and a result is read only where it starts.
CSS nesting and quoted strings (`content:"/*"`) are read as a browser reads them, and a style block that only the
string scan finds (inside a comment, `<title>` or `<textarea>`) can add hiding rules but never visible ones.

Kit v81: the minor findings from the kit v71 reviews (private-tasks card #176). `list --sort score` and `list --links`
pass the whole printed line through the one-line guard, and a card link flattens a hand-edited number. The guard now
removes only control characters, line and paragraph separators, lone surrogates and bidi embeddings, overrides and
isolates, so a title with an emoji ZWJ sequence, an RTL mark or a soft hyphen prints as stored. A hosted `add` stores
the checked label names. `--recommend` with a Unicode digit (²) refuses cleanly. Hand-edited timestamps such as
`T24:00` or `+05:99` are refused alike in keeptrack.py and board.js (no lapse either side). A hosted board's URL has its
own variable, `BOARD_HOSTED_API`; a GitHub board refuses to send its token while a hosted board's variables are set. A
config above a board clone is skipped only for a clone this person trusts (its own keeptrack.py runs, or `use` named its
board); any other clone with `board/tasks.json` no longer overrides the trusted config. New `cleared-ack <id>`: a
person marks agent-cleared flags checked, so doctor stops showing them. Web board: "Accept all recommended" answers at
most 20 per run and leaves a question alone when its text, options or recommendation changed after the confirm; the
Review Inbox works out the board's zone and today once per render.

Kit v80: archive many Done cards without "Busy, try again" (private-tasks card #243), and a plain English section in
the card guide (card #171). On the web board, a quick Archive click made while another archive commit runs no longer
fails: the card leaves the board at once and waits, and every card that waited is archived in the next single commit.
The Undo toast puts back all the cards of that commit, and Ctrl+Z does the same. The Done lane has a new **Archive
all** button in its header: after a confirm step it archives every Done card that no agent holds, in one commit.
`board/CARDS.md` has a new section, "Write in plain, simple English": short active sentences in the spirit of
ASD-STE100, and a list of machine-written signs to remove.

Kit v79: email-to-tasks reads several mailboxes, locally or in the cloud (pack 1.5.0, private-tasks card #232; spec
`docs/specs/email-to-tasks-sources.md`). New config `sources`: up to three gog account aliases, in order. Before any
read the check proves each one (the alias is set on this runner, its login has `gmail.readonly` and no scope that can
change, send or delete mail), and every gog call names that one address with gog's `--readonly`, `--gmail-no-send`,
`--no-input` and an exact command allowlist. Each source keeps its own window in a v2 cursor; a run starts with the
source after the last one that had items, so one busy mailbox never starves another. `resolve.py` reads only the
mailbox an item's ref names, and refuses a ref whose mailbox the board's own install does not name, so a team board
set to `work` never reads Personal mail. New blocked codes: `setup-missing:sources`, `setup-missing:gog-aliases`,
`setup-missing:account-<alias>`, `setup-missing:readonly-<alias>`. The skill reports `source_<alias>=N`. An install
without `sources` behaves as 1.4.1.

Kit v78: a card's links and to-dos in one command (card #233). `add --link URL [TITLE]` (repeatable) puts links on a
new card in the same save as its `--todo` items; `todo-add ID -` and
`link ID -` read one item per line from stdin (a link line is the URL, a tab, then the title). Every item is checked
before anything is written, each command is one board commit with a history line per item, and a lost race still
merges three-way. The `board` skill, `CARDS.md` and the README say to build a card in one call.

Kit v77: an agent closes its own Review Inbox items once the owner settled them in a conversation (card #198).
`proposals -q TEXT` and `--by WHO` find items by title (or question) and by who added them (`createdBy`, whole or its
agent part). `proposal-answer <id> --via "<where>"` records the owner's answer to a question the same agent identity
asked; `proposal-ignore <id> --via "<where>" --reason "<one line>"` withdraws an item it added (a card proposal the
owner declined, a question no longer needed). Both are refused on an item another agent or a person added, on a
question whose `decider` is someone other than `BOARD_USER`, and without `BOARD_AGENT`; an approval of exact content
is never answered through `--via` (only withdrawn), and an agent never accepts a card. The item records `decision.relayed` (`for`, `via`, and the withdraw
`reason`, which the 30-day slim removes), the history says who it was for and where they said it, and the board page
shows "Answered by … for @owner, as they said in …" or "Withdrawn by … : reason". A person undoes either with Reopen
(`proposal-reopen`). Without `--via`, an agent run (`BOARD_AGENT` set, or a hosted identity with an agent id)
can no longer accept, merge or undo any proposal, nor ignore one another agent or a person added, nor reopen anything
but its own withdrawal of its own item (never one that records the owner's word: a `--via` decision, or an ignore made with `--attended`, which is recorded as `decision.attended`), unless the command carries the new `--attended` flag (a person drives the
session and named the item); the keeptrack skills' chat flow ("accept the ones I name") passes it. `--attended` is a per-command flag, never an environment variable, so an unattended routine, worker, automation or connector can never inherit it; `BOARD_ATTENDED` stays for heartbeats only and does not affect these decisions. It is still self-declared: it guards well-behaved unattended runs, not a prompt-injected agent in a chat. `createdBy` is always this run (a payload value is dropped). An agent run whose identity cannot be told apart from a person's is refused for these decisions: `BOARD_AGENT` with a person's hosted token (no agent id), or `BOARD_AGENT` with no `BOARD_USER`. `--via` is a plain
label, the owner must be a board member (stored as the member's own login; the hosted handle in hosted mode), and
`proposal-result` gives `relayed`.

Board page: search lists people in their own section above tasks (a number query still puts the numbered card
first).

Kit v76: the manual keeptrack-email skill reads mail the way email-to-tasks does (card #185). New `keeptrack.py
email-view` runs the automation's cleaner (`safe_view.py`, loaded by path through the pack's `resolve.py`, never a
copy) on one message: `gog gmail get <id> --json | keeptrack.py email-view` prints the canonical `rfc822:` key,
Gmail's sender checks, what hidden content was removed and the visible text inside a random untrusted fence; input it
cannot read prints only `Unreadable:` (exit 1), never the raw message. New `keeptrack.py email-search` runs gog's
search itself (the email-to-tasks check's own query plus exact board addresses) and prints only each message's id,
thread id, date and `sent|received`, where `sent` is Gmail's SENT label, never a From line: gog's raw search output
carries sender, subject and snippet, which would reach the agent before the cleaner. `safe_view.py` now turns U+2028,
U+2029, NEL and \x1c-\x1e into real line breaks (and spaces in headers), so they cannot fake a line inside the fence.
The skill gets the automation's "Always" rules word for word (payment or access changes get only the fixed "Possible
fraud: verify by phone" text; mail never sets its own urgency or legitimacy; a task or follow-up date needs
`dmarc=pass`; the hidden-content and sender-check sentences end the touch, or the proposal's reason with the Review
Inbox on) and never reads attachments. With a connector only (no gog) it says plainly what is not protected: the raw
message, hidden parts included, has already reached the assistant, so every message read that way, sent mail included
(a forged From can name the owner), is treated as unverified: contact history with "Gmail could not verify the sender
of this email.", no follow-up date and no task. The routine guide points at the same rules. The pack's `resolve.py`
now builds the view text in one `render()` that both use (pack 1.4.1, with the line-break change above). New behaviour
evals for the skill (`skills/keeptrack-email/evals/cases.json`: a hidden payment lure, a failed sender check beside a
verified follow-up, a connector-only message with a hidden instruction, an unverified sender with the Review Inbox on,
a forged From naming the owner, and a hostile snippet in raw search output) and tests for `email-view` and
`email-search`.

Board page: search finds clients and projects by name, in a new "Clients and projects" section above people and
tasks ("hurst col" finds the client, not only its cards). A result opens the client or project details.

Kit v75: email-to-tasks reads only what a person would see (card #182; pack 1.4.0). Phishing mail now hides
instructions for the AI that reads it: HTML comments, CSS-invisible text, encoded blobs, zero-width and Unicode tag
characters. `resolve.py --save` now keeps each message's headers only (`<id>.json`, no body) and writes a cleaned view
(`<id>.txt`, from the new `safe_view.py`): the HTML part first (what people see; a plain part behind it can hide
text), with comments, scripts and hidden elements (display:none, visibility:hidden, zero size or opacity, off-screen,
clipped, tiny or near-invisible text, hidden attributes, classes a style block hides) removed, invisible characters
(zero-width, bidi, variation selectors, blank fillers, Unicode tags) and encoded runs (long, line-wrapped base64,
hex) dropped, capped at 8000 characters; attachments and forwarded messages are never read, and crafted markup
cannot make it run long. It counts what it removed and shows Gmail's own SPF, DKIM and DMARC results (the topmost
header only; a sender can add its own). The sender's headers sit inside the untrusted fence with the text. The skill reads mail only from that view; mail never sets its own urgency or
legitimacy; a request to change payment or access details becomes contact history with a fixed "possible fraud:
verify by phone" line, never a task; a task needs `dmarc=pass`; hidden content and failed or missing sender checks are named in the proposal with fixed
sentences, which the board now accepts on metadata-only (unconfirmed) proposals too. New tests for each hiding method
and four behaviour evals (a hidden payment lure, a failed and an unverified sender check, the warnings on a
two-member board).

Board page and AUTOMATIONS.md (no version change): the automation switch keeps its own 44x26 size on phones (dialog and header buttons get a
44px minimum height), with a grey off track and a white knob; the details drawer drops the "Not installed" / "On" pill
when it shows a switch, as the rows do. The cloud runner is described as any scheduled agent (a Claude routine, a
Codex or Cursor scheduled task, or another), not only a Claude routine; a runner that cannot give each automation
exactly its approved connectors runs only automations that need none (relay's dispatcher enforces it, not the page).

Kit v74: one runner, a switch per automation (card #180; `board/kit/AUTOMATIONS.md`, "The board page"). The
Automations page lists one row per pack with an on/off switch; a row opens its details in a drawer, as a card does.
The switch writes the install register as the person (as `automation install --runner cloud`, `setup --runtime claude
--runner cloud` and `enable` would), with the pack digest computed in the browser from the pack's files in git; it asks
before it grants a read beyond the board, the network, a connector or a secret, and never reuses another person's or
another pack's old register. The panel at the top is the cloud runner: it reads `automation/runner.json` (relay 0.9.35's
`runner-status`) and shows a guided checklist of what the routine still lacks, including installs that wait for the
owner's allowlist entry (relay 0.9.35: the switch turns an automation on, and the owner's merge-gated entry,
pinned to the pack's digest, approves every run). New shared component `ui.toggle` (a labelled
switch). Review Inbox: a proposal's Markdown fields render as Markdown. No schema or data change.

Kit v73: automations learn where they run (`board/kit/AUTOMATIONS.md`, "Runners and needs"). A pack manifest may carry
an optional `requires` object: `runner` (`any`, `cloud` or `local`), the claude.ai `connectors` and the secret NAMES
(`secrets`) a runner must hold, and `check` (`script`, or `model` when the check itself needs a connector), with
per-runner `cloud` / `local` overrides. The built-in packs declare theirs (pack version 1.3.0): stale-cards-nudge and
notes-folder-to-tasks need nothing; email-to-tasks needs its gog login locally and the secret `GOG_HOME_ARCHIVE` in
the cloud. `automation install` and `setup` take `--runner cloud|local` (default `local`); setup checks each secret
name is set (never printing a value) and, on `cloud`, each connector is in `--connectors` or `KEEPTRACK_CONNECTORS`,
and blocks naming what is missing. New read-only `automation needs --json` and `automation due --json` (both
`[--runner R]`) give the relay dispatcher what it needs without writing anything; `automation tick --only <slug>
[--runner R] [--digest D]` ticks exactly one active install of the caller and records `last_started_at` each time it
checks. A plain `automation tick` runs `local` installs only. The throttle honours the committed `last_started_at` as
well as the local check time, so two runners cannot run one automation twice in one interval. A ready cloud install
has setup status `ready-cloud`, so a kit before v73 never runs it; every cloud tick records `last_started_at` and
keeps its scan position in the committed register (`scan_cursor`), so a fresh clone goes on where the last worker
stopped; `--digest` fails closed (empty, malformed, or without `--only`); setup refuses to move an install with a
current run to another runner; `needs` reports `check: model` for a pack with no check script. Pack fixes (card
#174): email-to-tasks `resolve.py` looks on the next page and then in the item's window before `not-found`, falls
back to a window search for an overlong page token (the check now emits a window ref instead of the bare key), has
one deadline for the whole run, and `--save` keeps each fetched message for step 3; notes-folder-to-tasks
`resolve.py` prints each note's text as one JSON string (U+2028, U+2029 and U+0085 escaped too), so a note cannot
fake the resolver's markers; `resolve.py --save` deletes its folder when Gmail fails part way, and searches each page
at most once; the email
evals and SETUP.md use `@example.com` addresses only. Built-in pack digests changed: reinstall and set up again
(`UPGRADING.md`, v73). No schema change, no migration.

Kit v72: the three built-in automation packs (stale-cards-nudge, notes-folder-to-tasks, email-to-tasks) are rebuilt
(pack version 1.2.0). Each SKILL.md gives numbered steps with exact commands, the proposal shape with its evidence and
stable keys, skip rules, and a failure path that ends in a Review Inbox question in the `CARDS.md` "always recommend"
form or a counted stop. Each SETUP.md gives a verify command and expected output for every need, per runtime. Checks
are stricter: stale-cards-nudge reads the local board through `keeptrack.py` (flat or split) and reports malformed cards
once a week; notes-folder-to-tasks skips hidden, lock and empty files, hashes normalised text, skips copies and adds
`lookback_days` (a note's age is its mtime, or its last commit in a git folder such as a cloned notes repo, never its
ctime, so a restore, a sync or a fresh clone does not import old notes; such notes are judged before they are read);
email-to-tasks never treats a board member as a contact, skips spam, trash, drafts and bulk categories,
can match mail you sent (`max_recipients`, `include_sent`) and blocks early when CRM mode is off or no contact has an
address. email-to-tasks and notes-folder-to-tasks ship a `resolve.py`: the agent maps item keys through it, so no mail
header and no file name is ever typed into a shell (email: one search of the exact page the check read, named by the
item's `ref`, and the `rfc822:` key hashed from gog's own JSON; notes: the resolver prints the note itself). Any other
text to hash goes through a quoted `<<'KT_TEXT'` heredoc, and stale-cards-nudge writes its proposal files the same way. Each pack ships `evals/cases.json`, behaviour tests run with `relay.py eval`; a wording change to a pack is
kept only after its evals pass (`AUTOMATIONS.md`, "Behaviour tests"; the create skill adds one to new packs, from
`references/evals_template.json`). `tests/test_automation_packs.py` checks every built-in pack's evals file and docs.
Security (#175): `automation install`, `setup`, `enable`, `disable`, `uninstall`, `check`, `tick`, `mark` and `dry-run` refuse an
`--owner` that is not the person running the command (case ignored); no admin override. Built-in pack digests changed:
each install must be reinstalled and set up again (`UPGRADING.md`, v72). No schema change, no migration.

Kit v71: comments and routine answers that need a person say whose view each point is and what it rests on.
`CARDS.md` ("Comments that need a person: always recommend") adds "Who it affects" (the two or three viewpoints the
choice touches, scored from what they would say, not from an opinion of the agent's own) and "What it rests on" (each
reason links its evidence, or says "judgement"); the recommendation names whose concern decides it. The template and
the good example show both. `routine-prompt.md` follows the rule and, when asked "what do you think" or for research,
a review or a choice, names the people whose view matters before it recommends.
Review Inbox (ideas from petekp/inbox (MIT)): an `ask.choose` question may name its **recommended option**
(`change.recommended`, an option key; `proposal-add --recommend <key, number or label>`; anything else is refused). The
web board shows it first, as the main button marked "Recommended" in words, with **Accept all recommended** (one confirm
that lists every question it will answer with its recommended option; then each answer is saved in turn as if picked by
hand, with the button and the queued items off until the run ends, and an item someone answered meanwhile is skipped) and
the key `r`; `proposal-answer --recommended` does the same from the CLI, and
`proposals` marks it. A pending question unanswered for `settings.inbox_lapse_days` (default 14, 0 = never;
`settings-set --inbox-lapse-days`) is **lapsed**: worked out when the board is read (on the board's clock), never
written. The wait runs from when the question last became pending (its newest reopen, else when it was added), counted in
days on the board's time zone; a question's `created` is now always the time it was added, so a payload cannot start or
stop its lapse clock. The board marks it and
has a "Lapsed questions" filter; `proposals --lapsed`, `list --attention` (one `lapsed question …` line each, only with no
card filter or project scope; with `--assignee`, the questions named for that person plus those any member answers) and
`proposal-result` (`lapsed`, `lapsed_days`) report it. Agents do not ask a lapsed or dismissed question again unless the
person brings it up (`CARDS.md`). A dismissed question now reads "Dismissed". Every press in the Inbox shows its result:
"Saving…" with the item's controls off (no double submit), then "✓ Approved" / "✓ Answered" on the item, or why it was not
saved, with what the person typed kept. Card and proposal titles, labels, reasons and other one-line fields refuse every line break Python's
`splitlines` knows (`add`, `task-set --title`, `label-add`, `proposal-add`), and `list` prints every title, id and
decider on one line, so no title or hand-edited file can add a line to its output. `PLUGIN.md` gains "What it runs, sends and changes". Optional fields only: no schema change, no migration, and no
new `min_kit` (an older page shows the options in their stored order and no lapse).

Fixes after the hosted adapter (#140): the installed app caches `storage-hosted.js` (shell cache v2), so it opens offline
again; "Sign in to a local hosted board" shows only on a local page; the `api.github.com` preconnect is back. CLI:
`claim --on-behalf-of` on a GitHub board now fails clearly instead of being ignored; `approve` help says hosted boards
only; an empty `BOARD_BACKEND` means github and a mistyped one is refused by name. No schema change.

Kit v70: an Automations page in the web board (header button, `#view=automations`). Each automation is a card with a
node diagram of what it does (schedule, what it reads, the no-AI check, the agent, the Review Inbox), its status and
the command for each next step. Manifests may carry an optional `flow` for that diagram; the built-in packs have one.
Built-in pack digests changed: reinstall any v69 install of them. No schema change.

CLI: inside a board repo clone, the clone's own git remote names the board. A `.keeptrack` or `.board` config in a
folder above the clone that names another board (for example one `use` wrote in the home folder) is now ignored there,
and `where` names the file it skipped. Before, it set `BOARD_REPO` and sent the clone's commands to that other board.
A parent config naming the clone's own board still applies, and outside board clones nothing changes. A claim taken in
such a clone before this change was recorded in `.keeptrack/claim.json`; finish or release it with the older kit, or
claim again. START.md no longer suggests running `use` in the home folder. No schema change.

Web board: split boards fetch uncached files in GraphQL batches, so a new browser needs fewer GitHub calls.
Files GitHub cannot return this way fall back to the existing REST read. No schema change.

Web board: live board data and sync status now appear before optional widgets finish loading. Widgets redraw the board
only when their layout changes; stale widget responses are discarded. Demo loading is unchanged. No schema change.

Web board: the **Archive** button on Done cards now takes the card off the board at once, instead of after GitHub
has the commit (about 2 to 3 seconds on a split board). If the archive does not happen, the card comes back and the
toast says why. Undo still shows once the archive has landed. No schema change.

`board/upgrade.py` without `--push`: the "BACKUP IS IN THIS CLONE ONLY" warning no longer shows when the backup branch
is already on origin (made by hand or by an earlier run) and was reused. No schema change.

Web board: **card links open at once** in a browser that has used the board before. The drawer opens from this
browser's saved copy and refreshes in place when the live sync lands; edits wait until then ("Syncing…"). Split boards
also remember their last sync (head, ETag, file list), so an unchanged board now costs one free conditional
call instead of five serial calls. Measured on a 192-card board at 250 ms per call: card link 1.86 s → 0.17 s, live sync
1.41 s → 0.40 s. Opening a card also shows the drawer before redrawing the board behind it. No schema change.

## Kit v69 — 2026-10-15

- Harden kit-update against symlink aliases; reserve complete automation batches atomically and release undelivered runs as failed. Hash item action keys, retain invalid/missing packs in list, and report mixed tick problems while allowing work (exit 0). Failed completion remains possible after pack loss.

Board owners can install, check and explicitly enable proposal-only automations. One cheap tick reserves work only
when a source has new items. Includes stale-card nudges, notes-folder tasks, exact-contact Gmail tasks, a setup guide
and a create-automation skill. Checks use bounded output, private state and digest-pinned access approval.
Nothing is installed, enabled or scheduled by upgrading. Own packs and runtime state are protected from kit updates.
No schema change to board data. Adds separate automation-install and generic seen-log records under automation/.

## Kit v68 — 2026-10-15

Card links from the web board and CLI now include `card=<id>` and keep `#N`. On a split board, a browser without
that card cached reads the root and card in parallel and opens a read-only drawer after those two reads. The full
sync refreshes it in place. Invalid, missing or mismatched cards fall back to the ordinary load; number-only links
still work. Preview data is never saved as a snapshot or used as a write baseline. No schema change.

## Kit v67 — 2026-10-15

New kit file **`board/upgrade.py`**: the whole board-kit upgrade in one command (Ollie, 15 Oct: agents slipped twice doing
it by hand in each board repo). Run it from the board repo's root: `python3 board/upgrade.py [--push]`. It refuses a
checkout with uncommitted changes, finds the base branch (origin's default, else master, else main), makes the backup
branch `backup/kit<old>-<date>` (reused when it is already there at the same commit, else `-2`, `-3`), and works in a new
git worktree on `kit-upgrade/v<N>` from `origin/<base>`, so the main checkout never changes. There it runs `kit-update`,
puts back the repo's own lines from the new optional, repo-owned **`board/upgrade-keep.txt`** (`<path> :: <regex>`; it
stops when the number of matching lines changes), prints the `UPGRADING.md` sections for each new version and the
commands in them to do by hand (it never runs a migration), and lists the `keeptrack.py` lines of the kit's
`templates/AGENTS.md` that the repo's `AGENTS.md` lacks (report only). When the repo has `relay/`, it also upgrades the
relay kit (`relay.py kit-update --into <worktree>`, or the older `--from` way before relay 0.9.24) and runs relay's
`kit-check`, `check` and `selftest`. Owner-only relay files are listed for the owner; only `--owner-files` (the owner's
yes) copies those the repo never changed, and the PR names each one. It commits only the paths an upgrade step wrote. Then the board checks (`py_compile`, `kit-check`, `doctor`, `list`), a commit
("Board kit vA -> vB", with `--trailer` lines), and with `--push` the push and a draft PR through `gh` (else it prints
the PR text). It never merges. After the merge, `python3 board/upgrade.py --after-merge` checks the upgrade commit is
on the base branch, runs `verify --against` the backup on the board as it was in that commit, and removes the worktree. The board-upgrade skill now uses it first and keeps the hand steps as the fallback.
No schema change.

## Kit v66 — 2026-10-15

Web board: **one Activity timeline in the card drawer** (Ollie, 15 Oct: "combine comments and history, GitHub combines
and it's easier to track changes"). The Comments and History sections are now one **Activity** section, like the
conversation on a GitHub pull request: newest first under the comment box, comments as full cards, and the card's
history entries (moves, claims, progress notes, ticks, waits, edits) as compact rows with an icon on a timeline line
between them. A run of more than five changes in a row shows the newest four and **Show N more changes**. The
**History** button in the section header hides or shows the history rows (one choice per browser, `kb_cm_hist`);
comments always show. The section count is still the number of comments.
**New while open** (Ollie, 15 Oct: "make it clear an update has happened"): the open drawer already re-read the board
every 10 seconds, but silently. Now a comment or change by someone else that arrives while the card is open gets a
**New** mark (comment cards also get an accent border), and while the Activity section is out of view a bar at the top
of the drawer says "N new updates on this card" with **Show**, which scrolls to the first new item. Your own changes
are never marked. Opening the card again clears the marks. People drawers in the CRM keep their own
History section. Also fixed: a project change made in the browser logged the old project name in the history. No
schema change.

## Kit v65 — 2026-10-15

Web board: **Archive from the Done lane** (Ollie, 15 Oct). Done cards, and Done rows in List, have an **Archive** button
next to Edit and Copy for agent. On desktop it shows when you point at the card (or tab to it); on phones and other
touch screens it always shows. One click archives the card with no dialog; the toast has **Undo**, which puts the card
back on the board. Not shown on read-only boards or while an agent holds the card. Nothing is deleted: Search with
Include archive still finds and restores the card later. No bulk "archive all done" button: Settings → Board → Archive
already archives Done cards older than the board's limit. No schema change.

## Kit v64 — 2026-10-15

**Pending review** column: finished work that waits on a person's decision is no longer closed (Ollie, 15 Oct: a
research card went to Done with nothing decided).
- **keeptrack.py:** new `review ID --note "..." [--who LOGIN]`. Like `done` it needs a note, refuses open to-dos and
  ends the claim (and any wait) with a run record; unlike `done` the card stays open in the **Pending review** column
  (`pending-review`, after In progress; added the first time, so no migration) and the note is posted as a comment that
  @mentions who decides (default: the first assignee). `--note -` reads stdin. New boards get the column.
- **Web board:** the Today pulse shows a "to decide" count (cards in Pending review) when the board has the column.
- **CARDS.md:** new section "Done, Pending review or waiting". The board skill, README, routine prompt and AGENTS
  template say when to use `review` instead of `done`.
- No schema change.

## Kit v63 — 2026-10-15

Web board: the lane's add bar loses the pencil button, which did the same as Add. **Add** now adds the card and opens it
in the card drawer (with an empty box it asks for the title first), like Shift+Enter and the lane's ＋. **Enter** in the
box is still quick add: a title-only card that does not open. No schema migration.

## Kit v62 — 2026-10-15

Readable cards: Markdown in descriptions and comments, and comments that recommend a way forward.
- **Web board:** card descriptions and comments (also CRM touches) show as Markdown: `##` headings, `-` and `1.`
  lists (nested by indent), `- [ ]` / `- [x]` tick boxes, `|` tables, `>` quotes, fenced code, `---`, `**bold**`,
  `*italic*`, `~~strike~~` and `` `code` ``, with the existing links, `@mentions` and `#12`. It is a small built-in
  renderer that builds DOM nodes, never HTML, so no new library and no change to the page's security policy.
  **Raw** next to **Edit** shows the saved text (one choice per browser, `kb_md_raw`, for descriptions and comments).
  The description editor has **Write** and **Preview** tabs and a small toolbar (bold, italic, heading, lists, tick
  box, quote, code, link; Ctrl/Cmd+B and +I). Card faces and lists show the words without the marks.
  Under a comment, **Add to card links** puts each page the comment links to into the card's links with one tap
  (pages the card already links and this board's own cards are skipped). Links to other pages open in a new tab.
- **keeptrack.py:** `-` as `comment`'s text, `add --details`, `task-set --details` or `task-set --add-details` reads
  the text from stdin, so an agent can write multi-line Markdown with no shell quoting.
- **CARDS.md:** new sections "Format the text (Markdown)" and "Comments that need a person: always recommend": what
  waits and why, 2-4 options each with a score out of 10, the recommendation and its reason, and the next step. The
  board skill, plugin skill, routine prompt, AGENTS template and the "Copy for Codex" brief point to it.
- No schema change. Older pages show the same text as plain text.

## Kit v61 — 2026-10-15

Web board: a new card uses the card drawer, the same form as every other card. The v59 **New card** form is gone. The
lane's pencil, Shift+Enter, Add with an empty box, the lane's ＋ and the phone ＋ now save the card with its title and
open it in the drawer, where you add the details, client, project, priority, due date, labels, checklist and links.
With no title typed yet, a short prompt asks for one first. Quick add (type a title, press Enter) does not change.
No schema migration.

## Kit v60 — 2026-10-15

Backlog auto-research, a board setting that is off by default. When it is on, the relay dispatcher (relay 0.9.16 or
later) picks **bare** Backlog cards and an agent adds details, links and to-dos, posts one comment with what it found
and the questions it could not answer, and labels the card `researched`. The agent never moves, approves, claims or
retitles a card, and never replaces text a person wrote.
- `settings.backlog_research`: `{ "enabled": true, "per_run": 2 }`. Only `"enabled": true` turns it on; `per_run`
  (1-10, default 2) is how many cards one dispatcher run researches. Set it with `keeptrack.py settings-set
  --backlog-research on|off [--research-per-run N]`, or in the web board: Settings → Board → Backlog auto-research.
- A **bare** card has no to-dos, no links and details shorter than 120 characters (`board/CARDS.md`, tests 2-4).
  `keeptrack.py list --bare` lists them. Cards labelled `researched`, `researching`, `no-research`, `needs-human` or
  `held` are never picked; put `no-research` on a card to keep agents off it.
- `keeptrack.py research-lock '#N'` adds the label `researching` (the research run's lock; a claim would move the card)
  only when the setting is on and the card may still be researched. Of two dispatchers, only one gets the lock.
- `keeptrack.py research-suggest '#N' (--project P [--client C] | --ask) --reason R`: a researched card with no project
  goes to the Review Inbox (one item per card at a time). With `--project` (an exact open project), a suggestion that sets the client and project when a person accepts it (never a different client than the card has);
  with `--ask`, a question "Which client and project?". It never sets them itself. Needs split storage (the Inbox).
- `keeptrack.py task-set '#N' --add-details "<text>"` adds text below the current details (a blank line between) and
  never replaces them.
- No schema migration. Older kits and pages ignore the setting.
## Kit v59 — 2026-10-15

Web board: adding a task can open a **New card** form with every field a good card needs (`board/CARDS.md`): title,
details, column, client, project, priority, due date, assignee, labels, checklist (one step per line) and links (one
per line, `Title | URL`). The lane's pencil button, Shift+Enter in the lane's box, Add with an empty box, the lane's
＋ and the phone ＋ open it. Nothing is saved until **Add card**; a bad link line or an empty title keeps the form open
with a message. Quick add stays: type a title and press Enter (or Add) for a title-only card, as before. A new client
or label typed in the form joins the board's lists. No schema migration.

## Kit v58 — 2026-10-14

Web board: the bell opens **New for you**, a list of every card with news for you, newest first. Each row shows the
card, the newest new comment (with an "@ you" marker when it mentions you) and up to three new changes. A row opens
the card and marks it read. The footer has "Filter the board" (the old bell action: show only these cards) and "Mark
all as read". No schema migration.

## Kit v57 — 2026-10-14

Web board: the bell in the header counts only news from other people. Changes logged by your own agents
(`<agent>@<you>`, for example `claude@you`) are your work, so they no longer mark a card as new; a comment from one of
your agents counts only when it @mentions you (a question or a hand-back). Other people's changes and their agents'
changes still count. Before, one busy agent of yours could push the bell to 99+. No schema migration.

## Kit v56 — 2026-10-14

Card numbers are links. `keeptrack.py card-link '#N'` prints `[#N](<card link>) Title`; `show` prints the card's
`link:`, `add` and `todo-move` print it after `added #N`, and `list --links` adds it to each line. The board and
keeptrack skills, routine prompt, AGENTS.md template, README agent protocol and `board/CARDS.md` tell agents to write
every card number they name as a Markdown link. Web board: plain `#12` links carry the card's real address, Markdown
links show as their label (a card of this board opens in place), and the card menu copies `[#N](link)`. No schema
migration.

## Kit v55 — 2026-10-14

What a good card is. New `board/CARDS.md` (shipped to every board): the five tests of a good card, a bad card
and the same card written well, and how to put every PR, issue, document, folder and web page a card mentions in its
links section. The board, board-admin, keeptrack, keeptrack-notes and onboard-keeptrack skills, the routine prompt,
the AGENTS.md template, the README agent protocol and `docs/help/tasks.md` point at it. No schema migration.

The entries below were merged before v55 and were listed under Unreleased; v55 is the first kit version that
names them.

Web board: an **@Mentions** view, between Kanban and List. It lists every comment that
mentions you (`@` + your GitHub username in Settings), newest first, with the card, its description and the comment.
Your own comments are left out, the filters apply, and "New" marks comments since you last opened the card. A row
opens the card and scrolls to that comment, highlighted for a moment. Today shows an **@Mentions** tile when you have
any. Mentions stay out of the Review Inbox, which is for proposed changes only. No schema migration.

Web board: search puts a numbered card first. Type `26` or `#26` and card #26 is the top result, then cards whose
number starts with 26, then the other matches. No schema migration.

Web board: **Prep for call** on Today. Select a teammate and the board shows a brief for the call from board data
only: goals, "discuss with" cards, waits, overdue or stuck work, comments where you asked each other something this
week, shared cards, work done in the last 7 days and the Review Inbox count. **Copy brief** and **Copy for AI** copy
it as text. No network calls, no schema migration.

Web board: a **Pull requests** panel (header button, shown when a card links a pull request). It reads each linked
PR's state with the board login when opened (one batched GraphQL query, cached for two minutes, reads only), lists
what waits on you first, flags merged PRs on cards that are not Done as "can be finished" (it never moves the card),
and says "unknown" for a PR it cannot read. A relay-kit bar, like the board-kit bar, offers the upgrade owner one
"Make the relay update card" when the repo's `relay/KIT_VERSION` is older than the published relay kit
(`settings.relay_kit_source`, default `rain-ventures-ai/keeptrack-relay`). No schema migration.

Cards can run after other cards: an optional `after` list of card ids. `task-set ID --after '#62'` (repeatable),
`--not-after '#62'` and `--no-after`, and `add --after`, check that each card exists and refuse the card itself and
loops. `show` and `list` show the links and their state (an archived card counts as done only if it was Done; else
it is missing), the web board shows "after #62" chips on the card and a Runs after line in its details, proposals may
set `after`, and `doctor` checks it (`AFTER`, warning `AFTER_MISSING`). A hint and a gate, never a trigger: nothing
moves a card. No schema migration; older kits keep the field.

Web board: the card's **Client and project** picker has a search box. It narrows both lists with the board search
(MiniSearch: word starts and small typos) plus a plain "contains" match. A client also matches by its project names,
and with a search the project list covers every client. No schema migration.

## Kit v54 — 2026-10-14

Moved work is never lost. `todo-move ID N [--title] [--details]` moves an open to-do to a new follow-up card in one
save: the card goes to Backlog with the same client, project, labels, priority and assignees, the to-do as its
checklist; both cards get a link to the other ("Follow-up #N", "Split from #M") and a `related` relation with `from`
(the original card's id); the to-do is reworded "Moved to #N (t_id): ..." and ticked; both cards get a comment.
`relate A B --kind follow-up` links an existing card as A's follow-up, and `related` shows "Follow-up #N" / "Split
from #M". `done` and `move ... done` check every "Moved to #N (t_id)" to-do: a missing link is added, and a card on
neither the board nor the archive refuses (`done --cancel` only warns). The web board shows "Follow-up #N" / "From #M" chips on the card, Follow-up and Split from rows in Related
cards, and a "Move to a new card" action on each open to-do in the drawer. No schema migration.

## Kit v53 — 2026-10-14

Card dependency (`after`) follow-ups. The web board shows a link to a card that is not on the board as "unknown" until
the archive is loaded, then done, cancelled (an archived cancelled card), archived without Done or missing; before, an
archived Done card showed as an amber "missing" chip. Review Inbox Accept refuses `after` links to a card on neither
the board nor its archive, and links that make a loop, like `keeptrack.py` (the card itself is dropped). `doctor` checks `after` against card ids
only (a person's or project's id is `AFTER_MISSING`). No schema migration.

## Kit v52 — 2026-10-14

Similar cards: adding a card never stops, and close cards are marked as possible duplicates or additions on both
cards (`related`). New `similar`, `related`, `relate`, `unrelate` and `merge-card` (merge, then archive). The web board
shows the mark on the card and Merge, Link and Not related in the drawer. A pending new-task Inbox item checks open
cards again when shown, so a card added after the item was proposed shows as a possible duplicate. Shared scoring with a
Python/JS parity test. Pending Inbox items also check each other (similar new-task items show as possible
duplicates). Today Inbox rows show a short summary and "N from this person this day" for separate emails from one
person on one day; the email skill groups a person's emails of the day into one touch. Inbox cards say what Accept
does (create a task, add a CRM log entry, edit) and name the button after it. Today's Tasks due uses the Schedule
rows, grouped Overdue, Today, Later this week and Next week (closed), with "Show full schedule". No schema migration.

## Kit v51 — 2026-10-13

The heartbeat hook refreshes only its own agent's claims; re-claiming an attended claim unattended counts
against `max_agent_claims`; the "limit full" note prints once. Emails are ASCII only (CLI and web board).
Text cleaning keeps ZWJ emoji sequences whole, and `person` output is cleaned. A non-object contact no longer
crashes `today`, `people` or `doctor` (`PERSON_NOT_OBJECT`); `person-add`/`person-set` warn on a shared login.
No schema migration.

## Kit v50 — 2026-10-13

CLI `list --sort score|priority` exposes estimates, derived score and board-wide rank.
`priority-move` moves a task before/after another task or to the top/bottom, preserving
Kanban ranks and retrying the intent against the latest whole-board commit.
The web board keeps selected filters, layout and ordering in shareable URLs across
reloads and upgrades; browser Back/Forward restores them without carrying secrets.
No schema migration or automatic board data changes.

## Kit v49 — 2026-10-13

Optional Prioritise layout in List: inline value/effort, derived score, independent board-wide manual
ranking, and mobile controls. Standard List now honours its selected sort. Scoring fields are additive,
preserved through CLI edits, proposals and archiving; disabling the layout leaves board data intact.

## Kit v48 — 2026-10-13

- Added owner-bound `checkpoint show|save` for registered routines: privacy-safe typed progress, compare-and-save,
  active-run and board binding checks, immutable processed message keys and fixed-window resume. Partial/failed
  attempts retain the last successful window. Multiple mailboxes keep independent account state; legacy history is preserved.
- No board schema migration or automatic Review Inbox decisions.

## Web board

- **2026-10-25** — Comment activity builds links only for cards with comments in range. Copied Markdown keeps
  comment links ahead of the comment text and escapes older comment keys safely, including parentheses.

- **2026-10-24** — Comment entries in Activity include **Open comment**, which opens and highlights that comment in
  its card. The link can be bookmarked, opened in another tab, or copied with Activity as Markdown. Existing comments,
  including those without an ID, work without a migration.

- **2026-10-12** — The task drawer groups Status with Priority and Due date with Waiting for, while People, Labels and
  Client & project keep the full width. Waiting for opens a focused phone-safe sheet, and Client & project opens a
  linked picker with wrapping names instead of two cramped permanent rows.

- **2026-10-12** — Kit v46: each browser tab stays on the board it opened: switching boards in another tab can no
  longer make this tab save into the wrong repo. A board whose `settings.min_kit` is newer than the page is read-only, with a
  banner; archiving, restoring from the archive and Inbox decisions check it on the board they re-read too. A drop
  next to two cards with equal ranks lands just above them, not at the top of the column. The agent-claim limit, and whether a cleared wait may restart a blocked claim, are decided on the board as it
  is saved, with a whole-board commit. Accepting a Review Inbox proposal re-checks its field allow-list and value types,
  the same checks as `keeptrack.py`. The page has a Content-Security-Policy (GitHub's API, cron-job.org and Open-Meteo
  only; the bootstrap runs its scripts from `blob:` URLs). "Copy settings code" and "Copy setup link" leave tokens and
  keys out unless "Include tokens and keys" is ticked. Undo still keeps 20 changes in this tab, but stores at most the
  newest 5 for the next visit, and only while they fit in about 1 MB.

- **2026-10-12** — Inbox questions closed with `proposal-done --not-acted` show "Closed without acting by …" (kit v45).

- **2026-10-12** — Kanban cards show compact relative creation and last-activity ages, progressing from hours through
  days, weeks, months and years, with exact timestamps on hover. Activity includes task edits, comments, history and
  agent runs.

- **2026-10-12** — Mobile Find results keep the full height of wrapped titles and metadata when the on-screen keyboard
  reduces the available space, scrolling the result list instead of overlapping adjacent rows.

- **2026-10-12** — Review Inbox questions (kit v44): Choose, Approve and Question items show the question, its links
  and answer buttons in the Inbox and in Today's review, with an optional note, "Who answers" for a named person,
  Dismiss, and Change answer (Undo) until the agent has acted. Answers write only the question's file. The Inbox is
  always on for split boards; the Settings switch is gone.

- **2026-10-12** — Waiting-for: tasks can be marked as waiting on someone or something, with an optional member and
  chase day, from a Waiting row in the task drawer. Cards show a "waiting on .., Nd" chip that turns amber once the
  chase day has passed (and "waiting on you" on your own waits), a Waiting filter, and Needs attention includes waits
  due for a chase. Assign to Claude and `@claude` are off while a task waits. The page keeps `waiting`,
  `agent_cleared` and `settings.min_kit` on save, and merges `min_kit` as a maximum.

- **2026-10-12** — Today expands Inbox evidence and proposed changes inline, with explicit Accept and Ignore
  actions and Undo. Successful decisions refill a stable board-scoped queue while retaining order, reading position,
  focus and other expanded reviews. Failed saves and changed evidence never advance or silently accept a proposal.
  Existing-task updates show `Updates #N`; genuine other duplicate candidates still require edit/merge review.

- **2026-10-12** — The full Review Inbox uses clearer proposal summaries, source context, grouped changes and
  restrained decision controls, with responsive light/dark styling and visual QA coverage. No proposal decisions
  or board records are changed by this presentation update.

- **2026-10-12** — Today previews Inbox proposals with Review-only cards, source/type and duplicate warnings;
  decisions stay in the full Inbox after evidence review. Shareable links reopen views, settings sections and utility
  screens without carrying tokens. Task cards open with one click/tap or Enter/Space while embedded controls, selection
  and drag/hold gestures stay independent; an opening double-click cannot accidentally dismiss the drawer backdrop.

- **2026-10-12** — Review Inbox: a header Inbox button with a pending count (only when the board turns it on) opens a
  review view grouped by source and run, with filters, current-against-proposed values, Accept, Edit & accept, Merge,
  Ignore, Leave pending, Undo and Reopen, keyboard keys and a phone layout. Settings → Board has the switch.

- **2026-10-12** — Weather widgets offer explicit approximate browser location, with permission/failure guidance,
  rounded local coordinates, per-board/widget overrides and configured-city fallback. No automatic location requests,
  background tracking or GitHub location writes; fixed-city widgets remain supported.

- **2026-10-12** — Routine reports distinguish recorded setup, observed completion and unfinished attempts, with
  source/scope/management details and local-time display. A configurable routine setup form copies safe, board-scoped
  prompts without scheduling work. Members can explicitly link their own companies, protected from removal while
  linked. Double-clicking outside a task drawer closes it through the normal save/cleanup path.

- **2026-10-12** — Task Contacts suggests existing CRM people while typing, with keyboard and touch selection,
  stable CRM references and duplicate prevention. Individual tasks can be archived without losing their details,
  checklist, comments or history, then found and restored through Search.

- **2026-10-12** — Board-owned Today widgets and per-board browser appearance are opt-in. Search now finds Help,
  agent setup, connections and appearance settings, and can switch built-in themes while respecting the active board profile.

- **2026-10-12** — The hosted board is an installable PWA. Each repo/branch/path combination has a separate app identity, launch URL, name, colour and generated initials icon, so several boards can be installed together. The service worker caches the app shell for offline startup and keeps phone notification taps tied to the originating board.

## Schema versions

### Schema 4 (split storage)

- **2026-10-08** — Schema 4 introduced with kit v8 ([#11](https://github.com/rain-ventures-ai/keeptrack/pull/11)): `layout: "split"`, per-card `cards/*.json`, per-person `people/*.json`, `rank` on cards, `verify` and `doctor` for split boards.
- **2026-10-09** — Kit v17 ([#45](https://github.com/rain-ventures-ai/keeptrack/pull/45)): optional `projects/*.json`, client `north_star` in `client_info`, optional `project` on tasks, optional `github` on CRM people; `doctor` warnings `MEMBER_NO_PERSON` and `PROJECT`.

### Schema 3 (monolithic)

- **2026-10-08** — Schema 3 with kit v6–v7: single `tasks.json` holds `tasks` and `contacts`; onboarding and `import` (kit v7).

### Schema 2

- **2026-10-08** — Schema 2 with kit v1–v5: `keeptrack.py` kit commands (`kit-check`, `kit-update`, `migrate`), `init`, multi-repo `use` / `where`, rename from `board.py` to `keeptrack.py` (kit v5).

## Kit versions

### [47] — 2026-10-12

- `archive --done-days` (a one-off value) no longer shortens how long an unacted answer is kept; the board's
  `archive.done_days` decides.
- `proposal-done` (with or without `--not-acted`) by a person is refused unless they are the question's `decider`
  (when one is set). `proposal-ignore --reason` lines start with `ignored: `, and slimming removes the reason.
- Slimming after 30 days also removes the `proposal-done --note` text from `decision.done` and its history line.
- The hints after a rejection, a missing hash or a changed hash name `--not-acted --answer-id <answer_id>`.

### [46] — 2026-10-12

- `settings.min_kit` now prevents: `keeptrack.py` refuses to write a board whose `min_kit` is an integer above its
  `KIT_VERSION`, and says to run `kit-update`. Reads, `import`/`migrate`/`archive --dry-run` and plain `doctor` still
  work; `doctor --fix` writes nothing on such a board. A missing or non-integer value never blocks. A typo cannot lock
  every tool out: `settings-set --min-kit N` (on its own) may lower a stored value above the published kit to at most this
  kit and never below what the board's cards and questions need, and `doctor --fix` lowers it to the published kit. A
  value within the published kit (or when the kit cannot be fetched) is a real newer kit, and both refuse.
- `kit-update` and `kit-check` take the manifest and every file from one commit of the kit (raw at that sha, or a git
  clone checked out at it). `kit-update` checks that the fetched `keeptrack.py` is the release the manifest names,
  refuses a downgrade unless `--allow-downgrade` is given, and never writes or removes board data (`tasks.json`,
  `cards/`, `people/`, `projects/`, `proposals/`, `archive/`). A failing `BOARD_KIT_URL` stops with an error instead of
  falling back to the official kit. `kit-check` warns about template drift in `AGENTS.md` (rule 1 on split boards
  must name `cards/`, `people/` and each of `projects/`, `proposals/` and `archive/` the repo has, in any wording;
  heartbeat minutes), and the upgrade card links `blob/main`.
- `.board-claim.json` records each claimed card with its session, so two sessions in one clone keep separate claims.
  With `--session` or `BOARD_SESSION`, a run owns only that session's claims (a run whose id changed since the claim
  is told to rerun with the id it claimed with). Every rewrite of the record re-reads it
  under a lock and changes only that command's own cards, written atomically. Each entry keeps a hash of the Claude
  Code session that claimed it (`claimant`) and its own beat time (`beat_at`): the automatic heartbeat beats only its
  own Claude session's cards (entries without a claimant, and a hook that cannot name its session, beat as before;
  only `BOARD_SESSION`'s cards when the hook has it set), and a failed beat is tried again about a minute later, not
  at every tool call. `release`, `done` and `unwait` forget the local claim only after the save worked.
- `add` and `kit-check --card` print the #number the card has after saving; before, a save that lost a race could print
  a number that belonged to someone else's card.
- Ranks appended to a column get a short random tail, so concurrent saves no longer create `DUPLICATE_RANK`, and
  `move --before`/`--after` next to two equal ranks no longer crashes: the card gets a rank just below the pair, above
  the card before it, not the top of the column. `doctor --fix` breaks only the duplicate-rank
  ties, giving the later card of a tie a new rank between its neighbours; every other card keeps its rank and order.
- `proposal-accept` and `proposal-merge` re-check the stored change against the field allow-list, so a hand-written
  proposal cannot set `claim`, `num` or `waiting`. The web page now runs the same value checks; shared cases in
  `tests/fixtures/proposal-change-cases.json`.
- GitHub rate limits (403/429) are retried with a short back-off and reported as rate limited, not as a token without
  write access. On the one-file save, a 422 that is not a sha mismatch is reported instead of retried.
- Plugin `keeptrack` skill: the v43 waiting-for rules (`wait`; never `unwait` a wait you did not set or one on someone
  else), the 15-minute heartbeat with the 30-minute stale default, and `done --cancel`. The Codex and Cursor plugin
  manifests carry the same version as the Claude plugin (0.46.0). The `AGENTS.md` template's rule 1 names every board
  JSON file, rule 3 gives the 15-minute heartbeat, and its `wait` line warns against `unwait`.
- Tests: shared `merge3` cases (`tests/fixtures/merge3-cases.json`) run through both `keeptrack.py` and `board.js`; the
  key rules are checked in both board skills; frozen board `v4_kit46`. No schema migration.

### [45] — 2026-10-12

- `proposal-done --not-acted --answer-id <id> [--note]` closes an answered question without acting (`decision.done.acted: false`), so
  a rejected approval or a changed content hash no longer stays open for ever.
- An answered question that is not done is kept whole only for `archive.done_days`; after that it is slimmed and
  archived like other decided items.
- `proposal-done` refuses an `ask.approve` with no `content_hash` (it no longer skips the check).
- The unknown-kind error lists every kind, including `ask.*`.
- Docs: "the agent that asked" is the same `BOARD_AGENT@BOARD_USER`, not one session.

### [44] — 2026-10-12

- The Review Inbox is always on for split-storage boards; `settings.review_inbox` is no longer read. `settings` still
  prints `review_inbox.enabled: true` (or `false (needs split storage …)`) for older skill copies, and
  `settings-set review_inbox.enabled true` is a no-op (`false` is refused). New boards get no `review_inbox` setting.
- Questions: `ask.choose`, `ask.approve` and `ask.question` items, with status `answered`. `proposal-answer` (a person
  only, and only the item's `decider` when set), `proposal-result` (the asking agent reads its own answer),
  `proposal-done` (once, just before acting; an approval needs the matching `--content-hash`), `proposals --mine`
  and `--status answered`. `proposal-reopen` returns an answer not yet acted on to pending. Accept and merge refuse
  questions. The first question raises `settings.min_kit` to 44, and `doctor` reports `MIN_KIT_LOWERED` below that.

### [43] — 2026-10-12

- Waiting-for: `wait ID --on "text" [--who p_id|login] [--nudge +3|date] [--note ..]` parks a card on a person or an
  event; `unwait ID --note ".."` ends it, and so do `done` and `move ID done` (history keeps it). A waiting card is not
  claimable: `claim` refuses it and `next` skips it, and `--force` does not change that. `wait` blocks a running claim
  of its own session or a person's (`blocked_by_wait`); such a claim is live for `release`, and `heartbeat --status
  running` is refused while the card waits. `unwait` runs a young blocked claim again (within `max_agent_claims`) and
  releases a stale one to To do. An agent run ends only a wait it set in the same session that names nobody else.
  Overrides are recorded on the card in `agent_cleared` (newest 20).
- `today` has a CHASE NOW group and a count of other waits; `list --waiting`, `--waiting-on me|login|p_id`, a
  `[waiting: ..]` suffix, and `--attention` includes waits due for a chase. `people` shows `[waiting on them: n]` and
  `person` a "Waiting on them" list. `settings.waiting_days` (default 7, 0 = off) sets the chase day when there is no
  nudge. The single-task `archive` refuses a waiting card.
- `settings.min_kit`: set to 43 by the first `wait`, merged as a maximum. `KIT_VERSION` constant in `keeptrack.py`;
  `doctor` warns `KIT_OLD`, `MIN_KIT_LOWERED`, `CLAIM_BLOCKED` and `AGENT_CLEARED`; `settings-set --min-kit` accepts
  only a value between the stored one and this kit's version.
- Web board: a "waiting on .., Nd" chip (amber once the chase day has passed), a Waiting row in the task drawer, a
  Waiting filter, and Assign to Claude / `@claude` are off on a waiting card. No schema migration.

### [42] — 2026-10-12

- Review Inbox: agents and routines can propose a new task, a task change, a new or changed CRM person, or a contact
  interaction or follow-up. Proposals live in `board/proposals/<id>.json` (split storage only) and are never live
  records. New CLI commands: `proposal-add`, `proposals`, `proposal-show`, `proposal-accept`, `proposal-merge`,
  `proposal-ignore`, `proposal-reopen`, `proposal-undo`. Accept, merge and ignore write the record and the decision in
  one commit and never apply a proposal twice; a changed target stops for review. Email proposals hold no summary or
  subject without `--recipients-confirmed`. Decided proposals are slimmed after 30 days and archived by the sweep.
- The meeting-notes and email skills and their routine guides write proposals when the board turns the Inbox on.
  The Inbox is off by default; turning it on does not create, change or start any routine or schedule.

### [41] — 2026-10-12

- `email-key --stdin` accepts bounded untrusted header input as data; the safely invoked positional form and canonical
  hashes remain compatible. Email skills and shared routine guidance prohibit header interpolation into shell/script text.
- No schema migration, email re-import, board widget installation or routine schedule changes are required.

### [40] — 2026-10-12

- Optional member `own_companies` records explicit identity links, not CRM-employer inference. CLI member-set supports
  repeatable link/unlink options; company/member removal guards and client renames preserve identity protection on retries.
- Doctor checks optional company links, and company/member listings explain linked identity. No schema migration,
  board data changes or routine provisioning is required for this upgrade.

### [39] — 2026-10-12

- Archive an individual task with `archive <id>`, regardless of its age or status, while retaining its complete record.
  Unfinished agent claims must be released or finished first. Existing bulk archive and restore workflows remain available.
- Task contact entries may include an optional `person_id` referencing an existing CRM person alongside compatible
  name, role, email and phone snapshots. No data migration is required.

### [38] — 2026-10-12

- Canonical email message keys deduplicate shared-board scans across members' mailboxes. Bind verified messages to
  existing contact history without changing its summary, stage or date; retry overlap checks after concurrent saves.

### [37] — 2026-10-12

- Protect board-member CRM records from deletion. Add a repo-owned routine register and structured start/finish reports
  with management location, connections, last attempt, last success and bounded run history.

### [36] — 2026-10-12

- Claim ownership follow-ups, from the adversarial review of v35. The local claim record is read once per command (kept across the save retries) instead of two or three times, and `session_for` no longer takes an unused card id. A record that git tracks is ignored with one stderr note, before the file is opened (a symlinked record is never followed, and a record git cannot vouch for is not trusted either), so a board writer who commits `.board-claim.json` cannot give every pulling clone a known session id (one `git ls-files` on the read, so one to three git calls per claim command and none per tool call; the heartbeat hook checks it once per beat; not for a `--file` board or outside a git repo). Writing the record at a board repo's root warns when `.gitignore` does not list it, but still writes it. A bare `heartbeat` (or `--status blocked`), `done` or `release` whose save loses a race re-runs on the newer board, so it can no longer land a `heartbeat_at` or status on another session's fresh claim of the card (`move ID done` re-runs the same way); the API save path is unchanged (a one-file contents PUT still fails when that card's file changed, and the git path when the branch moved). The web page computes the agent-limit busy list once per render instead of once per card, and evaluates it once per `@claude` comment. The board skill says the automatic heartbeat runs at most every 15 minutes, as the code does.

### [35] — 2026-10-11

- Claim ownership and launch checks, from the external review of private-tasks. `done`, `release` and `heartbeat` refuse a card whose claim belongs to another session; `--force` on them is only for a person's explicit say-so, and it overrides only the assignee check and another session's live claim. Releasing a stale, stuck or blocked claim works from any session. A session is identified by `--session`, `BOARD_SESSION`, `CLAUDE_SESSION_ID`, `CODEX_SESSION_ID`, or else the local claim record this clone wrote, so an attended session keeps its own card. A routine's `claim` replaces the web page's `pending-...` placeholder for the same agent and person without `--force`. `--force` no longer bypasses `settings.max_agent_claims`; the capacity refusal says to raise it or use `--attended`. The web page will not send a card to Claude when the board's agent limit is full, and its quick-assign button says why. The routine text no longer mentions `--force`.
- Done evidence and time zones, from the same review. `done` needs `--note` and refuses open checklist items. `done --cancel --note "why"` closes a card without finishing it and records `outcome: cancelled`; a normal done records `outcome: completed`, also in `last_run.outcome`. `show` prints the outcome, the web page shows a "cancelled" pill and includes it in Copy as Markdown and the copied agent instructions, and `move ID done` still works but warns about open to-dos. `--due today` / `+N`, the OVERDUE/TODAY flags and `today` use the acting member's time zone (then the kit owner's, then the first member's), falling back to the host clock when none is on record. `today` starts with `Today is YYYY-MM-DD (Zone)`.

### [34] — 2026-10-11

- Security: only the ONE CRM person with a board member's GitHub login counts as that member's own record. If two or more share it, all stay contacts (so a board writer can't hide real contacts from follow-ups by giving them a member's login) and `doctor` warns `MEMBER_PERSON_DUP`. It is decided from each person's own login, never its id. `person-add`/`person-set`/`person-rm`/`sent` label a member's record like `people` does; a missing id or a null `people[]` no longer breaks `today` or `doctor`. Same rule on the web board, including the "add yourself" nudge. Known limit: at most one contact per member login can be marked, and members come from `people[]`, which board writers can edit; such a contact still shows in People with a "Board member" pill. `person_line` now cleans every board field it prints. From the relay-merge review of private-tasks#32.

### [33] — 2026-10-11

- A CRM person whose GitHub login is a board member's is that member's own record, not a contact (worked out from `people[]`, nothing stored). `today` never lists it as a follow-up and `people`/`person` mark it "board member @login: own record, not a contact". The web board shows it as **You** (or **Board member**), puts you first in People, keeps members out of Today's follow-ups and the Pipeline, and "Copy for AI" says it is a member rather than asking for contact help.

### [32] — 2026-10-11

- Output hardening: the sanitizer and `EMAIL_RE` also cover U+2028/2029, U+2060-2064 and tag characters; `identity_line` shows only a valid time zone and addresses of 254 characters or fewer; `members` cleans the agents line; `set_identity` refuses a non-list `emails`. Claims: the local claim record is written after the save; reviving a stale, stuck or blocked claim (by heartbeat or by re-claiming it in the same session) respects `max_agent_claims`. The sanitizer and email check go by Unicode category (control, format, separators, private-use, unassigned, variation selectors, fillers); `members` shows only valid addresses and time zones. From the relay-merge review of private-tasks#28 (card #12 there).

### [31] — 2026-10-11

- Member records hold work email addresses only (onboarding, `me`, help, skills, AGENTS template). Board data printed to terminals and agents goes through one sanitizer (control, zero-width, bidi); `identity_line` shows only valid addresses; `here` labels the identity line as board data; `settings` shows the enforced limit. From the relay-merge review of private-tasks#28.

### [30] — 2026-10-11

- Security: an item id from board data is used as a file name only if it is a plain token, and local reads and writes refuse paths whose real location is outside the board folder (a `..` or a committed symlink), so a crafted id can't make keeptrack write elsewhere on a member's machine (`doctor`: `BAD_ID`). `here` strips control characters from the project name and error text. Found by an automated security review.

### [29] — 2026-10-11

- The agent claim limit holds when two sessions claim different cards at once: the claim saves through a commit that fails on any newer save, and the losing claim is checked again on the newer board. A bad `max_agent_claims` value is ignored with a `doctor` warning. Member identity output strips control characters; example addresses use example.com. Found by the relay-merge review of private-tasks#28.

### [28] — 2026-10-11

- A board member's record is their identity: optional `emails` (every address they use) and `timezone` on `people[]` entries. `member-add` / `member-set --email` (repeatable), `--remove-email`, `--timezone`; new `me`; `members`, `here` show it; `init --email --timezone` for the first person. Onboarding asks once. `doctor` checks the addresses (`MEMBER_EMAIL`) and warns `MEMBER_NO_PERSON` only while the CRM section is on, so the CRM person stays optional. Agents are told to keep the record current and to write cards someone can act on later.

### [27] — 2026-10-11

- `settings.max_agent_claims`: `claim` refuses an agent claim past the board's limit, checked in the same write, so racing sessions can't exceed it. Found by the relay simulation (three front doors at once reached 3 of 2). Attended and stale claims don't count.

### [26] — 2026-10-11

- Automatic heartbeats every 15 minutes (was 5). New `claim --attended` / `BOARD_ATTENDED=1` for sessions a person drives: no heartbeats, stale only after 12 hours. Python and the web board agree.

### [25] — 2026-10-11

- The trusted-config list is JSON, so a path cannot add entries; rerun `use` once ([#60](https://github.com/rain-ventures-ai/keeptrack/pull/60)).

### [24] — 2026-10-11

- Kit guides (`ROUTINE-SETUP.md`, `README.md`, `board-routine-setup` skill) and `keeptrack.py`'s new-board message use the web board's new Settings tabs: Preferences, Board, Connection, Agents & integrations. No data change. The web board itself was rebuilt on shared components (`board/ui.js`).

### [23] — 2026-10-10

- `links` lists people's email addresses; `keeptrack-search` searches their mail and handles vague questions with a file inventory. Configs are read only if `use` wrote them on this computer (`~/.config/keeptrack/trusted`); rerun `use` once.

### [22] — 2026-10-10

- Repo-aware keeptrack: personal per-folder config moves to `.keeptrack/` (git-ignored; legacy `.board/` still read), `use --project` sets a default project scope for `list`, `next`, `add` and `links`, `here` and a SessionStart hook give connected repos board context and stay silent elsewhere, the heartbeat hook no longer starts Python in untracked repos, the claim file is per repo, `help [topic]` groups every command. Alarm template matches its own issue by author. A committed or symlinked config is never trusted ([#58](https://github.com/rain-ventures-ai/keeptrack/pull/58)).

### [21] — 2026-10-10

- Visibility alarm: test mode, fuller exposure steps, repeat alarms comment ([#57](https://github.com/rain-ventures-ai/keeptrack/pull/57)).

### [20] — 2026-10-10

- `links` command and `keeptrack-search` skill: search what a client or project links to with the session's connectors ([#56](https://github.com/rain-ventures-ai/keeptrack/pull/56)).

### [19] — 2026-10-10

- Columns and labels can be managed from Settings and the CLI; saves merge three ways on a race (web and `keeptrack.py`, exit status 3 on a real clash); renames reach archive files; `task-rm`, `person-rm`, agents commands, `todo-edit`, `project-unlink`, `client-unlink`, `list --label`; `verify` fix for large single-file boards; optional visibility-alarm workflow ([#42](https://github.com/rain-ventures-ai/keeptrack/issues/42), [#51](https://github.com/rain-ventures-ai/keeptrack/issues/51)).

### [18] — 2026-10-10

- Board administration from the CLI (labels, clients, members, settings, wider `task-set`), `board-admin` skill, `verify` on split boards ([#52](https://github.com/rain-ventures-ai/keeptrack/pull/52)).

### [17] — 2026-10-09

- Lightweight CRM projects, client north stars, board-member `github` on people ([#45](https://github.com/rain-ventures-ai/keeptrack/pull/45)).

### [16] — 2026-10-09

- `keeptrack-email` skill and contact-email reconciliation routine.

### [15] — 2026-10-09

- Multiple labelled emails/phones per person; profile vs file/folder resources ([#38](https://github.com/rain-ventures-ai/keeptrack/pull/38)).

### [14] — 2026-10-09

- Meeting-notes routine: verified legacy import, named non-board owners ([#35](https://github.com/rain-ventures-ai/keeptrack/pull/35)).

### [13] — 2026-10-09

- Meeting-notes rolling lookback and ingestion log ([#33](https://github.com/rain-ventures-ai/keeptrack/pull/33)).

### [12] — 2026-10-09

- `keeptrack-notes` recurring import guide ([#31](https://github.com/rain-ventures-ai/keeptrack/pull/31)).

### [11] — 2026-10-09

- `onboard-keeptrack` skill rename; new boards default to schema 4 split ([#29](https://github.com/rain-ventures-ai/keeptrack/pull/29)).

### [10] — 2026-10-09

- Onboarding handoff from web setup ([#21](https://github.com/rain-ventures-ai/keeptrack/pull/21)).

### [9] — 2026-10-09

- CLI column moves assign fresh ranks on split boards.

### [8] — 2026-10-08

- Split storage migration (`migrate --to 4`), web board split reads, `doctor` / `verify` ([#11](https://github.com/rain-ventures-ai/keeptrack/pull/11)).

### [7] — 2026-10-08

- `onboard-keeptrack` / `import` onboarding path.

### [6] — 2026-10-08

- Atomic `--file` writes, archive/unarchive fixes, comment ids.

### [5] — 2026-10-08

- `board.py` → `keeptrack.py`; archive commands and read cache.

### [4] — (historical)

- Early kit packaging in the consulting/co-assets era (see `board/kit/UPGRADING.md`).

### [3] — (historical)

- Multi-repo `use` / plugin layout (`repo-skills`).

### [2] — (historical)

- `init` and Settings → Boards new-board flow.

### [1] — (historical)

- First published kit; `kit-check`, `kit-update`, `migrate`, `kit-owner`.

## Repository tooling

### Unreleased

- Frozen boards under `tests/fixtures/` and CI running Python + Playwright upgrade tests ([#46](https://github.com/rain-ventures-ai/keeptrack/issues/46)).

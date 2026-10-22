# Tasks

## Prioritise and saved filters

In **List**, choose **Prioritise** to edit value and effort, see their calculated score,
and move tasks in board-wide manual order. The URL records selected clients, status,
other filters, layout and sort. Reloading or updating the web app keeps those choices;
Back and Forward restore earlier choices. Copy the URL to share the same filtered view.
Links include filter names, so avoid putting private information in search fields when
sharing them. Tokens and setup codes are never copied into navigation links.

Agents can use `list --sort score`, `list --sort priority`, and
`priority-move '#12' --before '#8'` (or `--after`, `--top`, `--bottom`) with kit v50.
Ranking is board-wide even when a list is filtered; status and Kanban ranks are unchanged.

If you selected **Tasks** when you made your board, you also have these views. They are under **Tasks** in the view bar (the people views are under **People**):
- **Kanban:** columns (Backlog, To do, In progress, Done). Drag cards between columns. Click or tap a card to open it, or focus it and press Enter or Space. Inline controls still work without opening the card. Each card shows compact **Created** and **Active** ages; activity includes edits, comments, history and agent runs. Hover a relative time for its exact date and time.
- **List:** the same tasks grouped by column. The square marks a task done (or reopens it). The tick box beside it selects the row. With rows selected, a bar offers **Move to…** (a column), **Mark done**, **Copy IDs** (for example `#150 #96`) and **Clear selection**. **Activity** is how long since the newest edit, comment or history entry (`3d ago`). A task with nothing for 14 days is marked so it is easy to spot. On a phone that time sits under the title.
- **Calendar** and **Schedule:** the same tasks by due date and by week. Schedule uses the same square to mark a task done.
- **Activity:** what was done today, yesterday or on a day that you select, by you and your agents. **📋 Copy** gives it as Markdown.
- **Archive:** the cards that were archived, by archive year (newest year first), with search and filters. Open one to read it or put it back on the board. See [Search and archive](search-and-archive.md).
- **@Mentions:** every comment that mentions you (`@your-github-username`), newest first, with the task, its description and the comment. A mention on a project opens that project. A reply says who it is replying to. Your own comments are not shown. **New** means posted since you last opened that task or project. Click a row to open it at that comment. Today shows an **@Mentions** tile when you have mentions. The filters apply to task mentions.

Open a task to edit its properties. Status and priority share a compact row, as do its due date and **Waiting for**.
People, labels and the combined **Client & project** control use the full width. The client/project picker filters projects
after you choose a client and keeps long names readable on a phone.

Views and utility screens can be bookmarked: the address keeps the selected view or settings section. Help, Settings,
Search and Copy offer **Copy link to this screen**; settings sections also offer their own links. Shared screen links
include the board, branch and file path, never your GitHub token. They do not grant repository access.

## Write a good card
A card is a note to someone who was not there. A good card has a title that says the outcome in plain words, details
that say what, why and what "done" means, steps you can tick, and a **link** for every pull request, document, file or
web page it talks about. Writing "see #481" in the text is not enough: add the page to the card's links so people can
click it and search finds it; a linked pull request also shows in the Pull requests panel. [Write a good card](../../board/kit/CARDS.md) has the
five tests, a bad card and the same card written well. Agents follow the same guide.

## Images (screenshots)
Add an image to a card's description or to a comment: paste it (Ctrl/Cmd+V), drag it into the box, or press **Image**. In **Links**, **Add image** puts the same file in the card's links instead of in the text. PNG, JPEG, GIF and WebP work, up to 2 MB; a bigger screenshot is made smaller first. Source files over 25 MB are refused before processing. The image is saved as a file in the board repo (`board/assets/<card>/`), and the text or the link uses a short path such as `assets/t_x/20261022-ab12cd.png`. Opening that link shows the image.

Reply to a comment with **Reply**. The reply sits under that comment, one level only. From the terminal: `keeptrack.py comment '#12' "text" --reply-to c_ab12cd`.

Only people who can open the board can see the images. A photo's hidden details (location, device, author and provenance) are removed before it is saved. APNG is saved as a still image. GIF and animated WebP keep their frames; animations over 2 MB must be made smaller first. Colour profiles are removed because they can contain identifying details. PNG colour-space and HDR descriptions are converted for still browser uploads before being removed. Browser uploads convert still-image colours before saving; terminal uploads and animations may look slightly different after a profile is removed. Don't add a screenshot that shows a password, token or confidential client detail: an image stays in the repo's history. Put that in Drive and link it. From the terminal: `keeptrack.py attach '#12' screenshot.png "what it shows"` (`--details` adds it to the description instead). Images are not available on hosted boards yet.

## Tasks for a person
Open a person and type in **☑ Tasks**. The task is linked to that person and their company, and it shows on **Today** when it is due.

## Agents and tasks
AI agents can claim a task, report progress and finish it. While an agent works on a task, the card shows its status. See [AI assistants](ai-assistants.md).

## Waiting for someone
When a task is parked on a person or an event (a client's approval, a colleague's pricing, DNS), use **Waiting for**
instead of using a label or a due date. Open the task and use **Waiting for** in its details: say what or whom it waits on
and, if you like, the day to chase. The card stays in its column and keeps its due date. It shows a
**waiting on …, Nd** chip, which turns amber once the chase day has passed. With no chase day, the task is due for a
chase after 7 days (a board can change this with `settings-set --waiting-days N`; 0 turns it off). The **Waiting**
filter shows only waiting tasks. **Clear** ends the wait, and marking the task done ends it too; the history keeps it.

A waiting task can't be sent to Claude: **Assign to Claude** and `@claude` are off until the wait is cleared, and an
agent's `claim` is refused. Agents that need a decision mark the card waiting, comment with `@you` and the question,
assign it to you and stop. An agent never clears a wait it did not set, or one on someone else; you do.

Agents and scripts use `wait ID --on "Acme finance" [--who p_id|login] [--nudge +3|YYYY-MM-DD] [--note ..]` and
`unwait ID --note "why"`. `today` lists waits due for a chase under **CHASE NOW**, `list --waiting` (or
`--waiting-on me`) lists waiting tasks, and `people` shows how many tasks wait on each person.

## Runs after another task
A task can run after other tasks: #63 after #62, say. Set it with `task-set '#63' --after '#62'` (repeat
`--after` for more; `--not-after '#62'` removes one, `--no-after` clears them), or `add "Title" --after '#62'`. Each id
must be a task on the board; a task can't run after itself, and a loop is refused. The card shows an **after #62** chip
for each task not done yet (amber when that task is missing or cancelled), and the task's details list every link and
its state. `show` prints them, and `list` adds `[after #62]`.

The links are a hint and a gate, never a trigger. Nothing moves a task into **To do** because the tasks before it are
done: you do that, and moving a chain into To do is approving it. Relay (if you use it) starts a task only once every
task it runs after is done, and tells you when a Backlog task is ready to approve or a chain has stopped. A task that is
no longer on the board counts as done only if the archive holds it as Done; otherwise it shows as missing.

## Labels

Type a label on a task to create it. To rename, recolour or delete labels, or add one with a colour, open **Settings → Board → Labels**. Renaming or deleting a label updates every task that uses it, and **Undo** reverts the whole change. The agent tool does the same with `label-set` and `label-rm`.

## Change the columns
Open **Settings → Board → Columns**. You can rename a column, move it up or down, add a new one, or remove one. Each change is saved at once and **Undo** reverses it.

A column's name can change, but its hidden id stays, so cards, the Done column and AI agents keep working. To remove a column that still has cards, Keeptrack asks where to move them. **To do**, **In progress** and **Done** cannot be removed, because agents use them, and a board always keeps at least one column. Agents and scripts have matching commands (`columns`, `column-add`, `column-set`, `column-move`, `column-rm`).

## Turn tasks or people on or off
Open **Settings → Board → Sections** and switch **Tasks** or **People & pipeline (CRM)** on or off. Keep at least one section on.

Turning a section off only hides its dedicated views. **Today** remains available and combines whichever sections are enabled. Nothing deletes tasks, people or history, and turning a section on again shows the same records. If you turn CRM on before there are any people, it opens as an empty CRM. The first person you add creates their record automatically.

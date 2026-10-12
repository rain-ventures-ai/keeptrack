# Tasks

If you selected **Tasks** when you made your board, you also have these views. They are under **Tasks** in the view bar (the people views are under **People**):
- **Kanban:** columns (Backlog, To do, In progress, Done). Drag cards between columns. Click or tap a card to open it, or focus it and press Enter or Space. Inline controls still work without opening the card.
- **List**, **Calendar** and **Schedule:** the same tasks by group, by due date and by week.
- **Activity:** what was done today, yesterday or on a day that you select, by you and your agents. **📋 Copy** gives it as Markdown.

Views and utility screens can be bookmarked: the address keeps the selected view or settings section. Help, Settings,
Search and Copy offer **Copy link to this screen**; settings sections also offer their own links. Shared screen links
include the board, branch and file path, never your GitHub token. They do not grant repository access.

## Tasks for a person
Open a person and type in **☑ Tasks**. The task is linked to that person and their company, and it shows on **Today** when it is due.

## Agents and tasks
AI agents can claim a task, report progress and finish it. While an agent works on a task, the card shows its status. See [AI assistants](ai-assistants.md).

## Waiting on someone
When a task is parked on a person or an event (a client's approval, a colleague's pricing, DNS), mark it as waiting
instead of using a label or a due date. Open the task and use **Waiting** in its details: say what or whom it waits on
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

## Labels

Type a label on a task to create it. To rename, recolour or delete labels, or add one with a colour, open **Settings → Board → Labels**. Renaming or deleting a label updates every task that uses it, and **Undo** reverts the whole change. The agent tool does the same with `label-set` and `label-rm`.

## Change the columns
Open **Settings → Board → Columns**. You can rename a column, move it up or down, add a new one, or remove one. Each change is saved at once and **Undo** reverses it.

A column's name can change, but its hidden id stays, so cards, the Done column and AI agents keep working. To remove a column that still has cards, Keeptrack asks where to move them. **To do**, **In progress** and **Done** cannot be removed, because agents use them, and a board always keeps at least one column. Agents and scripts have matching commands (`columns`, `column-add`, `column-set`, `column-move`, `column-rm`).

## Turn tasks or people on or off
Open **Settings → Board → Sections** and switch **Tasks** or **People & pipeline (CRM)** on or off. Keep at least one section on.

Turning a section off only hides its dedicated views. **Today** remains available and combines whichever sections are enabled. Nothing deletes tasks, people or history, and turning a section on again shows the same records. If you turn CRM on before there are any people, it opens as an empty CRM. The first person you add creates their record automatically.

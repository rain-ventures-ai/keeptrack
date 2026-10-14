# Tasks

First ask: "Do you want to stop using <tool>?"
- **No** (for example a team uses Trello every day): do not import the tasks. Link the board to the client instead (a folder entry or a link on a task). Keeptrack and the other tool must not both own the same tasks.
- **Yes**: import only what is still alive.

## What to import
- Open items only (not done, not archived).
- Changed in the last 90 days, unless the person asks for older ones.
- Keep: title, the client (from the board, list or label name), due date, checklist items (as `todos`), and a link back to the old card.
- Leave out: comments history, attachments (link the card instead), done items, and items with no title.

## Make each imported card readable
Old tools are full of cards like "Fix bug" or "Acme stuff". Before you put a task in the staging file, check it against
`CARDS.md` (next to `keeptrack.py`; `board/CARDS.md` in a board repo):
- Rewrite a title that a newcomer cannot understand. Keep the old title in the details ("Was: ...").
- Put each PR, issue, document, file or page that the old card names or attaches in its `links`, with a title, plus the
  link back to the old card.
- If you cannot tell what a card is about, do not guess: list it in `plan.md` under "Ask the owner".

## Map the columns
| Old tool | Keeptrack column |
|---|---|
| "To do", "Next", "Backlog" style lists | `todo` (or `backlog` for "someday" lists) |
| "Doing", "In progress", "This week" | `in-progress` |
| "Done", completed | do not import |
If a list name does not fit, ask once and use the answer for all its cards.

## A task or a follow-up?
A follow-up with a person ("call Priya on Friday") is the person's next step (`next` and `due` on the person), not a task. A task is work with steps ("Write the Northwind proposal"). Do not make a task for each follow-up.

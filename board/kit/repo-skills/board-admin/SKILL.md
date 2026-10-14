---
name: board-admin
description: Change the board's own structure through board/keeptrack.py - labels (create, rename, recolour, delete), clients (list, rename, remove), board members (add, rename, remove), settings (title, stale minutes, pipeline stages) - and edit any field on a task (title, details, priority, due, labels, links). Use when a person asks to "add a label", "rename the client", "add Sam to the board", "change the stages", "retitle #12", "take the label off", or any change that would otherwise mean editing board JSON by hand.
---

# Board admin

The board's structure (labels, clients, members, settings) lives in `board/tasks.json`. **Never edit that file or any
other board JSON by hand**, even for "just one label". Every change below goes through `python3 board/keeptrack.py`,
which re-reads the latest file, retries on conflict, writes history on the cards it touches, and keeps split boards
(`cards/`, `people/`, `projects/`) consistent.

## 1. Look before you change
```bash
python3 board/keeptrack.py settings   # title, stale minutes, stages, columns, counts
python3 board/keeptrack.py labels     # each label, its colour and how many cards carry it
python3 board/keeptrack.py clients    # each client and how many tasks, projects and people use it
python3 board/keeptrack.py members    # board members (assignable GitHub users), open tasks, upgrade owner
```

## 2. Do it

| Want | Command |
| :-- | :-- |
| New label | `label-add relay --color "#5e4db2"` (hex only; default grey) |
| Rename a label (all live cards follow) | `label-set relay --rename agents` |
| Recolour | `label-set relay --color "#0c66e4"` |
| Delete a label | `label-rm relay` (refuses while cards carry it); `--force` takes it off those cards |
| Label a card / take it off | `task-set '#12' --label relay --unlabel call` (a new label is created grey) |
| Retitle, details, priority, due | `task-set '#12' --title ".." --details ".." --priority high --due 2026-11-01` (`--due ""` clears) |
| Card's client or project | `task-set '#12' --client "Acme" --project "Rollout"` (project by name, id or prefix; stored as its id) |
| Add a link (PR, issue, document, folder, web page) | `link '#12' <full URL> --title "<what it is>"` |
| Remove a link | `unlink '#12' <url or title>` |
| Remove a project or client link | `project-unlink "Rollout" <url or title>`, `client-unlink "Acme" <url or title>` |
| Rename a client everywhere | `client-rename "Acme" "Acme Ltd"` (tasks, projects, people's company, client info) |
| Remove an unused client | `client-rm "Old Co"` (refuses while anything uses it) |
| Client north star | `client-set "Acme" --north-star ".."` |
| Add / change a project | `project-add "Rollout" --client "Acme" --north-star ".."`, `project-set "Rollout" --status done` |
| What is left on a project | `project "Rollout"` (goal, people, links, open tasks); `projects --client "Acme"` lists them |
| List columns with card counts | `columns` |
| Add a column | `column-add "In review" [--after todo]` (id is a slug of the name; default is just before Done) |
| Rename a column | `column-set in-review --rename "Review"` (the id stays, so cards and Done keep working) |
| Reorder columns | `column-move review --before todo` or `--after todo` |
| Remove a column | `column-rm review --move-to todo` (refuses while it has cards unless `--move-to` is given; never `todo`, `in-progress`, `done` or the last column) |
| Add / rename a board member | `member-add sam --name "Sam"`, `member-set sam --name "Sam K"` |
| A member's email addresses and time zone | `member-set sam --email sam@example.com --email sam@example.org --remove-email old@example.com --timezone Europe/London`; `me` shows yours |
| Remove a board member | `member-rm sam` (refuses with open tasks; `--unassign` takes them off). Never the upgrade owner |
| List / add / remove an agent name | `agents`, `agent-add codex`, `agent-rm codex` (refuses with open tasks or a claim; `--unassign` takes it off open tasks) |
| Delete a card or CRM person made by mistake | `task-rm '#12' --yes`, `person-rm "Cat" --yes` (refuse without `--yes`; ask first, it cannot be undone from the CLI). A finished task goes done and archive instead; a person who is not a fit goes to Lost |
| Board title, stale minutes | `settings-set --title "Ops" --stale-minutes 45` |
| Pipeline stages | `settings-set --rename-stage Talking=Meeting` (moves people), or `--stages "New,Contacted,Won,Lost"` (refuses if people would be left in a dropped stage) |

`ID` may be a task number such as `'#12'` (quote the `#`).

## 3. Rules
- **Ask before anything wide or lossy:** renaming or deleting a label, client or stage, removing a member or agent, `task-rm`, `person-rm`, `done --cancel`, or `--force`.
  Say what it touches (the commands print counts) and wait for a yes. Adding a label or retitling one card needs no ask.
- A refusal is information, not an obstacle: it names what still depends on the thing. Fix that, or ask. Do not work
  round it by editing JSON.
- Board members are GitHub users who can be assigned work, and their record is their identity (name, emails, time
  zone). CRM people (`person-add`) are separate, optional records; turning the CRM off never touches a member.
- Renames reach archived items too (`archive/<year>.json` is rewritten in the same save). A client's working folder (for example `clients/<name>/` in the repo) is not renamed: say so.
- Columns can't be changed from the CLI yet; tell the person and leave them as they are.
- When you retitle or rewrite a card, follow `board/CARDS.md` (the five tests of a good card). If the card mentions a
  PR, issue, document or page that is not in its links, add it with `link` in the same run.
- After a structural change, run `python3 board/keeptrack.py doctor` and report anything it finds.

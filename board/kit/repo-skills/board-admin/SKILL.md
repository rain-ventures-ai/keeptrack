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
| Remove a link | `unlink '#12' <url or title>` |
| Rename a client everywhere | `client-rename "Acme" "Acme Ltd"` (tasks, projects, people's company, client info) |
| Remove an unused client | `client-rm "Old Co"` (refuses while anything uses it) |
| Client north star | `client-set "Acme" --north-star ".."` |
| Add / rename a board member | `member-add sam --name "Sam"`, `member-set sam --name "Sam K"` |
| Remove a board member | `member-rm sam` (refuses with open tasks; `--unassign` takes them off). Never the upgrade owner |
| Board title, stale minutes | `settings-set --title "Ops" --stale-minutes 45` |
| Pipeline stages | `settings-set --rename-stage Talking=Meeting` (moves people), or `--stages "New,Contacted,Won,Lost"` (refuses if people would be left in a dropped stage) |

`ID` may be a task number such as `'#12'` (quote the `#`).

## 3. Rules
- **Ask before anything wide or lossy:** renaming or deleting a label, client or stage, removing a member, or `--force`.
  Say what it touches (the commands print counts) and wait for a yes. Adding a label or retitling one card needs no ask.
- A refusal is information, not an obstacle: it names what still depends on the thing. Fix that, or ask. Do not work
  round it by editing JSON.
- Board members are GitHub users who can be assigned work. CRM people (`person-add`) are separate records.
- Renames reach the live board only. Archived items keep the old name; after `unarchive`, fix them with `task-set`
  or `person-set`. A client's working folder (for example `clients/<name>/` in the repo) is not renamed either: say so.
- Columns can't be changed from the CLI yet; tell the person and leave them as they are.
- After a structural change, run `python3 board/keeptrack.py doctor` and report anything it finds.

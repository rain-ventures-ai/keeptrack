# Board widgets

A board can add small, read-only widgets to its Today page. The configuration lives beside the board data as
`board/widgets.json`, so each board can have a different home screen. A board without that file keeps the standard
Today page. In Settings → Preferences → Board customisations, turn on **Enable board widgets** to display them.
This is off by default and saved separately for each board, branch and file in this browser. Other members and
other browsers choose independently. Turning it off hides widgets and stops new widget requests; the repo file
is kept. Board switching never carries the preference to a different board.

**Use a separate appearance for this board** is another optional browser setting. Enable it to keep this board's
theme, card style and imported DESIGN.md colours separately. It starts with your current appearance. Changes then
affect this board only; disabling restores your browser default and keeps the board profile for later. Navigation
layout remains a browser preference. These appearance profiles are local, not committed to GitHub.

Widgets are configuration, not executable plugins. Keeptrack renders the supported widget types itself. The file
cannot run JavaScript, read the GitHub token, reach browser storage or load a widget from another repository. It is
read from the same repository, branch and folder as `tasks.json` and is limited to 64 KB and 12 widgets.

## Example

```json
{
  "version": 1,
  "widgets": [
    {
      "id": "recent-work",
      "slot": "today.after-shortcuts",
      "type": "task-strip",
      "title": "Recently added",
      "query": {
        "columns": ["backlog", "todo"],
        "sort": "created-desc",
        "limit": 6
      },
      "appearance": {
        "density": "thin",
        "show": ["number", "title", "column", "priority"]
      }
    }
  ]
}
```

The supported types are:

- `task-strip`: a single horizontally scrolling line of tasks. `query.columns`, `query.labels`, `query.assignee`
  (`"me"`), `query.limit` (1–12), and `query.sort` (`created-desc`, `updated-desc`, `due`, `priority` or `manual`)
  narrow and order it. `appearance.show` accepts `number`, `title`, `column`, `priority` and `due`.
- `weather`: current conditions and today's range from Open-Meteo. Set `location.name`, `location.latitude` and
  `location.longitude`; `units` is `celsius` or `fahrenheit`. This widget makes a direct, credential-free request to
  Open-Meteo when the Today page is open. It never sends board data or the GitHub token.
- `board-pulse`: counts cards in progress, running agents, work needing attention and cards completed today. When an
  agent is running, its first card is linked beneath the counts.

All current widgets use the `today.after-shortcuts` slot. Unknown types and invalid entries are ignored. A malformed
file shows a small warning on Today without stopping the board from loading. Keeptrack supports these declarative
widgets and their appearance options; it does not load arbitrary JavaScript plugins or CSS overrides from a board.

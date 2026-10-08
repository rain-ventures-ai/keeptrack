# Demo boards

Two read-only example boards with invented data. Use them to look at Keeptrack before you set it up.

| Demo | What it shows | Open it |
|---|---|---|
| `crm/` | People, follow-ups, pipeline and linked tasks | [https://rain-ventures-ai.github.io/keeptrack/board/?demo=crm](https://rain-ventures-ai.github.io/keeptrack/board/?demo=crm) |
| `board/` | A task board for a small team (no people or pipeline) | [https://rain-ventures-ai.github.io/keeptrack/board/?demo=board](https://rain-ventures-ai.github.io/keeptrack/board/?demo=board) |

The web board loads these files from the same site as the board page. Each file has `demo_base` (the date the data was written). The board moves every date by the days since `demo_base`, so "Today" always has items. A file with `demo_base` is always read-only, also when it is opened with `?repo=...&path=demo/crm/tasks.json` and a token.

To change a demo, edit its `tasks.json` and set `demo_base` to the day you edit it.

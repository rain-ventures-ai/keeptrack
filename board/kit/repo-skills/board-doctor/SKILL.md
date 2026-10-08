---
name: board-doctor
description: Check or repair a Keeptrack board. Use when the board shows errors, a save fails, after a migration, or when a person asks to check or repair the board.
---

# Check and repair the board

Use `python3 board/keeptrack.py`. Never edit board JSON files by hand.

1. Run `python3 board/keeptrack.py doctor`.
2. Show the full report to the person.
3. If the report lists safe fixes, ask if you may run them.
4. Run `python3 board/keeptrack.py doctor --fix` only after the person says yes.
5. Run `python3 board/keeptrack.py doctor` again. Show the new report.

`doctor --fix` does not delete data. It does not repair invalid JSON.

If a file has invalid JSON, show its git history:

```bash
git log --oneline --follow -- <path>
```

Suggest restoring the last good version. Ask before you restore it.

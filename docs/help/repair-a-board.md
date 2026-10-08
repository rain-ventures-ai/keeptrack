# Repair a board

Use the board doctor when the board shows an error. Also use it after a migration.

Run this command in the board repo:

```bash
python3 board/keeptrack.py doctor
```

The report gives each problem a short code. It does not change the board.

Exit code 0 means the board is healthy. Exit code 1 means it found a problem. Exit code 2 means it could not read the board.

Some problems have a safe fix. Read the report first. Then run:

```bash
python3 board/keeptrack.py doctor --fix
```

The fix command does not delete data. It does not change invalid JSON.

Run `doctor` again after the fix.

If a file has invalid JSON, ask for help. Use git history to find the last good copy. Do not edit the JSON by hand.

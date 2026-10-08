# Search and archive

## Search
Press **/** (or **Ctrl+K**, **⌘K** on a Mac), or click **🔍** at the top. Type a few letters. Search looks in names, companies, task titles, notes, checklists, comments and contact logs. It finds part of a word (`harb` finds Harbour Foods) and small spelling errors.

- Press **Enter** to open the first result. Use the arrow keys to move between results.
- Tick **Include archive** to search old items too.

## Archive
A board gets slower when the file gets large. The archive moves old items to other files in the same repo:

- tasks that have been done for more than 90 days,
- people at the stage **Lost** with no change for 180 days and no next step,
- old history lines (each card keeps its last 20). The trimmed lines are kept in the archive file, not deleted.

Open **⚙️ Settings → General → Archive** to see the board size and to archive now. When the board file is larger than 600 KB, a bar at the top asks you to archive.

Archived items are not deleted. Search finds them when you tick **Include archive**. Open one to read it, and click **Put back on the board** to bring it back.

**What the browser cannot show yet:** the old history lines that were trimmed off a card that is still on the board. Such a card shows only its last 20 history lines. (An archived item shows its full history, and **Put back on the board** brings the older lines back with it.) They are safe in the archive file (`archive/<year>.json`, under `history`). To read them, ask your AI assistant, or run `keeptrack.py archived-history ID` (ID is the task number such as `#12`, or a person's id). The same command also prints the full history of an item that is itself archived.

Your AI assistant can do the same: ask it to "archive old items", "find the old task about the Harbour Foods proposal" or "show the old history of task #12".

## Very large boards
Long lists show the first 150 items and a **Show more** button, so that the page stays fast. A board with 30,000 tasks still opens, but archive old items to keep it quick.

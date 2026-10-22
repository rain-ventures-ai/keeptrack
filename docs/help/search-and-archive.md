# Search and archive

## Search
Press **/** (or **Ctrl+K**, **⌘K** on a Mac), or click **🔍** at the top. Type a few letters. Search looks in names, companies, task titles, notes, checklists, comments and contact logs. It finds part of a word (`harb` finds Harbour Foods) and small spelling errors.

- Press **Enter** to open the first result. Use the arrow keys to move between results.
- Tick **Include archive** to search old items too. This browser remembers the tick box, so it stays ticked (or not) the next time you search.
- An archived result has an **Archived** pill with its archive year, for example **Archived 2025**.

## Browse the archive
You do not need to know what to search for:

- **Archive** is the last view under **Tasks** (after Activity). It lists the archived cards by archive year, newest year first. The year is the year of the archive file: the year a card was archived, or, for the old items that **Settings → Board → Archive** moves, the year the card last changed. Inside a year, the card archived last comes first.
  - Type in the search box to find a card by its title, details, checklist, comments, labels or number (`#102`).
  - Filter by **project**, **label**, **year** (the year of the archive file) and **Done or cancelled**. **Cancelled** means the card was archived without being done: closed as cancelled, or archived from another column.
  - The client filter at the top of the board applies here too.
  - The count says how many cards match. A long list shows 50 cards and a **Load more** button.
- **People** → the stage filter → **Archived** lists the people the archive moved out (people at the stage Lost). The search box works on this list too.

Click or tap a row to read the archived card or person. Click **Put back on the board** to bring it back. A read-only board lets you look but not put back.

The archive files load when you open one of these lists. If they cannot load (for example, you are offline), the list says so and has a **Try again** button.

## Archive
A board gets slower when the file gets large. The archive moves old items to other files in the same repo:

- tasks that have been done for more than 90 days,
- people at the stage **Lost** with no change for 180 days and no next step,
- old history lines (each card keeps its last 20). The trimmed lines are kept in the archive file, not deleted.

Open **⚙️ Settings → Board → Archive** to see the board size and to archive now. When the board file is larger than 600 KB, a bar at the top asks you to archive.

Archived items are not deleted. The **Archive** view lists them, and search finds them when you tick **Include archive**. Open one to read it, and click **Put back on the board** to bring it back.

For one task, open its **⋯ → Archive task** menu, or choose **Archive task instead** on the delete screen. This removes it from the active board without deleting any details, checklist, comments or history, regardless of its status or age. Tasks with an unfinished agent claim must be released or finished first. Prefer archiving to deleting when you want to keep a record.

From the CLI: `keeptrack.py archive '#102' --dry-run` previews one task; `keeptrack.py archive '#102'` archives it; `keeptrack.py unarchive '#102'` restores it. Without a reference, `archive` keeps its existing bulk age-based behaviour. Individual references cannot be combined with bulk archive rule flags.

**What the browser cannot show yet:** the old history lines that were trimmed off a card that is still on the board. Such a card shows only its last 20 history lines. (An archived item shows its full history, and **Put back on the board** brings the older lines back with it.) They are safe in the archive file (`archive/<year>.json`, under `history`). To read them, ask your AI assistant, or run `keeptrack.py archived-history ID` (ID is the task number such as `#12`, or a person's id). The same command also prints the full history of an item that is itself archived.

Your AI assistant can do the same: ask it to "archive old items", "find the old task about the Harbour Foods proposal" or "show the old history of task #12".

## Very large boards
Long lists show the first 150 items and a **Show more** button, so that the page stays fast. A board with 30,000 tasks still opens, but archive old items to keep it quick.

# When two writers change the same board

Keeptrack has two writers: the web board (`board/board.js`) and the agent CLI (`board/kit/keeptrack.py`). Both can save while the other is mid-edit. This page says what happens, before and after the three-way merge (issue #42).

## The rule

On every save the writer reads the board as it is on GitHub now (**theirs**), and compares three versions:

- **base**: the board as this writer loaded it
- **mine**: base plus this writer's change
- **theirs**: what is on GitHub now

`merge3(base, mine, theirs)` returns `{merged, clashes}`. The same rules are in `board/board.js` and `board/kit/keeptrack.py`.

- A value only one side changed: that change is kept. A value both sides changed to the same thing: kept once.
- Objects merge field by field, as deep as they go.
- Lists merge by item `id`: an item added on either side is kept; an item removed on one side and untouched on the other is removed; an item edited on both sides merges field by field. Items without an `id` (links, labels, history lines) are matched by their content, so additions and removals merge the same way. If one side reordered a list and the other did not, the reorder is kept; if both reordered, theirs wins (order is not content).
- Bookkeeping never clashes: `updated` and `updatedBy` take mine, `claim.heartbeat_at` takes mine, `next_num` takes the larger. Two new cards given the same `#number` are renumbered (the card that was already there keeps it).
- A **clash** is a value both sides changed to different things, or an item one side edited and the other deleted. `merged` keeps theirs at a clash; nothing is guessed.

What happens at a clash:

- **Web**: a resolution screen lists each clash with what you saw, mine and theirs. Per clash: Keep theirs (default), Keep mine, or Edit. "Discard my change" drops the whole change. Everything that did not clash is saved either way.
- **CLI / agents**: the command stops, writes nothing, leaves theirs intact, prints the clashing paths to stderr and exits with status 3. The agent should read the board again and redo the change if it still applies.

## What happened before (the audit)

| Case | Web board | CLI |
| --- | --- | --- |
| Two different fields of one card | Both kept (the edit is re-applied on the latest file). Correct. | Both kept (the command is re-run on the latest file). Correct. |
| Same field | Dialog: "Apply my change anyway" or "Discard my change". Shows every differing field of the whole card. Correct but coarse: all or nothing, and no per-field choice. | **Wrong.** The retry silently overwrote their value. Nothing was reported. |
| Entries added on both sides (comments, history lines, to-dos, people's notes) | Comments and history never conflicted. For other lists (to-dos, links, labels) any change on both sides raised the dialog even when they did not overlap; "Apply anyway" kept both unless the edit replaced the whole list, in which case their entry was dropped. | Kept both when the command appended to the list. A command that replaced a whole list (labels, assignees) silently dropped their entries. |
| I edit, they deleted | Toast "deleted by someone else; nothing changed". My edit is dropped but I am told. Acceptable. | Mostly stopped with an error because the card no longer exists. Acceptable. |
| I delete, they edited | Dialog. Correct. | **Wrong.** Deleted silently, losing their edit. |
| Board settings (`tasks.json`: columns, labels, clients, settings) | **Not checked.** Last write wins silently. | **Not checked.** Last write wins silently. |

## What is different now

- Web: `mutate` merges mine (the optimistic copy) into the latest file with `merge3` instead of re-running the edit on it, and asks only about real clashes. Lists no longer raise false clashes, and a replaced list keeps their additions. Settings are covered. Edit-against-delete is a clash with a choice (it used to be a toast).
- CLI: after a lost race, `_mutate` merges what it first loaded, what it wanted to save and what is there now. A clash stops with exit status 3 and no write.

## Known limits

- Items without an `id` that both sides edit differently are both kept (an edit looks like a removal plus an addition), so a duplicate is possible; nothing is lost.
- Cards are compared as whole files. Two writers adding a card with the same id is a clash on that card's fields.
- The CLI cannot ask questions, so a clash needs a re-run by the agent or a person.
- `--file` mode holds a lock, so it never loses a race and never reaches the merge.

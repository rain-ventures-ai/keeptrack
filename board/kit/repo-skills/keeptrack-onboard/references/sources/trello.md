# Trello

Tasks, lists, checklists. Value: high for tasks. Follow `../tasks.md`.

**Read it:** board menu > More > Print and export > Export as JSON (the person downloads the file and gives it to you). Or the Trello API with a key the person sets in an environment variable (never in a file or in the chat).

**Map it:** `cards` with `closed: false`; the list name gives the column; labels or the board name give the client; `checklists` give `todos`; the card's `shortUrl` goes in `links` as "Trello card". Use `dateLastActivity` for the 90-day rule.

**Traps:** archived lists (their cards look open: check the list's `closed` too); one board per client vs one board for everything (ask which).

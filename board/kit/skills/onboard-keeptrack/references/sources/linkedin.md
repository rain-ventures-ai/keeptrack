# LinkedIn

Contacts and their roles. Value: medium: many contacts are not clients.

**Read it:** the person exports their connections: LinkedIn > Settings > Data privacy > Get a copy of your data > Connections. LinkedIn emails a link; the file is `Connections.csv`. Do not scrape LinkedIn with the browser.

**Use:** only to fill `role`, `company` and `linkedin` for people who are already clients or leads (match by name and company), or for people the person picks from the list. Do not import all connections.

**Traps:** the first lines of the file are notes, not the header; many rows have no email; the company is the current one, not the one when you worked together.

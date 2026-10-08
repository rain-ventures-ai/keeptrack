# Spreadsheets (Excel, Google Sheets, Numbers, CSV)

Often the real client list already. Value: high.

**Read it:** a file the person gives you, a file in a connected folder, or a Google Sheet through the Drive connector (export as CSV). Numbers: ask the person to export as CSV (File > Export To > CSV).

**Map it:** find the columns for name, company, email, phone, stage or status, next step and date. Show your mapping to the person in one table before you use it. A status column maps to stages: ask once if the words do not match (for example "Hot" to `Talking`, "Signed" to `Won`).

**Traps:** one row per company with several people in one cell; dates in US format (check one date with the person); merged header rows; totals rows at the end; colour used as the status (you cannot read colour from a CSV: ask).

The simplest route: make a CSV with the import columns (`staging-format.md`) and run `import` on it.

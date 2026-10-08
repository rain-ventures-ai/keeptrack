# The staging file

`keeptrack.py import <file> [--dry-run] [--source "<evidence>"]` reads one file. Always run `--dry-run` first and show the result.

## JSON
```json
{
  "source": "Onboarding 2026-10-08",
  "companies": ["Northwind", "Acme Ltd"],
  "people": [
    {"name": "Priya Shah", "company": "Northwind", "role": "COO", "email": "priya@northwind.com",
     "linkedin": "https://www.linkedin.com/in/priyashah", "phone": "", "stage": "Talking",
     "next": "Send the proposal", "due": "2026-10-15", "value": "12000", "notes": "", "source": "Referral from Sam",
     "evidence": "Named by the owner; 14 emails sent, 3 meetings"}
  ],
  "folders": [
    {"company": "Northwind", "title": "Drive: Clients/Northwind", "url": "https://drive.google.com/drive/folders/..."}
  ],
  "tasks": [
    {"title": "Write the Northwind proposal", "client": "Northwind", "column": "todo", "priority": "medium",
     "due": "2026-10-15", "contact": "priya@northwind.com", "todos": ["Draft", "Review with Sam"],
     "links": [{"title": "Trello card", "url": "https://trello.com/c/..."}], "evidence": "Trello: Sales board"}
  ]
}
```
- Every list is optional. Every field except `name` (people), `company` and `url` (folders) and `title` (tasks) is optional.
- `stage`: one of the board's stages (`$B where` and the web board show them). Empty means the first stage.
- `due` is `YYYY-MM-DD`. A person's `due` needs a `next` step.
- `column`: `backlog`, `todo`, `in-progress` or `done` (or the board's own column ids). `priority`: `high`, `medium` or `low`.
- `contact` on a task: the person's email or name.
- `evidence`: one line on where the facts came from. It goes into the record's history. Without it, `source` (or `--source`) is used.

## CSV (people only)
For a person who fills a sheet in Excel. Columns (any order, a header row is required): `name, company, role, email, phone, linkedin, value, next, notes, source, stage, due, evidence`. Other columns are refused, so rename them first. Empty rows are skipped.

## What import does
- A person who is already on the board (same email, same LinkedIn URL, or same name and company) is not added again. Empty fields are filled; fields with a value are never changed.
- A task with the same title and client, or the same link, is not added again.
- A folder link that is already there is not added again.
- A file with a problem is refused whole, with a list of the problems. Nothing is half imported.

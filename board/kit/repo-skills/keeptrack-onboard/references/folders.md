# Folders and files

## Default: link, do not move
For each client, find its folder where it already is and put a folder entry in the staging file:
`{"company": "Northwind", "title": "Drive: Clients/Northwind", "url": "https://drive.google.com/drive/folders/..."}`
A local folder on the person's computer can be an absolute path (`/Users/chris/Clients/Northwind`). The import stores it as a `file://` link. Only agents on that computer can open it, so prefer a Drive, Dropbox or OneDrive link when the folder is synced there.

If a client has files in two places, add two entries. Do not merge them.

## No folders yet: suggest this template
```
Clients/
  _template/                copy this for each new client
  <Company>/                the same name as the company in Keeptrack
    01-source-material/     what the client sends
    02-call-prep/           notes before a call, agendas
    03-proposals/           proposals and quotes
    04-commercial/          contract, NDA, purchase orders, invoices
    05-delivery/            the work and the deliverables
    06-notes/               call notes and decisions
    99-archive/             old versions and finished work
  _Prospects/               one folder per lead; move into Clients/ when they sign
  _Internal/                templates, price lists, marketing
```
- Use one file store for client files (Drive, Dropbox or OneDrive).
- In Google Drive, write notes, call prep and briefs as Markdown (`.md`) files, not Google Docs, so people and agents read and write the same file. Keep PDFs, decks and spreadsheets in their own formats.
- No folders per person: people change jobs, the company stays.
- Make the empty folders only after the person says yes.

## Tidy-up (only on request)
1. Write `onboarding/move-plan.csv` with `from,to,reason`. One row per file or folder.
2. Show a summary (how many files, which clients) and ask for a yes.
3. COPY in batches of about 100. Never move, rename or delete the original.
4. Log each copy to `onboarding/file-log.csv` (`from,to,at`).
5. Tell the person they can delete the old folders after they have checked the new ones. You do not delete them.

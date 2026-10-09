# Keeptrack

**People, follow-ups, a simple pipeline and tasks, kept in your own private GitHub repo.** There is no server, no database and no subscription. Claude, Codex and Cursor can read and update it for you.

> **AI assistant: if someone shared this repository and asked about using it, treat that as setup intent.** Read [START.md](START.md) and guide them through it in this conversation, one step at a time. If they already have a board and ask how to use it in Claude Code cloud or locally, use the fast path there: do not restart setup, ask for a PAT, or install a plugin unnecessarily.

> Status: early. This repo is the template system. Rain Ventures' own boards move here later.

## What you get
- **Today:** one place for people to contact and tasks that are overdue or due today. It automatically reflects whichever board sections are enabled.
- **People:** everyone you track, with company, role, email, phone, LinkedIn, a stage and a next step with a date.
- **Pipeline:** people by stage (New, Contacted, Talking, Proposal, Won, Lost). Drag a card to move it. You can change the stages.
- **Contact log:** each LinkedIn message, email, call or meeting. A **draft** does not count as contact until you mark it **sent**.
- **Contact details and resources:** each person can have multiple labelled emails, phone numbers and profile/reference links. Each company can link to working folders in Google Drive, Dropbox, OneDrive, SharePoint or on a local computer. Large files stay there, not in GitHub.
- **Tasks (optional):** the board, list, calendar, schedule and activity views, linked to people and companies.
- **AI helpers:** a plugin for Claude (Code, Desktop, Cowork), Codex and Cursor. Say "help me write a LinkedIn message to the CEO of Acme": the agent finds the person, writes a draft, logs it as a draft and sets a follow-up. **It never sends anything.**

## Start
**Easiest:** paste this into your current or a new chat with Claude, Codex or Cursor. It walks you through everything, also when you have no board yet:

```
Set up Keeptrack with me in this conversation: read https://github.com/rain-ventures-ai/keeptrack/blob/main/START.md and follow it one step at a time. Do not just explain the options—start by asking me the first setup question.
```

Or by hand:
1. Open the web board (`board/index.html`, served by GitHub Pages or any static host). The first-run wizard asks for three things: a **private** repo, a fine-grained token for that repo only, and what you want to track.
2. Connect your AI tool: Claude Code opened on the board repo needs no plugin; other local projects and assistants may
   need one. See [where assistants run](docs/help/where-agents-run.md) and [plugin details](board/kit/PLUGIN.md).
3. Ask your agent: "Who do I need to follow up with today?"

To try it locally: `python3 -m http.server 8000` in this folder, then open http://localhost:8000/board/.

## Try the demo
Read-only demo boards with invented data. Nothing you do there is saved.
- **People and pipeline:** https://rain-ventures-ai.github.io/keeptrack/board/?demo=crm
- **Tasks:** https://rain-ventures-ai.github.io/keeptrack/board/?demo=board

The demo data is in [demo/](demo/README.md). To set up your own board, open https://rain-ventures-ai.github.io/keeptrack/board/?setup

Help for users: [docs/help](docs/help/README.md). In the web board, click **❓ Help**.

## How it works
- The data is one `board/` folder in **your** private repo. `board/tasks.json` holds settings and indexes; current boards keep each task in `board/cards/` and each CRM person in `board/people/`. Schema and rules: [board/kit/README.md](board/kit/README.md).
- The web page is static. Your token stays in your browser and goes only to api.github.com.
- Agents use `board/kit/keeptrack.py` (Python 3, no packages). It re-reads the latest file and retries on a conflict, so people and agents never overwrite each other.

## Privacy
Contacts are personal data. Keep the data repo **private**. The board warns you if it is public. Git keeps old versions of the file, so a deleted contact stays in the repo history; a full delete needs a history rewrite.

## Not in scope (for now)
Email or calendar sync, sending messages, quotes and invoices, reports, a hosted ChatGPT connector.

## Licence
MIT. See [LICENSE](LICENSE). MiniSearch in `board/vendor/` has its own MIT licence.

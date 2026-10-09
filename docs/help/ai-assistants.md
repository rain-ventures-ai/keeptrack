# AI assistants

Your AI assistant can read and update your board. It uses the Keeptrack **skill** (instructions) and `keeptrack.py` (a small tool). It **never sends** a message for you.

Not sure which assistant to use, or whether you need Python? See [Where your assistant runs](where-agents-run.md).

## What you can ask
- "Who do I need to follow up with today?"
- "Help me write a LinkedIn message to the CEO of Acme." The assistant finds or adds the person, reads the contact log, writes the draft, logs it as a draft, and sets a follow-up. You send it, then say "It is sent".
- "I just had a call with Sarah. She wants a proposal by Friday." The assistant logs the call and sets the next step.
- "Add these contacts from my spreadsheet." It refuses duplicates.
- "Add the leads from this week's opportunity run." It refuses leads that are already on the board.
- "Move Tom to Proposal." / "What is in my pipeline?"

## Connect the assistant
The quickest way: in the web board open **⚙️ Settings → Agents → An assistant in your chat app**, select your tool, and copy the steps. Claude Code does not always need a plugin:

| Tool | How |
|---|---|
| Claude Desktop or Cowork | **Customize → Plugins → Add → Add marketplace**, type `rain-ventures-ai/keeptrack`, then install **keeptrack**. |
| Claude Code cloud | Start the session on the board repo, or add the board repo as a second repo. No plugin or PAT. |
| Claude Code locally in the board repo | Start `claude` in the repo. No plugin; use your existing `gh` login. |
| Claude Code locally in another project | `claude plugin marketplace add rain-ventures-ai/keeptrack` then `claude plugin install keeptrack@keeptrack` |
| Codex | `codex plugin marketplace add rain-ventures-ai/keeptrack`, then install **keeptrack** from `/plugins`. |
| Cursor | In Agent chat: `/add-plugin https://github.com/rain-ventures-ai/keeptrack` |
| ChatGPT | ChatGPT cannot update the board yet. Use **🤖 Copy for AI** on a person, paste it into ChatGPT, then log the draft on the board yourself. |

The Keeptrack repo is public, so anyone can install the plugin. Full details: [board/kit/PLUGIN.md](../../board/kit/PLUGIN.md).

## What the plugin and skills provide

The **plugin** is the package that installs Keeptrack into an assistant when you are not working inside the board repo.
It includes `keeptrack.py` plus focused **skills**—instructions the assistant selects for the job:

- [`keeptrack`](../../board/kit/skills/keeptrack/SKILL.md): everyday people, follow-up, pipeline and task work.
- [`onboard-keeptrack`](../../board/kit/skills/onboard-keeptrack/SKILL.md): guided import of existing contacts and tasks.
- [`keeptrack-notes`](../../board/kit/skills/keeptrack-notes/SKILL.md): meeting notes and action items.
- [`keeptrack-email`](../../board/kit/skills/keeptrack-email/SKILL.md): safe mailbox-to-contact reconciliation.

Every board repo also carries the board-local versions it needs. That is why Claude Code can work directly in a board
repo without installing the plugin. See [the plugin and skill layout](../../board/kit/PLUGIN.md) for Claude, Codex and
Cursor, or [choose where your assistant runs](where-agents-run.md).

## First use: tell it your board
Inside the board repo, Claude gets the board name from the Git remote and does not need a `.board` setting. In another
local project, the plugin asks for your board repo (for example `your-name/my-keeptrack`) and GitHub username. It saves
them in a hidden `.board` folder in that project. It never saves your token.

Locally, it needs access to your repo in one of these ways:
- a GitHub login on your computer (`gh auth login`), or
- a token in an environment variable. Tell the assistant the **name** of the variable, never the token itself.

## @claude on the board
Type **@claude** in a task comment and your own Claude routine starts work on that task. To set it up, open **⚙️ Settings → Agents** and tick **I use @claude**. Five steps with a ✓ for each, then a real test. Details: [ROUTINE-SETUP.md](../../board/kit/ROUTINE-SETUP.md).

## Rules the assistant follows
- It never sends messages, emails or quotes. It writes drafts.
- It marks a message as sent only after you say that you sent it.
- It does not copy contact details to other places.
- It keeps large files out of GitHub and links them instead.

## Keep contact history up to date from email

Use a separate scheduled email routine to compare recent Gmail or Outlook messages with the exact email addresses on
your Keeptrack people. It can add concise sent/received email facts to contact logs and update an explicit next step,
but it never sends, drafts or deletes mail. The routine keeps its last successful run and recent run summaries in
`automation/contact-email-sync.json`, without storing message bodies, subjects, attachments or email addresses there.

Ask Claude Code in the board repo: **“Set up my Keeptrack contact email routine.”** It follows the
`keeptrack-email` skill and asks which mailbox and schedule to use. Keep this routine separate from the task-comment
routine so an untrusted board comment never has access to your mailbox.

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

## Install
The quickest way: in the web board open **⚙️ Settings → Agents → An assistant in your chat app**, select your tool, and copy the steps.

| Tool | How |
|---|---|
| Claude Desktop or Cowork | **Customize → Plugins → Add → Add marketplace**, type `rain-ventures-ai/keeptrack`, then install **keeptrack**. |
| Claude Code | `claude plugin marketplace add rain-ventures-ai/keeptrack` then `claude plugin install keeptrack@keeptrack` |
| Codex | `codex plugin marketplace add rain-ventures-ai/keeptrack`, then install **keeptrack** from `/plugins`. |
| Cursor | In Agent chat: `/add-plugin https://github.com/rain-ventures-ai/keeptrack` |
| ChatGPT | ChatGPT cannot update the board yet. Use **🤖 Copy for AI** on a person, paste it into ChatGPT, then log the draft on the board yourself. |

While Keeptrack is private, you need access to the `rain-ventures-ai/keeptrack` repo to install the plugin. Full details: [board/kit/PLUGIN.md](../../board/kit/PLUGIN.md).

## First use: tell it your board
The first time, the assistant asks for your board repo (for example `your-name/my-keeptrack`) and your GitHub username. It saves them in a hidden `.board` folder in your project. It never saves your token.

It needs access to your repo in one of these ways:
- a GitHub login on your computer (`gh auth login`), or
- a token in an environment variable. Tell the assistant the **name** of the variable, never the token itself.

## @claude on the board
Type **@claude** in a task comment and your own Claude routine starts work on that task. To set it up, open **⚙️ Settings → Agents** and tick **I use @claude**. Five steps with a ✓ for each, then a real test. Details: [ROUTINE-SETUP.md](../../board/kit/ROUTINE-SETUP.md).

## Rules the assistant follows
- It never sends messages, emails or quotes. It writes drafts.
- It marks a message as sent only after you say that you sent it.
- It does not copy contact details to other places.
- It keeps large files out of GitHub and links them instead.

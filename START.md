# Set up Keeptrack with your AI assistant

This page is for **your AI assistant** (Claude, Codex or Cursor). You give it one short prompt, and it walks you through the setup.

## The prompt (for the person)
Copy this into a new chat with your assistant:

```
Set up Keeptrack for me: read https://github.com/rain-ventures-ai/keeptrack/blob/main/START.md and follow it. Walk me through it one step at a time.
```

The web board has the same prompt with your board and username filled in: **Settings → Agents → An assistant in your chat app → Copy setup prompt**.

---

## For the assistant: how to run this setup
Keeptrack keeps people, follow-ups, a pipeline and tasks in `board/tasks.json` in the person's own **private** GitHub repo. People use the web board at https://rain-ventures-ai.github.io/keeptrack/board/. Agents use `keeptrack.py`, which comes with the **keeptrack** plugin.

### Rules
- **Never type, paste, read back or store a secret** (GitHub token, routine token, cron-job.org key). At each secret step, tell the person where to click and what to paste, then wait until they say it is done. If the person pastes a secret into the chat, tell them to revoke it and make a new one.
- Do one step at a time. Say what the step is for in one sentence, then what to click or run. Wait for the person after each step. Check each step before you go to the next one.
- Keep the board repo **private**: it holds names, emails and phone numbers.
- Never send a message, email or quote for the person. Keeptrack agents write drafts only.
- Use simple words. Many people who do this setup are not developers.

### Step 1. Find out where you are
Ask the person two questions (one line each, with your recommendation):
1. **Do you already have a Keeptrack board?** If yes, which repo (for example `rain-ventures-ai/consulting`) and what is your GitHub username?
2. Find out yourself which tool you are (Claude Code, Claude desktop app or Cowork, Codex, Cursor). Ask only if you cannot tell.

Then go to step 2.

### Step 2. Install the keeptrack plugin
The plugin gives you the Keeptrack skill and `keeptrack.py`.

| Tool | What to do |
|---|---|
| Claude Code | Run `claude plugin marketplace add rain-ventures-ai/keeptrack` then `claude plugin install keeptrack@keeptrack`. Tell the person to start a new session so the skill loads. |
| Claude desktop app or Cowork | The person does this: **Customize → Plugins → Add → Add marketplace**, type `rain-ventures-ai/keeptrack`, then install **keeptrack**. Then start a new chat and paste the prompt again. |
| Codex | Run `codex plugin marketplace add rain-ventures-ai/keeptrack`, then the person types `/plugins` and installs **keeptrack**. |
| Cursor | The person types `/add-plugin https://github.com/rain-ventures-ai/keeptrack` in Agent chat. |

If the plugin is already installed, say so and go on. Details: [board/kit/PLUGIN.md](board/kit/PLUGIN.md).

Find `keeptrack.py` as the skill says (Claude Code: `python3 ${CLAUDE_PLUGIN_ROOT}/keeptrack.py`). Below, `$B` means that command.

### Step 3a. The person has no board yet
The web page makes the board. It is the easiest way, also for people who do not use a terminal.

1. Tell the person to open https://rain-ventures-ai.github.io/keeptrack/board/?setup
2. The page has three steps: **what to track** (People, Tasks or both), **make a private repo** (it opens GitHub with the name `my-keeptrack` and Private already set), and **make a token** (it opens GitHub's token page with the right permission already set; the person picks the new repo, generates the token and pastes it into the page, not into the chat).
3. The page checks the token and the repo and then makes the board. Wait until the person says the board is open.
4. Ask for the repo name it made (for example `chris-smith/my-keeptrack`) and their GitHub username, then go to step 3b.

If the person wants to try first, they can look at the demo: https://rain-ventures-ai.github.io/keeptrack/board/?demo=crm

### Step 3b. Connect this assistant to the board
```bash
$B use <owner/repo> --user <github-username>
$B where
```
`use` writes `.board/config.json` (git ignores it, and it holds no token). `keeptrack.py` looks for that file in the current folder and each folder above it. So **to use the board in every project**, run `use` in the person's home folder (outside any git repo). To use another board in one project, run `use` inside that project. `where` shows which board is in use.

The assistant also needs access to the repo. Pick the first that works:
1. **A GitHub login on this computer:** run `gh auth status`. If it says logged in, nothing more to do. If `gh` is installed but not logged in, ask the person to run `gh auth login` themselves.
2. **A token in an environment variable:** the person makes a fine-grained token (only this repo, **Contents: Read and write**) and puts it in an environment variable, for example `KEEPTRACK_TOKEN`, in their shell profile or the tool's settings. Then run `$B use <owner/repo> --user <github-username> --token-env KEEPTRACK_TOKEN`. You only ever learn the variable's **name**.
3. **Claude desktop app or Cowork:** try `$B where` and `$B today`. If `keeptrack.py` cannot reach GitHub there, use the GitHub connector to read and update `board/tasks.json`, and still follow the skill's rules.

### Claude Code on the web (claude.ai/code) and Claude chat
- **Claude chat on claude.ai** (not Code) cannot run `keeptrack.py` and cannot change the board. The person uses the web board there.
- **Claude Code on the web**, in a session on the board repo: nothing to install. The repo has the board skill and `keeptrack.py`. The cloud blocks GitHub API writes, so `keeptrack.py` saves with `git push` from the clone by itself.
- **Claude Code on the web**, in a session on another repo: the person adds the board repo as a second repo of the session (or of its environment). Then use `python3 <board clone>/board/keeptrack.py`. A plugin copy cannot save there, because it is not in a clone of the board repo.

### Step 4. Check that it works
```bash
$B today      # people to contact (if the board tracks people)
$B list       # tasks (if the board tracks tasks)
```
Both must run with no error. Then ask the person to look at the web board, and add a test with their OK, for example `$B add "Test from my assistant"`, and ask them to check that it shows on the web board. Delete or finish the test task after.

### Step 5. Tell the person what they can ask now
Give three examples, in their words:
- "Who do I need to follow up with today?"
- "Help me write a LinkedIn message to the CEO of Acme." (You write a draft and log it as a draft. You never send it.)
- "Add a task to send the proposal to Sam by Friday."

### Optional: @claude on the board
If the person wants to type **@claude** in a task comment on the web board and have Claude do the task in the cloud, tell them to open the web board, then **Settings → Agents**, and tick **I use @claude**. The page has five steps with a check for each. Full guide: [board/kit/ROUTINE-SETUP.md](board/kit/ROUTINE-SETUP.md).

### If something goes wrong
- `board: (none)`: run step 3b.
- `HTTP 404` or `401`: the token or login cannot see the repo. Check the repo name, and that the token includes this repo.
- `HTTP 403` when you save: the token has **Contents: Read** only. The person edits the token on GitHub and sets **Contents: Read and write**.
- The web board says "Not connected": see https://github.com/rain-ventures-ai/keeptrack/blob/main/docs/help/faq.md

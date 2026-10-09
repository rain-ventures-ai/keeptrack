# Set up Keeptrack with your AI assistant

This page is for **your AI assistant** (Claude, Codex or Cursor). You give it one short prompt, and it walks you through the setup.

## The prompt (for the person)
Copy this into your current or a new chat with your assistant:

```
Set up Keeptrack with me in this conversation: read https://github.com/rain-ventures-ai/keeptrack/blob/main/START.md and follow it one step at a time. Do not just explain the options—start by asking me the first setup question.
```

The web board has the same prompt with your board and username filled in: **Settings → Agents → An assistant in your chat app → Copy setup prompt**.

---

## For the assistant: how to run this setup
Keeptrack keeps people, follow-ups, a pipeline and tasks in `board/tasks.json` in the person's own **private** GitHub repo. People use the web board at https://rain-ventures-ai.github.io/keeptrack/board/. Agents use `keeptrack.py`, which comes with the **keeptrack** plugin.

### Rules
- If the person shared the Keeptrack repository link or asked “How about using this?”, treat that as a request to begin setup. Start step 1 in the current conversation instead of replying with a compatibility report. Only ask them to start a new session when a newly installed plugin must be loaded.
- **Never type, paste, read back or store a secret** (GitHub token, routine token, cron-job.org key). At each secret step, tell the person where to click and what to paste, then wait until they say it is done. If the person pastes a secret into the chat, tell them to revoke it and make a new one.
- Do one step at a time. Say what the step is for in one sentence, then what to click or run. Wait for the person after each step. Check each step before you go to the next one.
- Keep the board repo **private**: it holds names, emails and phone numbers.
- Never send a message, email or quote for the person. Keeptrack agents write drafts only.
- Use simple words. Many people who do this setup are not developers.

### Always give the pre-filled token link
As soon as you know the board's `owner/repo`, give the person a **clickable link with that owner and the required
permissions pre-filled**. Do not send them to the generic token list and do not merely describe the permission fields.
Replace `<OWNER>` and `<REPO>` in this template and URL-encode their values:

```
https://github.com/settings/personal-access-tokens/new?name=Keeptrack%20<REPO>&description=Keeptrack%3A%20read%20and%20write%20board%2Ftasks.json%20and%20create%20issues&target_name=<OWNER>&expires_in=90&contents=write&issues=write
```

Say this immediately below the link: **"GitHub has pre-filled the resource owner and Contents/Issues: Read and write.
GitHub cannot preselect a private repo from a link, so under Repository access choose Only select repositories, then
select `<OWNER>/<REPO>`."** The person generates and copies the token; you never see it. If they already made a PAT,
offer the pre-filled new-token link as the simplest fix and also link to
https://github.com/settings/personal-access-tokens so they can edit the existing one themselves.

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
| Claude desktop app or Cowork | The person does this: open https://claude.ai/customize/plugins (or **Customize → Plugins** in the app), click **Add → Add marketplace**, type `rain-ventures-ai/keeptrack`, then install **keeptrack**. Then start a new chat and paste the prompt again. If it says "Failed to add marketplace", try once more with `https://github.com/rain-ventures-ai/keeptrack`; if that also fails, use Claude Code instead (see the next row), where the same plugin installs from the terminal. |
| Codex | Run `codex plugin marketplace add rain-ventures-ai/keeptrack`, then the person types `/plugins` and installs **keeptrack**. |
| Cursor | The person types `/add-plugin https://github.com/rain-ventures-ai/keeptrack` in Agent chat. |

If the plugin is already installed, say so and go on. Details: [board/kit/PLUGIN.md](board/kit/PLUGIN.md).

Useful links for the person: Claude plugins https://claude.ai/customize/plugins · make a private repo https://github.com/new?name=my-keeptrack&visibility=private · edit an existing GitHub token https://github.com/settings/personal-access-tokens (for a new token, use the pre-filled template above) · the web board https://rain-ventures-ai.github.io/keeptrack/board/

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
2. **A token in an environment variable:** give the person the pre-filled token link above for this `owner/repo`. They still select **Only select repositories → this repo**, generate it, and put it in an environment variable such as `KEEPTRACK_TOKEN` in their shell profile or the tool's settings. Then run `$B use <owner/repo> --user <github-username> --token-env KEEPTRACK_TOKEN`. You only ever learn the variable's **name**.
3. **Claude desktop app or Cowork:** try `$B where` and `$B today`. If `keeptrack.py` cannot reach GitHub there, set the person up with Claude Code on the web (next section) instead.

### Claude Code on the web and in the Claude app: the easiest way, with no token
For people who do not use a terminal, this is the main way. It works in a browser (https://claude.ai/code), in the desktop app and in the phone app (the **Code** tab), and it needs **no GitHub token**.
- **Claude Code on the web**, in a session on the board repo: nothing to install. The repo has the board skill and `keeptrack.py`. The cloud blocks GitHub API writes, so `keeptrack.py` saves with `git push` from the clone by itself.
- **Claude Code on the web**, in a session on another repo: the person adds the board repo as a second repo of the session (or of its environment). Then use `python3 <board clone>/board/keeptrack.py`. A plugin copy cannot save there, because it is not in a clone of the board repo.
- **Claude chat** (claude.ai or the phone app, not the Code tab) is not supported. Use Claude Code or the web board.

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

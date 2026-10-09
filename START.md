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
Keeptrack keeps one board in the `board/` folder of the person's own **private** GitHub repo. `board/tasks.json` is
the board's entry point and settings file; current boards keep individual tasks in `board/cards/` and CRM people in
`board/people/`. Tasks and CRM are optional modes of the same board, not separate databases. People use the web board
at https://rain-ventures-ai.github.io/keeptrack/board/. Agents use `keeptrack.py`, which comes with the **keeptrack**
plugin.

### Rules
- If the person shared the Keeptrack repository link or asked “How about using this?”, treat that as a request to begin setup. Start step 1 in the current conversation instead of replying with a compatibility report. Only ask them to start a new session when a newly installed plugin must be loaded.
- If the person already has a board and asks how to use it in **Claude Code cloud and locally**, follow the fast path below. Do not send them through new-board setup.
- **Never type, paste, read back or store a secret** (GitHub token, routine token, cron-job.org key). At each secret step, tell the person where to click and what to paste, then wait until they say it is done. If the person pastes a secret into the chat, tell them to revoke it and make a new one.
- Do one step at a time. Say what the step is for in one sentence, then what to click or run. Wait for the person after each step. Check each step before you go to the next one.
- Keep the board repo **private**: it holds names, emails and phone numbers.
- Never send a message, email or quote for the person. Keeptrack agents write drafts only.
- Use simple words. Many people who do this setup are not developers.

### Fast path: an existing board in Claude Code cloud and locally
When the person already has `<OWNER>/<BOARD-REPO>`, give them these instructions directly:

1. **Claude Code cloud** (claude.ai/code, or the Claude app's **Code** tab): start a new cloud session with the board
   repo selected. If working in a different code repo, add the board repo as the session's second repo. Say:
   **“Use Keeptrack from `<OWNER>/<BOARD-REPO>`. Show my tasks and anything needing attention.”** Nothing needs to
   be installed: cloud sessions do not load plugins, and the board repo already has `CLAUDE.md`, the board skill and
   `board/keeptrack.py`. The Claude GitHub connection supplies repo access; do not ask for a PAT.
2. **Claude Code locally, inside the board repo:** clone or pull the board repo, run `gh auth status`, `cd` into the
   repo and start `claude`. Use the same prompt. Do not install the plugin and do not ask for a PAT when `gh` is logged
   in and can access the repo.
3. **Claude Code locally, from another project:** install the Keeptrack plugin, start a fresh session, and ask Claude
   to use `<OWNER>/<BOARD-REPO>` for that project. The plugin is for this cross-project case.
4. **Ordinary Claude chat is not Claude Code.** A chat at claude.ai that is not in the **Code** tab cannot update the
   board. Use Claude Code or the web board.

Then verify read access with `where` and `list` or `today`. Ask permission before adding a small test task, verify it
appears on the web board, then finish or delete it. Do not merely explain the four cases and stop.

Claude's current documentation confirms that cloud sessions can include multiple repositories and do not load
plugins declared by a repository: https://code.claude.com/docs/en/desktop#install-plugins

### Give a token link only when a token is needed
A PAT is required by the **web board in the browser**. A local agent needs one only when there is no usable `gh` login.
Claude Code cloud working from the board repo does not need one. Never lead a cloud or already-authenticated local user
through token creation.

When a token is needed and you know the board's `owner/repo`, give the person a **clickable link with that owner and
the required permissions pre-filled**. Do not send them only to the generic token list. Replace `<OWNER>` and `<REPO>`
in this template and URL-encode their values:

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

If they already have a board and asked about Claude Code cloud or local use, take the fast path above and then go to
step 4. Otherwise go to step 2.

### Step 2. Make Keeptrack available in this session
First check whether the assistant is already running in the board repo (look for `board/keeptrack.py`). A board repo
contains its own instructions, skill and CLI, so it does **not** need the plugin. Claude Code cloud cannot load plugins;
start its session on the board repo, or add the board repo as a second repo.

Install the plugin only when the assistant is local and working from a different project, or when the tool needs the
general Keeptrack integration:

| Tool | What to do |
|---|---|
| Claude Code locally, from another project | Run `claude plugin marketplace add rain-ventures-ai/keeptrack` then `claude plugin install keeptrack@keeptrack`. Tell the person to start a new session so the skill loads. |
| Claude Code cloud | Do not install a plugin. Select the board repo for the session, or add it as a second repo. |
| Claude desktop app or Cowork | The person does this: open https://claude.ai/customize/plugins (or **Customize → Plugins** in the app), click **Add → Add marketplace**, type `rain-ventures-ai/keeptrack`, then install **keeptrack**. Then start a new chat and paste the prompt again. If it says "Failed to add marketplace", try once more with `https://github.com/rain-ventures-ai/keeptrack`; if that also fails, use the Claude Code fast path above. |
| Codex | Run `codex plugin marketplace add rain-ventures-ai/keeptrack`, then the person types `/plugins` and installs **keeptrack**. |
| Cursor | The person types `/add-plugin https://github.com/rain-ventures-ai/keeptrack` in Agent chat. |

If this is the board repo or the plugin is already installed, say so and go on. Details: [board/kit/PLUGIN.md](board/kit/PLUGIN.md).

Useful links for the person: Claude plugins https://claude.ai/customize/plugins · make a private repo https://github.com/new?name=my-keeptrack&visibility=private · edit an existing GitHub token https://github.com/settings/personal-access-tokens (for a new token, use the pre-filled template above) · the web board https://rain-ventures-ai.github.io/keeptrack/board/

Choose the command once. Below, `$B` means it:
- In the board repo: `python3 board/keeptrack.py`.
- In Claude cloud with the board as a second repo: `python3 <board-repo-folder>/board/keeptrack.py`.
- From an installed plugin: find `keeptrack.py` as the plugin skill says (in Claude Code it is under
  `${CLAUDE_PLUGIN_ROOT}`).

### Step 3a. The person has no board yet
The web page makes the board. It is the easiest way, also for people who do not use a terminal.

1. Tell the person to open https://rain-ventures-ai.github.io/keeptrack/board/?setup
2. The page has three steps: **what to track** (People, Tasks or both), **make a private repo** (it opens GitHub with the name `my-keeptrack` and Private already set), and **make a token** (it opens GitHub's token page with the right permission already set; the person picks the new repo, generates the token and pastes it into the page, not into the chat).
3. The page checks the token and the repo and then makes the board. Wait until the person says the board is open.
4. Ask for the repo name it made (for example `chris-smith/my-keeptrack`) and their GitHub username, then go to step 3b.
If the person wants to try first, they can look at the demo: https://rain-ventures-ai.github.io/keeptrack/board/?demo=crm

### Step 3b. Connect this assistant to the board
If `$B` is the copy inside the board repo, it gets the repo and branch from that clone. Do not run `use`; just verify:

```bash
$B where
```

If `$B` is the plugin copy in another local project, connect that project once:

```bash
$B use <owner/repo> --user <github-username>
$B where
```
`use` writes `.board/config.json` (git ignores it, and it holds no token). `keeptrack.py` looks for that file in the current folder and each folder above it. So **to use the board in every project**, run `use` in the person's home folder (outside any git repo). To use another board in one project, run `use` inside that project. `where` shows which board is in use.

`AGENTS.md` is not part of the data format and the web board does not need it. A board repo that agents work inside
should have it: `keeptrack.py init` creates `AGENTS.md` plus `CLAUDE.md`, and they tell repo-local agents to use the CLI
instead of editing board files. When the assistant uses the installed plugin from another project, the plugin skill
provides those operating rules instead.

The assistant also needs access to the repo. Pick the first that applies:
1. **Claude Code cloud with the board repo in the session:** use its GitHub repo access. No PAT.
2. **A GitHub login on this computer:** run `gh auth status`. If it says logged in and can see the repo, nothing more
   is needed. Otherwise ask the person to run `gh auth login` themselves.
3. **A token in an environment variable:** use this only when there is no usable GitHub login. Give the person the
   pre-filled token link above. They put it in an environment variable such as `KEEPTRACK_TOKEN`; you only learn the
   variable's **name**. Then run `$B use <owner/repo> --user <github-username> --token-env KEEPTRACK_TOKEN` when using
   the plugin copy.
4. **Claude desktop app or Cowork:** try `$B where` and `$B today`. If `keeptrack.py` cannot reach GitHub there, set
   the person up with Claude Code cloud instead.

### Claude Code on the web and in the Claude app: the easiest way, with no token
For people who do not use a terminal, this is the main way. It works in a browser (https://claude.ai/code), in the desktop app and in the phone app (the **Code** tab), and it needs **no GitHub token**.
- **Claude Code on the web**, in a session on the board repo: nothing to install. Plugins are unavailable in cloud
  sessions, but none is needed: the repo has `CLAUDE.md`, the board skill and `keeptrack.py`. The cloud blocks GitHub
  API writes, so `keeptrack.py` saves with `git push` from the clone by itself.
- **Claude Code on the web**, in a session on another repo: the person adds the board repo as a second repo of the session (or of its environment). Then use `python3 <board clone>/board/keeptrack.py`. A plugin copy cannot save there, because it is not in a clone of the board repo.
- **Claude chat** (claude.ai or the phone app, not the Code tab) is not supported. Use Claude Code or the web board.

### Step 4. Check that it works
```bash
$B today      # people to contact (if the board tracks people)
$B list       # tasks (if the board tracks tasks)
```
Both must run with no error. Then ask the person to look at the web board, and add a test with their OK, for example `$B add "Test from my assistant"`, and ask them to check that it shows on the web board. Delete or finish the test task after.

Then offer the guided import once: **"Would you like me to bring in existing people and clients (CRM), tasks, or
both?"** A yes hands over to `onboard-keeptrack`. If the skill is not available in this session, do not substitute
your own import process; start a fresh session on the board repo after the plugin/kit is current.

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

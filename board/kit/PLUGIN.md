# Keeptrack plugins: Claude, Codex, Cursor (and chat apps)

One plugin folder serves every tool: `board/kit/` in `rain-ventures-ai/keeptrack`. It holds `keeptrack.py` (the command-line tool), `skills/keeptrack/SKILL.md` (daily use and board-status audits), `skills/keeptrack-notes/SKILL.md` (meeting transcript and notes import), `skills/keeptrack-email/SKILL.md` (mailbox-to-contact reconciliation), `skills/onboard-keeptrack/SKILL.md` (guided CRM/task import) and one small manifest for each tool. The specialist skills are also copied into every board repo by the kit, so they can be discovered before or after opening the board repo.

## Claude Code: first choose where the session runs

**Inside a board repo, no plugin is needed.** The repo already contains `CLAUDE.md`, `.claude/skills/board/` and
`board/keeptrack.py`.

- **Claude Code cloud** (claude.ai/code or the Claude app's Code tab): select the board repo when starting the session.
  If the work is in another code repo, add the board repo as the second repo. Plugins are not available in cloud
  sessions, so always use the copy of `keeptrack.py` in the board clone. The Claude GitHub connection is the
  authentication; do not create a PAT for Claude cloud.
- **Claude Code locally in the board repo:** run `gh auth status`, start `claude` from the repo, and use
  `python3 board/keeptrack.py`. No plugin or PAT is needed when `gh` can access the repo.
- **Claude Code locally in another project:** install the plugin below, then connect that project to the board once.

Official Claude documentation: cloud sessions can have multiple repos, but do not load installed or repo-declared
plugins: https://code.claude.com/docs/en/desktop#install-plugins

### Install for another local project
Check first with `claude plugin list` (or `/plugin`): if `keeptrack@keeptrack` is there, skip this.
```bash
claude plugin marketplace add rain-ventures-ai/keeptrack
claude plugin install keeptrack@keeptrack
```
Or in a session: `/plugin marketplace add rain-ventures-ai/keeptrack`, then `/plugin install keeptrack@keeptrack`.

**Keep it updated:** `/plugin` → **Marketplaces** → **keeptrack** → **Enable auto-update**. Claude Code updates the plugin when `version` in `.claude-plugin/plugin.json` changes (`0.<kit version>.<patch>`), so bump it with each release. To update by hand: `claude plugin marketplace update keeptrack`.

Settings form (`~/.claude/settings.json`):
```json
{
  "extraKnownMarketplaces": { "keeptrack": { "source": { "source": "github", "repo": "rain-ventures-ai/keeptrack" }, "autoUpdate": true } },
  "enabledPlugins": { "keeptrack@keeptrack": true }
}
```
The plugin gives the skill `keeptrack:keeptrack`, `keeptrack.py` at `${CLAUDE_PLUGIN_ROOT}/keeptrack.py`, and a hook (`hooks/auto-heartbeat.sh`) that sends a quiet heartbeat while a task claim is active. Its directory icon is `.claude-plugin/icon.png`.

## Claude Desktop and Cowork (no terminal)
First look in **Customize → Plugins**: if **keeptrack** is already installed, just check it is switched on. If the **rain-ventures-ai/keeptrack** marketplace is already listed, install **keeptrack** from it. Otherwise: **Customize → Plugins → Add → Add marketplace**, type `rain-ventures-ai/keeptrack`, then install **keeptrack**. A Team or Enterprise admin can add the marketplace for the whole organisation. Then say, for example, "Who do I need to follow up with today?" or "Help me write a LinkedIn message to the CEO of Acme".

The plugin is not used by the **Code** tab of the Claude phone or desktop app, or by claude.ai/code: those are Claude Code cloud (above). Ordinary Claude chat on claude.ai or the phone app cannot run `keeptrack.py`; it uses the Relay connector (below).

Not yet checked: whether the Cowork sandbox lets `keeptrack.py` reach api.github.com. If it cannot, use Claude Code on the web or in the Claude app's **Code** tab, in a session on the board repo: it saves with no token.

## Codex (CLI, IDE extension, app)
```bash
codex plugin marketplace add rain-ventures-ai/keeptrack
```
Then install **keeptrack** from the plugin browser (`/plugins`). The marketplace file is `.agents/plugins/marketplace.json`; the plugin manifest is `board/kit/.codex-plugin/plugin.json`. Codex also reads plain skills from `.agents/skills/` in a repo or `~/.agents/skills/`. The skill finds `keeptrack.py` two folders above its `SKILL.md` (`../../keeptrack.py`), so copy both with this layout:
```
.agents/
  keeptrack.py                 <- board/kit/keeptrack.py
  CARDS.md                     <- board/kit/CARDS.md
  skills/
    keeptrack/
      SKILL.md                 <- board/kit/skills/keeptrack/SKILL.md
```
That is `.agents/skills/keeptrack/` for the skill and `.agents/keeptrack.py` for the CLI (not `.agents/skills/keeptrack.py`). The same shape works under `~/.agents/`. Use `BOARD_AGENT=codex` and your own `BOARD_SESSION`. Codex has no heartbeat hook: while it holds a claim it runs `keeptrack.py heartbeat` itself at least every 15 minutes.

## Cursor
In Agent chat: `/add-plugin https://github.com/rain-ventures-ai/keeptrack`. A team admin can import the repo under **Dashboard → Settings → Plugins → Team Marketplaces**. The manifests are `.cursor-plugin/marketplace.json` and `board/kit/.cursor-plugin/plugin.json`. Use `BOARD_AGENT=cursor`.

## ChatGPT, Grok and Claude chat (no shell)
These apps cannot run `keeptrack.py`. They reach a board through the **Relay connector**, a small remote MCP server
the owner hosts (`connector/README.md` in `rain-ventures-ai/keeptrack-relay`, a private repo: ask the board owner). It runs the board's own `keeptrack.py`
for every read and write, puts new cards in Backlog, and lets only an app the owner marks `approve` move a card to
To do (and starts the dispatcher, or edits cards already approved). Each app gets its own URL,
`https://<host>/mcp/<client token>`. That URL is a secret: anyone who has it can act as that app, so rotate it if it
leaks.

- **ChatGPT:** Settings, Apps and Connectors, developer mode, Create, the app's own URL, "No authentication". Write
  tools need a plan that allows them.
- **Grok:** grok.com/connectors, New Connector, Custom, the app's own URL.
- **Claude chat** (claude.ai, Desktop, mobile): Customize, Connectors, Add custom connector, the app's own URL, "No
  sign in". Add it on the web or Desktop; it then works on mobile.

Set-up for every place an assistant runs (chat apps, Claude Code projects and terminals, Codex, Grok Bot, routines):
`relay/ENVIRONMENTS.md` in `keeptrack-relay` (private). Without the connector, use **🤖 Copy for AI** on a person in the web
board: paste it into the app, get the draft, and log it on the board yourself.

## Each project: which board?
In a project that is not the board repo, run (or ask the agent to run):
```bash
python3 <plugin>/keeptrack.py use your-name/my-keeptrack --user your-name --token-env KEEPTRACK_TOKEN
python3 <plugin>/keeptrack.py where
```
- `use` writes `.keeptrack/config.json` and `.keeptrack/.gitignore` (`*`), so it is never committed and teammates never see it. It asks GitHub for the default branch. `--project <name>` makes that board project this repo's default scope. The older `.board/config.json` is still read.
- The plugin's session-start hook prints a few lines (board, project, your open cards) only in a repo with that file, or with `BOARD_REPO` set; everywhere else it prints nothing. The heartbeat hook checks for a claim with plain shell first, so projects without Keeptrack pay nothing.
- The file holds the repo, branch, path and user, and only the **name** of the environment variable with the token. Never the token.
- Auth: a `gh` login that can see the board repo, or a fine-grained token (Contents: Read and write on that repo) in that variable or in `BOARD_TOKEN`.

## What it runs, sends and changes
Facts from the code, so you can decide what to allow. File names are in `rain-ventures-ai/keeptrack`.

**What leaves your machine (the command-line tool, `board/kit/keeptrack.py`).**
- Board reads and writes go to the GitHub API for the board repo only: `https://api.github.com`, or `BOARD_API` when
  set (`http()`). The token is `BOARD_TOKEN` (else `GH_TOKEN` or `GITHUB_TOKEN`), sent as a Bearer header to that host.
  Without `BOARD_TOKEN`, and with `gh` installed, it runs `gh api` instead, under your own `gh` sign-in.
- In Claude's cloud sandbox, where API writes are refused, it commits the changed board files and runs `git push` to the
  board clone's own `origin` (`BOARD_WRITE=git` forces this, `BOARD_WRITE=api` turns it off).
- `kit-check`, `kit-update` and the `min_kit` check read the published kit: `git ls-remote` of
  `https://github.com/rain-ventures-ai/keeptrack`, then files from `raw.githubusercontent.com` (or a shallow
  `git clone` when that is blocked), or `BOARD_KIT_URL` when set. These requests carry no token and no board data.
- A hosted board (`BOARD_BACKEND=hosted`) talks only to its `BOARD_API`, never to GitHub.
- Nothing else: no analytics, no telemetry, no model calls. Agents that run the tool send what they send themselves.

**What leaves the browser (the web board, `board/board.js`).**
- The GitHub API (`api.github.com`, or the API you set), with the token you gave the page, kept in this browser's local
  storage.
- Only if you set up "@claude" on the board (Settings, Agents): `api.cron-job.org`, with your cron-job.org key. Each
  request makes a one-off job that holds your routine's fire URL (`api.anthropic.com`), its token, and a short request
  naming the board repo, the task number and who asked. The page deletes the job once it has run.
- Only if you add the weather widget: `api.open-meteo.com`, with the latitude and longitude you chose, no cookies and no
  referrer.

**Programs it starts.**

| Program | When |
|---|---|
| `git` | To find the board repo and branch from the clone, to read and write board files in a clone, the git-push fallback, and the kit checks above |
| `gh` | `gh api` and `gh auth token`, when `BOARD_TOKEN` is not set and `gh` is installed |
| `python3` on an automation's `check.py` or tests | Only for an automation pack you installed (`automation tick`, `setup`, `test`). It runs with a private temporary home, bounded output and a time limit, and on Linux without network access (`unshare -rn`) unless its manifest asks for network and you granted it at install |
| `unshare -rn true` | To test whether that network isolation is available (Linux) |

**What the hooks see and do** (`board/kit/hooks/`, and `board/kit/templates/settings.json` in a board repo).
- Neither hook reads the hook input Claude Code sends (tool names, arguments, prompts). They look only at files on disk.
- `PostToolUse` (`auto-heartbeat.sh`, after every tool call): walks up from the current folder looking for a claim
  record (`.keeptrack/claim.json`, `.board/claim.json` or `.board-claim.json`) with plain shell. With no record, a record
  with no card, a symlinked one or an attended claim, it stops there and starts nothing. Otherwise it runs
  `keeptrack.py auto-heartbeat`, which saves the claim's heartbeat time on the board at most every 15 minutes per card,
  and only for this session's own claims. The board repo's own hook runs the same command.
- `SessionStart` (`session-start.sh`): only where a personal `.keeptrack/config.json` (not tracked by git) or
  `BOARD_REPO` exists, it runs `keeptrack.py here --hook`, which reads the board and prints a few lines: the board, the
  project and your open cards. It writes nothing. Everywhere else it prints nothing.

**What it writes on your machine.**
- `.board-claim.json` at a board clone's root, or `.keeptrack/claim.json` in another project: the active claim, for the
  heartbeat hook. `done` and `release` clear it.
- `.keeptrack/config.json` and `.keeptrack/.gitignore` (`*`), only when you run `use`. They name the board and the
  name of the token variable, never the token.
- In a board clone: the board files a command changes (then committed and pushed, or saved through the API), the kit
  files on `kit-update`, and the automation state under `automation/` once you install one.
- A temporary folder for each automation check, removed when the check ends. When `raw.githubusercontent.com` is
  blocked, a shallow kit clone in the system temporary folder (`board-kit-…`), which is left for the system to clear.

## Limits
- From another project there is no clone of the board repo, so the git-push fallback is not available. In Claude's cloud sandbox (which blocks GitHub API writes) writes fail there.
- Claude Code cloud does not load plugins. Add the board repo to the cloud session and use its repo-local skill and CLI.
- `kit-check`, `kit-update` and `init` work only inside a board repo.
- Codex and Cursor manifest fields come from their current documentation (October 2026). Check them against `codex` and Cursor's plugin validator before the public launch.

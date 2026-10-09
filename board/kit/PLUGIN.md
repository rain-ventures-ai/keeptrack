# Keeptrack plugins: Claude, Codex, Cursor (and ChatGPT)

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
```bash
claude plugin marketplace add rain-ventures-ai/keeptrack
claude plugin install keeptrack@keeptrack
```
Or in a session: `/plugin marketplace add rain-ventures-ai/keeptrack`, then `/plugin install keeptrack@keeptrack`.

**Keep it updated:** `/plugin` → **Marketplaces** → **keeptrack** → **Enable auto-update**. The Claude manifest has no `version`, so each commit is a new version. To update by hand: `claude plugin marketplace update keeptrack`.

Settings form (`~/.claude/settings.json`):
```json
{
  "extraKnownMarketplaces": { "keeptrack": { "source": { "source": "github", "repo": "rain-ventures-ai/keeptrack" }, "autoUpdate": true } },
  "enabledPlugins": { "keeptrack@keeptrack": true }
}
```
The plugin gives the skill `keeptrack:keeptrack`, `keeptrack.py` at `${CLAUDE_PLUGIN_ROOT}/keeptrack.py`, and a hook that sends a quiet heartbeat while a task claim is active.

## Claude Desktop and Cowork (no terminal)
**Customize → Plugins → Add → Add marketplace**, type `rain-ventures-ai/keeptrack`, then install **keeptrack**. A Team or Enterprise admin can add the marketplace for the whole organisation. Then say, for example, "Who do I need to follow up with today?" or "Help me write a LinkedIn message to the CEO of Acme".

Not yet checked: whether the Cowork sandbox lets `keeptrack.py` reach api.github.com. If it cannot, use Claude Code on the web or in the Claude app's **Code** tab, in a session on the board repo: it saves with no token.

## Codex (CLI, IDE extension, app)
```bash
codex plugin marketplace add rain-ventures-ai/keeptrack
```
Then install **keeptrack** from the plugin browser (`/plugins`). The marketplace file is `.agents/plugins/marketplace.json`; the plugin manifest is `board/kit/.codex-plugin/plugin.json`. Codex also reads plain skills from `.agents/skills/` in a repo or `~/.agents/skills/`. The skill finds `keeptrack.py` two folders above its `SKILL.md` (`../../keeptrack.py`), so copy both with this layout:
```
.agents/
  keeptrack.py                 <- board/kit/keeptrack.py
  skills/
    keeptrack/
      SKILL.md                 <- board/kit/skills/keeptrack/SKILL.md
```
That is `.agents/skills/keeptrack/` for the skill and `.agents/keeptrack.py` for the CLI (not `.agents/skills/keeptrack.py`). The same shape works under `~/.agents/`. Use `BOARD_AGENT=codex`.

## Cursor
In Agent chat: `/add-plugin https://github.com/rain-ventures-ai/keeptrack`. A team admin can import the repo under **Dashboard → Settings → Plugins → Team Marketplaces**. The manifests are `.cursor-plugin/marketplace.json` and `board/kit/.cursor-plugin/plugin.json`. Use `BOARD_AGENT=cursor`.

## ChatGPT
ChatGPT's own GitHub app can only read repositories, so it cannot update the board. To let ChatGPT update Keeptrack we need a small hosted MCP server (a later step). Until then, use **🤖 Copy for AI** on a person in the web board: paste it into ChatGPT, get the draft, and log it on the board yourself.

## Each project: which board?
In a project that is not the board repo, run (or ask the agent to run):
```bash
python3 <plugin>/keeptrack.py use your-name/my-keeptrack --user your-name --token-env KEEPTRACK_TOKEN
python3 <plugin>/keeptrack.py where
```
- `use` writes `.board/config.json` and `.board/.gitignore` (`*`), so it is never committed. It asks GitHub for the default branch.
- The file holds the repo, branch, path and user, and only the **name** of the environment variable with the token. Never the token.
- Auth: a `gh` login that can see the board repo, or a fine-grained token (Contents: Read and write on that repo) in that variable or in `BOARD_TOKEN`.

## Limits
- From another project there is no clone of the board repo, so the git-push fallback is not available. In Claude's cloud sandbox (which blocks GitHub API writes) writes fail there.
- Claude Code cloud does not load plugins. Add the board repo to the cloud session and use its repo-local skill and CLI.
- `kit-check`, `kit-update` and `init` work only inside a board repo.
- Codex and Cursor manifest fields come from their current documentation (October 2026). Check them against `codex` and Cursor's plugin validator before the public launch.

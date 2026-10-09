# Where your assistant runs

Keeptrack has two parts:

- **People use the web board.** You look at Today, People, the pipeline and tasks. You add people, assign tasks and move cards. You do not install anything.
- **AI assistants use `keeptrack.py`.** Every board repo contains this small tool and its agent instructions. The
  Keeptrack plugin supplies another copy for working from other local projects. Both read and change the same `board/`
  folder as the web board in your private repo.

You do not run `keeptrack.py` yourself. You ask your assistant, for example "Who do I need to follow up with today?", and it runs the tool.

## Claude Code: cloud and local

If you already have a board at `<OWNER>/<BOARD-REPO>`, this is all you need:

### In Claude Code cloud

1. Open https://claude.ai/code or the Claude app's **Code** tab and start a cloud session.
2. Select `<OWNER>/<BOARD-REPO>`. If you are working in a different code repo, add the board repo as the second repo.
3. Say: **“Use Keeptrack from `<OWNER>/<BOARD-REPO>`. Show my tasks and anything needing attention.”**

No plugin or PAT is needed. Cloud sessions do not load plugins; the board repo itself supplies `CLAUDE.md`, the board
skill and `board/keeptrack.py`. The Claude GitHub connection lets the session clone and push the repo.

### In Claude Code locally

```bash
gh auth status
git clone git@github.com:<OWNER>/<BOARD-REPO>.git   # skip if already cloned
cd <BOARD-REPO>
git pull
claude
```

Then use the same prompt. If `gh auth status` says you are not logged in, run `gh auth login`. No Keeptrack plugin or
PAT is needed inside the board repo. Install the plugin only when you want Claude in a **different local project** to
use the board.

Ordinary Claude chat is not Claude Code and cannot update the board. Use the **Code** tab or the web board.

## Which set-up is best for me?

| You are... | Use |
|---|---|
| Not a terminal user | The web board, and **Claude Code in the Claude app** (the **Code** tab, or claude.ai/code in a browser), in a session on your board repo. It needs no token. |
| A developer | The web board, and **Claude Code**, **Codex** or **Cursor** on your computer. |
| Away from your computer | The web board on your phone, and the **Code** tab in the Claude phone app. |

## Summary

| Assistant | Where `keeptrack.py` runs | Do you need Python? | How it gets into your repo | Status |
|---|---|---|---|---|
| Claude Desktop (Cowork) | Cowork's own machine on your computer | No. Cowork has it. | A token | Writes to GitHub not tested yet |
| Claude Code on your computer | Your computer | Yes (Python 3) | `gh auth login` or a token | Works |
| Claude Code on the web and in the Claude app (Code tab) | A Claude cloud machine | No. It has Python. | The Claude GitHub app, with `git push`. No token. | Works, from a session on your board repo |
| Claude chat (not the Code tab) | - | - | - | Not supported. Use the Code tab. |
| Codex on your computer | Your computer | Yes (Python 3) | `gh auth login` or a token | Works |
| Codex cloud | A Codex cloud machine | No | Needs internet access to GitHub | Not tested yet |
| Cursor | Your computer | Yes (Python 3) | `gh auth login` or a token | Works |
| ChatGPT | Nowhere | - | ChatGPT cannot change the board yet | Use **🤖 Copy for AI** |

To install the plugin when it is actually needed, see [AI assistants](ai-assistants.md).

## Claude Desktop (Cowork)

This is the easiest set-up if you do not use a terminal.

1. Install the Claude desktop app and open **Cowork**.
2. Install the **keeptrack** plugin (see [AI assistants](ai-assistants.md)).
3. Ask "Who do I need to follow up with today?". The first time, the assistant asks for your board repo (for example `your-name/my-keeptrack`) and your GitHub username.

Cowork runs the tool in its own small Linux machine on your computer. That machine has Python, so you do not install Python on your Mac or PC.

The assistant needs a token to read and write your board. Use a fine-grained token for your board repo only, with **Contents: Read and write** (the same kind of token as the web board). Never paste the token into the chat.

> Status: we have not tested writes from Cowork to GitHub yet. If a write fails, do the step in the web board and tell us.

## Claude Code, Codex or Cursor on your computer

These run `keeptrack.py` on your own computer, so your computer needs **Python 3** and access to GitHub.

**Python 3**
- **Mac:** open Terminal and type `python3 --version`. If Python is not installed, macOS shows a box that offers the **Command Line Tools**. Click **Install** and wait a few minutes. This also installs `git`.
- **Windows:** install Python 3 from python.org or the Microsoft Store.
- **Linux:** Python 3 is usually installed already.

`keeptrack.py` uses only standard Python. You do not install other packages.

**Access to your repo** (one of these):
- `gh auth login` with the GitHub command-line tool. This is the easiest for developers.
- A fine-grained token in an environment variable, for example `KEEPTRACK_TOKEN`. Tell the assistant the **name** of the variable, never the token.

A fine-grained token covers the repos of one owner only. If you have boards under two owners (for example your own account and a company), you need one token for each owner.

## Claude Code on the web (cloud)

Claude Code on the web runs in a Claude cloud machine. It has Python.

- Start the session **on your board repo** (add the repo to the environment). Then the tool can save with `git push`.
- The cloud machine blocks writes through the GitHub API. This is not a token problem. `keeptrack.py` changes to `git push` by itself when it runs inside a clone of the board repo.
- From a session on a different repo, add the board repo as a second repo of the session. Then use `keeptrack.py` from that clone. Or do the step in the web board.
- The same works in the Claude desktop and phone apps: open the **Code** tab and start a session on your board repo.

## Codex cloud

Codex cloud tasks run in a cloud machine that has Python. The machine must be allowed to connect to `github.com` and `api.github.com`, and it needs a token. We have not tested this yet.

## ChatGPT

ChatGPT cannot read or change your board yet. A connector for ChatGPT is planned. Until then:

1. On a person, click **🤖 Copy for AI**.
2. Paste it into ChatGPT and ask for a draft.
3. Send the message yourself, then log it on the board.

## How the tool reads and saves your board

- Each command reads only the board subtree: `board/tasks.json` plus the task, CRM-person and archive files under `board/cards/`, `board/people/` and `board/archive/`. It does not download the whole repo.
- It always reads the newest version, so the assistant sees changes that you make in the web board at once. It keeps a copy in `.board/cache` (never committed). When the file has not changed, GitHub says so, and the tool uses the copy. This is fast and does not count against your GitHub limit.
- When it saves, GitHub checks that nobody else saved first. If somebody did, the tool reads the board again, makes the change again and saves. Your changes and the assistant's changes are not lost.
- In Claude Code on the web, the tool uses `git fetch` for the board branch. This downloads only new changes. It does not change the files in your folder.

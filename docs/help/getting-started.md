# Getting started

You need a GitHub account. Setup takes about ten minutes. You do not need a terminal.

You can do it all on a phone: open the setup page in your phone's browser. See [On your phone](where-agents-run.md#on-your-phone-or-at-claudeai-in-a-browser) for connecting Claude there too.

Do you want to look first? On the welcome page, open a demo board: **people and pipeline** or **tasks**. You can also add `?demo=crm` or `?demo=board` at the end of the board address. The demo board is read-only and has invented data. Nothing you do there is saved.

The setup wizard has three steps. To open it at any time, add `?setup` to the board address. In a demo board, click **Create my own board**.

## 1. What to track
Select **People** (follow-ups and a pipeline), **Tasks**, or both. Type a name for your board, for example "Sales". Click **Next**.

## 2. Make a private repo
1. Click **Open GitHub: make a private repo**. GitHub opens with the name `my-keeptrack`.
2. Make sure that **Private** is selected. Click **Create repository**.
3. Come back to the wizard and click **I made it**.

> Keep the repo private. It will hold names, emails and phone numbers.

## 3. Connect
The token lets the web board read and write your repo.
1. Click **Open GitHub: make a token**. GitHub opens with most fields filled in.
2. Under **Repository access**, select **Only select repositories**, then select your new repo.
3. Make sure that **Contents** is **Read and write**.
4. Click **Generate token**, copy it, and paste it in the wizard.

The wizard finds your GitHub username and your repo by itself. Green ticks show that the token works, that it can change the repo, and that the repo is private. Click **Create my board**. Keeptrack creates the `board/` data folder, starting with `board/tasks.json`, and opens it. Tasks and CRM people get their own files as you add them.

The token stays in this browser only. The board sends it only to `api.github.com`. Treat it like a password.

### Finding your way around
The board opens on **Today**: who to contact, what is due, and two shortcuts to **Kanban** (your tasks) and **People** (your CRM). The bar at the bottom of the screen goes everywhere: **Today**, **Tasks**, **People**, **Find** (search, and a quick way to jump to any view) and **Menu** (refresh, copy, help and **Settings**). In Tasks and People, the strip at the top switches views: Kanban, List, Calendar, Schedule and Activity, or People and Pipeline. After each change, the bar shows **Undo** for a few seconds.

New to Keeptrack? Tap **Show me around** on Today, or choose **Menu → Show me around** at any time, for a one-minute tour.

Prefer everything in the top bar? Choose **Settings → General → Layout → Classic**. The layout is saved in this browser only.

## 4. Add your first people
Type in the box at the bottom of **Today** or **People**:
```
Sarah Jones | Acme | CEO | sarah@acme.com
```
The order is name, company, role and email. Only the name is necessary. Press Enter. The person opens so that you can add a next step.

Have a spreadsheet of contacts? Ask your AI assistant to add them (see [AI assistants](ai-assistants.md)). It checks for duplicates.

## 5. Use it on another device
In **⚙️ Settings → General**, click **Copy setup link** and open the link on your other device. The link holds your token, so send it only to yourself. To use Claude on your phone too, see [On your phone](where-agents-run.md#on-your-phone-or-at-claudeai-in-a-browser).

## Next
- [People and follow-ups](people-and-follow-ups.md)
- [AI assistants](ai-assistants.md)

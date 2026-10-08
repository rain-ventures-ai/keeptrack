# Getting started

You need a GitHub account. Setup takes about ten minutes. You do not need a terminal.

Do you want to look first? On the welcome page, open a demo board: **people and pipeline** or **tasks**. You can also add `?demo=crm` or `?demo=board` at the end of the board address. The demo board is read-only and has invented data. Nothing you do there is saved.

## 1. Make a private repo
1. Open the Keeptrack web board. The **Welcome to Keeptrack** page opens.
2. Click **Open GitHub: new private repo**. GitHub opens with the name `my-keeptrack`.
3. Make sure that **Private** is selected. Click **Create repository**.

> Keep the repo private. It will hold names, emails and phone numbers.

## 2. Make an access token
The token lets the web board read and write one file in your repo.
1. On the Welcome page, click **Open GitHub: new token**. GitHub opens with most fields filled in.
2. Under **Repository access**, select **Only select repositories**, then select your new repo.
3. Make sure that **Contents** is **Read and write**.
4. Click **Generate token** and copy it.

The token stays in this browser only. The board sends it only to `api.github.com`. Treat it like a password.

## 3. Connect
1. On the Welcome page, type the repo as `your-name/my-keeptrack`, and your GitHub username.
2. Paste the token.
3. Type a name for your board, for example "Sales".
4. Select what you want to keep track of: **People, follow-ups and pipeline**, **Tasks**, or both.
5. Click **Create my board**.

The board checks that the repo is private and that the token can write to it. Then it makes the file `board/tasks.json` in your repo and opens **Today**.

## 4. Add your first people
Type in the box at the bottom of **Today** or **People**:
```
Sarah Jones | Acme | CEO | sarah@acme.com
```
The order is name, company, role and email. Only the name is necessary. Press Enter. The person opens so that you can add a next step.

Have a spreadsheet of contacts? Ask your AI assistant to add them (see [AI assistants](ai-assistants.md)). It checks for duplicates.

## 5. Use it on another device
In **⚙️ Settings → General**, click **Copy setup link** and open the link on your other device. The link holds your token, so send it only to yourself.

## Next
- [People and follow-ups](people-and-follow-ups.md)
- [AI assistants](ai-assistants.md)

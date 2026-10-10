# Questions and problems

**The board says "Not connected".**
Open **⚙️ Settings → Boards**. Check the repo name (`owner/name`) and paste the token again. Then open **Settings → Checks** and click **Run checks**. It tells you what is wrong. **Copy report** gives a report without your token.

**"Cannot see repository" or a 404 error.**
- The repo name has a typing error, or
- the token does not include this repo, or
- the repo belongs to an organisation, and the token's **Resource owner** is your own account. Make a new token with the organisation as Resource owner.

**The board says the file does not exist.**
The repo has no `board/tasks.json` yet, or the branch is wrong. New repos use the branch `main`. Older boards use `master`. Check the branch in **Settings → Boards**.

**I see a big warning that my board is public.**
Make the repo private. See [Privacy and security](privacy-and-security.md).

**My change says "Not saved".**
Someone (or an agent) changed the board at the same time. The board tries again by itself. If it asks, select which version to keep.

**"Board saved by newer tools".**
Another device or agent uses a newer version of Keeptrack. Reload the page (**Settings → General → Update to latest version**). Agents: run `keeptrack.py kit-update` in the board repo.

**My AI assistant cannot write to the board.**
- It needs a GitHub login or a token: see [AI assistants](ai-assistants.md).
- Claude's cloud (claude.ai/code or the app's **Code** tab) blocks writes through the GitHub API. Start the session on the board repo, so the tool saves with `git push`. See [Where your assistant runs](where-agents-run.md).
- Ordinary Claude chat on claude.ai or the phone app (not the **Code** tab) cannot write to the board at all.

**I do not see Today, People and Pipeline (or the task views).**
Your board shows only what you track (`settings.modes`). Ask your assistant to change it.

**How do I get reminders?**
Today shows what is due each time you open the board. While a tab is open, **Settings → Alerts** can show browser alerts. Reminders when the board is closed are not available yet.

**The board says "Read-only".**
The banner tells you why:
- **Demo board:** this is the example board. To make your own board, click **Create my own board**.
- **Public board with no token:** you can read the board but not change it. To change it, add a token in **Settings → Boards**.
- **Your token cannot change this board:** the token has **Contents: Read** only. On GitHub, edit the token and set **Contents** to **Read and write**, or make a new token. Then paste it again in **Settings → Boards**.

**Does the demo show my own boards?**
No. A demo link (`?demo=crm` or `?demo=board`) uses empty settings in memory. It does not read or change your boards, tokens or routines in this browser. Only the theme is shared.

**@claude does not start, or I want to check it.**
Open **⚙️ Settings → Agents**. Each setup step shows ✓ when it is done. Open **Test and fix problems**: **Test cron-job.org** checks cron-job.org without starting Claude, and **What happened to each send** shows where a send stopped. **Copy debug report** gives a report without tokens or keys.

**Is the board fast with a lot of data?**
Yes. A board with 500 tasks and 300 people changes views in less than a quarter of a second. Long lists show the first 150 items and a **Show more** button. When the file gets large, archive old items: see [Search and archive](search-and-archive.md). The page shows the last copy that it loaded at once, and then gets the newest version from GitHub. You can make changes when the status says "Synced".

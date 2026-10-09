# Privacy and security

## Where your data is
- All your data is in the `board/` folder of **your** GitHub repo. `board/tasks.json` holds settings and indexes; tasks and CRM people have individual files under `board/cards/` and `board/people/`.
- There is no Keeptrack server and no Keeptrack database. Nobody at Keeptrack can see your data.
- The web page talks only to `api.github.com`.

## Keep the repo private
Contacts are personal data (UK GDPR). If the repo is **public**, everybody can read it. The board shows a large warning on each load if your repo is public. To fix it: on GitHub, open your repo → **Settings** → **Danger Zone** → **Change visibility** → **Private**.

## Your token
- The token is kept only in this browser (local storage). It is sent only to `api.github.com`.
- Make the token for **one repo only**, with **Contents: Read and write**.
- **Settings → General → Copy setup link** and **Copy settings code** include the token. Send them only to yourself.
- To remove the token from this browser: **Settings → Boards → Forget token**. This also removes the copy of the board and its archive that this browser keeps (in IndexedDB) so that the page opens quickly.
- A token with **Contents: Read** only is safe for people who must only look. The board then shows a **Read-only** banner and does not let them change anything.
- If a token leaks, delete it on GitHub: **Settings → Developer settings → Personal access tokens**.

## Deleting a person
**Delete person** removes their current file. Git keeps old versions, so the person stays in the repo **history**. To remove them completely (for example after a GDPR request), the history must be rewritten. Ask a developer, or ask your AI assistant for the steps, and do it with care.

## AI assistants
An assistant can read the people on your board when you ask it to help. Use assistants that you trust with that data. The Keeptrack skill tells the assistant not to send messages and not to copy contact details elsewhere.

## Public boards
If the repo is public, anyone can read the board, also with no token. The board shows a warning when it finds a public repo. People who open a public board with no token see it read-only.

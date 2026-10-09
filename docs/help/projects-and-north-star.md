# Projects and north star

Keeptrack stays lightweight: nothing here is required, and older boards keep working.

## Client north star

A **north star** is a short note about what you are trying to solve for a client and what success looks like.

1. On the board, click the **arrow** on a client pill in the header, or open a person and choose **Open client**.
2. Edit **North star** and the client file links in the client panel.

The same text is stored in `client_info` for that client name.

## Projects under a client

A client can have several **projects**. Each project has a name, its own goal, a status (active, done, or paused), document links, and people (by email).

1. Open the client panel and type a name under **Projects**, then **Add** (or add a project from a task).
2. Open a project to see open and completed tasks, links, and people.
3. When adding people, the board suggests colleagues whose person record lists that client. Click to add; nothing is added automatically.
4. Remove a project from the project drawer (writable boards) or with `keeptrack.py project-remove` (`--clear-project` clears `task.project` on linked tasks).

On split-layout boards, use the v17 web board and an updated kit before creating projects so `projects/*.json` files stay in sync.

## Tasks and projects

On a task, set **Project** in the edit drawer (optional). Use the **Project** filter on the board to focus on one project. Done and paused projects are labelled in the filter and task picker.

## Board members as people

If you use CRM mode, add yourself as a person so follow-ups and client links stay consistent. After you save a GitHub token, the board may offer **Add yourself as a person**. If you skip it, a small reminder appears until you dismiss it or add a person with your GitHub login or email.

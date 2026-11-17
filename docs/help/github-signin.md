# Sign in with GitHub

The web board normally talks to GitHub with a fine-grained token that you paste into Settings. A board can also offer **Sign in with GitHub**. People then click a button, approve the app on github.com, and the page acts as them through a GitHub App. **Pasting a token still works and is never removed.** A board that does not turn sign-in on behaves exactly as before.

Sign-in needs one small server step, because GitHub does not let a web page trade the sign-in code for a token (no CORS, and the trade needs the app's client secret). A tiny Cloudflare Worker, in [`signin-worker/`](../../signin-worker/), does only that trade.

```
board page  ->  github.com (approve)  ->  back to the board page with ?code=&state=
board page  ->  Worker /exchange (code)  ->  github.com/login/oauth/access_token (with the client secret)
board page  <-  access token + refresh token        board page  ->  api.github.com (as the signed-in person)
```

## What the owner does once

1. **Client secret.** In GitHub: Settings, Developer settings, GitHub Apps, your app, then **Client secrets**, **Generate a new client secret**. Copy it once. It goes into the Worker (step 3) and nowhere else: not into the page, the repo, or a board.
2. **Callback URL.** On the app's settings page add the board page address as a **Callback URL**, with no query: `https://rain-ventures-ai.github.io/keeptrack/board/` (use your own page address if you host the page yourself). Keep **Expire user authorization tokens** on (the default): the page renews the short-lived token by itself. Give the app the repository permissions the board needs (**Contents** and **Issues**, read and write) and install it on the board repos.
3. **Deploy the Worker.** From `signin-worker/`, with the Wrangler tool you already use for Cloudflare:
   - Edit `wrangler.toml`: `ALLOWED_ORIGINS` is the page's origin (comma-separated, exact match), `ALLOWED_REDIRECTS` is the callback URL from step 2 (comma-separated, exact match), `GITHUB_CLIENT_ID` is the app's Client ID (public).
   - `wrangler secret put GITHUB_CLIENT_SECRET` and paste the secret.
   - Optional rate limit: `wrangler.toml` has a `[[ratelimits]]` block (binding `SIGNIN_LIMIT`, 20 requests per 60 seconds, keyed by the caller's `CF-Connecting-IP`). The Worker uses it when the binding exists and answers `429` with `Retry-After: 60` over the limit; remove the block and it simply does not limit. `namespace_id` is any number that is unique in your Cloudflare account, and `period` can only be 10 or 60.
   - `wrangler deploy`. Note the address it prints, for example `https://keeptrack-signin.<your-subdomain>.workers.dev`.
4. **Tell the page about the Worker.** In `board/index.html` add, above the first `<script>`, the meta described in the comment at the top of that file:
   `<meta name="kb-github-app-signin" content='{"client_id":"<Client ID>","exchange_url":"https://keeptrack-signin.<your-subdomain>.workers.dev"}'>`
   The page's security policy then allows the page to talk to that address and no other (list more addresses in `"origins"` if different boards use different Workers). The meta is not a script, so the policy's script hashes do not change. The hosted entry (`hosted.html`) never gets the meta and never signs in this way.

That meta alone makes **Sign in with GitHub** available as a choice in Settings on every board that opens on this page. It does not change any board's default: a fresh browser still starts on the pasted token (see below). A private board can only read its own settings once someone is signed in, so for private boards this page-level default is what makes the choice appear.

## Choosing per board

A board can also name its own app and Worker in `board/tasks.json`, under `settings`:

```json
"github_app_signin": { "client_id": "Iv23li...", "exchange_url": "https://keeptrack-signin.example.workers.dev" }
```

Set or remove it from the command line (kit v130) instead of editing the file by hand:

```
python3 board/keeptrack.py settings-set --github-app-signin '{"client_id":"Iv23...","exchange_url":"https://keeptrack-signin.example.workers.dev"}'
python3 board/keeptrack.py settings-set --clear-github-app-signin
```

The command checks the same shape as the page (a client id of 8 to 64 letters, digits, `.`, `_` or `-`; an `exchange_url` that is https with no login, query or fragment, saved without a trailing slash) and refuses anything else with a plain message. It cannot see the page's meta, so it does not check that the client id and origin are the ones the page allows; the page does that and says why in Settings if it ignores the value. `settings` shows what is stored. Hosted boards cannot use it.

- Absent: the board offers sign-in as a choice if the page has the meta, otherwise the token only. Either way it starts on the token.
- `client_id` must be the same app as the page's meta (a board cannot send people to some other GitHub App); `exchange_url` must be one of the page's listed origins. A board that names a different `client_id` is ignored with a note.
- Present and valid: Settings, Connection shows **How this browser signs in to GitHub** with two choices, **Sign in with GitHub** and **Use a fine-grained token**. The choice is remembered per board in this browser. Which one a browser starts on: a choice saved for this board wins; otherwise a saved token keeps being used; otherwise the board starts on **Sign in with GitHub** only if its own settings contain a valid `github_app_signin`, and on the token in every other case (including a page meta with no board setting).
- Present but wrong (not an object, no `client_id`, an `exchange_url` that is not https, or one the page does not allow): it is ignored, a note says why in Settings, and the token path works as normal.
- `exchange_url` is read only from board settings or the page default, never from the address bar. The page also refuses any address that is not in the page's own allow-list (step 4).

## What people see

- Settings, Connection shows which method is active. **Sign in with GitHub** sends you to github.com and back to the same board.
- The page renews its short-lived GitHub token about five minutes before it expires, and once after a refusal. If renewal fails (for example the refresh token was revoked or expired) the sign-in is cleared and the board asks you to sign in again. Only GitHub's real refusals (such as a revoked or used refresh token) end a sign-in. A network error, a server error, the Worker's rate limit (`429`) or one of the Worker's own errors (for example `not_configured`) keeps the sign-in and is retried after a minute.
- The page sends the callback as `.../board/` even when it was opened as `.../board/index.html`, so it matches `ALLOWED_REDIRECTS` and the app's Callback URL.
- **Sign out** removes the sign-in tokens from this browser. A pasted token is not touched. Forgetting a board also removes its sign-in.
- Sign-in tokens are kept in this browser only (per board, in `localStorage`), are never included in a settings code or a board move, and the refresh token is sent only to the Worker.

## Checks and limits

- Sign-in uses PKCE (S256): the page keeps a random `code_verifier` for the one sign-in, sends only its hash to github.com, and sends the verifier to the Worker, which refuses `/exchange` without a well-formed one and passes it to GitHub.
- While sign-in is the chosen method, **Forget token** is hidden (use **Sign out**) and cannot delete a saved pasted token.
- After a failed renewal (network error or a server error) the page waits a minute before trying again and keeps using the current token while it is still valid.
- The Worker answers only the origins in `ALLOWED_ORIGINS`, only passes redirect addresses in `ALLOWED_REDIRECTS` to GitHub, takes small JSON bodies by POST only, never logs codes or tokens, and returns only the five token fields or a short fixed error code. Its tests run with `node --test signin-worker/worker.test.js`.
- The page's checks (settings parsing, state check, address cleanup, which token is used, refresh timing) run with `node --test tests/signin.test.js`.
- Not for demo boards or the hosted board.
- GitHub App refresh tokens are single use. If two browser tabs renew at the same moment, the page uses a lock where the browser has one; otherwise one tab may need to sign in again.

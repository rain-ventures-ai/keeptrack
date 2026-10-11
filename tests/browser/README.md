# Browser tests

Run the browser suite from this folder (split-storage flows, mixed kit/board.js version checks and the ui.js component catalogue in `board/ui.html`):

```sh
npm ci
npx playwright install chromium
npm test
```

The tests start a local server for the board page. They mock the GitHub REST API with Playwright routes. No token or network access is used.

# Browser tests

Run the browser suite from this folder (split-storage flows plus mixed kit/board.js version checks):

```sh
npm ci
npx playwright install chromium
npm test
```

The tests start a local server for the board page. They mock the GitHub REST API with Playwright routes. No token or network access is used.

# Browser tests

Run the browser suite from this folder (split-storage flows, mixed kit/board.js version checks and the ui.js component catalogue in `board/ui.html`):

```sh
npm ci
npx playwright install chromium
npm test
```

`node prioritise.test.js` exercises the optional List prioritisation layout using fictional
GitHub API fixtures, including save conflicts, filtered moves, scroll/focus preservation and phone layout.

The tests start a local server for the board page. They mock the GitHub REST API with Playwright routes. No token or network access is used.

## UI change acceptance

Reuse the shared `ui.js` components and theme tokens before adding a new visual pattern. Browser assertions are necessary but do not establish visual quality: inspect fictional-data screenshots of the actual changed flow at desktop and narrow phone widths, in light and dark themes. Include long titles, dense metadata, empty/read-only states and existing content. Check hierarchy, wrapping, touch targets, keyboard navigation, and that decision wording matches what the operation really saves. Keep technical identifiers available in disclosures rather than turning them into headings. Never use real private board content in test screenshots.

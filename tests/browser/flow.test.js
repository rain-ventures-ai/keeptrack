'use strict';
// Fictional boards only. Run: node flow.test.js
const assert = require('node:assert/strict');
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');
const ROOT = path.resolve(__dirname, '../..');
const server = http.createServer((req, res) => {
  const file = path.resolve(ROOT, '.' + new URL(req.url, 'http://local').pathname);
  if (!file.startsWith(ROOT + path.sep)) return res.writeHead(403).end();
  fs.readFile(file, (err, data) => {
    if (err) return res.writeHead(404).end();
    res.setHeader('Content-Type', ({ '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json' })[path.extname(file)] || 'text/plain'); res.end(data);
  });
});
const now = new Date().toISOString();
const card = (n, extra = {}) => ({ id: 't_' + n, num: n, title: 'Task ' + n, column: 'todo', assignees: [], labels: [], todos: [], comments: [], history: [], links: [], contacts: [], created: now, updated: now, ...extra });
const tasks = [card(1, { title: 'Prepare a complete launch plan with a deliberately long title that wraps', claim: { agent: 'codex', status: 'running', heartbeat_at: now, claimed_at: now } }), card(2, { after: ['t_1'], project: 'p_blue', labels: ['launch'] }), card(3, { after: ['t_2'], claim: { agent: 'claude', status: 'blocked', heartbeat_at: now } }), card(4, { after: ['t_2'], claim: { agent: 'codex', status: 'running', heartbeat_at: '2020-01-01T00:00:00Z' } }), card(5, { column: 'done' }), card(6, { after: ['t_5'] }), card(7, { after: ['t_missing'] }), card(8, { after: ['t_9'] }), card(9, { after: ['t_8'] }), ...Array.from({ length: 105 }, (_, i) => card(i + 10))];
let raw = { version: 3, settings: { title: 'Launch team', modes: ['tasks'] }, columns: [{ id: 'todo', name: 'To do' }, { id: 'in-progress', name: 'In progress' }, { id: 'done', name: 'Done' }], tasks, projects: [{ id: 'p_blue', name: 'Blue launch', status: 'active' }], labels: [{ name: 'launch', color: '#2266aa' }], people: [{ github: 'alex', name: 'Alex' }], clients: [] };
let runner = null, counts = { board: 0, runner: 0, commits: 0, writes: 0 }, conditional = 0, revision = 1, commitsLost = false;
const commits = Array.from({ length: 20 }, (_, i) => ({ sha: (i + 1).toString(16).padStart(40, '0'), commit: { message: i ? 'Tick checklist item ' + i : '<script>unsafe</script> claim', author: { date: now } } }));
(async () => {
  await new Promise(ok => server.listen(0, '127.0.0.1', ok));
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } }), errors = [];
    page.on('pageerror', e => errors.push(e.message));
    await page.clock.install();
    await page.addInitScript(() => {
      if (!localStorage.getItem('flow_test_setup')) { Object.entries({ kb_repo: 'acme/board', kb_branch: 'main', kb_path: 'board/tasks.json', kb_token: 'test', kb_me: 'alex', kb_api: 'https://api.test', kb_layout: 'classic', kb_tour_seen: '1', kb_theme: 'light' }).forEach(([k, v]) => localStorage.setItem(k, v)); localStorage.setItem('flow_test_setup', '1'); } sessionStorage.setItem('kb_view', 'flow');
    });
    await page.route('https://api.test/**', async route => {
      const req = route.request(), u = new URL(req.url()), p = u.pathname.replace('/repos/acme/board', '');
      const json = (data, status = 200, headers = {}) => route.fulfill({ status, headers: { 'Content-Type': 'application/json', 'Access-Control-Expose-Headers': 'ETag', ...headers }, body: JSON.stringify(data) });
      if (req.method() !== 'GET') counts.writes++;
      if (p === '') return json({ private: true, permissions: { push: true } });
      if (p === '/user') return json({ login: 'alex' });
      if (p === '/contents/board/tasks.json') { counts.board++; if (req.headers()['if-none-match'] === 'board' + revision) return route.fulfill({ status: 304 }); return json({ sha: 'board' + revision, encoding: 'base64', content: Buffer.from(JSON.stringify(raw)).toString('base64') }, 200, { ETag: 'board' + revision }); }
      if (p === '/contents/automation/local-runner.json') {
        counts.runner++;
        if (req.headers().authorization === 'Bearer denied') return json({}, 403);
        if (!runner) return json({}, 404);
        if (req.headers()['if-none-match'] === 'runner1') { conditional++; return route.fulfill({ status: 304 }); }
        return json({ encoding: 'base64', content: Buffer.from(JSON.stringify(runner)).toString('base64') }, 200, { ETag: 'runner1' });
      }
      if (p === '/commits') { counts.commits++; if (commitsLost) return json({}, 404); if (req.headers().authorization === 'Bearer denied') return json({}, 403); assert.equal(u.searchParams.get('path'), 'board/'); assert.equal(u.searchParams.get('sha'), 'main'); return json(commits, 200, { ETag: 'commits1' }); }
      return json({}, 404);
    });
    await page.goto(`http://127.0.0.1:${server.address().port}/board/index.html`);
    await page.locator('.flow-event').first().waitFor();
    assert.equal(await page.locator('.flow-card').count(), 113);
    assert.equal(await page.locator('.flow-edge').count(), 5);
    const routes = await page.locator('.flow-edge-cycle').evaluateAll(nodes => nodes.map(n => n.getAttribute('d').match(/[\d.]+/g).map(Number)));
    routes.forEach(n => { assert.equal(n[0], n[6]); assert.ok(n[2] > n[0] && n[4] > n[6], 'cycle arrows use a right-hand gutter'); });
    assert.equal(await page.locator('.flow-cycle').count(), 2);
    assert.match(await page.locator('.flow-status').innerText(), /No runner status yet/);
    assert.match(await page.locator('[data-card="t_4"]').innerText(), /STALE/);
    assert.match(await page.locator('[data-card="t_3"]').innerText(), /BLOCKED/);
    assert.match(await page.locator('[data-card="t_6"]').innerText(), /#5 · done/);
    assert.match(await page.locator('[data-card="t_7"]').innerText(), /missing/);
    const box = n => page.locator(`[data-card="t_${n}"]`).boundingBox();
    assert.ok((await box(1)).x < (await box(2)).x && (await box(2)).x < (await box(3)).x);
    assert.equal(await page.locator('.flow-event').count(), 20);
    assert.match(await page.locator('.flow-feed').innerText(), /<script>unsafe<\/script>/);
    // Showing Done and changing filters perform no metadata fetches or writes.
    const initial = { ...counts };
    await page.getByRole('button', { name: 'Show Done', exact: true }).click();
    assert.equal(await page.locator('.flow-card').count(), 114);
    await page.selectOption('#fProject', 'p_blue', { force: true });
    assert.equal(await page.locator('.flow-card').count(), 1);
    assert.equal(await page.locator('.flow-card').getAttribute('data-card'), 't_2');
    await page.selectOption('#fProject', '', { force: true }); await page.selectOption('#fLabel', 'launch', { force: true });
    assert.equal(await page.locator('.flow-card').count(), 1);
    await page.selectOption('#fLabel', '', { force: true });
    assert.equal(counts.runner, initial.runner); assert.equal(counts.commits, initial.commits);
    // One 30s poll refreshes board and optional metadata; tab hidden stops all polling.
    runner = { status: 'paused', paused_by: 'owner', pause_reason: 'Maintenance', last_tick: now, engines_out: [{ engine: 'claude', until: 'tomorrow' }], sign_in: { claude: true, codex: false }, secret: 'DO NOT RENDER' };
    raw.tasks[0].claim.status = 'blocked'; revision++;
    await page.clock.fastForward(301000); // An absent runner is retried after five minutes, not every poll.
    await page.waitForFunction(() => document.querySelector('.flow-status').textContent.includes('Maintenance'));
    assert.match(await page.locator('[data-card="t_1"]').innerText(), /BLOCKED/);
    assert.match(await page.locator('.flow-status').innerText(), /codex sign-in: fails/);
    assert.ok(!(await page.locator('.flow-status').innerText()).includes('DO NOT RENDER'));
    await page.evaluate(() => { Object.defineProperty(document, 'hidden', { configurable: true, get: () => true }); document.dispatchEvent(new Event('visibilitychange')); });
    const hidden = { ...counts }; await page.clock.fastForward(31000);
    assert.deepEqual(counts, hidden);
    await page.evaluate(() => { window.flowGraph = document.querySelector('.flow-canvas'); });
    const refreshed = page.waitForResponse(r => r.url().includes('local-runner.json') && r.status() === 304);
    await page.evaluate(() => { Object.defineProperty(document, 'hidden', { configurable: true, get: () => false }); document.dispatchEvent(new Event('visibilitychange')); });
    await page.waitForFunction(() => document.querySelector('.flow-status').textContent.includes('Maintenance'));
    await refreshed; assert.ok(counts.board > hidden.board); assert.ok(conditional > 0);
    // An unchanged board and metadata refresh keeps the exact same graph DOM.
    assert.ok(await page.evaluate(() => window.flowGraph === document.querySelector('.flow-canvas')));
    // The Done button overrides the existing Hide Done switch.
    await page.getByRole('button', { name: 'Collapse Done', exact: true }).click();
    await page.selectOption('#fStatus', '__open', { force: true });
    await page.evaluate(() => { const c = document.querySelector('#fHideDone'); c.checked = true; c.dispatchEvent(new Event('change')); });
    await page.getByRole('button', { name: 'Show Done', exact: true }).click();
    assert.equal(await page.locator('[data-card="t_5"]').count(), 1);
    assert.equal(await page.locator('#fStatus').inputValue(), '__open');
    assert.equal(await page.locator('#fHideDone').isChecked(), true);
    await page.getByRole('button', { name: 'Collapse Done', exact: true }).click();
    for (const theme of ['light', 'dark']) {
      await page.evaluate(theme => document.documentElement.dataset.theme = theme, theme);
      for (const width of [1440, 390]) {
        await page.setViewportSize({ width, height: 1000 });
        await page.screenshot({ path: `/tmp/keeptrack-flow-${theme}-${width}.png` });
        assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'no page overflow');
      }
    }
    await page.locator('[data-card="t_2"]').focus(); await page.keyboard.press('Enter'); await page.locator('#dlgCard[open]').waitFor();
    assert.equal(counts.writes, 0); assert.deepEqual(errors, []);
    await page.locator('#cClose').click();
    // Filtering one side of a cycle does not erase the warning.
    Object.assign(raw.tasks.find(t => t.num === 8), { project: 'p_blue', title: 'Blue launch cycle' }); revision++;
    await page.clock.fastForward(31000);
    await page.waitForFunction(() => document.querySelector('[data-card="t_8"]')?.textContent.includes('Blue launch cycle'));
    await page.selectOption('#fProject', 'p_blue', { force: true });
    assert.equal(await page.locator('[data-card="t_8"] .flow-cycle').textContent(), 'Dependency cycle');
    await page.selectOption('#fProject', '', { force: true });
    // GitHub can conceal inaccessible repository activity with 404, not just 401/403.
    commitsLost = true;
    const lost = page.waitForResponse(r => r.url().includes('/commits?') && r.status() === 404);
    await page.clock.fastForward(31000); await lost;
    await page.waitForFunction(() => document.querySelectorAll('.flow-event').length === 0);
    commitsLost = false; await page.clock.fastForward(31000);
    await page.waitForFunction(() => document.querySelectorAll('.flow-event').length === 20);
    // Changing credentials in the real connection form clears metadata from the old token.
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.locator('#btnSettings').click(); await page.locator('#tabConn').click();
    await page.locator('#bEditFold > summary').click();
    await page.locator('#sToken').fill('denied'); await page.locator('#sSave').click();
    await page.waitForFunction(() => document.querySelector('.flow-status').textContent.includes('Could not refresh'));
    assert.ok(!(await page.locator('.flow-status').innerText()).includes('Maintenance'));
    assert.equal(await page.locator('.flow-event').count(), 0);
    // Existing explicitly enabled alerts still poll the board in the background,
    // independently of Flow metadata, which always pauses while hidden.
    await page.evaluate(() => { localStorage.setItem('kb_alerts', JSON.stringify({ on: true, kinds: [] })); Object.defineProperty(document, 'hidden', { configurable: true, get: () => true }); });
    const alerts = { ...counts }; const alertPoll = page.waitForResponse(r => r.url().includes('/contents/board/tasks.json'));
    await page.clock.fastForward(31000); await alertPoll;
    assert.ok(counts.board > alerts.board); assert.equal(counts.runner, alerts.runner); assert.equal(counts.commits, alerts.commits);
    await page.evaluate(() => { localStorage.setItem('kb_alerts', JSON.stringify({ on: false, kinds: [] })); Object.defineProperty(document, 'hidden', { configurable: true, get: () => false }); });
    // Public viewers keep the original two-minute cadence and make no metadata requests.
    await page.evaluate(() => { localStorage.removeItem('kb_token'); });
    await page.reload(); await page.locator('.flow-status').waitFor();
    assert.match(await page.locator('.flow-status').innerText(), /Sign in/);
    const publicCounts = { ...counts };
    await page.clock.fastForward(91000);
    assert.deepEqual(counts, publicCounts);
    // Stress a chain far beyond a recursive traversal's normal stack depth.
    raw.tasks = Array.from({ length: 12000 }, (_, n) => card(n + 1, { after: n ? ['t_' + n] : [] })); revision++;
    await page.evaluate(() => localStorage.setItem('kb_token', 'test'));
    await page.reload(); await page.locator('[data-card="t_500"]').waitFor({ state: 'attached', timeout: 60000 });
    assert.equal(await page.locator('.flow-card').count(), 500);
    assert.match(await page.locator('.flow-limit').innerText(), /Showing 500 of 12000/);
    await page.getByRole('button', { name: 'Show 500 more', exact: true }).click();
    assert.equal(await page.locator('.flow-card').count(), 1000);
    assert.deepEqual(errors, []);
    console.log('flow: 114-card UI, 12,000-card chain, filtered cycles, credentials, public quota, polling, alerts, runner status and screenshots passed');
  } finally { await browser.close(); server.close(); }
})().catch(e => { console.error(e); process.exit(1); });

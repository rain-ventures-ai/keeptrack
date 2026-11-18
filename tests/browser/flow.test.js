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
tasks.find(t => t.num === 3).after.push('t_1');
tasks.find(t => t.num === 10).after = ['t_10'];
tasks.find(t => t.num === 8).after.push('t_10'); // A link between separate cycles is not itself cyclic.
tasks.find(t => t.num === 11).claim = { agent: 'codex', status: 'running', heartbeat_at: now };
let raw = { version: 3, settings: { title: 'Launch team', modes: ['tasks'] }, columns: [{ id: 'todo', name: 'To do' }, { id: 'in-progress', name: 'In progress' }, { id: 'done', name: 'Done' }], tasks, projects: [{ id: 'p_blue', name: 'Blue launch', status: 'active' }], labels: [{ name: 'launch', color: '#2266aa' }], people: [{ github: 'alex', name: 'Alex' }], clients: [] };
let runner = null, counts = { board: 0, runner: 0, commits: 0, writes: 0 }, conditional = 0, revision = 1, commitsLost = false, runnerVersion = 1, runnerGate = null, branchGate = null, rootBoard = false, boardLimited = false, boardLost = false, boardNetwork = false, commitsLimited = false;
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
      const json = (data, status = 200, headers = {}) => route.fulfill({ status, headers: { 'Content-Type': 'application/json', 'Access-Control-Expose-Headers': 'ETag, X-RateLimit-Remaining, Retry-After', ...headers }, body: JSON.stringify(data) });
      if (req.method() !== 'GET') counts.writes++;
      if (p === '') return json({ private: true, permissions: { push: true } });
      if (p === '/user') return json({ login: 'alex' });
      if (p === '/contents/board/tasks.json' || p === '/contents/tasks.json') { counts.board++; if (boardNetwork) return route.abort('failed'); if (boardLost) return json({}, 401); if (boardLimited) return json({}, 403, { 'x-ratelimit-remaining': '0', 'retry-after': '60' }); if (branchGate && u.searchParams.get('ref') === 'dev') { const gate = branchGate; branchGate = null; gate.arrived(); await gate.wait; } if (req.headers()['if-none-match'] === 'board' + revision) return route.fulfill({ status: 304 }); return json({ sha: 'board' + revision, encoding: 'base64', content: Buffer.from(JSON.stringify(raw)).toString('base64') }, 200, { ETag: 'board' + revision }); }
      if (p === '/contents/automation/local-runner.json') {
        counts.runner++;
        if (runnerGate) { const gate = runnerGate; runnerGate = null; gate.request = req; gate.arrived(); await gate.wait; gate.released?.(); }
        if (u.searchParams.get('ref') === 'dev') return json({}, 403);
        if (req.headers().authorization === 'Bearer denied') return json({}, 403);
        if (!runner) return json({}, 404);
        if (req.headers()['if-none-match'] === 'runner' + runnerVersion) { conditional++; return route.fulfill({ status: 304 }); }
        return json({ encoding: 'base64', content: Buffer.from(JSON.stringify(runner)).toString('base64') }, 200, { ETag: 'runner' + runnerVersion });
      }
      if (p === '/commits') { counts.commits++; if (commitsLimited) return json({}, 429, { 'retry-after': '120' }); if (commitsLost) return json({}, 404); if (u.searchParams.get('sha') === 'dev' || req.headers().authorization === 'Bearer denied') return json({}, 403); assert.equal(u.searchParams.get('path'), rootBoard ? 'tasks.json' : 'board/tasks.json'); assert.equal(u.searchParams.get('sha'), 'main'); return json(commits, 200, { ETag: 'commits1' }); }
      return json({}, 404);
    });
    await page.goto(`http://127.0.0.1:${server.address().port}/board/index.html`);
    await page.locator('.flow-event').first().waitFor();
    assert.equal(await page.locator('.flow-card').count(), 113);
    assert.equal(await page.locator('.flow-edge').count(), 8);
    assert.equal(await page.locator('.flow-edge-cycle').count(), 3, 'only links inside one cycle are dashed');
    assert.equal(await page.locator('.flow-edge').evaluateAll(nodes => nodes.filter(n => n.getAttribute('d').includes(' V')).length), 1, 'skip-rank arrow uses an outside gutter');
    const routes = await page.locator('.flow-edge-cycle').evaluateAll(nodes => nodes.map(n => n.getAttribute('d').match(/[\d.]+/g).map(Number)));
    routes.forEach(n => { assert.equal(n[0], n[6]); assert.ok(n[2] > n[0] && n[4] > n[6], 'cycle arrows use a right-hand gutter'); });
    assert.equal(await page.locator('.flow-cycle').count(), 3);
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
    await page.clock.fastForward(31000);
    assert.equal(counts.runner, initial.runner, 'absent runner is not retried on each poll');
    await page.evaluate(() => { window.unchangedGraph = document.querySelector('.flow-canvas'); window.laneCard = document.querySelector('[data-card="t_11"]'); });
    await page.clock.fastForward(31 * 60000); // An unchanged board can cross the stale threshold.
    await page.waitForFunction(() => document.querySelector('.flow-status')?.textContent.includes('Maintenance'));
    assert.match(await page.locator('[data-card="t_1"]').innerText(), /STALE/);
    assert.ok(await page.evaluate(() => window.unchangedGraph === document.querySelector('.flow-canvas')), 'time-only refresh preserves graph');
    raw.tasks[0].claim.status = 'blocked'; revision++;
    raw.tasks.find(t => t.num === 11).claim.agent = 'claude';
    raw.tasks.find(t => t.num === 11).claim.heartbeat_at = await page.evaluate(() => new Date().toISOString());
    await page.clock.fastForward(31000);
    await page.waitForFunction(() => document.querySelector('[data-card="t_1"]').textContent.includes('BLOCKED'));
    assert.match(await page.locator('[data-card="t_11"] .flow-run').innerText(), /claude/);
    assert.ok(await page.evaluate(() => window.laneCard === document.querySelector('[data-card="t_11"]')), 'unlinked claim updates reuse the card node');
    assert.match(await page.locator('[data-card="t_1"]').innerText(), /BLOCKED/);
    assert.match(await page.locator('.flow-status').innerText(), /codex sign-in: fails/);
    assert.ok(!(await page.locator('.flow-status').innerText()).includes('DO NOT RENDER'));
    await page.evaluate(() => { Object.defineProperty(document, 'hidden', { configurable: true, get: () => true }); document.dispatchEvent(new Event('visibilitychange')); });
    const oldAge = await page.locator('.flow-event .hint').first().textContent();
    const hidden = { ...counts }; await page.clock.fastForward(61000);
    assert.deepEqual(counts, hidden);
    await page.evaluate(() => { window.flowGraph = document.querySelector('.flow-canvas'); });
    const refreshed = page.waitForResponse(r => r.url().includes('local-runner.json') && r.status() === 304);
    await page.evaluate(() => { Object.defineProperty(document, 'hidden', { configurable: true, get: () => false }); document.dispatchEvent(new Event('visibilitychange')); });
    await page.waitForFunction(() => document.querySelector('.flow-status')?.textContent.includes('Maintenance'));
    await refreshed; assert.ok(counts.board > hidden.board); assert.ok(conditional > 0);
    // An unchanged board and metadata refresh keeps the exact same graph DOM.
    assert.ok(await page.evaluate(() => window.flowGraph === document.querySelector('.flow-canvas')));
    assert.notEqual(await page.locator('.flow-event .hint').first().textContent(), oldAge);
    // A response arriving while hidden is reconciled from cache on immediate return,
    // even though the 25-second network throttle is still active.
    let releaseRunner, runnerArrived;
    const arrived = new Promise(resolve => { runnerArrived = resolve; });
    const heldUpdate = runnerGate = { arrived: runnerArrived, wait: new Promise(resolve => { releaseRunner = resolve; }) };
    commits[0].commit.message = 'Activity arrives independently';
    runnerVersion++; runner.pause_reason = 'Updated while hidden';
    await page.clock.fastForward(61000); await arrived;
    await page.waitForFunction(() => document.querySelector('.flow-feed').textContent.includes('Activity arrives independently'), null, { timeout: 1000 });
    assert.equal(heldUpdate.request.failure(), null, 'successful activity is visible while runner status is still pending');
    await page.evaluate(() => Object.defineProperty(document, 'hidden', { configurable: true, get: () => true }));
    const completed = page.waitForResponse(r => r.url().includes('local-runner.json') && r.status() === 200);
    releaseRunner(); await (await completed).finished(); await page.evaluate(() => Promise.resolve());
    assert.ok(!(await page.locator('.flow-status').innerText()).includes('Updated while hidden'));
    const hiddenResponseCount = counts.runner;
    await page.evaluate(() => { Object.defineProperty(document, 'hidden', { configurable: true, get: () => false }); document.dispatchEvent(new Event('visibilitychange')); });
    await page.waitForFunction(() => document.querySelector('.flow-status')?.textContent.includes('Updated while hidden'));
    assert.equal(counts.runner, hiddenResponseCount);
    boardLimited = true;
    await page.evaluate(() => { window.rateCanvas = document.querySelector('.flow-canvas'); });
    await page.clock.fastForward(31000);
    await page.waitForFunction(() => document.querySelector('#status').textContent.includes('rate limit'));
    assert.ok(await page.evaluate(() => window.rateCanvas === document.querySelector('.flow-canvas')), 'rate limiting preserves the loaded graph');
    boardLimited = false; boardNetwork = true;
    await page.clock.fastForward(31000);
    await page.waitForFunction(() => document.querySelector('#status').textContent.includes('Network or parse error'));
    assert.ok(await page.evaluate(() => window.rateCanvas === document.querySelector('.flow-canvas')), 'transient network failures preserve the loaded graph');
    boardNetwork = false; await page.clock.fastForward(31000);
    commitsLimited = true;
    await page.clock.fastForward(61000);
    await page.waitForFunction(() => document.querySelector('.flow-feed').textContent.includes('Could not refresh'));
    const limitedCount = counts.commits;
    await page.clock.fastForward(61000);
    assert.equal(counts.commits, limitedCount, 'Retry-After prevents metadata retries for 120 seconds');
    commitsLimited = false; await page.clock.fastForward(91000);
    await page.waitForFunction(() => !document.querySelector('.flow-feed').textContent.includes('Could not refresh'));
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
    await page.waitForFunction(() => !document.querySelector('#dlgCard').open && !new URL(location.href).searchParams.has('card') && !/^#\d/.test(location.hash));
    await page.reload(); await page.locator('.flow-card').first().waitFor();
    assert.equal(await page.locator('#dlgCard').evaluate(d => d.open), false, 'a reload after closing does not reopen the card');
    await page.locator('[data-card="t_2"]').click(); await page.locator('#dlgCard[open]').waitFor();
    boardLost = true;
    await page.clock.fastForward(31000);
    await page.waitForFunction(() => !document.querySelector('#dlgCard').open);
    assert.equal(await page.locator('.flow-card').count(), 0);
    assert.equal(await page.locator('#cTitle').inputValue(), '', 'lost access scrubs the open drawer');
    assert.equal(counts.writes, 0, 'forced drawer close does not save');
    boardLost = false;
    // Start the remaining projection tests on an explicit view route, independent of drawer history.
    await page.goto(`http://127.0.0.1:${server.address().port}/board/index.html?board_view=flow#view=flow`);
    await page.locator('.flow-event').first().waitFor();
    await page.selectOption('#fStatus', 'done', { force: true });
    assert.equal(await page.locator('[data-card="t_5"]').count(), 1);
    assert.equal(await page.getByRole('button', { name: 'Done selected' }).isDisabled(), true);
    await page.selectOption('#fStatus', '__open', { force: true });
    // Filtering one side of a cycle does not erase the warning.
    Object.assign(raw.tasks.find(t => t.num === 8), { project: 'p_blue', title: 'Blue launch cycle' }); revision++;
    await page.clock.fastForward(31000);
    await page.waitForFunction(() => document.querySelector('[data-card="t_8"]')?.textContent.includes('Blue launch cycle'));
    await page.selectOption('#fProject', 'p_blue', { force: true });
    assert.equal(await page.locator('[data-card="t_8"] .flow-cycle').textContent(), 'Dependency cycle');
    await page.selectOption('#fProject', '', { force: true });
    // Changing branch with the same token clears the old metadata before the new load returns.
    let releaseBranch, branchArrived;
    const branchStarted = new Promise(resolve => { branchArrived = resolve; });
    branchGate = { arrived: branchArrived, wait: new Promise(resolve => { releaseBranch = resolve; }) };
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.locator('#btnSettings').click(); await page.locator('#tabConn').click(); await page.locator('#bEditFold > summary').click();
    await page.locator('#sBranch').fill('dev'); await page.locator('#sSave').click(); await branchStarted;
    assert.ok(!(await page.locator('.flow-status').innerText()).includes('Updated while hidden'));
    assert.equal(await page.locator('.flow-event').count(), 0);
    assert.equal(await page.locator('.flow-card').count(), 0, 'old board cards clear while the new branch load is pending');
    releaseBranch(); await page.waitForFunction(() => document.querySelector('.flow-status')?.textContent.includes('Could not refresh'));
    await page.locator('#btnSettings').click(); await page.locator('#tabConn').click();
    if (!(await page.locator('#bEditFold').evaluate(n => n.open))) await page.locator('#bEditFold > summary').click();
    await page.locator('#sBranch').fill('main'); await page.locator('#sSave').click(); await page.locator('.flow-event').first().waitFor();
    // GitHub can conceal inaccessible repository activity with 404, not just 401/403.
    await page.evaluate(() => Object.defineProperty(document, 'hidden', { configurable: true, get: () => true }));
    await page.clock.fastForward(61000); // Activity has its own one-minute cadence.
    let releaseDeniedRunner, deniedArrived, deniedReleased;
    const deniedStarted = new Promise(resolve => { deniedArrived = resolve; }), peerReleased = new Promise(resolve => { deniedReleased = resolve; });
    const heldPeer = runnerGate = { arrived: deniedArrived, released: deniedReleased, wait: new Promise(resolve => { releaseDeniedRunner = resolve; }) };
    commitsLost = true;
    const lost = page.waitForResponse(r => r.url().includes('/commits?') && r.status() === 404);
    await page.evaluate(() => { Object.defineProperty(document, 'hidden', { configurable: true, get: () => false }); document.dispatchEvent(new Event('visibilitychange')); }); await lost;
    await page.waitForFunction(() => document.querySelectorAll('.flow-event').length === 0, null, { timeout: 1000 });
    await deniedStarted;
    assert.equal(heldPeer.request.failure(), null, 'the other metadata endpoint is genuinely still pending');
    const deniedPeer = page.waitForResponse(r => r.url().includes('local-runner.json'));
    releaseDeniedRunner(); await peerReleased; await deniedPeer; await page.evaluate(() => Promise.resolve());
    commitsLost = false; await page.clock.fastForward(61000);
    await page.waitForFunction(() => document.querySelectorAll('.flow-event').length === 20);
    // Changing credentials in the real connection form clears metadata from the old token.
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.locator('#btnSettings').click(); await page.locator('#tabConn').click();
    if (!(await page.locator('#bEditFold').evaluate(n => n.open))) await page.locator('#bEditFold > summary').click();
    await page.locator('#sToken').fill('denied'); await page.locator('#sSave').click();
    await page.waitForFunction(() => document.querySelector('.flow-status')?.textContent.includes('Could not refresh'));
    assert.ok(!(await page.locator('.flow-status').innerText()).includes('Maintenance'));
    assert.ok(!(await page.locator('.flow-status').innerText()).includes('Updated while hidden'));
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
    await page.goto(`http://127.0.0.1:${server.address().port}/board/index.html?board_view=flow#view=flow`); await page.locator('[data-card="t_500"]').waitFor({ state: 'attached', timeout: 60000 });
    assert.equal(await page.locator('.flow-card').count(), 500);
    assert.match(await page.locator('.flow-limit').innerText(), /Showing 500 of 12000/);
    await page.getByRole('button', { name: 'Next 500', exact: true }).click();
    assert.equal(await page.locator('.flow-card').count(), 500);
    assert.equal(await page.locator('[data-card="t_501"]').count(), 1);
    assert.equal(await page.locator('[data-card="t_1"]').count(), 0);
    // Exercise the iterative traversal within the edge budget, rather than summary fallback.
    raw.tasks = Array.from({ length: 9000 }, (_, n) => card(n + 1, { after: n ? ['t_' + n] : [] })); revision++;
    raw.tasks[0].claim = { agent: 'codex', status: 'running', heartbeat_at: await page.evaluate(() => new Date().toISOString()) };
    await page.goto(`http://127.0.0.1:${server.address().port}/board/index.html?board_view=flow#view=flow`); await page.locator('[data-card="t_500"]').waitFor({ state: 'attached' });
    await page.waitForFunction(() => document.querySelector('.flow-limit')?.textContent.includes('9000') && document.querySelector('.flow-canvas'));
    assert.equal(await page.locator('.flow-canvas').count(), 1);
    assert.equal(await page.locator('.flow-edge').count(), 499);
    await page.evaluate(() => { window.pulseCanvas = document.querySelector('.flow-canvas'); });
    raw.tasks[0].claim.agent = 'claude'; raw.tasks[0].claim.heartbeat_at = await page.evaluate(() => new Date().toISOString()); revision++;
    await page.clock.fastForward(31000);
    await page.waitForFunction(() => document.querySelector('[data-card="t_1"] .flow-run')?.textContent.includes('claude'));
    assert.ok(await page.evaluate(() => window.pulseCanvas === document.querySelector('.flow-canvas')), 'claim-only record updates reuse the graph');
    // Dense graphs must not allocate a quadratic SVG tree.
    raw.tasks = Array.from({ length: 500 }, (_, n) => card(n + 1, { after: Array.from({ length: n }, (_, i) => 't_' + (i + 1)) })); revision++;
    await page.goto(`http://127.0.0.1:${server.address().port}/board/index.html?board_view=flow#view=flow`); await page.locator('[data-card="t_500"]').waitFor({ state: 'attached' });
    await page.waitForFunction(() => document.querySelector('.flow-main')?.textContent.includes('More than 10,000 dependency links'));
    assert.equal(await page.locator('.flow-edge').count(), 0);
    assert.match(await page.locator('.flow-main').innerText(), /More than 10,000 dependency links/);
    rootBoard = true;
    await page.evaluate(() => localStorage.setItem('kb_path', 'tasks.json'));
    await page.goto(`http://127.0.0.1:${server.address().port}/board/index.html?path=tasks.json&board_view=flow#view=flow`);
    await page.locator('.flow-event').first().waitFor(); // The mock asserts a file-scoped commit query.
    assert.deepEqual(errors, []);
    console.log('flow: 114-card UI, 12,000-card chain, filtered cycles, credentials, public quota, polling, alerts, runner status and screenshots passed');
  } finally { await browser.close(); server.close(); }
})().catch(e => { console.error(e); process.exit(1); });

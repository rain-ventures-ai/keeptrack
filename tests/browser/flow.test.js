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
let runner = null, counts = { board: 0, runner: 0, commits: 0, writes: 0 }, conditional = 0, revision = 1, commitsLost = false, runnerVersion = 1, runnerGate = null, branchGate = null, boardGate = null, rootBoard = false, boardLimited = false, boardLost = false, boardNetwork = false, commitsLimited = false, runnerNetwork = false, runnerSharedLimit = false, commitsNetwork = false;
const otherBoardSubject = 'PRIVATE fixture: another board client changed confidential strategy <script>unsafe</script>';
const commits = Array.from({ length: 20 }, (_, i) => ({ sha: (i + 1).toString(16).padStart(40, '0'), commit: { message: i ? 'Tick checklist item ' + i : otherBoardSubject, author: { date: now } } }));
let primaryReset = 0;
(async () => {
  await new Promise(ok => server.listen(0, '127.0.0.1', ok));
  const browser = await chromium.launch({ headless: true });
  try {
    // A token is not proof that this repository is private. Reuse the repository metadata check.
    {
      const p = await browser.newPage({ viewport: { width: 1440, height: 1000 } }), seen = { runner: 0, commits: 0, writes: 0 };
      let visibility = false, visibilityStatus = 200, visibilityGate = null;
      await p.clock.install();
      await p.addInitScript(() => {
        Object.entries({ kb_repo: 'acme/board', kb_branch: 'main', kb_path: 'board/tasks.json', kb_token: 'test', kb_me: 'alex', kb_api: 'https://api.test', kb_layout: 'classic', kb_tour_seen: '1' }).forEach(([k, v]) => localStorage.setItem(k, v));
        sessionStorage.setItem('kb_view', 'flow');
      });
      await p.route('https://api.test/**', async route => {
        const request = route.request(), path = new URL(request.url()).pathname.replace('/repos/acme/board', '');
        const json = (value, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(value) });
        if (request.method() !== 'GET') seen.writes++;
        if (!path) {
          const privateValue = request.headers().authorization === 'Bearer replacement' ? false : visibility, status = visibilityStatus, held = visibilityGate;
          if (held) { visibilityGate = null; held.arrived(); await held.wait; }
          return json({ private: privateValue, full_name: 'acme/board' }, status);
        }
        if (path === '/contents/board/tasks.json') return json({ sha: 'private-fixture', encoding: 'base64', content: Buffer.from(JSON.stringify(raw)).toString('base64') });
        if (path === '/contents/automation/local-runner.json') { seen.runner++; return json({ encoding: 'base64', content: Buffer.from(JSON.stringify({ status: 'paused', pause_reason: 'Verified private fixture' })).toString('base64') }); }
        if (path === '/commits') { seen.commits++; return json(commits); }
        return json({}, 404);
      });
      const metadataResponse = () => p.waitForResponse(r => new URL(r.url()).pathname === '/repos/acme/board');
      await p.goto(`http://127.0.0.1:${server.address().port}/board/index.html?board_view=flow#view=flow`);
      await p.locator('#dlgPublic[open]').waitFor(); await p.locator('.flow-card').first().waitFor();
      assert.deepEqual(seen, { runner: 0, commits: 0, writes: 0 }, 'signed-in public boards make no optional metadata requests');
      await p.evaluate(() => document.querySelector('#dlgPublic').close());
      for (const [privateValue, status] of [[null, 200], [true, 503]]) {
        visibility = privateValue; visibilityStatus = status;
        const response = metadataResponse(); await p.clock.fastForward(61000); await (await response).finished(); await p.clock.runFor(100);
        assert.deepEqual(seen, { runner: 0, commits: 0, writes: 0 }, 'unknown or failed visibility stays closed');
        assert.equal(await p.locator('.flow-event').count(), 0);
      }
      visibility = true; visibilityStatus = 200;
      let releasePrivate, privateArrived;
      const privateStarted = new Promise(resolve => { privateArrived = resolve; });
      visibilityGate = { arrived: privateArrived, wait: new Promise(resolve => { releasePrivate = resolve; }) };
      await p.clock.fastForward(61000); await privateStarted;
      assert.deepEqual(seen, { runner: 0, commits: 0, writes: 0 }, 'pending initial confirmation authorises no metadata');
      releasePrivate(); await p.locator('.flow-event').first().waitFor();
      await p.waitForFunction(() => document.querySelector('.flow-status')?.textContent.includes('Verified private fixture'));
      assert.ok(seen.runner && seen.commits, 'confirmed private repositories retain both panels');
      visibilityStatus = 503;
      const failedVisibility = metadataResponse(); await p.clock.fastForward(61000); await (await failedVisibility).finished(); await p.clock.runFor(100);
      assert.equal(await p.locator('.flow-event').count(), 0, 'lost confirmation clears activity');
      assert.ok(!(await p.locator('.flow-status').innerText()).includes('Verified private fixture'), 'lost confirmation clears runner status');
      const closed = { ...seen };
      visibilityStatus = 200;
      let releaseOld, oldArrived;
      const oldStarted = new Promise(resolve => { oldArrived = resolve; });
      visibilityGate = { arrived: oldArrived, wait: new Promise(resolve => { releaseOld = resolve; }) };
      await p.clock.fastForward(61000); await oldStarted;
      await p.locator('#btnSettings').click(); await p.locator('#tabConn').click();
      await p.locator('#bEditFold > summary').click(); await p.locator('#sToken').fill('replacement');
      const replacementVisibility = metadataResponse(); await p.locator('#sSave').click(); await (await replacementVisibility).finished();
      await p.locator('#dlgPublic[open]').waitFor();
      const oldReply = metadataResponse(); releaseOld(); await (await oldReply).finished(); await p.clock.runFor(100);
      assert.deepEqual(seen, closed, 'a stale private response cannot authorise a new public connection');
      assert.equal(await p.locator('.flow-event').count(), 0);
      assert.ok(!(await p.locator('.flow-status').innerText()).includes('Verified private fixture'));
      await p.close();
    }
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } }), errors = [];
    page.on('pageerror', e => errors.push(e.message));
    await page.clock.install();
    await page.addInitScript(() => {
      if (!localStorage.getItem('flow_test_setup')) { Object.entries({ kb_repo: 'acme/board', kb_branch: 'main', kb_path: 'board/tasks.json', kb_token: 'test', kb_me: 'alex', kb_api: 'https://api.test', kb_layout: 'classic', kb_tour_seen: '1', kb_theme: 'light' }).forEach(([k, v]) => localStorage.setItem(k, v)); localStorage.setItem('flow_test_setup', '1'); } sessionStorage.setItem('kb_view', 'flow');
    });
    await page.route('https://api.test/**', async route => {
      const req = route.request(), u = new URL(req.url()), p = u.pathname.replace('/repos/acme/board', '');
      const json = (data, status = 200, headers = {}) => route.fulfill({ status, headers: { 'Content-Type': 'application/json', 'Access-Control-Expose-Headers': 'ETag, X-RateLimit-Remaining, X-RateLimit-Reset, Retry-After', ...headers }, body: JSON.stringify(data) });
      if (req.method() !== 'GET') counts.writes++;
      if (req.method() === 'PUT' && ['/contents/board/tasks.json', '/contents/tasks.json'].includes(p)) { raw = JSON.parse(Buffer.from(req.postDataJSON().content, 'base64').toString()); revision++; return json({ content: { sha: 'board' + revision } }); }
      if (p === '') return json({ private: true, permissions: { push: true } });
      if (p === '/user') return json({ login: 'alex' });
      if (p === '/contents/board/tasks.json' || p === '/contents/tasks.json') {
        counts.board++;
        const responseRevision = revision, responseBody = JSON.stringify(raw), held = boardGate;
        if (held) { boardGate = null; held.arrived(); await held.wait; }
        if (boardNetwork) return route.abort('failed');
        if (boardLost) return json({}, 401);
        if (boardLimited) return json({}, 403, { 'x-ratelimit-remaining': '0', 'retry-after': '60' });
        if (branchGate && u.searchParams.get('ref') === 'dev') { const gate = branchGate; branchGate = null; gate.arrived(); await gate.wait; }
        if (!held && req.headers()['if-none-match'] === 'board' + responseRevision) return route.fulfill({ status: 304 });
        return json({ sha: 'board' + responseRevision, encoding: 'base64', content: Buffer.from(responseBody).toString('base64') }, 200, { ETag: 'board' + responseRevision });
      }
      if (p === '/contents/automation/local-runner.json') {
        counts.runner++;
        if (runnerNetwork) return route.abort('failed');
        if (runnerSharedLimit) return json({}, runnerSharedLimit === 'primary' ? 403 : 429, { ...(runnerSharedLimit !== 'headerless' ? { 'retry-after': '120' } : {}), 'x-ratelimit-remaining': runnerSharedLimit === 'primary' ? '0' : '300', ...(runnerSharedLimit === 'primary' ? { 'x-ratelimit-reset': String(primaryReset) } : {}) });
        if (runnerGate) { const gate = runnerGate; runnerGate = null; gate.request = req; gate.arrived(); await gate.wait; gate.released?.(); }
        if (u.searchParams.get('ref') === 'dev') return json({}, 403);
        if (req.headers().authorization === 'Bearer denied') return json({}, 403);
        if (!runner) return json({}, 404);
        if (req.headers()['if-none-match'] === 'runner' + runnerVersion) { conditional++; return route.fulfill({ status: 304 }); }
        return json({ encoding: 'base64', content: Buffer.from(JSON.stringify(runner)).toString('base64') }, 200, { ETag: 'runner' + runnerVersion });
      }
      if (p === '/commits') { counts.commits++; if (commitsNetwork) return route.abort('failed'); if (commitsLimited) return json({}, 429, { ...(commitsLimited !== 'headerless' ? { 'retry-after': '120' } : {}), 'x-ratelimit-remaining': '300' }); if (commitsLost) return json({}, 404); if (u.searchParams.get('sha') === 'dev' || req.headers().authorization === 'Bearer denied') return json({}, 403); assert.equal(u.searchParams.get('path'), rootBoard ? 'tasks.json' : 'board/tasks.json'); assert.equal(u.searchParams.get('sha'), 'main'); return json(commits, 200, { ETag: 'commits1' }); }
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
    const feedDom = await page.locator('.flow-feed').evaluate(node => node.outerHTML);
    assert.ok(!feedDom.includes(otherBoardSubject) && !feedDom.includes('confidential strategy') && !feedDom.includes('unsafe'), 'matching commits never expose another board subject in text or attributes');
    assert.equal(await page.locator('.flow-event a').first().textContent(), 'Board update');
    assert.match(await page.locator('.flow-event a').first().getAttribute('href'), /\/commit\/0000000000000000000000000000000000000001$/);
    assert.ok(await page.locator('.flow-event .hint').first().textContent(), 'generic activity retains its timestamp');
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
    // Actual local_status.py build/validate fixtures, generated with empty fictional state/auth folders.
    const publisher = JSON.parse(fs.readFileSync(path.join(__dirname, 'fixtures/local-runner-v1.json')));
    const reportedTick = async (hours = 0) => page.evaluate(h => new Date(Date.now() - h * 3600000).toISOString().replace(/\.\d{3}Z$/, 'Z'), hours);
    const setRunner = async value => {
      runner = value; runnerVersion++;
      const reply = page.waitForResponse(r => r.url().includes('local-runner.json') && r.status() === 200);
      await page.clock.fastForward(31000); await (await reply).finished(); await page.clock.runFor(100);
      return page.locator('.flow-status').innerText();
    };
    const writesBeforeStatus = counts.writes;
    let status = await setRunner({ ...publisher.active, last_tick: await reportedTick() });
    assert.match(status, /Repository runner reported active/);
    assert.match(status, /Last reported tick/); assert.match(status, /not a live heartbeat/);
    status = await setRunner({ status: 'active', paused: false, paused_by: 'owner', pause_reason: 'Old pause reason', last_tick: await page.evaluate(() => new Date().toISOString()) });
    assert.match(status, /Repository runner reported active/); assert.ok(!status.includes('Old pause reason'));
    assert.ok(!status.includes('Last reported tick unknown'), 'legacy canonical millisecond timestamps remain supported');
    for (const legacyState of ['active', 'paused']) {
      for (const invalidTick of [null, '', false, 0, [], {}, 'not a timestamp', '2026-02-30T00:00:00Z', '0000-01-01T00:00:00Z']) {
        status = await setRunner({ status: legacyState, last_tick: invalidTick });
        assert.match(status, /status unknown · invalid report/, `supplied invalid legacy tick for ${legacyState}`);
        assert.ok(!status.includes(`Repository runner reported ${legacyState}`));
      }
      status = await setRunner({ status: legacyState });
      assert.match(status, new RegExp(`Repository runner reported ${legacyState}`));
      assert.match(status, /Last reported tick unknown · freshness unknown/);
      status = await setRunner({ status: legacyState, last_tick: await page.evaluate(() => new Date().toISOString()) });
      assert.match(status, new RegExp(`Repository runner reported ${legacyState}`));
      assert.ok(!status.includes('Last reported tick unknown'));
      status = await setRunner({ status: legacyState, last_tick: await reportedTick(7) });
      assert.match(status, /status unknown · stale report/);
      status = await setRunner({ status: legacyState, last_tick: await reportedTick(-1) });
      assert.match(status, /status unknown · report time is ahead/);
    }
    status = await setRunner({ ...publisher.paused, last_tick: await reportedTick() });
    assert.match(status, /Repository runner reported paused/); assert.match(status, /Reported pause by guard/);
    assert.match(status, /the board guard: the board changed outside its data/); assert.match(status, /codex reported out of usage/);
    status = await setRunner({ ...publisher.active, last_tick: await reportedTick(7) });
    assert.match(status, /status unknown · stale report/); assert.match(status, /Last reported state: active/);
    status = await setRunner({ ...publisher.active, last_tick: await reportedTick(-1) });
    assert.match(status, /status unknown · report time is ahead/);
    for (const malformed of [
      { ...publisher.active, paused: { by: 'owner', why: 'paused by hand' } },
      { ...publisher.paused, paused: null },
      { ...publisher.active, schema: 'keeptrack-local-runner/2', status: 'active' },
      { ...publisher.active, last_tick: '2026-02-30T00:00:00Z' },
      { ...publisher.active, engines: { ...publisher.active.engines, codex: { out_of_usage: 'false', sign_in: true, until: null } } },
      { ...publisher.paused, paused: { by: 'owner', why: '<img src=x onerror=window.runnerXss=1>' } },
      { status: 'paused', paused: false }, []
    ]) {
      status = await setRunner(malformed); assert.match(status, /status unknown · invalid report/);
      assert.ok(!status.includes('onerror'));
    }
    status = await setRunner({ status: 'paused', paused: true, paused_by: 'owner', pause_reason: '<img src=x onerror=window.runnerXss=1>', last_tick: await reportedTick(), sign_in: { codex: false, evil: true } });
    assert.match(status, /Repository runner reported paused/); assert.ok(status.includes('<img'));
    assert.equal(await page.locator('.flow-status img, .flow-status script').count(), 0);
    assert.equal(await page.evaluate(() => window.runnerXss), undefined); assert.ok(!status.includes('evil sign-in'));
    await setRunner({ status: 'paused', paused_by: 'owner', pause_reason: 'Maintenance', last_tick: await reportedTick(), sign_in: { codex: false } });
    assert.equal(counts.writes, writesBeforeStatus, 'runner status display never writes the board');
    await page.evaluate(() => { Object.defineProperty(document, 'hidden', { configurable: true, get: () => true }); document.dispatchEvent(new Event('visibilitychange')); });
    const oldAge = await page.locator('.flow-event .hint').first().textContent();
    const hidden = { ...counts }; await page.clock.fastForward(61000);
    assert.deepEqual(counts, hidden);
    await page.evaluate(() => { window.flowGraph = document.querySelector('.flow-canvas'); });
    const refreshed = page.waitForResponse(r => r.url().includes('local-runner.json') && r.status() === 304);
    await page.evaluate(() => { Object.defineProperty(document, 'hidden', { configurable: true, get: () => false }); document.dispatchEvent(new Event('visibilitychange')); });
    await page.waitForFunction(() => document.querySelector('.flow-status')?.textContent.includes('Maintenance'));
    await refreshed; await page.clock.runFor(100); assert.ok(counts.board > hidden.board); assert.ok(conditional > 0);
    // An unchanged board and metadata refresh keeps the exact same graph DOM.
    assert.ok(await page.evaluate(() => window.flowGraph === document.querySelector('.flow-canvas')));
    assert.notEqual(await page.locator('.flow-event .hint').first().textContent(), oldAge);
    // A response arriving while hidden is reconciled from cache on immediate return,
    // even though the 25-second network throttle is still active.
    let releaseRunner, runnerArrived;
    const arrived = new Promise(resolve => { runnerArrived = resolve; });
    const heldUpdate = runnerGate = { arrived: runnerArrived, wait: new Promise(resolve => { releaseRunner = resolve; }) };
    commits[0].commit.message = 'Activity arrives independently';
    commits[0].sha = 'f'.repeat(40);
    runnerVersion++; runner.pause_reason = 'Updated while hidden';
    await page.clock.fastForward(61000); await arrived;
    await page.waitForFunction(() => document.querySelector('.flow-event a')?.href.endsWith('f'.repeat(40)), null, { timeout: 1000 });
    assert.ok(!(await page.locator('.flow-feed').evaluate(node => node.outerHTML)).includes('Activity arrives independently'), 'later commit subjects are also omitted');
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
    boardNetwork = false;
    const recoveredBoard = page.waitForResponse(r => r.url().includes('/contents/board/tasks.json') && [200, 304].includes(r.status()));
    await page.clock.fastForward(31000); await recoveredBoard; await page.clock.runFor(100);
    await page.waitForFunction(() => document.querySelector('#status')?.textContent.includes('Synced'));
    commitsLimited = true;
    const limitedResponse = page.waitForResponse(r => r.url().includes('/commits?') && r.status() === 429);
    await page.clock.fastForward(61000);
    await (await limitedResponse).finished();
    await page.clock.runFor(100);
    await page.waitForFunction(() => document.querySelector('.flow-feed').textContent.includes('Could not refresh'));
    const limitedCount = counts.commits;
    const independentRunnerCount = counts.runner;
    await page.clock.fastForward(61000);
    await page.clock.runFor(100);
    assert.equal(counts.commits, limitedCount, 'Retry-After prevents metadata retries for 120 seconds');
    assert.equal(counts.runner, independentRunnerCount, 'secondary rate-limit Retry-After also pauses runner status despite remaining primary quota');
    commitsLimited = false; await page.clock.fastForward(91000);
    await page.waitForFunction(() => document.querySelectorAll('.flow-event').length === 20 && !document.querySelector('.flow-feed').textContent.includes('Could not refresh'));
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
    // Make the close/history race deterministic: the drawer disappears before its Back traversal completes.
    await page.evaluate(() => {
      const back = history.back.bind(history);
      history.back = () => { window.accessBackRequested = true; };
      window.finishAccessBack = () => new Promise(resolve => {
        window.addEventListener('popstate', () => { history.back = back; resolve(); }, { once: true });
        back();
      });
    });
    boardLost = true;
    await page.clock.fastForward(31000);
    await page.waitForFunction(() => !document.querySelector('#dlgCard').open);
    await page.waitForFunction(() => window.accessBackRequested);
    assert.equal(await page.locator('.flow-card').count(), 0);
    assert.equal(await page.locator('#cTitle').inputValue(), '', 'lost access scrubs the open drawer');
    assert.equal(counts.writes, 0, 'forced drawer close does not save');
    assert.equal(await page.evaluate(() => history.state?.kbDlg), 'dlgCard', 'a hidden drawer alone does not establish completed navigation');
    await page.evaluate(() => window.finishAccessBack());
    await page.waitForFunction(() => history.state?.kbDlg !== 'dlgCard' && !new URL(location.href).searchParams.has('card') && !/^#\d/.test(location.hash));
    boardLost = false;
    // A pending history.back() can cancel page.goto(); navigate only after the old drawer entry is gone.
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
    // Regression coverage for existing retention: a real save supersedes a poll without invalidating connection metadata.
    raw.tasks = [card(1), card(2, { after: ['t_1'] })]; revision++;
    runner = { status: 'paused', pause_reason: 'Keep this last runner copy', last_tick: now }; runnerVersion++;
    await page.goto(`http://127.0.0.1:${server.address().port}/board/index.html?path=tasks.json&board_view=flow#view=flow`);
    await page.waitForFunction(() => document.querySelector('.flow-status')?.textContent.includes('Keep this last runner copy') && document.querySelectorAll('.flow-event').length === 20);
    let releasePoll, pollArrived;
    const pollStarted = new Promise(resolve => { pollArrived = resolve; });
    boardGate = { arrived: pollArrived, wait: new Promise(resolve => { releasePoll = resolve; }) };
    await page.clock.fastForward(31000); await pollStarted;
    await page.locator('[data-card="t_2"]').click(); await page.locator('#dlgCard[open]').waitFor();
    const written = page.waitForResponse(r => r.request().method() === 'PUT');
    await page.locator('#cTitle').fill('Saved while the older board poll is pending'); await page.locator('#cTitle').blur(); await written;
    await page.waitForFunction(() => document.querySelector('#status')?.textContent.includes('Saved'));
    const oldPoll = page.waitForResponse(r => r.request().method() === 'GET' && r.url().includes('/contents/tasks.json'));
    releasePoll(); const staleResponse = await oldPoll; await staleResponse.finished();
    const staleBoard = JSON.parse(Buffer.from((await staleResponse.json()).content, 'base64').toString());
    assert.equal(staleBoard.tasks.find(t => t.id === 't_2').title, 'Task 2', 'the delayed response really contains the pre-save board');
    await page.clock.runFor(100); // Let fetch/JSON continuations and rendering process the stale response.
    assert.equal(await page.locator('#cTitle').inputValue(), 'Saved while the older board poll is pending');
    assert.match(await page.locator('[data-card="t_2"]').innerText(), /Saved while the older board poll is pending/);
    assert.match(await page.locator('#status').innerText(), /Saved/);
    assert.match(await page.locator('.flow-status').innerText(), /Keep this last runner copy/);
    assert.equal(await page.locator('.flow-event').count(), 20, 'a superseded board poll preserves the activity feed');
    await page.locator('#cClose').click(); await page.locator('#dlgCard').waitFor({ state: 'hidden' });
    // Existing transient retention keeps both copies; the new activity label makes the last-copy state explicit.
    runnerNetwork = commitsNetwork = true;
    await page.clock.fastForward(61000);
    await page.waitForFunction(() => document.querySelector('.flow-status')?.textContent.includes('showing last copy') && document.querySelector('.flow-feed')?.textContent.includes('showing last copy'));
    assert.match(await page.locator('.flow-status').innerText(), /Keep this last runner copy/);
    assert.equal(await page.locator('.flow-event').count(), 20);
    runnerNetwork = commitsNetwork = false;
    await page.clock.fastForward(181000);
    await page.waitForFunction(() => document.querySelector('.flow-status')?.textContent.includes('Keep this last runner copy') && document.querySelectorAll('.flow-event').length === 20 && !document.querySelector('.flow-status')?.textContent.includes('Could not refresh') && !document.querySelector('.flow-feed')?.textContent.includes('Could not refresh'));
    // Ordinary activity network failures back off without stopping the healthy runner endpoint.
    commitsNetwork = true;
    for (let i = 0; i < 2; i++) {
      const failure = page.waitForEvent('requestfailed', r => r.url().includes('/commits?'));
      await page.clock.fastForward(61000); await failure; await page.clock.runFor(100);
    }
    const activityBackoff = { ...counts };
    const healthyRunner = page.waitForResponse(r => r.url().includes('local-runner.json'));
    await page.clock.fastForward(61000); await healthyRunner; await page.clock.runFor(100);
    assert.equal(counts.commits, activityBackoff.commits, 'ordinary activity failures retain their own retry backoff');
    assert.ok(counts.runner > activityBackoff.runner, 'healthy runner reads continue during activity network backoff');
    commitsNetwork = false;
    await page.clock.fastForward(181000);
    await page.waitForFunction(() => document.querySelectorAll('.flow-event').length === 20 && !document.querySelector('.flow-feed')?.textContent.includes('Could not refresh'));
    // Persistent runner failures must not inherit the activity endpoint's schedule.
    runnerNetwork = true;
    const runnerBeforeFailures = counts.runner;
    for (let i = 1; i <= 6; i++) {
      commits[0].sha = String(i).repeat(40);
      await page.clock.fastForward(61000);
      await page.waitForFunction(sha => document.querySelector('.flow-event a')?.href.endsWith('/commit/' + sha), commits[0].sha);
      assert.ok(!(await page.locator('.flow-feed').innerText()).includes('Could not refresh'), 'fresh commits continue during repeated runner failure');
    }
    assert.ok(counts.runner - runnerBeforeFailures < 6, 'the failing runner endpoint independently backs off');
    runnerNetwork = false;
    await page.clock.fastForward(301000);
    await page.waitForFunction(() => document.querySelector('.flow-status')?.textContent.includes('Keep this last runner copy') && !document.querySelector('.flow-status')?.textContent.includes('Could not refresh'));
    // An exhausted shared quota still pauses both optional endpoints until its retry deadline.
    for (const limit of ['primary', 'secondary', 'headerless']) {
      primaryReset = Math.floor((await page.evaluate(() => Date.now()) + 301000) / 1000);
      runnerSharedLimit = limit;
      const limitedRunner = page.waitForResponse(r => r.url().includes('local-runner.json') && r.status() === (limit === 'primary' ? 403 : 429));
      await page.clock.fastForward(61000);
      await (await limitedRunner).finished(); await page.clock.runFor(100);
      await page.waitForFunction(() => document.querySelector('.flow-status')?.textContent.includes('Could not refresh'));
      const sharedCounts = { ...counts };
      await page.clock.fastForward(limit === 'headerless' ? 31000 : 61000); await page.clock.runFor(100);
      assert.equal(counts.runner, sharedCounts.runner);
      assert.equal(counts.commits, sharedCounts.commits, limit + ' GitHub rate limit pauses activity too');
      runnerSharedLimit = false;
      await page.clock.fastForward(91000);
      if (limit === 'primary') {
        await page.clock.runFor(100);
        assert.equal(counts.runner, sharedCounts.runner, 'a later primary reset takes precedence over the shorter Retry-After');
        assert.equal(counts.commits, sharedCounts.commits);
        await page.clock.fastForward(121000);
      }
      await page.waitForFunction(() => document.querySelector('.flow-status')?.textContent.includes('Keep this last runner copy') && !document.querySelector('.flow-status')?.textContent.includes('Could not refresh'));
    }
    commitsLimited = 'headerless';
    const headerlessCommit = page.waitForResponse(r => r.url().includes('/commits?') && r.status() === 429);
    await page.clock.fastForward(61000); await (await headerlessCommit).finished(); await page.clock.runFor(100);
    const headerlessCounts = { ...counts };
    await page.clock.fastForward(31000); await page.clock.runFor(100);
    assert.equal(counts.runner, headerlessCounts.runner, 'a headerless activity 429 shares its fallback cooldown with runner reads');
    assert.equal(counts.commits, headerlessCounts.commits);
    commitsLimited = false; await page.clock.fastForward(61000);
    await page.waitForFunction(() => document.querySelectorAll('.flow-event').length === 20 && !document.querySelector('.flow-feed')?.textContent.includes('Could not refresh'));
    assert.deepEqual(errors, []);
    console.log('flow: 114-card UI, 12,000-card chain, filtered cycles, credentials, public quota, polling, alerts, runner status and screenshots passed');
  } finally { await browser.close(); server.close(); }
})().catch(e => { console.error(e); process.exit(1); });

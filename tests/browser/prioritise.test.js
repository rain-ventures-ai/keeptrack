'use strict';

const assert = require('node:assert/strict');
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');

const ROOT = path.resolve(__dirname, '../..');
const mime = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json', '.svg': 'image/svg+xml' };
const server = http.createServer((req, res) => {
  const rel = decodeURIComponent(new URL(req.url, 'http://local').pathname).replace(/^\/+/, '') || 'board/index.html';
  const file = path.resolve(ROOT, rel); if (!file.startsWith(ROOT + path.sep)) { res.writeHead(403).end(); return; }
  fs.readFile(file, (err, data) => { if (err) res.writeHead(404).end(); else { res.setHeader('Content-Type', mime[path.extname(file)] || 'application/octet-stream'); res.end(data); } });
});

const root = { version: 4, layout: 'split', settings: { title: 'Test' }, columns: [{ id: 'todo', name: 'To do' }, { id: 'done', name: 'Done' }], people: [{ github: 'alex', name: 'Alex' }], agents: ['codex'], clients: ['Acme'], labels: [{ name: 'pale', color: '#dce1e7' }, { name: 'dark', color: '#334155' }], client_info: {}, next_num: 3, archive: { files: {} } };
const cards = {
  'cards/t_one.json': { id: 't_one', num: 1, title: 'First', column: 'todo', client: 'Acme', priority: 'high', due: '', labels: ['pale', 'dark'], assignees: ['alex'], details: '', links: [], contacts: [], todos: [], comments: [], history: [], claim: null, created: '2026-10-01T08:00:00.000Z', updated: '2026-10-01T08:00:00.000Z', rank: 'a0' },
  'cards/t_two.json': { id: 't_two', num: 2, title: 'Second', column: 'todo', client: '', priority: 'medium', due: '', labels: [], assignees: [], details: '', links: [], contacts: [], todos: [], comments: [], history: [], claim: null, created: '2026-10-02T08:00:00.000Z', updated: '2026-10-02T08:00:00.000Z', rank: 'a1' },
};
const person = { id: 'p_one', name: 'Casey Example', company: 'Acme', role: '', email: '', phone: '', linkedin: '', stage: 'New', value: '', source: '', notes: '', next: '', next_due: '', links: [], comments: [], history: [], created: '2026-10-01T08:00:00.000Z', updated: '2026-10-01T08:00:00.000Z' };
const text = x => JSON.stringify(x, null, 2) + '\n';

class Github {
  constructor(v4 = true) { this.v4 = v4; this.files = v4 ? { 'tasks.json': text(root), ...Object.fromEntries(Object.entries(cards).map(([k, v]) => [k, text(v)])), 'people/p_one.json': text(person) } : { 'tasks.json': text({ ...root, version: 3, layout: undefined, tasks: Object.values(cards), contacts: [person] }) }; this.readme = null; this.head = 'head-1'; this.n = 1; this.calls = []; this.blobs = {}; this.pending = null; this.failPatch = false; this.denyRepo = false; this.visibleRepos = [{ full_name: 'acme/another-board', permissions: { push: true } }]; }
  sha(p) { return require('node:crypto').createHash('sha1').update(this.files[p] || '').digest('hex'); }   // content-addressed, like git
  tree() { return Object.entries(this.files).map(([p, content]) => ({ path: p, type: 'blob', sha: this.sha(p), size: Buffer.byteLength(content) })); }
  async route(route) {
    const req = route.request(), u = new URL(req.url()), method = req.method(), p = u.pathname.replace('/repos/acme/board', ''); this.calls.push({ method, path: p + u.search, body: req.postDataJSON?.(), auth: req.headers()['authorization'] || '' });
    if (this.delayRead && method === 'GET') await new Promise(resolve => setTimeout(resolve, this.delayRead));
    const json = (body, status = 200, headers = {}) => route.fulfill({ status, headers: { 'Content-Type': 'application/json', ...headers }, body: JSON.stringify(body) });
    if (p === '/user' && method === 'GET') return json({ login: 'alex' });
    if (p.startsWith('/contents/board/KIT_VERSION') && method === 'GET') return route.fulfill({ status: 200, body: '49' });
    if (p.startsWith('/user/repos') && method === 'GET') return json(this.visibleRepos);
    if (p === '' && method === 'GET') return this.denyRepo ? json({ message: 'Not Found' }, 404) : json({ full_name: 'acme/board', private: true, permissions: { push: true }, default_branch: 'main' });
    if (p.startsWith('/contents/README.md') && method === 'GET') {
      if (this.readme == null) return json({ message: 'Not Found' }, 404);
      return json({ sha: 'readme-sha', size: Buffer.byteLength(this.readme), encoding: 'base64', content: Buffer.from(this.readme).toString('base64') });
    }
    if (p.startsWith('/contents/README.md') && method === 'PUT') { const b = req.postDataJSON(); this.readme = Buffer.from(b.content, 'base64').toString(); return json({ content: { sha: 'readme-sha' }, commit: { sha: 'readme-commit' } }); }
    if (p.startsWith('/contents/board/tasks.json') && method === 'GET') {
      if (!this.files['tasks.json']) return json({ message: 'Not Found' }, 404);
      return json({ sha: this.sha('tasks.json'), size: Buffer.byteLength(this.files['tasks.json']), encoding: 'base64', content: Buffer.from(this.files['tasks.json']).toString('base64') }, 200, { ETag: '"tasks"' });
    }
    if (p.startsWith('/contents/board/') && method === 'PUT') { const rel = p.slice('/contents/board/'.length), b = req.postDataJSON(); this.files[rel] = Buffer.from(b.content, 'base64').toString(); this.head = 'head-' + ++this.n; return json({ content: { sha: this.sha(rel) }, commit: { sha: this.head, tree: { sha: 'root-' + this.n } } }); }
    if (p.startsWith('/contents/board/') && method === 'DELETE') { const rel = p.slice('/contents/board/'.length); delete this.files[rel]; this.head = 'head-' + ++this.n; return json({ commit: { sha: this.head, tree: { sha: 'root-' + this.n } } }); }
    if (p === '/git/ref/heads/main' && method === 'GET') return json({ object: { sha: this.head } }, 200, { ETag: '"' + this.head + '"' });
    if (p.startsWith('/git/commits/') && method === 'GET') return json({ tree: { sha: 'root-' + this.n } });
    if (p.startsWith('/git/trees/root-') && method === 'GET') return json({ tree: [{ path: 'board', type: 'tree', sha: 'board-' + this.n }] });
    if (p.startsWith('/git/trees/board-') && method === 'GET') return json({ truncated: false, tree: this.tree() });
    if (p.startsWith('/git/blobs/') && method === 'GET') { const sha = p.split('/').pop(), rel = Object.keys(this.files).find(x => this.sha(x) === sha); return json({ encoding: 'base64', content: Buffer.from(this.files[rel]).toString('base64') }); }
    if (p === '/git/blobs' && method === 'POST') { const b = req.postDataJSON(), sha = 'new-blob-' + ++this.n; this.blobs[sha] = b.content; return json({ sha }); }
    if (p === '/git/trees' && method === 'POST') { this.pending = req.postDataJSON().tree; return json({ sha: 'new-tree-' + ++this.n }); }
    if (p === '/git/commits' && method === 'POST') return json({ sha: 'new-commit-' + ++this.n });
    if (p === '/git/refs/heads/main' && method === 'PATCH') { if (this.failPatch) { this.failPatch = false; this.head = 'racing-head'; return json({ message: 'Reference update failed' }, 422); }
      for (const e of this.pending || []) { const rel = e.path.replace(/^board\//, ''); if (e.sha === null) delete this.files[rel]; else this.files[rel] = this.blobs[e.sha]; } this.head = req.postDataJSON().sha; return json({ object: { sha: this.head } }); }
    return json({ message: 'not mocked: ' + method + ' ' + p }, 404);
  }
}

let base;
(async () => {
  await new Promise(ok => server.listen(0, '127.0.0.1', ok)); base = 'http://127.0.0.1:' + server.address().port;
  const browser = await chromium.launch({ headless: true });
  try {
    const api = new Github(), page = await browser.newPage({ viewport: { width: 1280, height: 860 } }), errors = [];
    if (process.env.CPU_RATE) { const session = await page.context().newCDPSession(page); await session.send('Emulation.setCPUThrottlingRate', { rate: Number(process.env.CPU_RATE) }); }
    const member = JSON.parse(api.files['people/p_one.json']); member.name = 'Alex'; member.github = 'alex'; api.files['people/p_one.json'] = text(member);
    page.on('pageerror', e => errors.push(e.message));
    const seed = JSON.parse(api.files['cards/t_one.json']); seed.value = 5; seed.effort = 'S'; api.files['cards/t_one.json'] = text(seed);
    for (let i = 3; i <= 35; i++) api.files['cards/t_' + i + '.json'] = text({ ...seed, id: 't_' + i, num: i, title: 'Fictional task ' + i + ' with a long title and useful outcome', column: i % 2 ? 'todo' : 'done', client: i % 3 ? 'Acme' : '', rank: 'a' + i, value: i === 5 ? 5 : i % 5 + 1, effort: 'M' });
    await page.addInitScript(() => {
      localStorage.setItem('kb_repo', 'acme/board'); localStorage.setItem('kb_branch', 'main'); localStorage.setItem('kb_path', 'board/tasks.json'); localStorage.setItem('kb_token', 'test'); localStorage.setItem('kb_me', 'alex'); localStorage.setItem('kb_api', 'https://api.test'); localStorage.setItem('kb_layout', 'classic'); localStorage.setItem('kb_tour', 'done'); sessionStorage.setItem('kb_view', 'list');
    });
    await page.route('https://api.test/**', route => api.route(route));
    await page.goto(base + '/board/index.html');
    await page.locator('#listPrioritise').waitFor();
    // Client and all selected filter controls are bookmarkable, including an explicit
    // clear snapshot. Reloads/asset upgrades and browser history restore the same scope.
    await page.locator('.cpill').filter({ hasText: 'Acme' }).click({ position: { x: 25, y: 15 } });
    await page.waitForFunction(() => new URL(location.href).searchParams.get('client') === 'Acme');
    await page.reload();
    await page.waitForFunction(() => document.getElementById('fClient').selectedOptions[0]?.value === 'Acme');
    assert.equal(await page.locator('.cpill.on').first().textContent().then(s => s.includes('Acme')), true);
    await page.locator('#listStatus').selectOption('__open');
    await page.waitForFunction(() => new URL(location.href).searchParams.get('status') === '__open');
    await page.goBack();
    await page.waitForFunction(() => document.getElementById('fStatus').value === '' && document.getElementById('fClient').selectedOptions[0]?.value === 'Acme');
    await page.goForward();
    await page.waitForFunction(() => document.getElementById('fStatus').value === '__open');
    await page.locator('#fClear').evaluate(b => b.click());
    await page.waitForFunction(() => !new URL(location.href).searchParams.has('client') && !new URL(location.href).searchParams.has('status'));
    await page.reload();
    await page.locator('#listPrioritise').waitFor();
    assert.equal(await page.locator('#fClient').evaluate(s => s.selectedOptions.length), 0);
    assert.equal(await page.locator('#fStatus').inputValue(), '');
    await page.locator('#listPrioritise').click();
    await page.locator('.prioritise-row').first().waitFor();
    assert.equal(new URL(page.url()).searchParams.get('layout'), 'prioritise');
    await page.locator('#prioritiseSort').selectOption('score');
    await page.reload();
    await page.waitForFunction(() => document.getElementById('prioritiseSort')?.value === 'score');
    await page.waitForTimeout(100);
    await page.locator('#prioritiseSort').selectOption('manual');
    await page.waitForFunction(() => new URL(location.href).searchParams.get('order') === 'manual');
    assert.equal(await page.locator('#prioritiseSort').inputValue(), 'manual');
    assert.equal(await page.locator('[data-list-task="t_one"] .prioritise-score').textContent(), '2.5');
    assert.equal(await page.locator('[data-list-task="t_two"] .prioritise-score').textContent(), '—');
    const order = () => page.locator('.prioritise-row').evaluateAll(rs => rs.map(r => r.dataset.listTask));
    const before = await order();
    await page.locator('[data-list-task="t_two"] [data-list-control="up"]').click();
    await page.waitForFunction(() => /^Saved /.test(document.getElementById('status').textContent));
    assert.equal((await order())[0], 't_two');
    assert.equal((await order())[1], 't_one');
    assert.equal(JSON.parse(api.files['cards/t_one.json']).rank, 'a0', 'column rank unchanged');
    // Keyboard moves invoke the same persisted board-wide relative intent, in both directions.
    let keyboardHead = api.head;
    await page.locator('[data-list-task="t_two"] [data-list-control="open"]').press('Alt+ArrowDown');
    for (let i = 0; i < 100 && api.head === keyboardHead; i++) await page.waitForTimeout(20);
    assert.notEqual(api.head, keyboardHead, 'Alt+ArrowDown commits');
    await page.waitForFunction(() => /^Saved /.test(document.getElementById('status').textContent));
    assert.deepEqual((await order()).slice(0, 2), ['t_one', 't_two']);
    keyboardHead = api.head;
    await page.locator('[data-list-task="t_two"] [data-list-control="open"]').press('Alt+ArrowUp');
    for (let i = 0; i < 100 && api.head === keyboardHead; i++) await page.waitForTimeout(20);
    assert.notEqual(api.head, keyboardHead, 'Alt+ArrowUp commits');
    await page.waitForFunction(() => /^Saved /.test(document.getElementById('status').textContent));
    assert.deepEqual((await order()).slice(0, 2), ['t_two', 't_one']);
    await page.locator('#prioritiseSort').selectOption('score');
    assert.equal((await order())[0], 't_one');
    assert.equal((await order()).at(-1), 't_two', 'unscored tasks sort last');
    assert((await order()).indexOf('t_4') < (await order()).indexOf('t_5'), 'equal scores retain manual order');
    assert(await page.locator('[data-list-task="t_one"] [data-list-control="down"]').isDisabled());
    await page.locator('#prioritiseSort').selectOption('manual');
    await page.evaluate(() => { document.getElementById('board').scrollTop = 450; });
    const pos = await page.locator('#board').evaluate(b => b.scrollTop);
    await page.evaluate(() => { const b = document.getElementById('board'), top = b.getBoundingClientRect().top, row = [...b.querySelectorAll('.prioritise-row')].find(r => r.getBoundingClientRect().top >= top); const s = row.querySelector('[data-list-control="value"]'); s.focus({ preventScroll: true }); s.value = '5'; s.dispatchEvent(new Event('change')); });
    await page.waitForFunction(() => /^Saved /.test(document.getElementById('status').textContent));
    assert(Math.abs(await page.locator('#board').evaluate(b => b.scrollTop) - pos) < 2, 'score save preserves scroll');
    assert.equal(await page.evaluate(() => document.activeElement.dataset.listControl), 'value', 'score save preserves focus');
    assert.deepEqual(await order(), [before[1], before[0], ...before.slice(2)], 'editing score never reorders manual rows');
    const focusedTask = await page.evaluate(() => document.activeElement.closest('[data-list-task]').dataset.listTask);
    const refreshedCard = JSON.parse(api.files['cards/' + focusedTask + '.json']); refreshedCard.value = 3; api.files['cards/' + focusedTask + '.json'] = text(refreshedCard); api.head = 'remote-refresh-head';
    await page.evaluate(() => document.getElementById('btnRefresh').click());
    await page.waitForFunction(id => document.querySelector('[data-list-task="' + id + '"] [data-list-control="value"]')?.value === '3' && !/^(Loading|Refreshing)/.test(document.getElementById('status').textContent), focusedTask);
    assert(Math.abs(await page.locator('#board').evaluate(b => b.scrollTop) - pos) < 2, 'GitHub refresh preserves scroll');
    assert.equal(await page.evaluate(() => document.activeElement.closest('[data-list-task]')?.dataset.listTask), focusedTask, 'GitHub refresh preserves focused task');
    assert.equal(await page.evaluate(() => document.activeElement.dataset.listControl), 'value', 'GitHub refresh preserves focused control');
    // A conflicting save retries the relative move against a newly moved neighbour, retaining its other changes.
    api.failPatch = true;
    const third = JSON.parse(api.files['cards/t_3.json']); third.details = 'Intervening remote edit'; third.priority_rank = 'Zy'; api.files['cards/t_3.json'] = text(third);
    await page.locator('[data-list-task="t_one"] [data-list-control="up"]').click();
    await page.waitForFunction(() => /^Saved /.test(document.getElementById('status').textContent));
    assert.equal(JSON.parse(api.files['cards/t_3.json']).details, 'Intervening remote edit');
    assert.deepEqual((await order()).slice(0, 3), ['t_3', 't_one', 't_two'], 'retry uses latest global ranks');
    // Filtered move crosses a hidden task without shuffling other hidden tasks.
    const fullOrderBeforeFiltered = await order();
    const hiddenRank = JSON.parse(api.files['cards/t_two.json']).priority_rank;
    await page.locator('#btnFilter').click(); await page.locator('#fLabel').selectOption('dark');
    await page.locator('#btnFilter').click();
    const beforeMove = api.head;
    await page.locator('[data-list-task="t_one"] [data-list-control="down"]').click();
    for (let i = 0; i < 100 && api.head === beforeMove; i++) await page.waitForTimeout(20);
    assert.notEqual(api.head, beforeMove, 'filtered move is committed');
    await page.waitForFunction(() => /^Saved /.test(document.getElementById('status').textContent));
    await page.locator('#btnFilter').click(); await page.locator('#fLabel').selectOption(''); await page.locator('#btnFilter').click();
    assert.equal(JSON.parse(api.files['cards/t_two.json']).priority_rank, hiddenRank);
    assert((await order()).indexOf('t_4') < (await order()).indexOf('t_one'), 'filtered move crosses the neighbouring visible task across columns');
    assert.deepEqual((await order()).filter(id => id !== 't_one'), fullOrderBeforeFiltered.filter(id => id !== 't_one'), 'all untouched visible and hidden tasks retain relative order');
    // Status is discoverable inline and shares one state with the global filter panel.
    await page.locator('#listStatus').selectOption('__open');
    assert.equal(await page.locator('#fStatus').inputValue(), '__open');
    assert.equal(await page.evaluate(() => document.activeElement.id), 'listStatus', 'status filtering retains keyboard focus');
    assert((await order()).every(id => JSON.parse(api.files['cards/' + id + '.json']).column !== 'done'));
    await page.locator('#listStatus').selectOption('done');
    assert((await order()).every(id => JSON.parse(api.files['cards/' + id + '.json']).column === 'done'));
    await page.locator('#btnFilter').click(); await page.locator('#fClear').click();
    assert.equal(await page.locator('#listStatus').inputValue(), '');
    assert.equal(await page.locator('#filterBadge').isVisible(), false);
    const customRoot = JSON.parse(api.files['tasks.json']); customRoot.columns.push({ id: 'review', name: 'Review needed' }); api.files['tasks.json'] = text(customRoot);
    const customCard = JSON.parse(api.files['cards/t_35.json']); customCard.column = 'review'; api.files['cards/t_35.json'] = text(customCard); api.head = 'custom-status-head';
    await page.locator('#btnRefresh').click();
    await page.locator('#listStatus option[value="review"]').waitFor({ state: 'attached' });
    await page.locator('#listStatus').selectOption('review'); assert.deepEqual(await order(), ['t_35'], 'custom columns are filterable');
    await page.locator('#listStatus').selectOption('');
    await page.locator('#btnFilter').click(); await page.locator('#fHideDone').check(); await page.locator('#btnFilter').click();
    await page.locator('#listStatus').selectOption('done'); assert.equal(await page.locator('#fHideDone').isChecked(), false, 'explicit status overrides hide done');
    await page.locator('#btnFilter').click(); await page.locator('#fHideDone').check();
    assert.equal(await page.locator('#fStatus').inputValue(), '', 'hide done clears conflicting Done status');
    await page.locator('#fClear').click();
    for (const width of [768, 980]) {
      await page.setViewportSize({ width, height: 860 });
      await page.locator('#board').evaluate(b => b.scrollTop = 0);
      assert(await page.locator('.prioritise-head').isVisible(), 'tablet retains compact table');
      assert(await page.locator('[data-list-task="t_one"] select[data-list-control="value"]').isVisible());
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
      await page.screenshot({ path: '/tmp/prioritise-' + width + '-light.png', fullPage: true });
      await page.evaluate(() => window.kbTheme.set('dark'));
      await page.waitForTimeout(300); // wait for token-driven button transitions before visual proof
      await page.screenshot({ path: '/tmp/prioritise-' + width + '-dark.png', fullPage: true });
      await page.evaluate(() => window.kbTheme.set('light'));
      await page.waitForTimeout(300);
    }
    // Mobile controls are disclosed, with no horizontal scrolling.
    await page.setViewportSize({ width: 350, height: 780 });
    await page.locator('#board').evaluate(b => b.scrollTop = 0);
    await page.waitForFunction(() => !/^Saving/.test(document.getElementById('status').textContent));
    await page.locator('[data-list-task="t_two"] .prioritise-expand').click();
    assert(await page.locator('[data-list-task="t_two"] select[data-list-control="value"]').isVisible());
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    await page.screenshot({ path: '/tmp/prioritise-phone-light.png', fullPage: true });
    await page.evaluate(() => window.kbTheme.set('dark')); await page.waitForTimeout(300);
    await page.screenshot({ path: '/tmp/prioritise-phone-dark.png', fullPage: true });
    await page.setViewportSize({ width: 1280, height: 860 });
    await page.screenshot({ path: '/tmp/prioritise-desktop-dark.png', fullPage: true });
    await page.evaluate(() => window.kbTheme.set('light')); await page.waitForTimeout(300);
    await page.screenshot({ path: '/tmp/prioritise-desktop-light.png', fullPage: true });
    await page.locator('#listPrioritise').click(); assert.equal(await page.locator('.prioritise-row').count(), 0);
    await page.locator('#btnFilter').click(); await page.locator('#sortMenu').selectOption('newest'); await page.locator('#btnFilter').click();
    const standardOrder = await page.locator('.lsec[data-col="todo"] [data-list-task]').evaluateAll(rs => rs.map(r => r.dataset.listTask));
    assert(standardOrder.indexOf('t_two') < standardOrder.indexOf('t_one'), 'standard List applies selected newest sort');
    const bookmark = new URL(page.url());
    bookmark.searchParams.set('client', 'Acme'); bookmark.searchParams.set('status', 'review');
    bookmark.searchParams.set('layout', 'prioritise'); bookmark.searchParams.set('order', 'score'); bookmark.hash = '#1';
    await page.goto(bookmark.href);
    await page.locator('#dlgCard[open]').waitFor();
    assert.equal(await page.locator('#fStatus').inputValue(), 'review', 'custom status survives reload');
    const safeLink = await page.evaluate(() => window.kbNavigation.link('#settings=prefs'));
    assert.equal(new URL(safeLink).searchParams.get('client'), 'Acme');
    assert.equal(new URL(safeLink).searchParams.get('order'), 'score');
    await page.locator('#dlgCard').evaluate(d => d.close());
    await page.waitForFunction(() => !document.getElementById('dlgCard').open && new URL(location.href).searchParams.get('client') === 'Acme');
    assert.equal(await page.locator('#fStatus').inputValue(), 'review', 'closing drawer restores filters');
    // A link from another browser may reference a client/status absent in the
    // cached board. Keep it until the fresh snapshot arrives, not silently All.
    const futureRoot = JSON.parse(api.files['tasks.json']); futureRoot.clients.push('Future client'); futureRoot.columns.push({ id: 'future', name: 'Future status' }); api.files['tasks.json'] = text(futureRoot);
    const futureCard = JSON.parse(api.files['cards/t_35.json']); futureCard.client = 'Future client'; futureCard.column = 'future'; api.files['cards/t_35.json'] = text(futureCard); api.head = 'future-status-head'; api.delayRead = 40;
    const futureLink = new URL(page.url()); futureLink.searchParams.set('client', 'Future client'); futureLink.searchParams.set('status', 'future'); futureLink.hash = '#view=list';
    await page.goto(futureLink.href); await page.locator('#listPrioritise').waitFor();
    assert.equal(new URL(page.url()).searchParams.get('client'), 'Future client', 'stale cache must not erase unseen client');
    await page.waitForFunction(() => document.getElementById('fStatus').value === 'future' && document.getElementById('fClient').selectedOptions[0]?.value === 'Future client');
    assert.deepEqual(await order(), ['t_35']); api.delayRead = 0;
    const unsafe = new URL(page.url()); unsafe.hash = '#view=list';
    unsafe.searchParams.set('client', '<img src=x onerror=alert(1)>'); unsafe.searchParams.set('status', 'unknown-column');
    unsafe.searchParams.set('priority', 'bad'); unsafe.searchParams.set('order', 'bad');
    unsafe.searchParams.set('token', 'must-not-copy'); unsafe.searchParams.set('kbcfg', 'must-not-copy');
    await page.goto(unsafe.href); await page.locator('#listPrioritise').waitFor();
    await page.waitForFunction(() => !new URL(location.href).searchParams.has('token'));
    assert.equal(await page.locator('#fClient').evaluate(s => s.selectedOptions.length), 0);
    assert.equal(await page.locator('#fStatus').inputValue(), '');
    assert.equal(await page.locator('#fPrio').inputValue(), '');
    assert.equal(await page.locator('#prioritiseSort').inputValue(), 'manual');
    assert(!new URL(await page.evaluate(() => window.kbNavigation.link('#help'))).searchParams.has('kbcfg'));
    assert.equal(errors.length, 0, errors.join('\n'));
    await page.close();
    const readonly = await browser.newPage({ viewport: { width: 350, height: 780 } });
    await readonly.addInitScript(() => sessionStorage.setItem('kb_view', 'list'));
    await readonly.goto(base + '/board/index.html?demo=board'); await readonly.locator('#listPrioritise').click();
    assert(await readonly.locator('.prioritise-rank button').first().isDisabled(), 'read-only rank controls disabled');
    await readonly.locator('.prioritise-expand').first().click();
    assert(await readonly.locator('.prioritise-value select').first().isDisabled(), 'read-only scoring controls disabled');
    await readonly.close(); console.log('Prioritise list: pass');
  } finally { await browser.close(); server.close(); }
})().catch(e => { console.error(e); process.exitCode = 1; server.close(); });


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
    const json = (body, status = 200, headers = {}) => route.fulfill({ status, headers: { 'Content-Type': 'application/json', ...headers }, body: JSON.stringify(body) });
    if (p === '/user' && method === 'GET') return json({ login: 'alex' });
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

async function openBoard(browser, api) {
  const page = await browser.newPage(); page.on('pageerror', e => console.error('page error:', e.message)); await page.addInitScript(() => { localStorage.setItem('kb_repo', 'acme/board'); localStorage.setItem('kb_branch', 'main'); localStorage.setItem('kb_path', 'board/tasks.json'); localStorage.setItem('kb_token', 'test'); localStorage.setItem('kb_me', 'alex'); localStorage.setItem('kb_api', 'https://api.test'); localStorage.setItem('kb_view', 'board'); });
  await page.route('https://api.test/**', r => api.route(r)); await page.goto(base + '/board/index.html'); try { await page.waitForSelector('.card, .todayhead'); } catch (e) { console.error('status:', await page.locator('#status').textContent().catch(() => '?'), 'calls:', api.calls); throw e; } return page;
}

let base;
(async () => {
  await new Promise(ok => server.listen(0, '127.0.0.1', ok)); base = `http://127.0.0.1:${server.address().port}`; const browser = await chromium.launch({ headless: true });
  try {
    for (const kind of ['crm', 'board']) {
      const demo = await browser.newPage(); await demo.goto(base + '/board/index.html?demo=' + kind); await demo.locator('#roBar').waitFor({ state: 'visible' });
      const details = demo.locator('#roBar a.morelink'); assert.equal(await details.textContent(), 'View the repository for more details'); assert.equal(await details.getAttribute('href'), 'https://github.com/rain-ventures-ai/keeptrack'); assert.equal(await details.getAttribute('target'), '_blank'); await demo.close();
    }

    // Every browser creation path starts on split schema v4 and adds a root README that links back to Keeptrack.
    // The empty board writes only its board root/index; the first task then gets its own card file without a legacy v3 round trip.
    const freshApi = new Github(true); freshApi.files = {};
    const fresh = await browser.newPage(); fresh.on('dialog', d => d.accept());
    await fresh.addInitScript(() => { localStorage.setItem('kb_repo', 'acme/board'); localStorage.setItem('kb_branch', 'main'); localStorage.setItem('kb_path', 'board/tasks.json'); localStorage.setItem('kb_token', 'test'); localStorage.setItem('kb_me', 'alex'); localStorage.setItem('kb_api', 'https://api.test'); localStorage.setItem('kb_view', 'board'); });
    await fresh.route('https://api.test/**', r => freshApi.route(r)); await fresh.goto(base + '/board/index.html');
    const create = fresh.locator('button', { hasText: 'Create a new empty board' }); await create.waitFor(); const created = fresh.waitForResponse(r => r.request().method() === 'PUT' && r.url().includes('/contents/board/tasks.json')); const readmeCreated = fresh.waitForResponse(r => r.request().method() === 'PUT' && r.url().includes('/contents/README.md')); await create.click(); await Promise.all([created, readmeCreated]);
    const freshRoot = JSON.parse(freshApi.files['tasks.json']); assert.equal(freshRoot.version, 4); assert.equal(freshRoot.layout, 'split'); assert(!('tasks' in freshRoot)); assert(!('contacts' in freshRoot));
    assert.match(freshApi.readme, /powered by \[Keeptrack\]/); assert.match(freshApi.readme, /repo=acme%2Fboard/); assert.match(freshApi.readme, /path=board%2Ftasks\.json/);
    const freshAdd = fresh.locator('.col[data-col="todo"] .add input'); await freshAdd.fill('First v4 task'); const freshSaved = fresh.waitForResponse(r => r.request().method() === 'PATCH' && r.url().includes('/git/refs/heads/main')); await freshAdd.press('Enter'); await freshSaved;
    assert.equal(Object.keys(freshApi.files).filter(p => p.startsWith('cards/')).length, 1); assert(!('tasks' in JSON.parse(freshApi.files['tasks.json']))); await fresh.close();

    // Creating a board in an existing project never replaces that project's README.
    const documentedApi = new Github(true); documentedApi.files = {}; documentedApi.readme = '# Existing project\n';
    const documented = await browser.newPage(); documented.on('dialog', d => d.accept());
    await documented.addInitScript(() => { localStorage.setItem('kb_repo', 'acme/board'); localStorage.setItem('kb_branch', 'main'); localStorage.setItem('kb_path', 'board/tasks.json'); localStorage.setItem('kb_token', 'test'); localStorage.setItem('kb_me', 'alex'); localStorage.setItem('kb_api', 'https://api.test'); localStorage.setItem('kb_view', 'board'); });
    await documented.route('https://api.test/**', r => documentedApi.route(r)); await documented.goto(base + '/board/index.html'); const documentedCreate = documented.locator('button', { hasText: 'Create a new empty board' }); await documentedCreate.waitFor(); const documentedBoard = documented.waitForResponse(r => r.request().method() === 'PUT' && r.url().includes('/contents/board/tasks.json')); const readmeChecked = documented.waitForResponse(r => r.request().method() === 'GET' && r.url().includes('/contents/README.md')); await documentedCreate.click(); await Promise.all([documentedBoard, readmeChecked]);
    assert.equal(documentedApi.readme, '# Existing project\n'); assert(!documentedApi.calls.some(x => x.method === 'PUT' && x.path.startsWith('/contents/README.md'))); await documented.close();

    const api = new Github(true), page = await openBoard(browser, api);
    assert.deepEqual(await page.locator('.card .t').allTextContents(), ['First', 'Second']);
    const labelStyles = await page.locator('.card .tag.label').evaluateAll(xs => xs.map(x => ({ text: x.textContent, background: getComputedStyle(x).backgroundColor, color: getComputedStyle(x).color })));
    assert.deepEqual(labelStyles, [{ text: 'pale', background: 'rgb(220, 225, 231)', color: 'rgb(0, 0, 0)' }, { text: 'dark', background: 'rgb(51, 65, 85)', color: 'rgb(255, 255, 255)' }]);
    assert.equal(await page.locator('#viewSw .vgrp').count(), 0);
    assert.deepEqual(await page.locator('#viewSw > .viewgroup').evaluateAll(xs => xs.map(x => x.getAttribute('aria-label'))), ['Today', 'People views', 'Task views']);
    assert.deepEqual(await page.locator('#viewSw > .viewgroup[data-grp="today"] button').evaluateAll(xs => xs.map(x => x.dataset.view)), ['today']);
    assert.deepEqual(await page.locator('#viewSw > .viewgroup[data-grp="crm"] button').evaluateAll(xs => xs.map(x => x.dataset.view)), ['people', 'pipeline']);
    assert.deepEqual(await page.locator('#viewSw > .viewgroup[data-grp="tasks"] button').evaluateAll(xs => xs.map(x => x.dataset.view)), ['board', 'list', 'cal', 'sched', 'activity']);
    const visibleViewLabels = () => page.locator('#viewSw .vt').evaluateAll(xs => xs.filter(x => getComputedStyle(x).display !== 'none').map(x => x.textContent.trim()));
    assert.deepEqual(await visibleViewLabels(), ['People', 'Kanban']);
    const taskGroupX = (await page.locator('#viewSw .viewgroup[data-grp="tasks"]').boundingBox()).x; await page.locator('#viewSw button[data-view="people"]').click(); assert.equal((await page.locator('#viewSw .viewgroup[data-grp="tasks"]').boundingBox()).x, taskGroupX, 'selecting a People view must not move the Task views group'); assert.deepEqual(await visibleViewLabels(), ['People', 'Kanban']); await page.locator('#viewSw button[data-view="list"]').click(); assert.deepEqual(await visibleViewLabels(), ['People', 'Kanban']); await page.locator('#viewSw button[data-view="board"]').click();
    await page.evaluate(() => { window.__copied = ''; Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText: async text => { window.__copied = text; } } }); });
    assert.equal(await page.locator('#btnAgent, #btnCopyMd, #fCopyMd, #sortMenuMobile, .sortpick').count(), 0);
    await page.locator('#btnCopy').click(); assert.equal(await page.locator('#dlgCopy').getAttribute('open'), ''); assert.deepEqual(await page.locator('#dlgCopy .copychoices b').allTextContents(), ['Copy as Markdown', 'Copy prompt for an agent']); await page.locator('#copyAgent').click(); assert.match(await page.evaluate(() => window.__copied), /You are working from the Keeptrack board/);
    await page.locator('#btnCopy').click(); await page.locator('#copyMarkdown').click(); assert.match(await page.evaluate(() => window.__copied), /^# Board: acme\/board/);
    await page.locator('#btnHelp').click(); const helpRepo = page.locator('#dlgHelp .mainRepoLink'); assert.equal(await helpRepo.getAttribute('href'), 'https://github.com/rain-ventures-ai/keeptrack'); assert.equal(await helpRepo.getAttribute('target'), '_blank'); await page.locator('#hSetupPrompt').click(); assert.match(await page.evaluate(() => window.__copied), /in this conversation.*Do not just explain the options/); await page.locator('#hClose').click();
    await page.locator('#btnSettings').click(); const settingsRepo = page.locator('#dlgSettings .mainRepoLink'); assert.equal(await settingsRepo.getAttribute('href'), 'https://github.com/rain-ventures-ai/keeptrack'); assert.equal(await settingsRepo.getAttribute('target'), '_blank'); assert.equal(await page.locator('#sSetupPrompt').isVisible(), true);
    await page.locator('#tabClaude').click(); await page.locator('#agTools button', { hasText: 'Claude Code' }).click(); const codeHelp = await page.locator('#agToolBody').textContent(); assert.match(codeHelp, /Cloud: start a Code session with this board repo selected/); assert.match(codeHelp, /No plugin or PAT is needed/); assert.match(codeHelp, /Only for a local session in another project: install the plugin/);
    await page.locator('#tabBoards').click(); await page.locator('#bEditBtn').click(); assert.equal(await page.locator('#sTokenState').textContent(), 'Saved for this board'); assert.equal(await page.locator('#sTokenBtns').isVisible(), true); await page.locator('#sClose').click();
    assert(!api.calls.some(x => /git\/trees\/root-.*recursive/.test(x.path)), 'must not read the whole repository tree');
    assert(api.calls.some(x => /git\/trees\/board-.*recursive/.test(x.path)), 'must read only the board subtree');

    // Client pills are additive filters: several clients can be selected at once, an active pill removes only
    // that client, and All clears the complete selection.
    const multiApi = new Github(true), multiRoot = JSON.parse(multiApi.files['tasks.json']); multiRoot.clients = ['Acme', 'Beta']; multiRoot.next_num = 4; multiApi.files['tasks.json'] = text(multiRoot);
    multiApi.files['cards/t_three.json'] = text({ ...cards['cards/t_two.json'], id: 't_three', num: 3, title: 'Third', client: 'Beta', created: '2026-10-03T08:00:00.000Z', updated: '2026-10-03T08:00:00.000Z', rank: 'a2' });
    const multi = await openBoard(browser, multiApi); await multi.setViewportSize({ width: 360, height: 720 }); await multi.waitForTimeout(100); const titles = () => multi.locator('.card .t').allTextContents();
    await multi.locator('.cpill.more').click(); await multi.locator('.cmenu').filter({ hasText: 'Acme' }).click(); await multi.locator('.cmenu').filter({ hasText: 'Beta' }).click();
    assert.deepEqual((await titles()).sort(), ['First', 'Third']); assert.deepEqual(await multi.locator('#fClient option:checked').evaluateAll(xs => xs.map(x => x.value).sort()), ['Acme', 'Beta']); assert.equal(await multi.locator('.cpill.all').getAttribute('aria-pressed'), 'false');
    await multi.locator('.cmenu').filter({ hasText: 'Acme' }).click(); assert.deepEqual(await titles(), ['Third']);
    await multi.locator('.cpill.all').click(); assert.deepEqual((await titles()).sort(), ['First', 'Second', 'Third']); await multi.close();

    const desktopView = await page.locator('#viewSw .seg button.on').boundingBox(), desktopFilter = await page.locator('#btnFilter').boundingBox();
    assert(Math.abs((desktopView.y + desktopView.height) - (desktopFilter.y + desktopFilter.height)) <= 2, 'desktop header controls must share a bottom edge');

    // Cinema mode focuses one lane, forces high-to-low priority order, and flows cards down before using
    // the next screen column. Escape restores the complete board.
    const cinemaApi = new Github(true), cinemaRoot = JSON.parse(cinemaApi.files['tasks.json']); cinemaRoot.next_num = 10; cinemaApi.files['tasks.json'] = text(cinemaRoot);
    [['t_three', 3, 'Low three', 'low', 'a2'], ['t_four', 4, 'High four', 'high', 'a3'], ['t_five', 5, 'Medium five', 'medium', 'a4'], ['t_six', 6, 'Low six', 'low', 'a5'], ['t_seven', 7, 'High seven', 'high', 'a6'], ['t_eight', 8, 'Medium eight', 'medium', 'a7'], ['t_nine', 9, 'Low nine', 'low', 'a8']].forEach(([id, num, title, priority, rank]) => {
      cinemaApi.files[`cards/${id}.json`] = text({ ...cards['cards/t_two.json'], id, num, title, priority, rank, created: `2026-10-0${num}T08:00:00.000Z`, updated: `2026-10-0${num}T08:00:00.000Z` });
    });
    const cinema = await openBoard(browser, cinemaApi); await cinema.setViewportSize({ width: 1200, height: 520 }); await cinema.locator('.col[data-col="todo"] .hcinema').click();
    assert.equal(await cinema.locator('body').getAttribute('class'), 'cinema'); assert.equal(await cinema.locator('body > header').isHidden(), true); assert.equal(await cinema.locator('.col[data-col="done"]').isHidden(), true); assert.equal(await cinema.locator('.cinema-col .add').isHidden(), true); assert.equal(await cinema.locator('.cinema-col .hcinema').getAttribute('aria-label'), 'Exit cinema mode');
    assert.deepEqual(await cinema.locator('.cinema-col .card .t').allTextContents(), ['First', 'High four', 'High seven', 'Second', 'Medium five', 'Medium eight', 'Low three', 'Low six', 'Low nine']);
    const cinemaCards = cinema.locator('.cinema-col .card'), firstCinema = await cinemaCards.first().boundingBox(), secondCinema = await cinemaCards.nth(1).boundingBox(), lastCinema = await cinemaCards.last().boundingBox();
    assert(secondCinema.y > firstCinema.y, 'cinema cards must flow downward first'); assert(lastCinema.x > firstCinema.x, 'later low-priority cards must continue in a column to the right');
    await cinema.keyboard.press('Escape'); assert.equal(await cinema.locator('body').getAttribute('class'), ''); assert.equal(await cinema.locator('body > header').isVisible(), true); assert.equal(await cinema.locator('.col[data-col="done"]').isVisible(), true); await cinema.close();

    // The compact header has intentional rows: board + views, then board filters. Low-priority utilities move into
    // one More menu on phones instead of wrapping into loose buttons on a third line.
    const compactApi = new Github(true), compact = await browser.newPage({ viewport: { width: 700, height: 800 } }); compact.on('pageerror', e => console.error('page error:', e.message));
    await compact.addInitScript(() => { localStorage.setItem('kb_repo', 'acme/board'); localStorage.setItem('kb_branch', 'main'); localStorage.setItem('kb_path', 'board/tasks.json'); localStorage.setItem('kb_token', 'test'); localStorage.setItem('kb_me', 'alex'); localStorage.setItem('kb_api', 'https://api.test'); localStorage.setItem('kb_view', 'board'); });
    await compact.route('https://api.test/**', r => compactApi.route(r)); await compact.goto(base + '/board/index.html'); await compact.waitForSelector('#viewSw');
    const compactBoard = await compact.locator('#boardBtn').boundingBox(), compactViews = await compact.locator('#viewSw').boundingBox(), compactFilters = await compact.locator('.hfilters').boundingBox();
    assert(Math.abs((compactBoard.y + compactBoard.height) - (compactViews.y + compactViews.height)) <= 2, 'board switcher and views must share a bottom edge in the first row'); assert(compactFilters.y > compactViews.y + 20, 'filters must form the second row');
    const compactAll = await compact.locator('.cpill.all').boundingBox(), compactSearch = await compact.locator('#btnSearch').boundingBox(); assert(Math.abs((compactAll.y + compactAll.height / 2) - (compactSearch.y + compactSearch.height / 2)) <= 3, 'compact filter controls must share a centre line');
    assert.equal(await compact.locator('#btnMore').isVisible(), true); assert.equal(await compact.locator('.hutils #btnSettings').isHidden(), true); assert.equal(await compact.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth), true, 'compact header must not widen the page');
    assert.deepEqual(await compact.locator('#viewSw .vt').evaluateAll(xs => xs.filter(x => getComputedStyle(x).display !== 'none').map(x => x.textContent.trim())), ['People', 'Kanban']);
    await compact.locator('#btnFilter').click(); assert.equal(await compact.locator('#filterPop').isVisible(), true); await compact.locator('#sortMenu').selectOption('due'); assert.equal(await compact.locator('#sortMenu').inputValue(), 'due'); assert.equal(await compact.locator('#filterPop').isVisible(), true); await compact.locator('#btnFilter').click();
    await compact.locator('#btnMore').click(); assert.equal(await compact.locator('#morePop').isVisible(), true); assert.equal(await compact.locator('[data-head-action="btnCopy"]').count(), 1); await compact.locator('[data-head-action="btnCopy"]').click(); assert.equal(await compact.locator('#dlgCopy').getAttribute('open'), ''); await compact.locator('#copyClose').click();
    await compact.locator('#btnMore').click(); await compact.locator('[data-head-action="btnSettings"]').click(); assert.equal(await compact.locator('#dlgSettings').getAttribute('open'), ''); await compact.locator('#sClose').click(); await compact.close();

    const tabletApi = new Github(true), tablet = await browser.newPage({ viewport: { width: 900, height: 700 } }); tablet.on('pageerror', e => console.error('page error:', e.message));
    await tablet.addInitScript(() => { localStorage.setItem('kb_repo', 'acme/board'); localStorage.setItem('kb_branch', 'main'); localStorage.setItem('kb_path', 'board/tasks.json'); localStorage.setItem('kb_token', 'test'); localStorage.setItem('kb_me', 'alex'); localStorage.setItem('kb_api', 'https://api.test'); }); await tablet.route('https://api.test/**', r => tabletApi.route(r)); await tablet.goto(base + '/board/index.html'); await tablet.waitForSelector('#viewSw');
    assert.equal(await tablet.locator('#btnMore').isVisible(), true); assert.equal(await tablet.locator('.hutils #btnSettings').isHidden(), true); assert.equal(await tablet.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth), true, 'tablet header must not widen the page'); await tablet.close();

    // Token controls distinguish browser storage from an unsaved/password-manager value. A token saved for
    // another board is silently tested against this repo and reused only after the repo and board file are readable.
    const noToken = new Github(true), reuse = await browser.newPage(); reuse.on('pageerror', e => console.error('page error:', e.message));
    await reuse.addInitScript(() => { localStorage.setItem('kb_repo', 'acme/board'); localStorage.setItem('kb_branch', 'main'); localStorage.setItem('kb_path', 'board/tasks.json'); localStorage.setItem('kb_me', 'alex'); localStorage.setItem('kb_api', 'https://api.test'); localStorage.setItem('kb_boards', JSON.stringify({ 'other/board': { branch: 'main', path: 'board/tasks.json', token: 'reusable-token' }, 'acme/board': { branch: 'main', path: 'board/tasks.json' } })); });
    await reuse.route('https://api.test/**', r => noToken.route(r)); await reuse.goto(base + '/board/index.html'); await reuse.locator('#sTokenReuse').filter({ hasText: 'Reused a token' }).waitFor();
    assert.equal(await reuse.evaluate(() => localStorage.getItem('kb_token')), 'reusable-token'); assert.equal(await reuse.evaluate(() => JSON.parse(localStorage.getItem('kb_boards'))['acme/board'].token), 'reusable-token');
    assert.equal(await reuse.locator('#sTokenState').textContent(), 'Saved for this board'); assert.equal(await reuse.locator('#sTokenBtns').isVisible(), true);
    assert(noToken.calls.some(x => x.path === '' && x.auth === 'Bearer reusable-token'), 'the saved candidate must be tested against the target repo'); await reuse.close();

    const blankApi = new Github(true), blank = await browser.newPage(); blank.on('pageerror', e => console.error('page error:', e.message));
    await blank.addInitScript(() => { localStorage.setItem('kb_repo', 'acme/board'); localStorage.setItem('kb_branch', 'main'); localStorage.setItem('kb_path', 'board/tasks.json'); localStorage.setItem('kb_me', 'alex'); localStorage.setItem('kb_api', 'https://api.test'); });
    await blank.route('https://api.test/**', r => blankApi.route(r)); await blank.goto(base + '/board/index.html'); await blank.locator('#dlgSettings').waitFor();
    assert.equal(await blank.locator('#sTokenState').textContent(), 'No token saved'); assert.equal(await blank.locator('#sTokenBtns').isHidden(), true);
    await blank.locator('#sToken').evaluate(el => { el.value = 'password-manager-value'; }); await blank.waitForTimeout(1300);
    assert.equal(await blank.locator('#sTokenState').textContent(), 'Value present · not saved'); assert.equal(await blank.locator('#sTokenBtns').isVisible(), true); await blank.close();

    // A repository-access failure leads with the exact next action; visible repos are supporting evidence only.
    const deniedApi = new Github(true), denied = await openBoard(browser, deniedApi); deniedApi.denyRepo = true; deniedApi.calls = [];
    await denied.locator('#btnSettings').click(); await denied.locator('#tabChecks').click(); await denied.locator('#ckRun').click(); const next = denied.locator('.cknext'); await next.waitFor();
    assert.match(await next.textContent(), /Do this next.*acme\/board.*Contents.*Run checks/s); assert.equal(await next.locator('a.btnlink').textContent(), 'Make a correctly configured PAT'); const patHref = await next.locator('a.btnlink').getAttribute('href'); assert.match(patHref, /github\.com\/settings\/personal-access-tokens\/new/); assert.match(patHref, /target_name=acme/); assert.match(patHref, /contents=write/); await denied.close();

    const missingPermApi = new Github(true), missingPerm = await openBoard(browser, missingPermApi); missingPermApi.calls = [];
    await missingPerm.locator('#btnSettings').click(); await missingPerm.locator('#tabChecks').click(); await missingPerm.locator('#ckRun').click(); const permFix = missingPerm.locator('.cknext'); await permFix.waitFor();
    assert.match(await missingPerm.locator('.ck.bad').last().textContent(), /PAT permissions.*cannot read its default branch/s); const permHref = await permFix.locator('a.btnlink').getAttribute('href'); assert.match(permHref, /target_name=acme/); assert.match(permHref, /contents=write/); await missingPerm.close();

    api.calls = []; await page.locator('.card').first().dblclick(); await page.locator('#cTitle').fill('First edited'); const edited = page.waitForResponse(r => r.request().method() === 'PUT' && r.url().includes('/contents/board/cards/')); await page.locator('#cTitle').blur(); await edited;
    const puts = api.calls.filter(x => x.method === 'PUT'); assert.equal(puts.length, 1, JSON.stringify(api.calls, null, 2)); assert.equal(puts[0].path, '/contents/board/cards/t_one.json');

    await page.locator('#cClose').click(); api.calls = []; const add = page.locator('.col[data-col="todo"] .add input'); await add.fill('Third'); const added = page.waitForResponse(r => r.request().method() === 'PATCH' && r.url().includes('/git/refs/heads/main')); await add.press('Enter'); await added;
    assert.equal(api.calls.filter(x => x.path === '/git/refs/heads/main' && x.method === 'PATCH').length, 1); assert.deepEqual(api.pending.map(x => x.path.replace(/^board\/cards\/t_[0-9a-z]{10}\.json$/, 'NEW CARD')).sort(), ['NEW CARD', 'board/tasks.json']);

    api.calls = []; const dragged = page.waitForResponse(r => r.request().method() === 'PUT' && r.url().includes('/contents/board/cards/')); await page.evaluate(() => { const cards = document.querySelectorAll('.card'), dt = new DataTransfer(); dt.setData('text/plain', 't_two'); cards[0].dispatchEvent(new DragEvent('drop', { bubbles: true, cancelable: true, dataTransfer: dt })); }); await dragged;
    const dragPuts = api.calls.filter(x => x.method === 'PUT'); assert.equal(dragPuts.length, 1); assert.equal(dragPuts[0].path, '/contents/board/cards/t_two.json');
    await page.close();

    // Today is a permanent cross-board view: it combines due people and tasks, then respects either mode being disabled.
    const day = new Date(), today = `${day.getFullYear()}-${String(day.getMonth() + 1).padStart(2, '0')}-${String(day.getDate()).padStart(2, '0')}`;
    const todayApi = new Github(true), dueCard = JSON.parse(todayApi.files['cards/t_one.json']), duePerson = JSON.parse(todayApi.files['people/p_one.json']); dueCard.due = today; duePerson.next = 'Call Casey'; duePerson.next_due = today; todayApi.files['cards/t_one.json'] = text(dueCard); todayApi.files['people/p_one.json'] = text(duePerson);
    const todayPage = await openBoard(browser, todayApi); await todayPage.locator('#viewSw button[data-view="today"]').click(); assert.match(await todayPage.locator('.todayhead h2').textContent(), /1 person to contact · 1 task/); assert.equal(await todayPage.locator('.prow').filter({ hasText: 'Casey Example' }).count(), 1); assert.equal(await todayPage.locator('.ttoday').filter({ hasText: 'First' }).count(), 1); await todayPage.close();
    const tasksTodayApi = new Github(true), tasksRoot = JSON.parse(tasksTodayApi.files['tasks.json']), taskDue = JSON.parse(tasksTodayApi.files['cards/t_one.json']), hiddenPerson = JSON.parse(tasksTodayApi.files['people/p_one.json']); tasksRoot.settings.modes = ['tasks']; taskDue.due = today; hiddenPerson.next_due = today; tasksTodayApi.files['tasks.json'] = text(tasksRoot); tasksTodayApi.files['cards/t_one.json'] = text(taskDue); tasksTodayApi.files['people/p_one.json'] = text(hiddenPerson);
    const tasksTodayPage = await openBoard(browser, tasksTodayApi); await tasksTodayPage.locator('#viewSw button[data-view="today"]').click(); assert.equal(await tasksTodayPage.locator('#viewSw .viewgroup[data-grp="today"]').isVisible(), true); assert.equal(await tasksTodayPage.locator('#viewSw .viewgroup[data-grp="crm"]').isHidden(), true); assert.equal(await tasksTodayPage.locator('.ttoday').filter({ hasText: 'First' }).count(), 1); assert.equal(await tasksTodayPage.locator('.prow').filter({ hasText: 'Casey Example' }).count(), 0); assert.equal(await tasksTodayPage.locator('.padd').count(), 0); await tasksTodayPage.close();
    const crmTodayApi = new Github(true), crmRoot = JSON.parse(crmTodayApi.files['tasks.json']), crmPerson = JSON.parse(crmTodayApi.files['people/p_one.json']), hiddenTask = JSON.parse(crmTodayApi.files['cards/t_one.json']); crmRoot.settings.modes = ['crm']; crmPerson.next_due = today; hiddenTask.due = today; crmTodayApi.files['tasks.json'] = text(crmRoot); crmTodayApi.files['people/p_one.json'] = text(crmPerson); crmTodayApi.files['cards/t_one.json'] = text(hiddenTask);
    const crmTodayPage = await openBoard(browser, crmTodayApi); await crmTodayPage.locator('#viewSw button[data-view="today"]').click(); assert.equal(await crmTodayPage.locator('#viewSw .viewgroup[data-grp="today"]').isVisible(), true); assert.equal(await crmTodayPage.locator('#viewSw .viewgroup[data-grp="tasks"]').isHidden(), true); assert.equal(await crmTodayPage.locator('.prow').filter({ hasText: 'Casey Example' }).count(), 1); assert.equal(await crmTodayPage.locator('.ttoday').count(), 0); await crmTodayPage.close();

    // Board sections can be hidden and restored after setup. The mode save changes only settings, never task or person files.
    const modesApi = new Github(true), modesPage = await openBoard(browser, modesApi); await modesPage.locator('#btnSettings').click();
    assert.equal(await modesPage.locator('#sModeTasks').isChecked(), true); assert.equal(await modesPage.locator('#sModeCrm').isChecked(), true); modesApi.calls = [];
    const crmOff = modesPage.waitForResponse(r => r.request().method() === 'PUT' && r.url().includes('/contents/board/tasks.json')); await modesPage.locator('#sModeCrm').uncheck(); await crmOff;
    assert.deepEqual(JSON.parse(modesApi.files['tasks.json']).settings.modes, ['tasks']);
    assert.equal(await modesPage.locator('#viewSw button[data-view="people"]').isHidden(), true);
    assert.equal(await modesPage.locator('#viewSw .viewgroup[data-grp="today"]').isVisible(), true); assert.equal(await modesPage.locator('#viewSw .viewgroup[data-grp="crm"]').isHidden(), true); assert.equal(await modesPage.locator('#viewSw .viewgroup[data-grp="tasks"]').isVisible(), true);
    assert('people/p_one.json' in modesApi.files, 'hiding CRM must keep person files'); assert('cards/t_one.json' in modesApi.files, 'hiding CRM must keep task files');
    await modesPage.locator('#sModeTasks').click(); assert.equal(await modesPage.locator('#sModeTasks').isChecked(), true, 'at least one section must stay on');
    assert.deepEqual(modesApi.calls.filter(x => ['PUT', 'PATCH', 'POST', 'DELETE'].includes(x.method)).map(x => x.method + ' ' + x.path), ['PUT /contents/board/tasks.json']);
    modesApi.calls = []; const crmOn = modesPage.waitForResponse(r => r.request().method() === 'PUT' && r.url().includes('/contents/board/tasks.json')); await modesPage.locator('#sModeCrm').check(); await crmOn;
    assert.deepEqual(JSON.parse(modesApi.files['tasks.json']).settings.modes, ['tasks', 'crm']); assert.equal(await modesPage.locator('#viewSw button[data-view="people"]').isVisible(), true); assert.equal(await modesPage.locator('#viewSw .viewgroup[data-grp="crm"]').isVisible(), true);
    assert('people/p_one.json' in modesApi.files, 'restoring CRM must show the existing person file'); await modesPage.close();

    // Enabling CRM on a board with no people creates no placeholder. Adding the first person creates their own file.
    const emptyCrm = new Github(true); emptyCrm.files['tasks.json'] = text({ ...root, settings: { ...root.settings, modes: ['tasks'] } }); delete emptyCrm.files['people/p_one.json'];
    const emptyPage = await openBoard(browser, emptyCrm); await emptyPage.locator('#btnSettings').click(); emptyCrm.calls = [];
    const enabled = emptyPage.waitForResponse(r => r.request().method() === 'PUT' && r.url().includes('/contents/board/tasks.json')); await emptyPage.locator('#sModeCrm').check(); await enabled;
    assert.equal(Object.keys(emptyCrm.files).some(x => x.startsWith('people/')), false, 'enabling an empty CRM must not create a placeholder person');
    assert.deepEqual(emptyCrm.calls.filter(x => ['PUT', 'PATCH', 'POST', 'DELETE'].includes(x.method)).map(x => x.method + ' ' + x.path), ['PUT /contents/board/tasks.json']);
    await emptyPage.locator('#sDone').click(); await emptyPage.locator('#viewSw button[data-view="people"]').click(); emptyCrm.calls = [];
    await emptyPage.locator('.padd input').fill('Ada Example'); const firstPerson = emptyPage.waitForResponse(r => r.request().method() === 'PUT' && /\/contents\/board\/people\//.test(r.url())); await emptyPage.locator('.padd input').press('Enter'); await firstPerson;
    const peopleFiles = Object.keys(emptyCrm.files).filter(x => x.startsWith('people/')); assert.equal(peopleFiles.length, 1); assert.equal(JSON.parse(emptyCrm.files[peopleFiles[0]]).name, 'Ada Example');
    assert.deepEqual(emptyCrm.calls.filter(x => ['PUT', 'PATCH', 'POST', 'DELETE'].includes(x.method)).map(x => x.method + ' ' + x.path), ['PUT /contents/board/' + peopleFiles[0]]); await emptyPage.close();

    // The structured add-person form requires only a name, cancellation writes nothing, and optional fields are saved in one person record.
    const formApi = new Github(true); delete formApi.files['people/p_one.json']; const formPage = await openBoard(browser, formApi); await formPage.locator('#viewSw button[data-view="people"]').click(); formApi.calls = [];
    await formPage.locator('.padd button').click(); assert.equal(await formPage.locator('#dlgAddPerson').getAttribute('open'), ''); await formPage.locator('#apCancel').click();
    assert.equal(formApi.calls.filter(x => ['PUT', 'PATCH', 'POST', 'DELETE'].includes(x.method)).length, 0, 'cancelling the form must write nothing');
    await formPage.locator('.padd button').click(); await formPage.locator('#apSave').click(); assert.equal(await formPage.locator('#dlgAddPerson').getAttribute('open'), '', 'name is required');
    await formPage.locator('#apName').fill('Grace Hopper'); await formPage.locator('#apCompany').fill('Acme'); await formPage.locator('#apRole').fill('Admiral'); await formPage.locator('#apEmail').fill('grace@example.test'); await formPage.locator('#apPhone').fill('+1 555 0100'); await formPage.locator('#apLinkedin').fill('https://linkedin.com/in/grace-hopper');
    const formSaved = formPage.waitForResponse(r => r.request().method() === 'PUT' && /\/contents\/board\/people\//.test(r.url())); await formPage.locator('#apSave').click(); await formSaved;
    const formFiles = Object.keys(formApi.files).filter(x => x.startsWith('people/')); assert.equal(formFiles.length, 1); const grace = JSON.parse(formApi.files[formFiles[0]]);
    assert.deepEqual({ name: grace.name, company: grace.company, role: grace.role, email: grace.email, phone: grace.phone, linkedin: grace.linkedin }, { name: 'Grace Hopper', company: 'Acme', role: 'Admiral', email: 'grace@example.test', phone: '+1 555 0100', linkedin: 'https://linkedin.com/in/grace-hopper' });
    assert.equal(await formPage.locator('#dlgContact').getAttribute('open'), '', 'the new person card opens after saving'); await formPage.close();

    const racing = new Github(true); racing.failPatch = true; const retry = await openBoard(browser, racing); await retry.evaluate(() => { window.__statuses = []; new MutationObserver(() => window.__statuses.push(document.querySelector('#status').textContent)).observe(document.querySelector('#status'), { childList: true }); }); const input = retry.locator('.col[data-col="todo"] .add input'); await input.fill('Retry card'); const retried = retry.waitForResponse(r => r.request().method() === 'PATCH' && r.url().includes('/git/refs/heads/main') && r.status() === 200); await input.press('Enter'); await retried; assert.equal(racing.calls.filter(x => x.path === '/git/refs/heads/main' && x.method === 'PATCH').length, 2); assert((await retry.evaluate(() => window.__statuses)).some(x => x.includes('retrying')), 'the conflict retry must be shown'); await retry.close();

    const old = new Github(false), legacy = await openBoard(browser, old); old.calls = []; await legacy.locator('.card').first().dblclick(); await legacy.locator('#cTitle').fill('Legacy edit'); const legacySaved = legacy.waitForResponse(r => r.request().method() === 'PUT' && r.url().includes('/contents/board/tasks.json')); await legacy.locator('#cTitle').blur(); await legacySaved; const oldPuts = old.calls.filter(x => x.method === 'PUT'); assert.equal(oldPuts.length, 1); assert.equal(oldPuts[0].path, '/contents/board/tasks.json'); await legacy.close();

    // A card file written by another tool can miss fields the page fills in. Editing a different card must still write one file.
    const sparse = new Github(true); { const t = JSON.parse(sparse.files['cards/t_two.json']); delete t.todos; delete t.claim; delete t.contacts; sparse.files['cards/t_two.json'] = text(t); }
    const sp = await openBoard(browser, sparse); sparse.calls = []; await sp.locator('.card', { hasText: 'First' }).dblclick(); await sp.locator('#cTitle').fill('First again'); const spSaved = sp.waitForResponse(r => r.request().method() === 'PUT'); await sp.locator('#cTitle').blur(); await spSaved;
    const spPuts = sparse.calls.filter(x => x.method === 'PUT' || x.method === 'PATCH'); assert.equal(spPuts.length, 1, JSON.stringify(spPuts)); assert.equal(spPuts[0].path, '/contents/board/cards/t_one.json'); await sp.close();

    // A drag between two cards gives the dragged card a rank between them, and changes no other file.
    const dr = new Github(true); { const t = JSON.parse(dr.files['cards/t_two.json']); t.priority = 'high'; t.rank = 'a2'; dr.files['cards/t_two.json'] = text(t); dr.files['cards/t_three.json'] = text({ ...t, id: 't_three', num: 3, title: 'Third', rank: 'a1' }); dr.files['tasks.json'] = text({ ...root, next_num: 4 }); }
    const dp = await openBoard(browser, dr); await dp.evaluate(() => { localStorage.setItem('kb_sort:acme/board', 'manual'); }); await dp.reload(); await dp.waitForFunction(() => /Synced/.test(document.querySelector('#status').textContent));
    assert.deepEqual(await dp.locator('.card .t').allTextContents(), ['First', 'Third', 'Second']); dr.calls = [];
    const drSaved = dp.waitForResponse(r => r.request().method() === 'PUT'); await dp.evaluate(() => { const target = [...document.querySelectorAll('.card')].find(c => c.textContent.includes('Third')), dt = new DataTransfer(); dt.setData('text/plain', 't_two'); target.dispatchEvent(new DragEvent('drop', { bubbles: true, cancelable: true, dataTransfer: dt })); }); await drSaved;
    const drPuts = dr.calls.filter(x => x.method === 'PUT' || x.method === 'PATCH'); assert.equal(drPuts.length, 1); assert.equal(drPuts[0].path, '/contents/board/cards/t_two.json');
    const moved = JSON.parse(dr.files['cards/t_two.json']); assert(moved.rank > 'a0' && moved.rank < 'a1', 'rank must sit between First (a0) and Third (a1), got ' + moved.rank); await dp.close();

    // A split board rolled back to one tasks.json while the page is open: the next save writes the whole board, never an empty task list.
    const rb = new Github(true), rp = await openBoard(browser, rb);
    rb.files = { 'tasks.json': text({ ...root, version: 3, layout: undefined, tasks: Object.values(cards), contacts: [person] }) }; rb.head = 'head-' + ++rb.n; rb.calls = [];
    await rp.locator('.card', { hasText: 'First' }).dblclick(); await rp.locator('#cTitle').fill('After rollback'); const rbSaved = rp.waitForResponse(r => r.request().method() === 'PUT'); await rp.locator('#cTitle').blur(); await rbSaved;
    const rbPut = rb.calls.find(x => x.method === 'PUT'); assert.equal(rbPut.path, '/contents/board/tasks.json'); const rbBoard = JSON.parse(rb.files['tasks.json']);
    assert.equal(rbBoard.version, 3); assert.equal(rbBoard.tasks.length, 2, 'rolled-back board must keep its tasks'); assert(rbBoard.tasks.some(t => t.title === 'After rollback')); await rp.close();

    // Someone else edits the same card while this page edits it: the conflict dialog opens and nothing is written.
    const cf = new Github(true), cp = await openBoard(browser, cf);
    await cp.locator('.card', { hasText: 'First' }).dblclick(); await cp.locator('#cTitle').fill('Mine');
    { const t = JSON.parse(cf.files['cards/t_one.json']); t.title = 'Theirs'; t.updated = '2026-10-03T08:00:00.000Z'; cf.files['cards/t_one.json'] = text(t); cf.head = 'head-' + ++cf.n; } cf.calls = [];
    await cp.locator('#cTitle').blur(); await cp.waitForFunction(() => document.querySelector('#dlgConflict').open);
    assert.equal(cf.calls.filter(x => ['PUT', 'PATCH', 'DELETE'].includes(x.method)).length, 0, 'nothing is written before the person chooses'); await cp.close();

    {
    // A card file without fields the page fills in (here: no "details" and no "links") is not rewritten by an unrelated save.
    const sparse = new Github(true); const bare = JSON.parse(sparse.files['cards/t_two.json']); delete bare.details; delete bare.links; sparse.files['cards/t_two.json'] = JSON.stringify(bare, null, 2) + '\n';
    const sp = await openBoard(browser, sparse); sparse.calls = []; await sp.locator('.card').filter({ hasText: 'First' }).dblclick(); await sp.locator('#cTitle').fill('First again'); const spSaved = sp.waitForResponse(r => ['PUT', 'PATCH'].includes(r.request().method()) && r.url().includes('/repos/acme/board/')); await sp.locator('#cTitle').blur(); await spSaved;
    assert.deepEqual(sparse.calls.filter(x => ['PUT', 'PATCH', 'POST'].includes(x.method)).map(x => x.method + ' ' + x.path), ['PUT /contents/board/cards/t_one.json']); await sp.close();

    // Two files with one id: the page refuses to save (a save would keep only one of them).
    const dupe = new Github(true); dupe.files['cards/copy.json'] = dupe.files['cards/t_one.json'];
    const dp = await openBoard(browser, dupe); dupe.calls = []; await dp.locator('.card').filter({ hasText: 'Second' }).first().dblclick(); await dp.locator('#cTitle').fill('Second edited'); await dp.locator('#cTitle').blur(); await dp.waitForFunction(() => /Save failed/.test(document.querySelector('#status').textContent));
    assert.equal(dupe.calls.filter(x => ['PUT', 'PATCH', 'POST', 'DELETE'].includes(x.method)).length, 0, 'nothing may be written'); await dp.close();

    // A page that loaded a v3 board saves correctly after the board is split by keeptrack.py.
    const moving = new Github(false), mv = await openBoard(browser, moving);
    const split = new Github(true); moving.v4 = true; moving.files = split.files; moving.calls = [];
    await mv.locator('.card').filter({ hasText: 'First' }).dblclick(); await mv.locator('#cTitle').fill('After split'); const mvSaved = mv.waitForResponse(r => r.request().method() === 'PUT' && r.url().includes('/contents/board/cards/')); await mv.locator('#cTitle').blur(); await mvSaved;
    assert.deepEqual(moving.calls.filter(x => ['PUT', 'PATCH', 'POST', 'DELETE'].includes(x.method)).map(x => x.method + ' ' + x.path), ['PUT /contents/board/cards/t_one.json']);
    assert.equal(JSON.parse(moving.files['cards/t_one.json']).title, 'After split'); assert(!('tasks' in JSON.parse(moving.files['tasks.json'])), 'tasks.json must stay settings only'); await mv.close();

    // An old (v2) board file is saved as v3, as before.
    const v2 = new Github(false); const v2root = JSON.parse(v2.files['tasks.json']); v2root.version = 2; v2.files['tasks.json'] = JSON.stringify(v2root, null, 2) + '\n';
    const vp = await openBoard(browser, v2); await vp.locator('.card').first().dblclick(); await vp.locator('#cTitle').fill('v2 edit'); const v2Saved = vp.waitForResponse(r => r.request().method() === 'PUT'); await vp.locator('#cTitle').blur(); await v2Saved;
    assert.equal(JSON.parse(v2.files['tasks.json']).version, 3); await vp.close();
    }
    console.log('split storage browser tests passed');
  } finally { await browser.close(); server.close(); }
})().catch(err => { console.error(err); server.close(); process.exitCode = 1; });

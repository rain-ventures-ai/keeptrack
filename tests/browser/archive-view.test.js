'use strict';
// Archive view (Tasks → Archive) and People → Archived (kit v96): archived cards and people can be browsed, not only
// found by searching. The list loads the archive files when the view opens (loading and error states), shows the newest
// archived first, filters by search, project, label, year, Done or cancelled and the top client filter, counts, pages
// with "Load more", and a row opens the read-only archived card with Put back (hidden on a read-only board). Search
// remembers Include archive in this browser and marks archived results with an "Archived <year>" pill.
// Run: node archive-view.test.js   (SHOTS=<dir> also saves screenshots: 1280px and 390px)

const assert = require('node:assert/strict');
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { chromium } = require('playwright');

const ROOT = path.resolve(__dirname, '../..');
const SHOTS = process.env.SHOTS || '';
const mime = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json', '.svg': 'image/svg+xml' };
const server = http.createServer((req, res) => {
  const rel = decodeURIComponent(new URL(req.url, 'http://local').pathname).replace(/^\/+/, '') || 'board/index.html';
  const file = path.resolve(ROOT, rel); if (!file.startsWith(ROOT + path.sep)) { res.writeHead(403).end(); return; }
  fs.readFile(file, (err, data) => { if (err) res.writeHead(404).end(); else { res.setHeader('Content-Type', mime[path.extname(file)] || 'application/octet-stream'); res.end(data); } });
});

const text = x => JSON.stringify(x, null, 2) + '\n';
const stamp = '2026-03-01T08:00:00.000Z';
const card = (id, num, title, extra) => ({ id, num, title, column: 'done', client: '', priority: 'medium', due: '', labels: [], assignees: [], details: '', links: [], contacts: [], todos: [], comments: [], history: [], claim: null, created: stamp, updated: stamp, rank: 'a' + num, ...extra });
const person = (id, name, extra) => ({ id, name, company: '', role: '', stage: 'Lost', emails: [], phones: [], links: [], comments: [], history: [], created: stamp, updated: stamp, ...extra });

// archive/<year>.json: an archive run appends, so the last card in a file is the newest archived
function fixture({ extra = 0 } = {}) {
  const a2025 = { version: 3, archive: true, year: '2025', history: {},
    tasks: [card('a25_one', 10, 'Old website brief', { client: 'Acme', project: 'pr_web', labels: ['web'], details: 'The first brief for the site.' }),
      card('a25_two', 11, 'Dropped pitch', { client: 'Bluebell Events', column: 'todo' })],
    contacts: [person('p_lena', 'Lena Lost', { company: 'Acme', role: 'Buyer', notes: 'Went with another agency.' }), person('p_omar', 'Omar Gone', { company: 'Bluebell Events' })] };
  const a2026 = { version: 3, archive: true, year: '2026', history: {},
    tasks: [card('a26_one', 20, 'Invoice March', { client: 'Acme', labels: ['billing'], comments: [{ at: stamp, by: 'alex', text: 'Paid in full' }] }),
      card('a26_two', 21, 'Cancelled run', { client: 'Northwind Traders', outcome: 'cancelled', last_run: { agent: 'claude', note: 'not needed' } }),
      card('a26_three', 22, 'Spring launch', { client: 'Acme', project: 'pr_web', labels: ['web'], todos: [{ text: 'Ship', done: true }] })],
    contacts: [] };
  const files = { '2025': { tasks: 2, contacts: 2 }, '2026': { tasks: 3, contacts: 0 } };
  const out = { 'archive/2025.json': text(a2025), 'archive/2026.json': text(a2026) };
  if (extra) { out['archive/2024.json'] = text({ version: 3, archive: true, year: '2024', history: {}, tasks: Array.from({ length: extra }, (_, i) => card('a24_' + i, 100 + i, `Old chore ${100 + i}`, { client: 'Acme' })), contacts: [] }); files['2024'] = { tasks: extra, contacts: 0 }; }
  const root = { version: 4, layout: 'split', settings: { title: 'Archive test' }, columns: [{ id: 'todo', name: 'To do' }, { id: 'done', name: 'Done' }], people: [{ github: 'alex', name: 'Alex' }], agents: [], clients: ['Acme', 'Bluebell Events', 'Northwind Traders'], labels: [{ name: 'web', color: '#0c66e4' }, { name: 'billing', color: '#334155' }], client_info: {}, next_num: 30, archive: { files } };
  return { 'tasks.json': text(root), 'cards/t_live.json': text(card('t_live', 1, 'Live work', { column: 'todo', client: 'Acme' })), 'people/p_alex.json': text(person('p_alex', 'Alex', { github: 'alex', stage: 'New' })), 'projects/pr_web.json': text({ id: 'pr_web', client: 'Acme', name: 'Website', north_star: '', status: 'active', links: [], people: [], created: stamp, updated: stamp }), ...out };
}

// A small GitHub: contents API for reads and single-file writes, git data API for multi-file commits (as quick-archive.test.js)
class Github {
  constructor(opts = {}) { this.files = fixture(opts); this.push = opts.push !== false; this.head = 'head-1'; this.n = 1; this.blobs = {}; this.pending = null; }
  sha(p) { return crypto.createHash('sha1').update(this.files[p] || '').digest('hex'); }
  async route(route) {
    const req = route.request(), u = new URL(req.url()), method = req.method(), p = u.pathname.replace('/repos/acme/board', '');
    const json = (body, status = 200) => route.fulfill({ status, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    if (p === '/user' && method === 'GET') return json({ login: 'alex' });
    if (p.startsWith('/user/repos')) return json([]);
    if (p === '' && method === 'GET') return json({ full_name: 'acme/board', private: true, permissions: { push: this.push, pull: true }, default_branch: 'main' });
    if (p.startsWith('/contents/README.md')) return json({ message: 'Not Found' }, 404);
    if (p.startsWith('/contents/board/KIT_VERSION')) return route.fulfill({ status: 200, contentType: 'text/plain', body: '999' });   // up to date: no kit bar in the screenshots
    if (p.startsWith('/contents/board/tasks.json') && method === 'GET') return json({ sha: this.sha('tasks.json'), size: Buffer.byteLength(this.files['tasks.json']), encoding: 'base64', content: Buffer.from(this.files['tasks.json']).toString('base64') });
    if (p.startsWith('/contents/board/') && method === 'GET' && this.rawFiles && this.rawFiles.has(p.slice('/contents/board/'.length))) {   // a large file: the contents API sends no body, the page asks for the raw file
      const rel = p.slice('/contents/board/'.length); if (/raw/.test(req.headers()['accept'] || '')) return route.fulfill({ status: 200, contentType: 'text/plain', body: this.files[rel] });
      return json({ sha: this.sha(rel), encoding: 'none', content: '' }); }
    if (p.startsWith('/contents/board/archive/') && method === 'GET' && this.files[p.slice('/contents/board/'.length)]) {   // archive files carry an ETag: an unchanged file is a 304, as on GitHub
      const rel = p.slice('/contents/board/'.length), tag = `"${this.sha(rel)}"`;
      if (req.headers()['if-none-match'] === tag) { this.notModified = (this.notModified || 0) + 1; return route.fulfill({ status: 304, headers: { ETag: tag, 'Access-Control-Allow-Origin': '*', 'Access-Control-Expose-Headers': 'ETag' } }); }
      return route.fulfill({ status: 200, headers: { 'Content-Type': 'application/json', ETag: tag, 'Access-Control-Allow-Origin': '*', 'Access-Control-Expose-Headers': 'ETag' }, body: JSON.stringify({ sha: this.sha(rel), encoding: 'base64', content: Buffer.from(this.files[rel]).toString('base64') }) }); }
    if (p.startsWith('/contents/board/') && method === 'GET') { const rel = p.slice('/contents/board/'.length); return this.files[rel] ? json({ sha: this.sha(rel), encoding: 'base64', content: Buffer.from(this.files[rel]).toString('base64') }) : json({ message: 'Not Found' }, 404); }
    if (p.startsWith('/contents/board/') && method === 'PUT') { const rel = p.slice('/contents/board/'.length), b = req.postDataJSON(); this.files[rel] = Buffer.from(b.content, 'base64').toString(); this.head = 'head-' + ++this.n; return json({ content: { sha: this.sha(rel) }, commit: { sha: this.head, tree: { sha: 'root-' + this.n } } }); }
    if (/^\/git\/ref\/heads\/(main|dev)$/.test(p) && method === 'GET') return json({ object: { sha: this.head } });   // dev: the branch switch test
    if (p.startsWith('/git/commits/') && method === 'GET') return json({ tree: { sha: 'root-' + this.n } });
    if (p.startsWith('/git/trees/root-') && method === 'GET') return json({ tree: [{ path: 'board', type: 'tree', sha: 'board-' + this.n }] });
    if (p.startsWith('/git/trees/board-') && method === 'GET') return json({ truncated: false, tree: Object.entries(this.files).map(([f, c]) => ({ path: f, type: 'blob', sha: this.sha(f), size: Buffer.byteLength(c) })) });
    if (p.startsWith('/git/blobs/') && method === 'GET') { const sha = p.split('/').pop(), rel = Object.keys(this.files).find(x => this.sha(x) === sha); return json({ encoding: 'base64', content: Buffer.from(this.files[rel]).toString('base64') }); }
    if (p === '/git/blobs' && method === 'POST') { const content=req.postDataJSON().content, sha=crypto.createHash('sha1').update(content).digest('hex'); this.n++; this.blobs[sha]=content; return json({ sha }); }
    if (p === '/git/trees' && method === 'POST') { this.pending = req.postDataJSON().tree; return json({ sha: 'new-tree-' + ++this.n }); }
    if (p === '/git/commits' && method === 'POST') return json({ sha: 'new-commit-' + ++this.n });
    if (p === '/git/refs/heads/main' && method === 'PATCH') { for (const e of this.pending || []) { const rel = e.path.replace(/^board\//, ''); if (e.sha === null) delete this.files[rel]; else this.files[rel] = this.blobs[e.sha]; } this.head = req.postDataJSON().sha; return json({ object: { sha: this.head } }); }
    return json({ message: 'not mocked: ' + method + ' ' + p }, 404);
  }
  json(rel) { return this.files[rel] ? JSON.parse(this.files[rel]) : null; }
  single() {   // the same board as one tasks.json (no split layout): the page reads archive files one by one (readArchive)
    const root = this.json('tasks.json'), of = dir => Object.keys(this.files).filter(f => f.startsWith(dir)).map(f => this.json(f));
    delete root.layout; root.version = 3; root.tasks = of('cards/'); root.contacts = of('people/'); root.projects = of('projects/');
    const arch = Object.fromEntries(Object.entries(this.files).filter(([f]) => f.startsWith('archive/'))); this.files = { 'tasks.json': text(root), ...arch }; return this;
  }
}

let base;
const shot = async (page, name) => { if (SHOTS) { fs.mkdirSync(SHOTS, { recursive: true }); await page.screenshot({ path: path.join(SHOTS, name + '.png') }); } };
const init = ([view, layout]) => { localStorage.setItem('kb_repo', 'acme/board'); localStorage.setItem('kb_branch', 'main'); localStorage.setItem('kb_path', 'board/tasks.json'); localStorage.setItem('kb_token', 'test'); localStorage.setItem('kb_me', 'alex'); localStorage.setItem('kb_api', 'https://api.test'); localStorage.setItem('kb_layout', layout || 'classic'); localStorage.setItem('kb_tour', 'done'); if (!sessionStorage.getItem('kb_view')) sessionStorage.setItem('kb_view', view); };
const nums = page => page.locator('.archrow .ui-task__num').allTextContents();
const waitNums = (page, want) => page.waitForFunction(w => [...document.querySelectorAll('.archrow .ui-task__num')].map(x => x.textContent).join() === w.join(), want, { timeout: 5000 });
const fits = page => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1);
async function open(browser, api, { view = 'archive', viewport = { width: 1280, height: 860 }, layout = 'classic', route, readOnly } = {}) {
  const phone = viewport.width < 700, ctx = await browser.newContext({ viewport, isMobile: phone, hasTouch: phone }), page = await ctx.newPage(), errors = [];
  page.on('pageerror', e => errors.push(e.message)); page.on('dialog', d => { errors.push('native dialog: ' + d.message()); d.dismiss().catch(() => {}); });
  await page.addInitScript(init, [view, layout]); if (readOnly) await page.addInitScript(() => localStorage.setItem('kb_ro:acme/board', '1'));   // the page learnt that this token cannot write
  await page.route('https://api.test/**', r => (route ? route(r) : api.route(r)));
  await page.goto(base + '/board/index.html'); await page.waitForFunction(v => document.body.dataset.view === v, view);
  page.errors = errors; page.done = () => ctx.close(); return page;
}
async function pick(page, key, label) { await page.locator(`select[data-arch-filter="${key}"]`).selectOption({ label }); }

(async () => {
  await new Promise(ok => server.listen(0, '127.0.0.1', ok)); base = `http://127.0.0.1:${server.address().port}`;
  const browser = await chromium.launch({ headless: true });
  try {
    // ---- desktop: the tab, a loading state while the files load, newest archived first, filters, count, open and Put back ----
    { const api = new Github();
      const page = await open(browser, api);
      assert.deepEqual(await page.locator('#viewSw > .viewgroup[data-grp="tasks"] button').evaluateAll(xs => xs.map(x => x.dataset.view)), ['board', 'mentions', 'list', 'cal', 'sched', 'activity', 'archive'], 'Archive is the last tab of the Tasks group');
      assert.equal(await page.locator('#viewSw button[data-view="archive"]').getAttribute('aria-selected'), 'true');
      await page.locator('.archrow').first().waitFor();
      assert.deepEqual(await nums(page), ['#22', '#21', '#20', '#11', '#10'], 'newest archived first: 2026 before 2025, the last archived of a year first');
      assert.equal(await page.locator('.archcount').innerText(), '5 archived cards');
      assert.equal(await page.locator('.archrow', { hasText: 'Live work' }).count(), 0, 'cards on the board are not listed');
      const row21 = page.locator('.archrow', { hasText: 'Cancelled run' });
      assert.deepEqual(await row21.locator('.ui-pill').allTextContents().then(xs => xs.filter(x => /Done|Cancelled|Archived/.test(x))), ['Cancelled', 'Archived 2026'], 'a cancelled Done card shows Cancelled');
      assert.ok((await page.locator('.archrow', { hasText: 'Dropped pitch' }).innerText()).includes('Cancelled'), 'a card archived outside Done counts as cancelled');
      assert.ok((await page.locator('.archrow', { hasText: 'Invoice March' }).innerText()).includes('Done'));
      await shot(page, 'archive-view-1280');
      // search: title, comments and #number. Typing is debounced (one redraw for a burst of keys), and the index of the
      // archive (order, search text, filter options) is built once per load, not on each key or filter
      const builds = await page.evaluate(() => window.kbArchIndexBuilds);
      await page.evaluate(() => { window.archDraws = 0; new MutationObserver(ms => ms.forEach(m => m.addedNodes.forEach(n => { if (n.classList && n.classList.contains('archv')) window.archDraws++; }))).observe(document.getElementById('board'), { childList: true }); });
      await page.locator('.archq').pressSequentially('paid', { delay: 15 }); await waitNums(page, ['#20']);
      assert.ok(await page.evaluate(() => window.archDraws) <= 1, 'four quick keys redraw the list once: ' + await page.evaluate(() => window.archDraws));
      assert.equal(await page.locator('.archcount').innerText(), '1 of 5 archived cards', 'search reads comments');
      assert.equal(await page.evaluate(() => document.activeElement.classList.contains('archq')), true, 'typing keeps the focus in the box');
      await page.locator('.archq').fill('#11'); await waitNums(page, ['#11']);
      await page.locator('.archq').fill('nothing like this'); await page.locator('.archv .ui-empty', { hasText: 'No archived cards match' }).waitFor();
      await page.locator('.archv .ui-empty').getByRole('button', { name: 'Clear filters' }).click(); await page.waitForFunction(() => document.querySelectorAll('.archrow').length === 5);
      assert.equal(await page.locator('.archq').inputValue(), '');
      // filters
      await pick(page, 'year', '2025'); assert.deepEqual(await nums(page), ['#11', '#10']);
      await pick(page, 'year', 'Any year'); await pick(page, 'outcome', 'Cancelled (not Done)'); assert.deepEqual(await nums(page), ['#21', '#11']);
      await pick(page, 'outcome', 'Done'); assert.deepEqual(await nums(page), ['#22', '#20', '#10']);
      await pick(page, 'outcome', 'Done and cancelled'); await pick(page, 'label', 'web'); assert.deepEqual(await nums(page), ['#22', '#10']);
      await pick(page, 'label', 'Any label'); await pick(page, 'project', 'Website'); assert.deepEqual(await nums(page), ['#22', '#10']); await shot(page, 'archive-filter-1280');
      await pick(page, 'project', 'Any project');
      assert.equal(await page.evaluate(() => window.kbArchIndexBuilds), builds, 'typing and filters do not rebuild the archive index');
      // the client filter at the top applies here too
      await page.evaluate(() => { const s = document.getElementById('fClient'); [...s.options].forEach(o => { o.selected = o.value === 'Acme'; }); s.dispatchEvent(new Event('change')); });
      await page.waitForFunction(() => document.querySelectorAll('.archrow').length === 3); assert.deepEqual(await nums(page), ['#22', '#20', '#10']);
      assert.equal(await page.locator('.archcount').innerText(), '3 of 5 archived cards · Acme');
      await page.evaluate(() => { const s = document.getElementById('fClient'); [...s.options].forEach(o => { o.selected = false; }); s.dispatchEvent(new Event('change')); });
      await page.waitForFunction(() => document.querySelectorAll('.archrow').length === 5);
      // a tap opens the read-only archived card; Put back brings it back to the board and it leaves the list
      await page.locator('.archrow', { hasText: 'Spring launch' }).click(); await page.locator('#dlgArch[open]').waitFor();
      assert.equal(await page.locator('#aTitle').innerText(), '#22 Spring launch'); assert.match(await page.locator('#aMeta').innerText(), /Archived in 2026/);
      assert.equal(await page.locator('#aRestore').isVisible(), true); await shot(page, 'archive-open-1280');
      await page.locator('#aRestore').click(); await page.locator('#dlgArch').waitFor({ state: 'hidden' });
      for (let i = 0; i < 50 && !api.json('cards/a26_three.json'); i++) await page.waitForTimeout(100);
      assert.ok(api.json('cards/a26_three.json'), 'Put back writes the card file'); assert.deepEqual(api.json('archive/2026.json').tasks.map(t => t.id), ['a26_one', 'a26_two'], 'and removes it from the archive file');
      await page.keyboard.press('Escape'); await page.locator('#dlgCard').waitFor({ state: 'hidden' }).catch(() => {});
      if (await page.evaluate(() => document.body.dataset.view) !== 'archive') await page.locator('#viewSw button[data-view="archive"]').click();
      await page.waitForFunction(() => document.querySelectorAll('.archrow').length === 4); assert.equal(await page.locator('.archcount').innerText(), '4 archived cards');
      // search: Include archive is remembered in this browser, and archived hits carry an "Archived <year>" pill
      await page.locator('#btnSearch').click(); assert.equal(await page.locator('#qArch').isChecked(), false);
      await page.locator('#qArch').check(); await page.locator('#qQ').fill('Invoice'); await page.locator('.qhit', { hasText: 'Invoice March' }).waitFor();
      assert.equal(await page.locator('.qhit', { hasText: 'Invoice March' }).locator('.qarch').innerText(), 'Archived 2026');
      assert.equal(await page.evaluate(() => localStorage.getItem('kb_q_arch')), '1');
      await page.locator('#qClose').click(); await page.waitForFunction(() => !/search/.test(location.hash)); await page.reload(); await page.waitForFunction(() => document.body.dataset.view === 'archive');
      await page.locator('#btnSearch').click(); assert.equal(await page.locator('#qArch').isChecked(), true, 'Include archive is still ticked after a reload');
      await page.locator('#qQ').fill('Lena'); await page.locator('.qhit', { hasText: 'Lena Lost' }).waitFor(); assert.equal(await page.locator('.qhit', { hasText: 'Lena Lost' }).locator('.qarch').innerText(), 'Archived 2025'); await shot(page, 'archive-search-1280');
      await page.locator('#qArch').uncheck(); await page.locator('#qClose').click(); assert.equal(await page.evaluate(() => localStorage.getItem('kb_q_arch')), '');
      await page.locator('#btnSearch').click(); assert.equal(await page.locator('#qArch').isChecked(), false, 'unticking is remembered too'); await page.locator('#qClose').click();
      assert.deepEqual(page.errors, [], 'no page errors'); await page.done(); }

    // ---- a year split into part files (2026 and 2026-1, kit v107): one year in the Year filter and the pills; Put back reads the part ----
    { const api = new Github(), a26 = api.json('archive/2026.json'), moved = a26.tasks.splice(1, 1);
      api.files['archive/2026.json'] = text(a26);
      api.files['archive/2026-1.json'] = text({ version: 3, archive: true, year: '2026', history: {}, tasks: moved, contacts: [] });
      const root = api.json('tasks.json'); root.archive.files = { '2025': { tasks: 2, contacts: 2 }, '2026': { tasks: 2, contacts: 0 }, '2026-1': { tasks: 1, contacts: 0 } };
      root.settings.min_kit = 107; api.files['tasks.json'] = text(root);
      const page = await open(browser, api); await page.locator('.archrow').first().waitFor();
      assert.equal(await page.locator('.archcount').innerText(), '5 archived cards');
      assert.deepEqual(await page.locator('select[data-arch-filter="year"] option').allTextContents(), ['Any year', '2026', '2025'], 'a part file is not a year of its own');
      await pick(page, 'year', '2026'); assert.deepEqual((await nums(page)).sort(), ['#20', '#21', '#22'], 'the year filter includes the cards stored in its part files');
      const row21 = page.locator('.archrow', { hasText: 'Cancelled run' });
      assert.ok((await row21.locator('.archpill').innerText()).endsWith('Archived 2026'), 'the pill names the year, not the part');
      assert.equal(await row21.locator('.archpill').getAttribute('title'), 'In the archive (archive/2026-1.json)', 'its tooltip names the file');
      await row21.click(); await page.locator('#dlgArch[open]').waitFor(); assert.match(await page.locator('#aMeta').innerText(), /^Archived in 2026 ·/);
      await page.locator('#aRestore').click(); await page.locator('#dlgArch').waitFor({ state: 'hidden' });
      for (let i = 0; i < 50 && !api.json('cards/a26_two.json'); i++) await page.waitForTimeout(100);
      assert.ok(api.json('cards/a26_two.json'), 'Put back from a part file writes the card'); assert.deepEqual(api.json('archive/2026-1.json').tasks, [], 'and removes it from that part');
      assert.deepEqual(page.errors, [], 'no page errors'); await page.done(); }

    // ---- People → stage filter → Archived: archived people, search and the client filter, open read-only with Put back ----
    { const api = new Github(), page = await open(browser, api, { view: 'people' });
      const stage = page.locator('.peoplev select.pillsel');
      assert.equal(await stage.locator('option').last().innerText(), 'Archived', 'Archived is the last option of the stage filter');
      await stage.selectOption({ label: 'Archived' }); await page.locator('.parch').first().waitFor();
      assert.deepEqual(await page.locator('.parch .pwho b').allTextContents(), ['Omar Gone', 'Lena Lost'], 'newest archived first');
      assert.equal(await page.locator('.archcount').innerText(), '2 archived people');
      await page.waitForFunction(() => [...document.querySelectorAll('.parch .archpill')].every(x => x.innerText));
      assert.equal(await page.locator('.parch', { hasText: 'Lena Lost' }).locator('.archpill').innerText(), 'Archived 2025');
      assert.equal(await page.locator('.peoplev .padd').count(), 0, 'no quick add in the archived list');
      await page.locator('.psearch').fill('agency'); await page.waitForFunction(() => document.querySelectorAll('.parch').length === 1);
      assert.equal(await page.locator('.archcount').innerText(), '1 of 2 archived people'); await page.locator('.psearch').fill('');
      await page.waitForFunction(() => document.querySelectorAll('.parch').length === 2); await shot(page, 'people-archived-1280');
      await page.locator('.parch', { hasText: 'Lena Lost' }).click(); await page.locator('#dlgArch[open]').waitFor();
      assert.equal(await page.locator('#aTitle').innerText(), 'Lena Lost'); assert.match(await page.locator('#aMeta').innerText(), /Archived in 2025 · Buyer · Acme · Lost/);
      await page.locator('#aRestore').click(); await page.locator('#dlgArch').waitFor({ state: 'hidden' });
      for (let i = 0; i < 50 && !api.json('people/p_lena.json'); i++) await page.waitForTimeout(100);
      assert.ok(api.json('people/p_lena.json'), 'Put back writes the person file');
      await page.locator('#dlgContact[open]').waitFor(); await page.keyboard.press('Escape');
      await page.waitForFunction(() => [...document.querySelectorAll('.parch .pwho b')].map(b => b.textContent).join() === 'Omar Gone', null, { timeout: 10000 });   // the list reloads after the save
      await page.waitForTimeout(1000);   // Back from the drawer restores this view's address (stage=__archived) a moment later
      await stage.selectOption({ label: 'All stages' }); await page.locator('.prow', { hasText: 'Lena Lost' }).waitFor();
      await page.waitForTimeout(300); assert.equal(await page.locator('.parch').count(), 0);
      assert.deepEqual(page.errors, [], 'no page errors'); await page.done(); }

    // ---- error state: a failed read shows the error and Try again; Try again loads it ----
    { const api = new Github().single(); let fail = true;
      const page = await open(browser, api, { route: r => (fail && r.request().url().includes('/archive/2025.json') ? r.fulfill({ status: 500, contentType: 'application/json', body: '{"message":"boom"}' }) : api.route(r)) });
      await page.locator('.archerr').waitFor(); assert.match(await page.locator('.archerr').innerText(), /Could not load the archive/); await shot(page, 'archive-error-1280');
      fail = false; await page.locator('.archerr').getByRole('button', { name: 'Try again' }).click();
      await page.waitForFunction(() => document.querySelectorAll('.archrow').length === 5);
      assert.deepEqual(page.errors, [], 'no page errors'); await page.done(); }

    // ---- paging: Load more ----
    { const api = new Github({ extra: 60 }), page = await open(browser, api);
      await page.locator('.archrow').first().waitFor();
      assert.equal(await page.locator('.archrow').count(), 50); assert.equal(await page.locator('.archcount').innerText(), '65 archived cards · showing 50');
      await page.evaluate(() => { document.querySelectorAll('.archrow')[0].dataset.kept = 'yes'; });
      await page.getByRole('button', { name: 'Load more (15 not shown)' }).click(); await page.waitForFunction(() => document.querySelectorAll('.archrow').length === 65);
      assert.equal(await page.locator('.archmore').isHidden(), true, 'no Load more once everything shows');
      assert.equal(await page.evaluate(() => document.querySelectorAll('.archrow')[0].dataset.kept), 'yes', 'Load more keeps the rows already drawn and only adds the next ones');
      await page.locator('.archq').fill('chore'); await page.waitForFunction(() => document.querySelectorAll('.archrow').length === 50);
      assert.equal(await page.locator('.archcount').innerText(), '60 of 65 archived cards · showing 50', 'a new search starts at the first page again');
      assert.deepEqual(page.errors, [], 'no page errors'); await page.done(); }

    // ---- read-only board (the token cannot push): browse and open, no Put back ----
    { const api = new Github({ push: false }), page = await open(browser, api, { readOnly: true });
      await page.locator('.archrow').first().waitFor(); assert.match(await page.locator('.archcount').innerText(), /read-only: you can look, not put back/);
      await page.locator('.archrow', { hasText: 'Invoice March' }).click(); await page.locator('#dlgArch[open]').waitFor();
      assert.equal(await page.locator('#aRestore').isVisible(), false, 'no Put back on a read-only board'); await page.locator('#aClose').click();
      await page.locator('#viewSw button[data-view="people"]').click(); await page.locator('.peoplev select.pillsel').selectOption({ label: 'Archived' });
      await page.locator('.parch', { hasText: 'Lena Lost' }).click(); await page.locator('#dlgArch[open]').waitFor(); assert.equal(await page.locator('#aRestore').isVisible(), false);
      assert.deepEqual(page.errors, [], 'no page errors'); await page.done(); }

    // ---- phone (760px breakpoint): the dock's Tasks strip has Archive; filters wrap; nothing scrolls sideways ----
    { const api = new Github(), page = await open(browser, api, { viewport: { width: 390, height: 844 }, layout: 'dock' });
      assert.deepEqual(await page.locator('#subnav [role="tab"]').allTextContents(), ['Kanban', '@Mentions', 'List', 'Calendar', 'Schedule', 'Activity', 'Archive']);
      await page.locator('.archrow').first().waitFor(); assert.equal(await fits(page), true, 'no sideways scroll'); await shot(page, 'archive-view-390');
      const boxes = await page.locator('.archbar > *').evaluateAll(xs => xs.map(x => { const r = x.getBoundingClientRect(); return [r.left, r.right]; }));
      assert.ok(boxes.every(([l, r]) => l >= 0 && r <= 390), 'every control of the bar is on screen: ' + JSON.stringify(boxes));
      await pick(page, 'outcome', 'Cancelled (not Done)'); assert.deepEqual(await nums(page), ['#21', '#11']); assert.equal(await fits(page), true); await shot(page, 'archive-filter-390');
      await page.locator('.archrow', { hasText: 'Cancelled run' }).tap(); await page.locator('#dlgArch[open]').waitFor(); await shot(page, 'archive-open-390'); await page.locator('#aClose').tap();
      await page.locator('#dock .dtab[data-grp="crm"]').tap(); await page.waitForFunction(() => document.body.dataset.view === 'people');
      await page.locator('.peoplev select.pillsel').selectOption({ label: 'Archived' }); await page.locator('.parch').first().waitFor();
      assert.equal(await page.locator('.parch', { hasText: 'Lena Lost' }).locator('.archpill').isVisible(), true, 'the Archived pill shows on a phone'); assert.equal(await fits(page), true); await shot(page, 'people-archived-390');
      assert.deepEqual(page.errors, [], 'no page errors'); await page.done(); }

    // ---- a filter whose select goes away (the last card of that project was put back) stops filtering ----
    { const api = new Github(), page = await open(browser, api);
      await page.locator('.archrow').first().waitFor(); await pick(page, 'project', 'Website'); assert.deepEqual(await nums(page), ['#22', '#10']);
      for (const title of ['Spring launch', 'Old website brief']) {
        await page.locator('.archrow', { hasText: title }).click(); await page.locator('#aRestore').click(); await page.locator('#dlgArch').waitFor({ state: 'hidden' });
        await page.locator('#dlgCard[open]').waitFor(); await page.keyboard.press('Escape'); await page.locator('#dlgCard').waitFor({ state: 'hidden' });
        if (await page.evaluate(() => document.body.dataset.view) !== 'archive') await page.locator('#viewSw button[data-view="archive"]').click();
      }
      await waitNums(page, ['#21', '#20', '#11']);
      assert.equal(await page.locator('select[data-arch-filter="project"]').count(), 0, 'no project select once no archived card has a project');
      assert.equal(await page.locator('.archcount').innerText(), '3 archived cards', 'the hidden project filter no longer narrows the list');
      assert.deepEqual(page.errors, [], 'no page errors'); await page.done(); }

    // ---- People → Archived has its own address parameter (people_archived=1): links and Back/Forward open it, a stage named
    //      __archived round-trips as a stage, and an older stage=__archived link still opens the archive ----
    { const api = new Github(); const root = api.json('tasks.json'); root.settings.stages = ['New', '__archived', 'Lost']; api.files['tasks.json'] = text(root);
      api.files['people/p_odd.json'] = text(person('p_odd', 'Odd Stage', { stage: '__archived' }));
      const page = await open(browser, api, { view: 'people' }); const stage = page.locator('.peoplev select.pillsel');
      const param = k => page.evaluate(k => new URL(location.href).searchParams.get(k), k);
      await page.locator('.prow', { hasText: 'Odd Stage' }).waitFor();
      await stage.selectOption({ label: '__archived' }); await page.locator('.prow', { hasText: 'Odd Stage' }).waitFor();
      assert.equal(await page.locator('.parch').count(), 0, 'a stage named __archived is a stage, not the archive');
      await page.waitForFunction(() => new URL(location.href).searchParams.get('stage') === '__archived'); const stageLink = page.url();
      await stage.selectOption({ label: 'Archived' }); await page.locator('.parch').first().waitFor();
      await page.waitForFunction(() => new URL(location.href).searchParams.get('people_archived') === '1');
      assert.equal(await param('stage'), null, 'the archived list is not written as a stage'); const link = page.url();
      await stage.selectOption({ label: 'All stages' }); await page.waitForFunction(() => !new URL(location.href).searchParams.get('people_archived'));
      const fresh = await open(browser, api, { view: 'people' });
      await fresh.goto(link); await fresh.locator('.parch', { hasText: 'Lena Lost' }).waitFor();
      assert.equal(await fresh.locator('.peoplev select.pillsel option:checked').innerText(), 'Archived', 'a people_archived=1 link opens People → Archived');
      await fresh.goto(stageLink); await fresh.locator('.prow', { hasText: 'Odd Stage' }).waitFor();
      assert.equal(await fresh.locator('.peoplev select.pillsel option:checked').innerText(), '__archived', 'a stage named __archived round-trips through a link');
      assert.equal(await fresh.locator('.parch').count(), 0);
      assert.deepEqual(fresh.errors, [], 'no page errors'); await fresh.done();
      assert.deepEqual(page.errors, [], 'no page errors'); await page.done(); }
    { const api = new Github(), page = await open(browser, api, { view: 'people' }); await page.locator('.peoplev').waitFor();
      const legacy = new URL(page.url()); legacy.searchParams.set('filters', '1'); legacy.searchParams.set('board_view', 'people'); legacy.searchParams.set('stage', '__archived'); legacy.hash = '#view=people';
      await page.goto(legacy.href); await page.locator('.parch', { hasText: 'Lena Lost' }).waitFor();
      assert.equal(await page.locator('.peoplev select.pillsel option:checked').innerText(), 'Archived', 'an older stage=__archived link still opens the archive');
      assert.deepEqual(page.errors, [], 'no page errors'); await page.done(); }

    // ---- After chips: a card that runs after an archived card; the id map is built once per loaded archive, not per card or render ----
    { const api = new Github(); api.files['cards/t_next.json'] = text(card('t_next', 2, 'Follow-up work', { column: 'todo', after: ['a26_one'] }));
      for (let i = 3; i < 23; i++) api.files[`cards/t_n${i}.json`] = text(card('t_n' + i, 30 + i, `Plain card ${i}`, { column: 'todo' }));
      const page = await open(browser, api);
      await page.locator('.archrow').first().waitFor(); await page.locator('#viewSw button[data-view="board"]').click();
      await page.locator('.card', { hasText: 'Follow-up work' }).locator('.afterchip.ok').waitFor();
      const builds = await page.evaluate(() => window.kbArchIdMapBuilds);
      assert.equal(builds, 1, 'one id map for the loaded archive');
      for (const v of ['list', 'board', 'list', 'board']) { await page.locator(`#viewSw button[data-view="${v}"]`).click(); await page.waitForFunction(x => document.body.dataset.view === x, v); }
      assert.equal(await page.evaluate(() => window.kbArchIdMapBuilds), builds, 'renders reuse the id map');
      // Chrome 156: innerText is empty for a chip inside .card { content-visibility: auto } even when the card is on screen. textContent still has the label.
      assert.match(await page.locator('.card', { hasText: 'Follow-up work' }).locator('.afterchip').textContent(), /after #20/);
      assert.deepEqual(page.errors, [], 'no page errors'); await page.done(); }

    // ---- a damaged archive file (list fields that are not lists, entries that are not objects) never breaks the views ----
    { const api = new Github(); const root = api.json('tasks.json'); root.archive.files['2023'] = { tasks: 6, contacts: 2 }; api.files['tasks.json'] = text(root);
      api.files['archive/2023.json'] = text({ version: 3, archive: true, year: '2023', history: { a23_bad: 'not a list', a23_dup: [null, { at: stamp, by: 'alex', text: 'old line' }] },
        tasks: [card('a23_dup', 6, 'Twice filed card'), card('a23_dup', 6, 'Twice filed card'), card('a23_bad', 5, 'Damaged card', { todos: 'x', comments: { a: 1 }, labels: 'web', assignees: 7, links: null, history: [null, 3], title: 'Damaged card', details: 42 }), null, 'junk', { title: 'no id' }],
        contacts: [person('p_bad', 'Damaged person', { emails: 'x@y', phones: null, comments: [null, 'x'], links: 5 }), 7] });
      const page = await open(browser, api);
      await page.locator('.archrow', { hasText: 'Damaged card' }).waitFor();
      await page.locator('.archq').fill('damaged'); await waitNums(page, ['#5']);
      await page.locator('.archrow', { hasText: 'Damaged card' }).click(); await page.locator('#dlgArch[open]').waitFor(); await page.locator('#aClose').click();
      await page.locator('#viewSw button[data-view="people"]').click(); await page.locator('.peoplev select.pillsel').selectOption({ label: 'Archived' });
      await page.locator('.parch', { hasText: 'Damaged person' }).click(); await page.locator('#dlgArch[open]').waitFor(); await page.locator('#aClose').click();
      await page.locator('#btnSearch').click(); await page.locator('#qArch').check(); await page.locator('#qQ').fill('Damaged'); await page.locator('.qhit', { hasText: 'Damaged person' }).waitFor();
      await page.locator('#qQ').fill('Twice filed'); await page.locator('.qhit', { hasText: 'Twice filed card' }).waitFor();
      assert.equal(await page.locator('.qhit', { hasText: 'Twice filed card' }).count(), 1, 'a repeated id is listed once and search still works');
      await page.locator('.qhit', { hasText: 'Twice filed card' }).click(); await page.locator('#dlgArch[open]').waitFor();
      assert.match(await page.locator('#aBody').innerText(), /History \(1\)/, 'a history list with a null entry opens with the valid line'); await page.locator('#aClose').click();
      assert.deepEqual(page.errors, [], 'no page errors'); await page.done(); }

    // ---- single-file board (no split layout): Put back refreshes the Archive view at once ----
    { const api = new Github(); api.files['cards/t_shipped.json'] = text(card('t_shipped', 3, 'Shipped live', { column: 'done', client: 'Acme' })); api.single();
      const reads = {}; let hold = null;
      const page = await open(browser, api, { route: async r => { const m = r.request().method() === 'GET' && /\/archive\/(\d{4})\.json/.exec(r.request().url()); if (m) reads[m[1]] = (reads[m[1]] || 0) + 1;
        if (m && m[1] === '2026' && !hold) await new Promise(ok => { hold = ok; }); return api.route(r); } });
      await page.locator('.archload').waitFor(); assert.match(await page.locator('.archload').innerText(), /Loading the archive/); await shot(page, 'archive-loading-1280');
      for (let i = 0; i < 50 && !hold; i++) await page.waitForTimeout(50); hold();
      await waitNums(page, ['#22', '#21', '#20', '#11', '#10']);
      assert.deepEqual(reads, { 2025: 1, 2026: 1 }, 'one read per year');
      await page.locator('.archrow', { hasText: 'Invoice March' }).click(); await page.locator('#aRestore').click(); await page.locator('#dlgArch').waitFor({ state: 'hidden' });
      for (let i = 0; i < 50 && !api.json('tasks.json').tasks.some(t => t.id === 'a26_one'); i++) await page.waitForTimeout(100);
      assert.ok(api.json('tasks.json').tasks.some(t => t.id === 'a26_one'), 'the card is back in the board file');
      await page.locator('#dlgCard[open]').waitFor(); await page.keyboard.press('Escape'); await page.locator('#dlgCard').waitFor({ state: 'hidden' });
      if (await page.evaluate(() => document.body.dataset.view) !== 'archive') await page.locator('#viewSw button[data-view="archive"]').click();
      await waitNums(page, ['#22', '#21', '#11', '#10']); assert.equal(await page.locator('.archcount').innerText(), '4 archived cards');
      // an archive run changes only this year's entry: only this year's file is read again (the other year comes from this page's copy)
      const year = String(new Date().getFullYear()), other = year === '2026' ? '2025' : '2026';
      await page.locator('#viewSw button[data-view="board"]').click(); const shipped = page.locator('.col[data-col="done"] .card', { hasText: 'Shipped live' });
      await shipped.hover(); await shipped.locator('.quickarch').click(); await page.getByRole('button', { name: 'Undo', exact: true }).waitFor();
      // the archive run itself reads every year (older history lines); from here on, only loading the view: every year is
      // checked against the captured tree; the unchanged archive reuses its SHA body and only the changed year is normalised again
      const norms = await page.evaluate(() => window.kbArchNormYears), beforeReads = { ...reads };
      await page.locator('#viewSw button[data-view="archive"]').click(); await page.locator('.archrow', { hasText: 'Shipped live' }).waitFor();
      assert.equal(reads[other], beforeReads[other], `the unchanged ${other} archive reuses the immutable snapshot blob`);
      assert.equal(await page.evaluate(() => window.kbArchNormYears) - norms, 1, `only the ${year} file is normalised again`);
      assert.deepEqual(page.errors, [], 'no page errors'); await page.done(); }

    // ---- single-file board: archive a card, Undo, edit it, archive it again, Undo (and Put back): the edits survive. The
    //      year's counts come back to the same values, so a copy reused on counts would bring back the first version ----
    { const api = new Github(); api.files['cards/t_shipped.json'] = text(card('t_shipped', 3, 'Shipped live', { column: 'done', client: 'Acme' })); api.single();
      const page = await open(browser, api, { view: 'board' }); const year = String(new Date().getFullYear());
      const boardCard = () => api.json('tasks.json').tasks.find(t => t.id === 't_shipped'), until = async (ok, what) => { for (let i = 0; i < 80 && !ok(); i++) await page.waitForTimeout(100); assert.ok(ok(), what); };
      const shipped = () => page.locator('.col[data-col="done"] .card', { hasText: /Shipped (live|v2)/ }), undo = page.getByRole('button', { name: 'Undo', exact: true });
      const archiveIt = async () => { await shipped().hover(); await shipped().locator('.quickarch').click(); await undo.waitFor(); await until(() => !boardCard(), 'archived: off the board file'); };
      const undoIt = async () => { await undo.click(); await until(() => { const f = api.json('archive/' + year + '.json'), ix = api.json('tasks.json').archive.files[year]; return boardCard() && !(f.tasks || []).some(t => t.id === 't_shipped') && ix && ix.tasks === f.tasks.length; }, 'Undo: back on the board, out of the archive file, and the index counts it'); await shipped().waitFor(); };
      await shipped().waitFor(); await archiveIt(); const counts = JSON.stringify(api.json('tasks.json').archive.files[year]);
      await page.locator('#viewSw button[data-view="archive"]').click(); await page.locator('.archrow', { hasText: 'Shipped live' }).waitFor();   // the view loads (and keeps) this year's copy
      await page.locator('#viewSw button[data-view="board"]').click(); await undoIt();
      await shipped().click(); await page.locator('#dlgCard[open]').waitFor();
      await page.locator('#cTitle').fill('Shipped v2'); await page.locator('#cTitle').blur(); await until(() => boardCard().title === 'Shipped v2', 'the edit is saved');
      await page.keyboard.press('Escape'); await page.locator('#dlgCard').waitFor({ state: 'hidden' });
      await archiveIt(); assert.equal(JSON.stringify(api.json('tasks.json').archive.files[year]), counts, 'the year\'s counts are the same as when the view loaded it');
      await undoIt(); assert.equal(boardCard().title, 'Shipped v2', 'Undo restores the edited card, not the first archived copy');
      // and through the Archive view: archive it again, the row shows the edit, Put back keeps it
      await archiveIt(); await page.locator('#viewSw button[data-view="archive"]').click();
      await page.locator('.archrow', { hasText: 'Shipped v2' }).waitFor(); assert.equal(await page.locator('.archrow', { hasText: 'Shipped live' }).count(), 0, 'the view shows the edited copy');
      await page.locator('.archrow', { hasText: 'Shipped v2' }).click(); await page.locator('#aRestore').click(); await page.locator('#dlgArch').waitFor({ state: 'hidden' });
      await until(() => boardCard() && boardCard().title === 'Shipped v2', 'Put back restores the edited card');
      assert.deepEqual(page.errors, [], 'no page errors'); await page.done(); }

    // ---- single-file board: Undo while Settings switches to another branch (the new board still loading): it refuses and
    //      says to put the card back from that branch; nothing is written ----
    { const api = new Github(); api.files['cards/t_shipped.json'] = text(card('t_shipped', 3, 'Shipped live', { column: 'done', client: 'Acme' })); api.single();
      let hold = null, held = false; const writes = [];
      const page = await open(browser, api, { view: 'board', route: async r => { const q = r.request(), u = q.url();
        if (q.method() !== 'GET' && held) writes.push(q.method() + ' ' + new URL(u).pathname);
        if (u.includes('/contents/board/tasks.json') && u.includes('ref=dev') && !held) { held = true; await new Promise(ok => { hold = ok; }); }
        return api.route(r); } });
      const shipped = page.locator('.col[data-col="done"] .card', { hasText: 'Shipped live' }); await shipped.waitFor();
      await shipped.hover(); await shipped.locator('.quickarch').click();
      const undo = page.getByRole('button', { name: 'Undo', exact: true }); await undo.waitFor();
      for (let i = 0; i < 80 && api.json('tasks.json').tasks.some(t => t.id === 't_shipped'); i++) await page.waitForTimeout(100);
      await page.evaluate(() => { const v = (id, x) => { document.getElementById(id).value = x; }; v('sRepo', 'acme/board'); v('sBranch', 'dev'); v('sPath', 'board/tasks.json'); v('sMe', 'alex'); document.getElementById('sSave').click(); });
      for (let i = 0; i < 100 && !hold; i++) await page.waitForTimeout(50); assert.ok(hold, 'the new board\'s read is in flight');
      await page.locator('.ui-toast').getByRole('button', {name:'Undo', exact:true}).click();
      await page.locator('.ui-toast', { hasText: 'The board changed; put it back from that branch' }).waitFor();
      assert.equal(await page.locator('.ui-toast', { hasText: 'did not load' }).count(), 0, 'not "the archive did not load"');
      assert.deepEqual(writes, [], 'nothing is written'); hold();
      assert.deepEqual(page.errors, [], 'no page errors'); await page.done(); }

    // ---- Settings → another branch: while the new board loads, a render loads no archive (state is still the old board's) ----
    { const api = new Github().single(); let hold = null, held = false; const reads = [];
      const page = await open(browser, api, { route: async r => { const u = r.request().url();
        if (/\/archive\/\d{4}\.json/.test(u)) reads.push({ dev: u.includes('ref=dev'), held: !!hold });
        if (u.includes('/contents/board/tasks.json') && u.includes('ref=dev') && !held) { held = true; await new Promise(ok => { hold = ok; }); hold = null; }
        return api.route(r); } });
      await waitNums(page, ['#22', '#21', '#20', '#11', '#10']);
      await page.evaluate(() => { const v = (id, x) => { document.getElementById(id).value = x; }; v('sRepo', 'acme/board'); v('sBranch', 'dev'); v('sPath', 'board/tasks.json'); v('sMe', 'alex'); document.getElementById('sSave').click(); });
      for (let i = 0; i < 100 && !hold; i++) await page.waitForTimeout(50); assert.ok(hold, 'the new board\'s read is in flight');
      await page.locator('#viewSw button[data-view="people"]').click(); await page.locator('#viewSw button[data-view="archive"]').click();   // renders while the board loads
      await page.locator('.archload').waitFor(); await page.waitForTimeout(300); assert.equal(await page.locator('.archrow').count(), 0, 'the old board\'s archive is not shown');
      assert.deepEqual(reads.filter(x => x.held), [], 'no archive read while the new board is still loading');
      hold(); await waitNums(page, ['#22', '#21', '#20', '#11', '#10']);
      assert.ok(reads.some(x => x.dev && !x.held), 'the archive loads from the new branch once its board is in');
      assert.deepEqual(page.errors, [], 'no page errors'); await page.done(); }

    // ---- Forget token while a save is on its way: the old board does not come back (no state, no snapshot) ----
    { const api = new Github(); api.files['cards/t_shipped.json'] = text(card('t_shipped', 3, 'Shipped live', { column: 'done', client: 'Acme' })); api.single();
      let hold = null, held = false;
      const page = await open(browser, api, { view: 'board', route: async r => { if (r.request().method() === 'PUT' && r.request().url().includes('/contents/board/tasks.json') && !held) { held = true; await new Promise(ok => { hold = ok; }); } return api.route(r); } });
      const shipped = page.locator('.col[data-col="done"] .card', { hasText: 'Shipped live' }); await shipped.waitFor();
      await shipped.click(); await page.locator('#dlgCard[open]').waitFor(); await page.locator('#cTitle').fill('Shipped v2'); await page.locator('#cTitle').blur();
      for (let i = 0; i < 100 && !hold; i++) await page.waitForTimeout(50); assert.ok(hold, 'the save is in flight');
      await page.keyboard.press('Escape');
      await page.evaluate(() => document.getElementById('sForget').click()); await page.locator('dialog[open]').getByRole('button', { name: 'Forget token' }).click();
      await page.waitForFunction(() => !localStorage.getItem('kb_token')); hold(); await page.waitForTimeout(800);
      assert.equal(await page.locator('.card', { hasText: /Shipped|Live work/ }).count(), 0, 'the old board is not drawn again after the save finishes');
      const keys = await page.evaluate(() => new Promise(ok => { const r = indexedDB.open('keeptrack', 1); r.onsuccess = () => { const q = r.result.transaction('kv', 'readonly').objectStore('kv').getAllKeys(); q.onsuccess = () => ok(q.result.map(String)); }; r.onerror = () => ok([]); }));
      assert.deepEqual(keys.filter(k => /^kb_(snap|arch):/.test(k)), [], 'no board snapshot or archive copy in IndexedDB');
      assert.deepEqual(page.errors, [], 'no page errors'); await page.done(); }

    // ---- single-file board: Put back restores the card as the archive file has it NOW. Another tab, device or keeptrack.py
    //      changed it behind this page with the same counts (and no new last_run); the loaded copy is not what comes back ----
    { const api = new Github().single(); const page = await open(browser, api);
      await waitNums(page, ['#22', '#21', '#20', '#11', '#10']);
      const a = api.json('archive/2026.json'); a.tasks = a.tasks.map(t => t.id === 'a26_one' ? { ...t, title: 'Invoice March v2', details: 'edited elsewhere' } : t); api.files['archive/2026.json'] = text(a); api.head='external-edit-'+ ++api.n;
      await page.locator('.archrow', { hasText: 'Invoice March' }).click(); assert.equal(await page.locator('#aTitle').innerText(), '#20 Invoice March', 'the page still shows the copy it loaded');
      await page.locator('#aRestore').click(); await page.locator('#dlgArch').waitFor({ state: 'hidden' });
      const back = () => api.json('tasks.json').tasks.find(t => t.id === 'a26_one');
      for (let i = 0; i < 80 && !back(); i++) await page.waitForTimeout(100);
      assert.equal(back().title, 'Invoice March v2', 'Put back restores the archive file as it is now'); assert.equal(back().details, 'edited elsewhere');
      // a card that left the archive file meanwhile is refused, not restored from the old copy
      await page.keyboard.press('Escape'); await page.locator('#dlgCard').waitFor({ state: 'hidden' });
      if (await page.evaluate(() => document.body.dataset.view) !== 'archive') await page.locator('#viewSw button[data-view="archive"]').click();
      await waitNums(page, ['#22', '#21', '#11', '#10']);
      const b = api.json('archive/2025.json'); b.tasks = b.tasks.filter(t => t.id !== 'a25_one'); b.tasks.push(card('a25_other', 12, 'Another card', {})); api.files['archive/2025.json'] = text(b); api.head='external-edit-'+ ++api.n;
      await page.locator('.archrow', { hasText: 'Old website brief' }).click(); await page.locator('#aRestore').click();
      await page.locator('.ui-toast', { hasText: 'was changed elsewhere' }).waitFor();
      assert.ok(!api.json('tasks.json').tasks.some(t => t.id === 'a25_one'), 'not restored from the page\'s old copy');
      assert.deepEqual(page.errors, [], 'no page errors'); await page.done(); }

    // ---- single-file board: Put back writes the card as the archive file holds it (raw), not the display copy: a field
    //      the view normalises (a non-text field becomes text) is written back unchanged, with its older history lines ----
    { const api = new Github().single(); const a = api.json('archive/2026.json');
      a.tasks = a.tasks.map(t => t.id === 'a26_one' ? { ...t, notes: 42, extra_field: { kept: true } } : t); a.history = { a26_one: [{ at: stamp, by: 'alex', text: 'older line' }] }; api.files['archive/2026.json'] = text(a);
      const page = await open(browser, api); await waitNums(page, ['#22', '#21', '#20', '#11', '#10']);
      await page.locator('.archrow', { hasText: 'Invoice March' }).click(); await page.locator('#aRestore').click(); await page.locator('#dlgArch').waitFor({ state: 'hidden' });
      const back = () => api.json('tasks.json').tasks.find(t => t.id === 'a26_one');
      for (let i = 0; i < 80 && !back(); i++) await page.waitForTimeout(100);
      assert.ok(back(), 'the card is back'); assert.deepEqual([back().notes, back().extra_field], [42, { kept: true }], 'the raw fields come back, not the normalised display copy');
      assert.equal(back().history[0].text, 'older line', 'the older history lines come back first');
      assert.deepEqual(page.errors, [], 'no page errors'); await page.done(); }

    // Put back rehydrates history across older years and part files in both layouts, even after the view cached them.
    for (const layout of ['split', 'single']) {
      const api = new Github();
      const root = api.json('tasks.json'); root.archive.files['2025-2'] = { tasks: 0, contacts: 0 };
      api.files['tasks.json'] = text(root);
      const older = { at: '2025-01-01T00:00:00Z', by: 'alex', text: 'older year history' };
      const middle = { at: '2025-02-01T00:00:00Z', by: 'alex', text: 'older part history' };
      const own = { at: stamp, by: 'alex', text: 'own latest history' };
      const a = api.json('archive/2026.json'); a.tasks.find(t => t.id === 'a26_one').history = [middle, own, own];
      a.history.a26_one = [middle]; api.files['archive/2026.json'] = text(a);
      const prev = api.json('archive/2025.json'); prev.history.a26_one = [older, older]; api.files['archive/2025.json'] = text(prev);
      api.files['archive/2025-2.json'] = text({ version: 3, archive: true, year: '2025', tasks: [], contacts: [], history: { a26_one: [older, middle] } });
      if (layout === 'single') api.single();
      const page = await open(browser, api); await waitNums(page, ['#22', '#21', '#20', '#11', '#10']);
      // Change older history after the Archive view loaded: Put back must use its own fresh reads.
      const late = { at: '2025-03-01T00:00:00Z', by: 'alex', text: 'fresh older history' };
      const changed = api.json('archive/2025-2.json'); changed.history.a26_one.push(late); api.files['archive/2025-2.json'] = text(changed);
      api.head = 'head-' + ++api.n;   // a real external commit changes the immutable tree identity too
      await page.locator('.archrow', { hasText: 'Invoice March' }).click(); await page.locator('#aRestore').click();
      await page.locator('#dlgArch').waitFor({ state: 'hidden' });
      const back = () => layout === 'split' ? api.json('cards/a26_one.json') : api.json('tasks.json').tasks.find(t => t.id === 'a26_one');
      for (let i = 0; i < 80 && !back(); i++) await page.waitForTimeout(100);
      assert.ok(back(), `${layout}: restored card exists`);
      assert.deepEqual(back().history.slice(0, 4).map(h => h.text), [older.text, middle.text, late.text, own.text], `${layout}: all indexed history is hydrated fresh in year/part order`);
      assert.equal(back().history.filter(h => h.text === middle.text).length, 1, `${layout}: repeated history is deduplicated`);
      assert.equal(back().history.filter(h => h.text === own.text).length, 1, `${layout}: own duplicates are deduplicated`);
      assert.equal(api.json('archive/2025.json').history.a26_one[0].text, older.text, 'other archive evidence is retained');
      assert.deepEqual(page.errors, [], `${layout}: no page errors`); await page.done();
    }

    // ---- split board: Put back reads the year file from a fresh snapshot. A card that left that file elsewhere (deleted or
    //      purged), or a year file that is gone, is refused, the archived card closes and nothing is written; the page's
    //      loaded copy never brings it back ----
    for (const how of ['gone', 'onBoard', 'noFile']) {
      const api = new Github(), writes = [];
      const page = await open(browser, api, { route: r => { if (r.request().method() !== 'GET') writes.push(r.request().method() + ' ' + new URL(r.request().url()).pathname); return api.route(r); } });
      await waitNums(page, ['#22', '#21', '#20', '#11', '#10']);
      if (how === 'noFile') delete api.files['archive/2026.json'];
      else { const a = api.json('archive/2026.json'); a.tasks = a.tasks.filter(t => t.id !== 'a26_one'); api.files['archive/2026.json'] = text(a); }
      if (how === 'onBoard') api.files['cards/a26_one.json'] = text(card('a26_one', 20, 'Invoice March', { column: 'todo', client: 'Acme', details: 'put back elsewhere' }));
      api.head = 'head-' + ++api.n;   // someone else's commit
      await page.locator('.archrow', { hasText: 'Invoice March' }).click(); await page.locator('#dlgArch[open]').waitFor(); await page.locator('#aRestore').click();
      await page.locator('.ui-toast', { hasText: how === 'onBoard' ? 'is already back on the board' : 'is not in that archive file now' }).waitFor();
      await page.locator('#dlgArch').waitFor({ state: 'hidden' });
      assert.deepEqual(writes, [], `${how}: nothing is written`);
      if (how === 'onBoard') assert.equal(api.json('cards/a26_one.json').details, 'put back elsewhere', 'the board copy is untouched');
      else assert.equal(api.json('cards/a26_one.json'), null, `${how}: the card is not restored from the page's loaded copy`);
      assert.deepEqual(page.errors, [], 'no page errors'); await page.done(); }

    // ---- both layouts: Put back passes the raw card through the board's own card tolerance. A card with no labels, links
    //      or to-dos opens fine; an own "__proto__" key in the file is dropped and pollutes nothing; null history lines go ----
    for (const layout of ['single', 'split']) {
      const api = new Github(); if (layout === 'single') api.single();
      const a = api.json('archive/2026.json');
      a.tasks = a.tasks.map(t => { if (t.id !== 'a26_one') return t; const x = { ...t, history: [null, { at: stamp, by: 'alex', text: 'own line' }] }; delete x.labels; delete x.links; delete x.todos; return x; });
      a.tasks.unshift(null, { id: { invalid: true }, title: 'Malformed id' }, { id: '../unsafe', title: 'Unsafe id' });
      a.history = { a26_one: [null, { at: stamp, by: 'alex', text: 'older line' }, 'junk'] };
      api.files['archive/2026.json'] = text(a).replace('"id": "a26_one",', '"__proto__": { "polluted": true },\n      "constructor": { "polluted": true },\n      "id": "a26_one",');
      assert.ok(api.files['archive/2026.json'].includes('"__proto__"'), 'the fixture carries an own __proto__ key');
      const page = await open(browser, api); await waitNums(page, ['#22', '#21', '#20', '#11', '#10']);
      await page.locator('.archrow', { hasText: 'Invoice March' }).click(); await page.locator('#aRestore').click(); await page.locator('#dlgArch').waitFor({ state: 'hidden' });
      const rel = layout === 'single' ? 'tasks.json' : 'cards/a26_one.json';
      const raw = () => api.files[rel] || '', back = () => layout === 'single' ? api.json('tasks.json').tasks.find(t => t.id === 'a26_one') : api.json('cards/a26_one.json');
      for (let i = 0; i < 80 && !back(); i++) await page.waitForTimeout(100);
      assert.ok(back(), `${layout}: the card is back`); await page.locator('#dlgCard[open]').waitFor();
      assert.deepEqual([back().labels, back().links, back().todos], [[], [], []], `${layout}: missing lists are filled`);
      assert.ok(!/"__proto__"|"constructor"/.test(raw()), `${layout}: no __proto__ or constructor key is written`);
      assert.deepEqual(back().history.slice(0, 3).map(h => h.text), ['older line', 'own line', 'restored from the archive'], `${layout}: only real history lines, older first`);   // (single-file: the page's own change log adds "created" after)
      assert.ok(back().history.every(h => h && typeof h === 'object'), `${layout}: no null or text history entries`);
      assert.equal(await page.evaluate(() => ({}).polluted), undefined, 'Object.prototype stays clean');
      assert.deepEqual(page.errors, [], `${layout}: no page errors`); await page.done(); }

    // ---- single-file board: Undo while an archive load started before the archive commit is still in flight. That load
    //      finishes stale; Undo loads once more and puts the card back (no "the archive did not load") ----
    { const api = new Github(); api.files['cards/t_shipped.json'] = text(card('t_shipped', 3, 'Shipped live', { column: 'done', client: 'Acme' })); api.single();
      let arm = false, hold = null;
      const page = await open(browser, api, { view: 'board', route: async r => { if (arm && !hold && r.request().method() === 'GET' && r.request().url().includes('/archive/2025.json')) await new Promise(ok => { hold = ok; }); return api.route(r); } });
      const boardCard = () => api.json('tasks.json').tasks.find(t => t.id === 't_shipped'), until = async (ok, what) => { for (let i = 0; i < 80 && !ok(); i++) await page.waitForTimeout(100); assert.ok(ok(), what); };
      const shipped = page.locator('.col[data-col="done"] .card', { hasText: 'Shipped live' }); await shipped.waitFor();
      arm = true; await page.locator('#viewSw button[data-view="archive"]').click(); await until(() => hold, 'the archive load is in flight');
      await page.locator('#viewSw button[data-view="board"]').click(); await shipped.hover(); await shipped.locator('.quickarch').click();
      const undo = page.getByRole('button', { name: 'Undo', exact: true }); await undo.waitFor(); await until(() => !boardCard(), 'archived');
      await undo.click(); await page.waitForTimeout(200); hold();
      await until(() => boardCard(), 'Undo puts the card back');
      assert.equal(await page.locator('.ui-toast', { hasText: 'did not load' }).count(), 0, 'no false "did not load"');
      assert.deepEqual(page.errors, [], 'no page errors'); await page.done(); }

    // ---- Settings → another branch while a save is on its way: the switch waits, and the save goes to the branch it started on ----
    { const api = new Github(); api.files['cards/t_shipped.json'] = text(card('t_shipped', 3, 'Shipped live', { column: 'done', client: 'Acme' })); api.single();
      let hold = null, held = false; const puts = [];
      const page = await open(browser, api, { view: 'board', route: async r => { const q = r.request();
        if (q.method() === 'PUT') puts.push({ path: new URL(q.url()).pathname, branch: q.postDataJSON().branch, at: Date.now() });
        if (q.method() === 'PUT' && q.url().includes('/contents/board/tasks.json') && !held) { held = true; await new Promise(ok => { hold = ok; }); }
        return api.route(r); } });
      const shipped = page.locator('.col[data-col="done"] .card', { hasText: 'Shipped live' }); await shipped.waitFor();
      await shipped.click(); await page.locator('#dlgCard[open]').waitFor(); await page.locator('#cTitle').fill('Shipped v2'); await page.locator('#cTitle').blur();
      for (let i = 0; i < 100 && !hold; i++) await page.waitForTimeout(50); assert.ok(hold, 'the save is in flight'); await page.keyboard.press('Escape');
      const devReads = () => page.evaluate(() => performance.getEntriesByType('resource').filter(e => e.name.includes('ref=dev')).length);
      await page.evaluate(() => { const v = (id, x) => { document.getElementById(id).value = x; }; v('sRepo', 'acme/board'); v('sBranch', 'dev'); v('sPath', 'board/tasks.json'); v('sMe', 'alex'); document.getElementById('sSave').click(); });
      await page.waitForTimeout(400);
      assert.equal(await page.evaluate(() => localStorage.getItem('kb_branch')), 'main', 'the switch waits for the save');
      assert.match(await page.locator('#sSave').innerText(), /Waiting/); assert.equal(await page.locator('#sSave').isDisabled(), true);
      assert.equal(await devReads(), 0, 'nothing is read from the other branch yet');
      hold(); await page.waitForFunction(() => localStorage.getItem('kb_branch') === 'dev', null, { timeout: 10000 });
      const save = puts.find(x => x.path.endsWith('/contents/board/tasks.json'));
      assert.equal(save.branch, 'main', 'the save goes to the branch it started on');
      assert.equal(api.json('tasks.json').tasks.find(t => t.id === 't_shipped').title, 'Shipped v2');
      assert.deepEqual(puts.filter(x => x.branch !== 'main'), [], 'nothing is written to the other branch');
      assert.deepEqual(page.errors, [], 'no page errors'); await page.done(); }

    // ---- Forget token during a single-file archive run: it waits for the run, then nothing of the archive stays; no false errors ----
    { const api = new Github(); api.files['cards/t_shipped.json'] = text(card('t_shipped', 3, 'Shipped live', { column: 'done', client: 'Acme' })); api.single();
      let hold = null, held = false;
      const page = await open(browser, api, { view: 'board', route: async r => { const q = r.request();
        if (q.method() === 'PATCH' && q.url().endsWith('/git/refs/heads/main') && !held) { held = true; await new Promise(ok => { hold = ok; }); }
        return api.route(r); } });
      const shipped = page.locator('.col[data-col="done"] .card', { hasText: 'Shipped live' }); await shipped.waitFor();
      await shipped.hover(); await shipped.locator('.quickarch').click();
      for (let i = 0; i < 100 && !hold; i++) await page.waitForTimeout(50); assert.ok(hold, 'the atomic archive commit is in flight');
      await page.evaluate(() => document.getElementById('sForget').click()); await page.locator('dialog[open]').getByRole('button', { name: 'Forget token' }).click();
      await page.waitForTimeout(300); assert.ok(await page.evaluate(() => localStorage.getItem('kb_token')), 'Forget token waits for the archive run');
      hold(); await page.waitForFunction(() => !localStorage.getItem('kb_token'), null, { timeout: 10000 }); await page.waitForTimeout(800);
      assert.ok(!api.json('tasks.json').tasks.some(t => t.id === 't_shipped'), 'the run finished on its board before the token went');
      const keys = await page.evaluate(() => new Promise(ok => { const r = indexedDB.open('keeptrack', 1); r.onsuccess = () => { const q = r.result.transaction('kv', 'readonly').objectStore('kv').getAllKeys(); q.onsuccess = () => ok(q.result.map(String)); }; r.onerror = () => ok([]); }));
      assert.deepEqual(keys.filter(k => /^kb_(snap|arch):/.test(k)), [], 'no board snapshot or archive copy in IndexedDB');
      assert.equal(await page.locator('.ui-toast', { hasText: /not saved|Archive failed|Could not/i }).count(), 0, 'no false error');
      assert.equal(await page.locator('.card', { hasText: /Shipped|Live work/ }).count(), 0);
      assert.deepEqual(page.errors, [], 'no page errors'); await page.done(); }

    // ---- a crafted index key (not a four-digit year) is never fetched; Forget token empties the archived card and search ----
    { const api = new Github().single(); const root = api.json('tasks.json'); root.archive.files['../x'] = { tasks: 1, contacts: 0 }; api.files['tasks.json'] = text(root); const urls = [];
      const page = await open(browser, api, { route: r => { urls.push(r.request().url()); return api.route(r); } });
      await waitNums(page, ['#22', '#21', '#20', '#11', '#10']);
      assert.deepEqual(urls.filter(u => /x\.json|%2E%2E|\.\.\//i.test(u)), [], 'no request for ../x');
      await page.locator('.archrow', { hasText: 'Invoice March' }).click(); await page.locator('#dlgArch[open]').waitFor(); await page.locator('#aClose').click();
      await page.locator('#btnSearch').click(); await page.locator('#qArch').check(); await page.locator('#qQ').fill('Invoice'); await page.locator('.qhit', { hasText: 'Invoice March' }).waitFor(); await page.locator('#qClose').click();
      await page.evaluate(() => document.getElementById('sForget').click()); await page.locator('dialog[open]').getByRole('button', { name: 'Forget token' }).click();
      await page.waitForFunction(() => !localStorage.getItem('kb_token'));
      assert.deepEqual(await page.evaluate(() => ['aBody', 'aTitle', 'aMeta', 'qRes'].map(id => document.getElementById(id).textContent).concat(document.getElementById('qQ').value)), ['', '', '', '', ''], 'no archived text left on the page');
      assert.deepEqual(page.errors, [], 'no page errors'); await page.done(); }

    // ---- Forget token while an archive file's body is still downloading: nothing is cached; with the token back the archive loads ----
    { const api = new Github().single(); api.rawFiles = new Set(['archive/2026.json']); let hold = null, held = false;
      const page = await open(browser, api, { route: async r => { if (/raw/.test(r.request().headers()['accept'] || '') && r.request().url().includes('/archive/2026.json') && !held) { held = true; await new Promise(ok => { hold = ok; }); } return api.route(r); } });
      for (let i = 0; i < 100 && !hold; i++) await page.waitForTimeout(50); assert.ok(hold, 'the raw body read is in flight');
      await page.evaluate(() => document.getElementById('sForget').click()); await page.locator('dialog[open]').getByRole('button', { name: 'Forget token' }).click();
      await page.waitForFunction(() => !localStorage.getItem('kb_token')); hold(); await page.waitForTimeout(800);
      const keys = await page.evaluate(() => new Promise(ok => { const r = indexedDB.open('keeptrack', 1); r.onsuccess = () => { const q = r.result.transaction('kv', 'readonly').objectStore('kv').getAllKeys(); q.onsuccess = () => ok(q.result.map(String)); }; r.onerror = () => ok([]); }));
      assert.deepEqual(keys.filter(k => k.startsWith('kb_arch:')), [], 'no archive copy in IndexedDB after Forget token');
      await page.evaluate(() => { const v = (id, x) => { document.getElementById(id).value = x; }; v('sRepo', 'acme/board'); v('sBranch', 'main'); v('sPath', 'board/tasks.json'); v('sMe', 'alex'); v('sToken', 'test'); document.getElementById('sSave').click(); });
      await page.waitForFunction(() => document.body.dataset.view === 'archive'); await waitNums(page, ['#22', '#21', '#20', '#11', '#10']);
      assert.equal(await page.locator('.archerr').count(), 0, 'the cancelled load left no error behind');
      assert.deepEqual(page.errors, [], 'no page errors'); await page.done(); }

    // ---- Settings: another branch with the same archive index is another board: its own archive shows, never the old one ----
    { const api = new Github(), page = await open(browser, api);
      await waitNums(page, ['#22', '#21', '#20', '#11', '#10']);
      const other = api.json('archive/2026.json'); other.tasks = other.tasks.map(t => ({ ...t, title: 'Dev ' + t.title })); api.files['archive/2026.json'] = text(other); api.head = 'dev-head';
      await page.evaluate(() => { const v = (id, x) => { document.getElementById(id).value = x; }; v('sRepo', 'acme/board'); v('sBranch', 'dev'); v('sPath', 'board/tasks.json'); v('sMe', 'alex'); document.getElementById('sSave').click(); });
      await page.locator('.archrow', { hasText: 'Dev Invoice March' }).waitFor();
      assert.equal(await page.locator('.archrow', { hasText: /^((?!Dev ).)*Invoice March/ }).count(), 0, 'the old branch\'s card is gone');
      assert.deepEqual(page.errors, [], 'no page errors'); await page.done(); }

    // ---- Search with Include archive: a failed archive load is not retried on every key, only when search opens again ----
    { const api = new Github().single(); let fail = true, reads = 0;
      const page = await open(browser, api, { view: 'board', route: r => { if (r.request().url().includes('/archive/2025.json')) { reads++; if (fail) return r.fulfill({ status: 500, contentType: 'application/json', body: '{"message":"boom"}' }); } return api.route(r); } });
      await page.locator('.card').first().waitFor();
      await page.locator('#btnSearch').click(); await page.locator('#qArch').check(); await page.waitForTimeout(300);
      assert.equal(reads, 0, 'an empty query does not load the archive');
      await page.locator('#qQ').fill('Lena'); await page.locator('#qInfo', { hasText: 'Could not load the archive' }).waitFor();
      const after = reads; await page.locator('#qQ').pressSequentially(' Lost', { delay: 120 }); await page.waitForTimeout(300);
      assert.equal(reads, after, 'typing after a failure does not try again');
      fail = false; await page.locator('#qClose').click(); await page.waitForFunction(() => !/search/.test(location.hash));
      await page.locator('#btnSearch').click(); await page.locator('.qhit', { hasText: 'Lena Lost' }).waitFor();
      assert.ok(reads > after, 'reopening search tries again');
      assert.deepEqual(page.errors, [], 'no page errors'); await page.done(); }

    // ---- a board with no archive: an empty state that says how cards get there ----
    { const api = new Github(); const root = api.json('tasks.json'); root.archive = { files: {} }; api.files['tasks.json'] = text(root);
      const page = await open(browser, api); await page.locator('.archv .ui-empty', { hasText: 'Nothing archived yet' }).waitFor();
      assert.deepEqual(page.errors, [], 'no page errors'); await page.done(); }
    console.log('archive-view: all checks passed');
  } finally { await browser.close(); server.close(); }
})().catch(e => { console.error(e); process.exit(1); });

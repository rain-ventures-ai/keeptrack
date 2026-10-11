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

// The board asks with in-page dialogs (ui.confirm / ui.promptText), never window.confirm. autoConfirm answers every one of
// them with its confirm button, like the old page.on('dialog', d => d.accept()); it also covers pages opened later in the page.
const AUTO_CONFIRM = () => { const go = () => new MutationObserver(() => { document.querySelectorAll('dialog.ui-sheet--alert[open]:not([data-auto])').forEach(d => { d.dataset.auto = '1'; setTimeout(() => { const b = d.querySelectorAll('.ui-sheet__foot button'); if (b.length) b[b.length - 1].click(); }); }); }).observe(document.documentElement, { childList: true, subtree: true, attributes: true, attributeFilter: ['open'] });
  if (document.documentElement) go(); else document.addEventListener('DOMContentLoaded', go); };
async function autoConfirm(page) { page.on('dialog', d => d.accept());   /* the task drawer still has a few native confirms */ await page.addInitScript(AUTO_CONFIRM); await page.evaluate(AUTO_CONFIRM).catch(() => {}); }
// The confirm sheet that is open now: check its text, then press the named button.
async function answer(page, re, label) { const d = page.getByRole('alertdialog'); await d.waitFor(); assert.match(await d.textContent(), re); await d.getByRole('button', { name: label, exact: true }).click(); }

async function openBoard(browser, api) {
  const page = await browser.newPage(); page.on('pageerror', e => console.error('page error:', e.message)); await page.addInitScript(() => { localStorage.setItem('kb_repo', 'acme/board'); localStorage.setItem('kb_branch', 'main'); localStorage.setItem('kb_path', 'board/tasks.json'); localStorage.setItem('kb_token', 'test'); localStorage.setItem('kb_me', 'alex'); localStorage.setItem('kb_api', 'https://api.test'); localStorage.setItem('kb_layout', 'classic'); sessionStorage.setItem('kb_view', 'board'); });
  await page.route('https://api.test/**', r => api.route(r)); await page.goto(base + '/board/index.html'); try { await page.waitForSelector('.card, .todayhead'); } catch (e) { console.error('status:', await page.locator('#status').textContent().catch(() => '?'), 'calls:', api.calls); throw e; } return page;
}

// ---- save queue: saves run one at a time, in order, visibly, and never hang ----------------------------------------
// The fake GitHub can hold each commit (the PATCH of a multi-file commit, or a PUT/DELETE of one card file) until the
// test lets it through, fails or drops it. Every wait below is on a condition, never a fixed sleep.
function gated() {
  const api = new Github(true), orig = api.route.bind(api); api.hold = false; api.held = []; api.hangNext = 0;
  api.route = async r => {
    const req = r.request(), m = req.method(), u = req.url();
    const write = (m === 'PATCH' && u.includes('/git/refs/')) || ((m === 'PUT' || m === 'DELETE') && u.includes('/contents/board/'));
    if (write && api.hangNext) { api.hangNext--; api.hung = (api.hung || 0) + 1; return; }   // never answers: the board's timeout must give up
    if (write && api.hold) {
      const commits = api.calls.filter(c => c.method === 'POST' && c.path === '/git/commits'), label = m === 'PATCH' ? (commits[commits.length - 1] || {}).body.message : (req.postDataJSON() || {}).message;
      const action = await new Promise(go => api.held.push({ label, go }));
      if (action === 'fail') return r.fulfill({ status: 500, headers: { 'Content-Type': 'application/json' }, body: '{"message":"boom"}' });
    }
    return orig(r);
  };
  api.next = async () => { await until(() => api.held.length); return api.held.shift(); };   // the next held commit, once it arrives
  return api;
}
async function until(fn, what = 'condition', ms = 15000) {
  const end = Date.now() + ms; for (;;) { const v = await fn(); if (v) return v; if (Date.now() > end) throw new Error('timed out waiting for ' + what); await new Promise(r => setTimeout(r, 25)); }
}
const titles = api => Object.entries(api.files).filter(([p]) => p.startsWith('cards/')).map(([, v]) => JSON.parse(v).title).sort();
const status = page => page.locator('#status').textContent();
const toasts = page => page.locator('.ui-toast').allTextContents();
const addTask = async (page, title) => { const i = page.locator('.col[data-col="todo"] .add input'); await i.fill(title); await i.press('Enter'); };
const saved = page => until(async () => /^Saved /.test(await status(page)), '"Saved" status');
const blur = page => page.evaluate(() => document.activeElement && document.activeElement.blur());
const unloadBlocked = page => page.evaluate(() => { const e = new Event('beforeunload', { cancelable: true }); window.dispatchEvent(e); return e.defaultPrevented; });

let base;
(async () => {
  await new Promise(ok => server.listen(0, '127.0.0.1', ok)); base = `http://127.0.0.1:${server.address().port}`; const browser = await chromium.launch({ headless: true });
  try {
    { // two quick adds: the second waits visibly ("Saving… (1 waiting)", drawn faded at once) and they commit in order
      const api = gated(), page = await openBoard(browser, api); api.hold = true;
      assert.equal(await unloadBlocked(page), false, 'nothing saving: leaving the page is not blocked');
      await addTask(page, 'Alpha'); const first = await api.next(); assert.equal(first.label, 'Add task: Alpha');
      await addTask(page, 'Beta');
      await until(async () => await status(page) === 'Saving… (1 waiting)', '"Saving… (1 waiting)"');
      assert.deepEqual(await page.locator('.card .t').allTextContents(), ['First', 'Second', 'Alpha', 'Beta'], 'the queued card is shown before it is saved');
      assert.equal(await page.locator('.card.pending').count(), 1); assert.match(await page.locator('.card.pending').textContent(), /Beta/);
      assert.equal(await page.locator('.col[data-col="todo"] .add input').inputValue(), '', 'the add box is cleared for the next task');
      assert.equal(await unloadBlocked(page), true, 'leaving the page while saves are queued asks first');
      first.go('release'); const second = await api.next(); assert.equal(second.label, 'Add task: Beta', 'the queued save starts only after the first one');
      assert.equal(await status(page), 'Saving…'); assert.deepEqual(titles(api), ['Alpha', 'First', 'Second']);
      second.go('release'); await saved(page);
      assert.deepEqual(titles(api), ['Alpha', 'Beta', 'First', 'Second']); assert.equal(await page.locator('.card.pending').count(), 0);
      assert.deepEqual(api.calls.filter(c => c.method === 'POST' && c.path === '/git/commits').map(c => c.body.message), ['Add task: Alpha', 'Add task: Beta']);
      assert.equal(await unloadBlocked(page), false); await page.close();
    }

    { // a failed save leaves an error toast; the save queued behind it still runs and its "Saved" does not hide the error
      const api = gated(), page = await openBoard(browser, api); api.hold = true;
      await addTask(page, 'Alpha'); const first = await api.next(); await addTask(page, 'Beta');
      await until(async () => await status(page) === 'Saving… (1 waiting)', 'queued status');
      first.go('fail'); const second = await api.next(); assert.equal(second.label, 'Add task: Beta');
      second.go('release'); await saved(page);
      assert.ok((await toasts(page)).some(t => /Save failed \(error:500\)/.test(t)), 'the failure is still on screen: ' + (await toasts(page)).join(' | '));
      assert.deepEqual(titles(api), ['Beta', 'First', 'Second']);
      assert.deepEqual(await page.locator('.card .t').allTextContents(), ['First', 'Second', 'Beta']); await page.close();
    }

    { // a request that never answers times out (short limit for the test), shows an error, and the queue moves on
      const api = gated(), page = await openBoard(browser, api); await page.evaluate(() => localStorage.setItem('kb_fetch_timeout_ms', '1500'));
      api.hangNext = 1; await addTask(page, 'Alpha'); await until(() => api.hung === 1, 'the hanging commit');
      await addTask(page, 'Beta'); await until(async () => await status(page) === 'Saving… (1 waiting)', 'queued status');
      await blur(page); await page.keyboard.press('Control+z');   // undo while a save is stuck: say so, do not stay silent
      await until(async () => (await toasts(page)).some(t => /Undo will run after the current save/.test(t)), 'undo-waits toast');
      await until(async () => (await toasts(page)).some(t => /did not answer in time/.test(t)), 'timeout error toast');
      await until(() => titles(api).includes('Beta'), 'Beta saved after the timeout');
      // the queued Ctrl+Z then undid the newest change (Beta)
      await until(() => !titles(api).includes('Beta'), 'the waiting undo ran');
      assert.deepEqual(titles(api), ['First', 'Second']); await page.close();
    }

    { // Ctrl+Z twice undoes the two changes newest first; undoing "Add task" on a split board asks about no conflict
      const api = gated(), page = await openBoard(browser, api);
      await addTask(page, 'Alpha'); await until(() => titles(api).includes('Alpha'), 'Alpha saved'); await saved(page);
      await addTask(page, 'Beta'); await until(() => titles(api).includes('Beta'), 'Beta saved'); await saved(page);
      api.hold = true; await blur(page);
      await page.keyboard.press('Control+z'); const u1 = await api.next(); assert.equal(u1.label, 'Undo: Add task: Beta');
      await page.keyboard.press('Control+z');
      await until(async () => (await toasts(page)).some(t => /Undo will run after the current save/.test(t)), 'undo-waits toast');
      u1.go('release'); const u2 = await api.next(); assert.equal(u2.label, 'Undo: Add task: Alpha');
      assert.deepEqual(titles(api), ['Alpha', 'First', 'Second']);
      u2.go('release'); await until(() => !titles(api).includes('Alpha'), 'Alpha undone'); await saved(page);
      assert.deepEqual(titles(api), ['First', 'Second']); assert.equal(await page.locator('#dlgConflict[open]').count(), 0, 'no false conflict');
      assert.deepEqual(await page.locator('.card .t').allTextContents(), ['First', 'Second']); await page.close();
    }

    { // undo of one "Add task" on a split board: no conflict dialog (the saved card read back has fields the new card lacked)
      const api = gated(), page = await openBoard(browser, api);
      await addTask(page, 'Gamma'); await until(() => titles(api).includes('Gamma'), 'Gamma saved'); await saved(page);
      await blur(page); await page.keyboard.press('Control+z');
      await until(async () => (await toasts(page)).some(t => /Undid: Add task: Gamma/.test(t)) || await page.locator('#dlgConflict[open]').count(), 'undo result');
      assert.equal(await page.locator('#dlgConflict[open]').count(), 0, 'no false conflict');
      assert.deepEqual(titles(api), ['First', 'Second']); await page.close();
    }

    { // a toast's Undo belongs to its own change: after a newer change it explains instead of undoing the newer one
      const api = gated(), page = await openBoard(browser, api), card = () => JSON.parse(api.files['cards/t_one.json']);
      await page.locator('.card', { hasText: 'First' }).dblclick(); await page.locator('#dlgCard').waitFor({ state: 'visible' });
      await page.locator('#cPrio').selectOption('low'); await page.locator('.ui-toast', { hasText: 'Priority: First' }).waitFor();
      await until(() => card().priority === 'low', 'priority saved');
      api.hold = true; await page.locator('#cCol').selectOption('done'); const move = await api.next();
      const writes = api.calls.filter(c => ['PUT', 'PATCH', 'DELETE'].includes(c.method)).length + 1;   // + the held move
      assert.equal(await page.evaluate(() => { const t = [...document.querySelectorAll('.ui-toast')].find(x => /Priority: First/.test(x.textContent)); const b = t && t.querySelector('button'); if (b) b.click(); return !!b; }), true, 'the priority toast still offers Undo');
      await until(async () => (await toasts(page)).some(t => /Undo will run after the current save/.test(t)), 'undo-waits toast');
      move.go('release');
      await until(async () => (await toasts(page)).some(t => /A newer change was saved since; press Ctrl\+Z to undo the latest/.test(t)), 'newer-change toast');
      assert.equal(card().priority, 'low', 'the priority change was not undone'); assert.equal(card().column, 'done', 'nor the newer move');
      assert.equal(api.calls.filter(c => ['PUT', 'PATCH', 'DELETE'].includes(c.method)).length, writes, 'nothing but the move was written');
      await page.close();
    }

    console.log('save queue browser tests passed');
  } finally { await browser.close(); server.close(); }
})().catch(err => { console.error(err); server.close(); process.exitCode = 1; });

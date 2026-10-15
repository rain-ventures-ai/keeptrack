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
    const json = (body, status = 200, headers = {}) => route.fulfill({ status, headers: { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*', 'Access-Control-Expose-Headers': 'ETag', ...headers }, body: JSON.stringify(body) });
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


let base;
(async () => {
  await new Promise(ok => server.listen(0, '127.0.0.1', ok)); base = `http://127.0.0.1:${server.address().port}`;
  const browser = await chromium.launch({ headless: true });
  try {
    const api = new Github(), page = await browser.newPage(); let hold = null, release = null, outside = false;
    await page.addInitScript(() => { for (const [k, v] of Object.entries({ repo: 'acme/board', branch: 'main', path: 'board/tasks.json', token: 'test', me: 'alex', api: 'https://api.test', layout: 'classic' })) localStorage.setItem('kb_' + k, v); sessionStorage.setItem('kb_view', 'board'); });
    await page.route('https://api.test/**', async route => {
      const req = route.request(), u = new URL(req.url()), p = u.pathname.replace('/repos/acme/board', '');
      if (p === '/git/ref/heads/main') {
        if (hold) { const ready = hold; hold = null; ready(); await new Promise(ok => { release = ok; }); }
        if (req.headers()['if-none-match'] === '"' + api.head + '"') { api.calls.push({ method: 'GET', path: p, conditional: true }); return route.fulfill({ status: 304 }); }
      }
      if (outside && p.startsWith('/git/trees/root-')) { api.calls.push({ method: 'GET', path: p }); return route.fulfill({ json: { tree: [{ path: 'board', type: 'tree', sha: 'board-2' }] } }); }
      return api.route(route);
    });
    const synced = () => page.waitForFunction(() => /^Synced/.test(document.querySelector('#status').textContent));
    const data = () => api.calls.filter(x => /^\/(git|contents\/board)/.test(x.path) && !x.path.includes('KIT_VERSION'));   // board data only: the kit version check is not a board read
    await page.goto(base + '/board/index.html'); await synced();
    // Wait for cache transactions as well as the visible render before leaving.
    await page.evaluate(() => new Promise(ok => { const r = indexedDB.open('keeptrack', 1); r.onsuccess = () => { const t = r.result.transaction('kv', 'readonly'); t.objectStore('kv').getAll(); t.oncomplete = ok; }; }));
    const changed = JSON.parse(api.files['cards/t_one.json']); changed.title = 'Fresh title'; api.files['cards/t_one.json'] = text(changed); api.head = 'head-' + ++api.n;
    let reached; const held = new Promise(ok => { reached = ok; }); hold = reached; api.calls = [];
    await page.goto(base + '/board/index.html#1'); await held; await page.locator('#dlgCard[open]').waitFor(); assert.equal(await page.locator('#cTitle').inputValue(), 'First');
    await page.evaluate(() => { window.drawerOpens = 0; new MutationObserver(ms => { window.drawerOpens += ms.filter(m => m.attributeName === 'open').length; }).observe(document.querySelector('#dlgCard'), { attributes: true }); });
    await page.locator('#cTitle').fill('Unsafe edit'); await page.locator('#cTitle').blur(); assert.match(await page.locator('#dSaved').textContent(), /Syncing/);
    assert.equal(api.calls.filter(x => ['PUT', 'PATCH', 'POST', 'DELETE'].includes(x.method)).length, 0);
    // Discard the rejected local draft so the live title can be shown.
    await page.locator('#cTitle').fill('First'); await page.locator('#cTitle').blur();
    release(); await synced(); assert.equal(await page.locator('#cTitle').inputValue(), 'Fresh title'); assert.equal(await page.evaluate(() => window.drawerOpens), 0, 'drawer refreshes without reopening');
    api.calls = []; await page.reload(); await synced(); assert.equal(data().length, 1, JSON.stringify(data())); assert.equal(data()[0].conditional, true);
    // A new commit that changes no board file re-lists the board but reads no files: they are cached by SHA.
    api.head = 'other-commit'; api.n++; api.calls = []; await page.reload(); await synced(); assert(data().some(x => x.path.includes('recursive'))); assert(!data().some(x => x.path.startsWith('/git/blobs/')), JSON.stringify(data()));
    const next = JSON.parse(api.files['cards/t_one.json']); next.title = 'Real change'; api.files['cards/t_one.json'] = text(next); api.head = 'real-change'; api.n++; api.calls = [];
    await page.reload(); await synced(); assert.equal(await page.locator('#cTitle').inputValue(), 'Real change'); assert(data().some(x => x.path.startsWith('/git/blobs/')));
    await page.close(); console.log('fast start browser tests passed');
  } finally { await browser.close(); server.close(); }
})().catch(err => { console.error(err); server.close(); process.exitCode = 1; });

'use strict';
// The bell in the header counts cards with news for you since you last opened them. Changes logged by your own agents
// (<agent>@<you>) are your work, not news; their comments count only when they @mention you. Run: node unread-bell.test.js

const assert = require('node:assert/strict');
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { chromium } = require('playwright');

const ROOT = path.resolve(__dirname, '../..');
const mime = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json', '.svg': 'image/svg+xml' };
const server = http.createServer((req, res) => {
  const rel = decodeURIComponent(new URL(req.url, 'http://local').pathname).replace(/^\/+/, '') || 'board/index.html';
  const file = path.resolve(ROOT, rel); if (!file.startsWith(ROOT + path.sep)) { res.writeHead(403).end(); return; }
  fs.readFile(file, (err, data) => { if (err) res.writeHead(404).end(); else { res.setHeader('Content-Type', mime[path.extname(file)] || 'application/octet-stream'); res.end(data); } });
});

const text = x => JSON.stringify(x, null, 2) + '\n';
const root = { version: 4, layout: 'split', settings: { title: 'Bell test' }, columns: [{ id: 'todo', name: 'To do' }, { id: 'done', name: 'Done' }], people: [{ github: 'alex', name: 'Alex' }, { github: 'sam', name: 'Sam' }], agents: [], clients: ['Acme'], labels: [{ name: 'urgent', color: '#dce1e7' }], client_info: {}, archive: { files: {} } };
const card = (id, num, title, extra) => ({ id, num, title, column: 'todo', client: '', priority: 'medium', due: '', labels: [], assignees: [], details: '', links: [], contacts: [], todos: [], comments: [], history: [], claim: null, created: '2026-10-01T08:00:00.000Z', updated: '2026-10-01T08:00:00.000Z', rank: 'a' + num, ...extra });

// A small GitHub: contents API for reads and single-file writes, git data API for multi-file commits (same shape as split-storage.test.js).
class Github {
  constructor() {
    const h = (at, by, text) => ({ at, by, text }), c = (id, at, by, text) => ({ id, at, by, text }), T = '2026-10-10T09:00:00.000Z';
    const cards = [
      card('t_a', 1, 'Own agent changed it', { history: [h(T, 'claude@alex', 'claimed')] }),
      card('t_b', 2, 'Own agent reported', { comments: [c('c_b', T, 'codex@Alex', 'Done: PR opened.')] }),
      card('t_c', 3, 'Own agent asks me', { comments: [c('c_c', T, 'claude@alex', '@alex let it finish, or stop it?')] }),
      card('t_d', 4, 'Sam changed it', { history: [h(T, 'sam', 'moved to Done')] }),
      card('t_e', 5, 'Sam agent changed it', { history: [h(T, 'claude@sam', 'heartbeat')] }),
      card('t_f', 6, 'I changed it', { history: [h(T, 'alex', 'edited')], comments: [c('c_f', T, 'alex', 'note')] }),
      card('t_g', 7, 'Look-alike agent', { history: [h(T, 'claude@alexander', 'claimed')] })];
    this.files = { 'tasks.json': text({ ...root, next_num: 8 }) }; cards.forEach(x => { this.files[`cards/${x.id}.json`] = text(x); });
    this.head = 'head-1'; this.n = 1; this.blobs = {}; this.pending = null;
  }
  sha(p) { return crypto.createHash('sha1').update(this.files[p] || '').digest('hex'); }
  async route(route) {
    const req = route.request(), u = new URL(req.url()), method = req.method(), p = u.pathname.replace('/repos/acme/board', '');
    const json = (body, status = 200, headers = {}) => route.fulfill({ status, headers: { 'Content-Type': 'application/json', ...headers }, body: JSON.stringify(body) });
    if (p === '/user' && method === 'GET') return json({ login: 'alex' });
    if (p.startsWith('/user/repos')) return json([]);
    if (p === '' && method === 'GET') return json({ full_name: 'acme/board', private: true, permissions: { push: true }, default_branch: 'main' });
    if (p.startsWith('/contents/README.md')) return json({ message: 'Not Found' }, 404);
    if (p.startsWith('/contents/board/tasks.json') && method === 'GET') return json({ sha: this.sha('tasks.json'), size: Buffer.byteLength(this.files['tasks.json']), encoding: 'base64', content: Buffer.from(this.files['tasks.json']).toString('base64') });
    if (p.startsWith('/contents/board/') && method === 'GET') { const rel = p.slice('/contents/board/'.length); return this.files[rel] ? json({ sha: this.sha(rel), encoding: 'base64', content: Buffer.from(this.files[rel]).toString('base64') }) : json({ message: 'Not Found' }, 404); }
    if (p.startsWith('/contents/board/') && method === 'PUT') { const rel = p.slice('/contents/board/'.length), b = req.postDataJSON(); this.files[rel] = Buffer.from(b.content, 'base64').toString(); this.head = 'head-' + ++this.n; return json({ content: { sha: this.sha(rel) }, commit: { sha: this.head, tree: { sha: 'root-' + this.n } } }); }
    if (p.startsWith('/contents/board/') && method === 'DELETE') { delete this.files[p.slice('/contents/board/'.length)]; this.head = 'head-' + ++this.n; return json({ commit: { sha: this.head, tree: { sha: 'root-' + this.n } } }); }
    if (p === '/git/ref/heads/main' && method === 'GET') return json({ object: { sha: this.head } });
    if (p.startsWith('/git/commits/') && method === 'GET') return json({ tree: { sha: 'root-' + this.n } });
    if (p.startsWith('/git/trees/root-') && method === 'GET') return json({ tree: [{ path: 'board', type: 'tree', sha: 'board-' + this.n }] });
    if (p.startsWith('/git/trees/board-') && method === 'GET') return json({ truncated: false, tree: Object.entries(this.files).map(([f, c]) => ({ path: f, type: 'blob', sha: this.sha(f), size: Buffer.byteLength(c) })) });
    if (p.startsWith('/git/blobs/') && method === 'GET') { const sha = p.split('/').pop(), rel = Object.keys(this.files).find(x => this.sha(x) === sha); return json({ encoding: 'base64', content: Buffer.from(this.files[rel]).toString('base64') }); }
    if (p === '/git/blobs' && method === 'POST') { const sha = 'new-blob-' + ++this.n; this.blobs[sha] = req.postDataJSON().content; return json({ sha }); }
    if (p === '/git/trees' && method === 'POST') { this.pending = req.postDataJSON().tree; return json({ sha: 'new-tree-' + ++this.n }); }
    if (p === '/git/commits' && method === 'POST') return json({ sha: 'new-commit-' + ++this.n });
    if (p === '/git/refs/heads/main' && method === 'PATCH') { for (const e of this.pending || []) { const rel = e.path.replace(/^board\//, ''); if (e.sha === null) delete this.files[rel]; else this.files[rel] = this.blobs[e.sha]; } this.head = req.postDataJSON().sha; return json({ object: { sha: this.head } }); }
    return json({ message: 'not mocked: ' + method + ' ' + p }, 404);
  }
}

(async () => {
  await new Promise(ok => server.listen(0, '127.0.0.1', ok)); const base = `http://127.0.0.1:${server.address().port}`;
  const browser = await chromium.launch({ headless: true });
  try {
    const api = new Github(), page = await browser.newPage({ viewport: { width: 1280, height: 900 } }), errors = []; page.on('pageerror', e => errors.push(e.message));
    const seen = {}; ['t_a', 't_b', 't_c', 't_d', 't_e', 't_f', 't_g'].forEach(id => { seen[id] = { c: '2026-10-01T00:00:00.000Z', h: '2026-10-01T00:00:00.000Z' }; });
    await page.addInitScript(s => { localStorage.setItem('kb_repo', 'acme/board'); localStorage.setItem('kb_branch', 'main'); localStorage.setItem('kb_path', 'board/tasks.json'); localStorage.setItem('kb_token', 'test'); localStorage.setItem('kb_me', 'alex'); localStorage.setItem('kb_api', 'https://api.test'); localStorage.setItem('kb_tour', 'done'); localStorage.setItem('kb_seen:acme/board:board/tasks.json', s); sessionStorage.setItem('kb_view', 'board'); }, JSON.stringify(seen));
    await page.route('https://api.test/**', r => api.route(r)); await page.goto(base + '/board/index.html');
    await page.waitForFunction(() => document.getElementById('board').childElementCount > 0);
    await page.waitForFunction(() => document.getElementById('unreadBadge').textContent === '4', null, { timeout: 5000 }).catch(() => {});
    assert.equal(await page.locator('#unreadBadge').textContent(), '4', 'own agent question, Sam, Sam agent, look-alike');
    assert.match(await page.locator('#btnUnread').getAttribute('title'), /^4 cards with new comments or changes from others/);
    await page.locator('#btnUnread').click();
    await page.waitForFunction(() => !document.getElementById('board').textContent.includes('Own agent changed it'));
    const shown = await page.locator('#board').textContent();
    for (const t of ['Own agent asks me', 'Sam changed it', 'Sam agent changed it', 'Look-alike agent']) assert.ok(shown.includes(t), t + ' is shown');
    for (const t of ['Own agent reported', 'I changed it']) assert.ok(!shown.includes(t), t + ' is hidden');
    assert.deepEqual(errors, []);
    console.log('unread bell: ok');
  } finally { await browser.close(); server.close(); }
})().catch(e => { console.error(e); process.exit(1); });

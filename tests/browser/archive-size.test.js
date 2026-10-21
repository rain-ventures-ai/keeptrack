'use strict';
// Archive year files have their own size limit (kit v86): past 900 KB the items bound for that year stay on the board,
// past 700 KB the archive is written and the toast warns. Run: node archive-size.test.js

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
const root = { version: 4, layout: 'split', settings: { title: 'Drawer test' }, columns: [{ id: 'todo', name: 'To do' }, { id: 'done', name: 'Done' }], people: [{ github: 'alex', name: 'Alex' }, { github: 'sam', name: 'Sam' }], agents: [], clients: ['Acme', 'Bluebell Events', 'Northwind Traders'], labels: [{ name: 'pale', color: '#dce1e7' }, { name: 'dark', color: '#334155' }], client_info: {}, next_num: 4, archive: { files: {} } };
const card = (id, num, title, extra) => ({ id, num, title, column: 'todo', client: '', priority: 'medium', due: '', labels: [], assignees: [], details: '', links: [], contacts: [], todos: [], comments: [], history: [], claim: null, created: '2026-10-01T08:00:00.000Z', updated: '2026-10-01T08:00:00.000Z', rank: 'a' + num, ...extra });

// A small GitHub: contents API for reads and single-file writes, git data API for multi-file commits (same shape as split-storage.test.js).
class Github {
  constructor() {
    this.files = { 'tasks.json': text(root), 'cards/t_one.json': text(card('t_one', 1, 'Open work')), 'cards/t_two.json': text(card('t_two', 2, 'Finished work', { column: 'done', history: [{ at: '2026-10-02T08:00:00.000Z', by: 'alex', text: 'moved to Done' }] })), 'cards/t_three.json': text(card('t_three', 3, 'Agent still on it', { column: 'done', claim: { agent: 'claude', on_behalf_of: 'alex', session: 'abcdef12', status: 'working', since: '2026-10-15T08:00:00.000Z', heartbeat: new Date().toISOString() } })) };
    this.files['people/p_craig.json'] = text({ id: 'p_craig', name: 'Craig Example', company: 'Acme', role: 'Director', emails: [{ label: 'Work', value: 'craig@example.com' }], phones: [], links: [], comments: [], history: [] });
    this.files['people/p_chris.json'] = text({ id: 'p_chris', name: 'Chris Example', company: 'Other', emails: [{ label: 'Work', value: 'chris@example.com' }], phones: [], links: [], comments: [], history: [] });
    this.head = 'head-1'; this.n = 1; this.blobs = {}; this.pending = null; this.writes = 0;
  }
  sha(p) { return crypto.createHash('sha1').update(this.files[p] || '').digest('hex'); }
  async route(route) {
    const req = route.request(), u = new URL(req.url()), method = req.method(), p = u.pathname.replace('/repos/acme/board', '');
    const json = (body, status = 200, headers = {}) => route.fulfill({ status, headers: { 'Content-Type': 'application/json', ...headers }, body: JSON.stringify(body) });
    if (method !== 'GET') this.writes++;
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
  card(id = 't_one') { return this.files[`cards/${id}.json`] ? JSON.parse(this.files[`cards/${id}.json`]) : null; }
}

let base;
const shot = async (page, name) => { if (SHOTS) { fs.mkdirSync(SHOTS, { recursive: true }); await page.screenshot({ path: path.join(SHOTS, name + '.png') }); } };
const init = view => { localStorage.setItem('kb_repo', 'acme/board'); localStorage.setItem('kb_branch', 'main'); localStorage.setItem('kb_path', 'board/tasks.json'); localStorage.setItem('kb_token', 'test'); localStorage.setItem('kb_me', 'alex'); localStorage.setItem('kb_api', 'https://api.test'); localStorage.setItem('kb_layout', 'classic'); localStorage.setItem('kb_tour_seen', '1'); localStorage.setItem('kb_tab', 'done'); sessionStorage.setItem('kb_view', view); };
const opacity = loc => loc.evaluate(e => Number(getComputedStyle(e).opacity));

(async () => {
  await new Promise(ok => server.listen(0, '127.0.0.1', ok)); base = `http://127.0.0.1:${server.address().port}`;
  const browser = await chromium.launch({ headless: true });
  try {
    for (const [kb, held] of [[905, true], [710, false]]) {
      const api = new Github(), card2 = api.card('t_two'), year = String(card2.updated || card2.created).slice(0, 4);
      api.files[`archive/${year}.json`] = text({ version: 3, archive: true, year, tasks: [], contacts: [], history: {}, pad: 'x'.repeat(kb * 1024) });
      api.files['tasks.json'] = text({ ...JSON.parse(api.files['tasks.json']), archive: { files: { [year]: { tasks: 0, contacts: 0 } } } });
      const page = await browser.newPage({ viewport: { width: 1280, height: 860 } }), errors = []; page.on('pageerror', e => errors.push(e.message));
      await page.addInitScript(init, 'board'); await page.route('https://api.test/**', r => api.route(r)); await page.goto(base + '/board/index.html'); await page.waitForSelector('.card');
      const snapshot = JSON.stringify(api.files), writes = api.writes;
      const done = page.locator('.col[data-col="done"] .card', { hasText: 'Finished work' }); await done.hover(); await done.locator('.quickarch').click();
      if (held) {
        await page.locator('.ui-toast__text', { hasText: 'Held back 1 item' }).waitFor();
        const t = await page.locator('.ui-toast__text', { hasText: 'Held back' }).first().textContent();
        assert.match(t, new RegExp(`archive/${year}\\.json`)); assert.match(t, /board owner/); assert.match(t, /stay on the board/);
        assert.equal(JSON.stringify(api.files), snapshot, 'not one file changed'); assert.equal(api.writes, writes, 'nothing was written to GitHub');
        assert.ok(api.card('t_two'), 'the card is still on the board');
      } else {
        await page.locator('.ui-toast__text', { hasText: 'doctor fails above 900 KB' }).waitFor();
        assert.equal(api.card('t_two'), null, 'the card left the board');
        assert.deepEqual(JSON.parse(api.files[`archive/${year}.json`]).tasks.map(t => t.id), ['t_two']);
        assert.ok(Buffer.byteLength(api.files[`archive/${year}.json`]) > 710 * 1024, 'the year file grew');
      }
      assert.deepEqual(errors, []); await page.close();
    }
    console.log('archive-size browser tests passed');
  } finally { await browser.close(); server.close(); }
})().catch(e => { console.error(e); process.exit(1); });

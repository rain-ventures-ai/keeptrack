'use strict';
// The @Mentions view: comments that mention you (@your-login), newest first, with the card, its description and the comment.
// Your own comments and look-alikes (@alexander, alex@acme.test) are left out; a row opens the card and scrolls to that
// comment; Today has an @Mentions tile. Run: node mentions.test.js

const assert = require('node:assert/strict');
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { chromium } = require('playwright');

const ROOT = path.resolve(__dirname, '../..');
const SHOTS = process.env.SHOTS || '';   // a folder: also save screenshots
const shot = async (page, name) => { if (SHOTS) { fs.mkdirSync(SHOTS, { recursive: true }); await page.screenshot({ path: path.join(SHOTS, name + '.png') }); } };
const mime = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json', '.svg': 'image/svg+xml' };
const server = http.createServer((req, res) => {
  const rel = decodeURIComponent(new URL(req.url, 'http://local').pathname).replace(/^\/+/, '') || 'board/index.html';
  const file = path.resolve(ROOT, rel); if (!file.startsWith(ROOT + path.sep)) { res.writeHead(403).end(); return; }
  fs.readFile(file, (err, data) => { if (err) res.writeHead(404).end(); else { res.setHeader('Content-Type', mime[path.extname(file)] || 'application/octet-stream'); res.end(data); } });
});

const text = x => JSON.stringify(x, null, 2) + '\n';
const root = { version: 4, layout: 'split', settings: { title: 'Mentions test' }, columns: [{ id: 'todo', name: 'To do' }, { id: 'done', name: 'Done' }], people: [{ github: 'alex', name: 'Alex' }, { github: 'sam', name: 'Sam' }], agents: [], clients: ['Acme'], labels: [{ name: 'urgent', color: '#dce1e7' }], client_info: {}, next_num: 4, archive: { files: {} } };
const card = (id, num, title, extra) => ({ id, num, title, column: 'todo', client: '', priority: 'medium', due: '', labels: [], assignees: [], details: '', links: [], contacts: [], todos: [], comments: [], history: [], claim: null, created: '2026-10-01T08:00:00.000Z', updated: '2026-10-01T08:00:00.000Z', rank: 'a' + num, ...extra });

// A small GitHub: contents API for reads and single-file writes, git data API for multi-file commits (same shape as split-storage.test.js).
class Github {
  constructor() {
    const c = (id, at, by, text) => ({ id, at, by, text });
    const filler = Array.from({ length: 12 }, (_, i) => c('c_f' + i, `2026-10-0${1 + (i % 5)}T09:${String(10 + i).padStart(2, '0')}:00.000Z`, 'sam', 'Progress note ' + (i + 1) + '. '.repeat(1) + 'Some longer text so the stream needs to scroll. '.repeat(4)));
    this.files = { 'tasks.json': text({ ...root, next_num: 5 }),
      'cards/t_one.json': text(card('t_one', 1, 'Write the case study', { details: 'Two pages for the Acme case study, with one number from the client.', comments: [c('c_ask', '2026-10-02T10:00:00.000Z', 'sam', '@alex can you check the second paragraph?'), ...filler, c('c_self', '2026-10-06T10:00:00.000Z', 'alex', 'Note to self @alex: chase this')] })),
      'cards/t_two.json': text(card('t_two', 2, 'Book the workshop room', { comments: [c('c_bot', '2026-10-07T10:00:00.000Z', 'claude', 'Done. @alex please confirm the date.')] })),
      'cards/t_three.json': text(card('t_three', 3, 'Renew the domain', { comments: [c('c_not', '2026-10-08T10:00:00.000Z', 'sam', '@alexander has the login. email alex@acme.test')] })),
      'cards/t_four.json': text(card('t_four', 4, 'Old finished work', { column: 'done', comments: [c('c_done', '2026-10-01T10:00:00.000Z', 'sam', '@alex thanks')] })) };
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

async function open(browser, base, { view = 'mentions', me = 'alex', viewport = { width: 1280, height: 900 }, theme = '' } = {}) {
  const api = new Github(), page = await browser.newPage({ viewport }), errors = []; page.on('pageerror', e => errors.push(e.message));
  await page.addInitScript(([v, m, th]) => { localStorage.setItem('kb_repo', 'acme/board'); localStorage.setItem('kb_branch', 'main'); localStorage.setItem('kb_path', 'board/tasks.json'); localStorage.setItem('kb_token', 'test'); localStorage.setItem('kb_me', m); localStorage.setItem('kb_api', 'https://api.test'); localStorage.setItem('kb_tour', 'done'); if (th) localStorage.setItem('kb_theme', th); sessionStorage.setItem('kb_view', v); }, [view, me, theme]);
  await page.route('https://api.test/**', r => api.route(r)); await page.goto(base + '/board/index.html');
  await page.waitForFunction(v => document.body.dataset.view === v && document.getElementById('board').childElementCount > 0, view);
  page.errors = errors; return page;
}

(async () => {
  await new Promise(ok => server.listen(0, '127.0.0.1', ok)); const base = `http://127.0.0.1:${server.address().port}`;
  const browser = await chromium.launch({ headless: true });
  try {
    // 1. The tab sits with the task views; it lists only comments that mention me, newest first.
    {
      const page = await open(browser, base); await page.waitForSelector('.mnrow');
      assert.equal(await page.locator('#viewSw [data-view="mentions"]').getAttribute('aria-selected'), 'true');
      const rows = page.locator('.mnrow');
      assert.deepEqual(await rows.evaluateAll(r => r.map(x => x.dataset.cid)), ['c_bot', 'c_ask', 'c_done'], 'newest first; my own comment and look-alikes are left out');
      const first = await rows.nth(1).textContent();
      assert.match(first, /#1/); assert.match(first, /Write the case study/); assert.match(first, /one number from the client/, 'the description'); assert.match(first, /second paragraph/, 'the comment');
      // Hide done also hides mentions on done cards
      if (!(await page.locator('#fHideDone').isChecked())) { await page.evaluate(() => { const x = document.getElementById('fHideDone'); x.checked = true; x.dispatchEvent(new Event('change', { bubbles: true })); }); }
      await page.waitForFunction(() => document.querySelectorAll('.mnrow').length === 2);
      await shot(page, 'mentions-desktop');
      // 2. A click opens that card and scrolls to the comment, briefly highlighted.
      await rows.nth(1).click(); await page.locator('#dlgCard').waitFor({ state: 'visible' });
      await page.waitForFunction(() => { const r = document.querySelector('#cmStream .cmcard[data-cid="c_ask"]'); return r && r.classList.contains('cmflash'); });
      await page.waitForTimeout(400);
      const inView = await page.evaluate(() => { const r = document.querySelector('#cmStream .cmcard[data-cid="c_ask"]').getBoundingClientRect(); return r.top >= 0 && r.bottom <= window.innerHeight; });
      assert.ok(inView, 'the mentioned comment is scrolled into view');
      assert.match(page.url(), /#1$/);
      await shot(page, 'mentions-open');
      assert.deepEqual(page.errors, []); await page.close();
    }
    // 3. Someone else has no mentions here: an empty state, no rows.
    {
      const page = await open(browser, base, { me: 'sam' });
      assert.equal(await page.locator('.mnrow').count(), 0); assert.match(await page.locator('#board').textContent(), /No comments mention you/);
      assert.deepEqual(page.errors, []); await page.close();
    }
    // 4. Without a GitHub username the view says how to set it, and Today shows no tile.
    {
      const page = await open(browser, base, { me: '' });
      assert.match(await page.locator('#board').textContent(), /Set your GitHub username/);
      assert.deepEqual(page.errors, []); await page.close();
    }
    // 5. Today has an @Mentions tile that opens the view; a phone renders it without sideways scroll (dark theme too).
    {
      const page = await open(browser, base, { view: 'today', viewport: { width: 390, height: 844 }, theme: 'dark' });
      const tile = page.locator('.tgo[data-go="mentions"]'); await tile.waitFor();
      await tile.click(); await page.waitForFunction(() => document.body.dataset.view === 'mentions'); await page.waitForSelector('.mnrow');
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1), false, 'no sideways scroll on a phone');
      await shot(page, 'mentions-phone');
      assert.deepEqual(page.errors, []); await page.close();
    }
    console.log('mentions: all checks passed');
  } finally { await browser.close(); server.close(); }
})().catch(e => { console.error(e); process.exit(1); });

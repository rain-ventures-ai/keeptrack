'use strict';
// Card numbers as links (kit v56): a plain #2 and a Markdown [#2](card link) in a comment or description both show as
// "#2" and open card #2 here; their href is the card's real link (copy, long-press, new tab). A Markdown link to another
// page shows its label and opens in a new tab. Run: node card-links.test.js

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
    const _filler = Array.from({ length: 12 }, (_, i) => c('c_f' + i, `2026-10-0${1 + (i % 5)}T09:${String(10 + i).padStart(2, '0')}:00.000Z`, 'sam', 'Progress note ' + (i + 1) + '. '.repeat(1) + 'Some longer text so the stream needs to scroll. '.repeat(4)));
    this.files = { 'tasks.json': text({ ...root, next_num: 3 }),
      'cards/t_one.json': text(card('t_one', 1, 'Write the case study', { details: 'Runs after [#2](https://rain-ventures-ai.github.io/keeptrack/board/?repo=acme%2Fboard&branch=main&path=board%2Ftasks.json#2).', comments: [c('c_a', '2026-10-02T10:00:00.000Z', 'sam', 'See #2 and [#2](https://rain-ventures-ai.github.io/keeptrack/board/?repo=acme%2Fboard&branch=main&path=board%2Ftasks.json#2) and [the brief](https://example.test/brief) and [#2](https://rain-ventures-ai.github.io/keeptrack/board/?repo=other%2Fboard&branch=main&path=board%2Ftasks.json#2).')] })),
      'cards/t_two.json': text(card('t_two', 2, 'Book the workshop room')) };
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
    const page = await open(browser, base, { view: 'board' });
    await page.waitForSelector('.card');
    await page.evaluate(() => { location.hash = '#1'; }); await page.locator('#dlgCard[open]').waitFor();
    await page.waitForSelector('#cmStream .cmcard[data-cid="c_a"]');
    const links = await page.locator('#cmStream .cmcard[data-cid="c_a"] .cmbody a').evaluateAll(a => a.map(x => ({ text: x.textContent, href: x.href, cls: x.className, target: x.target })));
    const mine = 'https://rain-ventures-ai.github.io/keeptrack/board/?repo=acme%2Fboard&branch=main&path=board%2Ftasks.json#2';
    assert.equal(links.length, 4, JSON.stringify(links));
    assert.equal(links[0].text, '#2'); assert.equal(links[0].cls, 'mref'); assert.match(links[0].href, /[?&]repo=acme%2Fboard\b.*#2$/, 'a plain #2 has the real card link');
    assert.deepEqual(links[1], { text: '#2', href: mine, cls: 'mref', target: '' }, 'a Markdown card link shows as #2');
    assert.deepEqual([links[2].text, links[2].target], ['the brief', '_blank'], 'another Markdown link shows its label');
    assert.deepEqual([links[3].text, links[3].cls, links[3].target], ['#2', '', '_blank'], 'a card on another board opens in a new tab');
    assert.equal(await page.locator('#cDescView a.mref').textContent(), '#2', 'the description too');
    await page.locator('#cmStream .cmcard[data-cid="c_a"] .cmbody a').nth(1).click();
    await page.waitForFunction(() => location.hash === '#2' && document.querySelector('#dNum .ui-pill__text').textContent === '#2');
    assert.deepEqual(page.errors, []); await page.close();
    console.log('card-links: all checks passed');
  } finally { await browser.close(); server.close(); }
})().catch(e => { console.error(e); process.exit(1); });

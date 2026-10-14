'use strict';
// Follow-up cards (kit v54) on a writable board with a faked GitHub API: a to-do's "Move to a new card" adds a Backlog card
// with the card's client, labels and priority, links both cards (relation, links, comments), rewords and ticks the to-do,
// and both cards show a follow-up chip and a Follow-up / Split from row in Related cards. Run: node follow-up.test.js

const assert = require('node:assert/strict');
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { chromium } = require('playwright');

const ROOT = path.resolve(__dirname, '../..');
const SHOTS = process.env.SHOTS || '';   // a folder: also save screenshots of the card and the drawer
const shot = async (page, name) => { if (SHOTS) { fs.mkdirSync(SHOTS, { recursive: true }); await page.screenshot({ path: path.join(SHOTS, name + '.png') }); } };
const mime = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json', '.svg': 'image/svg+xml' };
const server = http.createServer((req, res) => {
  const rel = decodeURIComponent(new URL(req.url, 'http://local').pathname).replace(/^\/+/, '') || 'board/index.html';
  const file = path.resolve(ROOT, rel); if (!file.startsWith(ROOT + path.sep)) { res.writeHead(403).end(); return; }
  fs.readFile(file, (err, data) => { if (err) res.writeHead(404).end(); else { res.setHeader('Content-Type', mime[path.extname(file)] || 'application/octet-stream'); res.end(data); } });
});

const text = x => JSON.stringify(x, null, 2) + '\n';
const root = { version: 4, layout: 'split', settings: { title: 'Follow-up test' }, columns: [{ id: 'backlog', name: 'Backlog' }, { id: 'todo', name: 'To do' }, { id: 'done', name: 'Done' }], people: [{ github: 'alex', name: 'Alex' }, { github: 'sam', name: 'Sam' }], agents: [], clients: ['Acme'], labels: [{ name: 'urgent', color: '#dce1e7' }], client_info: {}, next_num: 4, archive: { files: {} } };
const card = (id, num, title, extra) => ({ id, num, title, column: 'todo', client: '', priority: 'medium', due: '', labels: [], assignees: [], details: '', links: [], contacts: [], todos: [], comments: [], history: [], claim: null, created: '2026-10-01T08:00:00.000Z', updated: '2026-10-01T08:00:00.000Z', rank: 'a' + num, ...extra });

// A small GitHub: contents API for reads and single-file writes, git data API for multi-file commits (same shape as split-storage.test.js).
class Github {
  constructor() {
    this.files = { 'tasks.json': text(root),
      'cards/t_one.json': text(card('t_one', 1, 'Ship the widget', { client: 'Acme', labels: ['urgent'], priority: 'high', assignees: ['alex'], todos: [{ id: 'd_a', text: 'Build it', done: true }, { id: 'd_b', text: 'Owner turns it on', done: false }] })),
      'cards/t_two.json': text(card('t_two', 2, 'Write notes')),
      'cards/t_three.json': text(card('t_three', 3, 'Call Casey')) };
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

(async () => {
  await new Promise(ok => server.listen(0, '127.0.0.1', ok)); const base = `http://127.0.0.1:${server.address().port}`;
  const browser = await chromium.launch({ headless: true });
  try {
    const api = new Github();
    const page = await browser.newPage({ viewport: { width: 1280, height: 900 } }); const errors = []; page.on('pageerror', e => errors.push(e.message));
    await page.addInitScript(() => { localStorage.setItem('kb_repo', 'acme/board'); localStorage.setItem('kb_branch', 'main'); localStorage.setItem('kb_path', 'board/tasks.json'); localStorage.setItem('kb_token', 'test'); localStorage.setItem('kb_me', 'alex'); localStorage.setItem('kb_api', 'https://api.test'); localStorage.setItem('kb_layout', 'classic'); localStorage.setItem('kb_tour_seen', '1'); sessionStorage.setItem('kb_view', 'board'); });
    await page.route('https://api.test/**', r => api.route(r)); await page.goto(base + '/board/index.html'); await page.waitForSelector('.card');
    assert.equal(await page.locator('.card .fupchip').count(), 0, 'no follow-up chip before a move');

    // the drawer: a done to-do has no move action, an open one has
    await page.locator('.card', { hasText: 'Ship the widget' }).locator('.t').click();
    await page.waitForSelector('#cTodos .dtodo');
    assert.equal(await page.locator('#cTodos button[data-act=move-todo]').count(), 1, 'only the open to-do can move');
    await page.locator('#cTodos button[data-act=move-todo]').click();
    const dlg = page.locator('dialog.ui-sheet--alert[open]'); await dlg.waitFor();
    assert.equal(await dlg.locator('input').inputValue(), 'Owner turns it on', 'the title starts as the to-do text');
    await dlg.locator('input').fill('Turn on the widget (waits on the owner)');
    await shot(page, 'follow-up-dialog');
    await dlg.locator('button', { hasText: 'Move' }).click();

    let fresh = null; for (let i = 0; i < 100 && !fresh; i++) { await page.waitForTimeout(100); fresh = Object.keys(api.files).map(f => f.startsWith('cards/') ? JSON.parse(api.files[f]) : null).find(c => c && !['t_one', 't_two', 't_three'].includes(c.id)); }
    assert(fresh, 'the follow-up card was saved');
    let one = api.card('t_one'); for (let i = 0; i < 50 && !(one.todos[1].done); i++) { await page.waitForTimeout(100); one = api.card('t_one'); }
    assert.equal(fresh.num, 4); assert.equal(fresh.column, 'backlog'); assert.equal(fresh.title, 'Turn on the widget (waits on the owner)');
    assert.deepEqual([fresh.client, fresh.labels, fresh.priority, fresh.assignees], ['Acme', ['urgent'], 'high', ['alex']]);
    assert.deepEqual(fresh.todos.map(d => [d.text, d.done]), [['Owner turns it on', false]]);
    assert.match(fresh.details, /^Split from #1 \(t_one\)/);
    assert.equal(one.todos[1].text, `Moved to #4 (${fresh.id}): Owner turns it on`); assert.equal(one.todos[1].done, true);
    const r1 = one.related.find(r => r.id === fresh.id), r2 = fresh.related.find(r => r.id === 't_one');
    assert.deepEqual([r1.kind, r1.status, r1.from], ['related', 'confirmed', 't_one']); assert.deepEqual([r2.kind, r2.status, r2.from], ['related', 'confirmed', 't_one']);
    assert(one.links.some(l => l.title === 'Follow-up #4' && /repo=acme%2Fboard/.test(l.url) && l.url.endsWith('#4')), 'link to the follow-up');
    assert(fresh.links.some(l => l.title === 'Split from #1' && l.url.endsWith('#1')), 'link back');
    assert.match(one.comments.at(-1).text, /moved to follow-up card #4/); assert.match(fresh.comments.at(-1).text, /Split from #1/);

    // the drawer shows the follow-up in Related cards, the to-do reads "Moved to #4" and has no move action now
    await page.waitForSelector('#cRelSec:not([hidden]) .drel[data-kind=follow-up]');
    assert.match(await page.locator('#cRelList .drel').first().textContent(), /Follow-up.*#4 Turn on the widget/);
    assert.equal(await page.locator('#cTodos button[data-act=move-todo]').count(), 0);
    await page.locator('#cRelSec').scrollIntoViewIfNeeded(); await shot(page, 'follow-up-drawer');

    // the board: both cards carry the chip
    await page.keyboard.press('Escape'); await page.waitForTimeout(300);
    const chips = await page.locator('.card .fupchip').allTextContents();
    assert.deepEqual(chips.map(s => s.trim()).sort(), ['Follow-up #4', 'From #1']);
    await shot(page, 'follow-up-board');

    // the follow-up's drawer reads "Split from #1"
    await page.locator('.card', { hasText: 'Turn on the widget' }).locator('.t').click();
    await page.waitForSelector('#cRelSec:not([hidden]) .drel[data-kind=follow-up]');
    assert.match(await page.locator('#cRelList .drel').first().textContent(), /Split from.*#1 Ship the widget/);

    assert.deepEqual(errors, []);
    console.log('follow-up: all checks passed');
  } finally { await browser.close(); server.close(); }
})().catch(e => { console.error(e); process.exit(1); });

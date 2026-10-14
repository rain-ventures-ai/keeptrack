'use strict';
// Related cards (kit v52) on a writable board with a faked GitHub API: a possible duplicate shows on the card and in the
// drawer; Link and Not related save both cards; Merge copies the work into the older card and archives the newer one;
// adding a card with a close title marks both cards without stopping the add. Run: node related-cards.test.js

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
const root = { version: 4, layout: 'split', settings: { title: 'Related test' }, columns: [{ id: 'todo', name: 'To do' }, { id: 'done', name: 'Done' }], people: [{ github: 'alex', name: 'Alex' }, { github: 'sam', name: 'Sam' }], agents: [], clients: ['Acme'], labels: [{ name: 'urgent', color: '#dce1e7' }], client_info: {}, next_num: 4, archive: { files: {} } };
const card = (id, num, title, extra) => ({ id, num, title, column: 'todo', client: '', priority: 'medium', due: '', labels: [], assignees: [], details: '', links: [], contacts: [], todos: [], comments: [], history: [], claim: null, created: '2026-10-01T08:00:00.000Z', updated: '2026-10-01T08:00:00.000Z', rank: 'a' + num, ...extra });

// A small GitHub: contents API for reads and single-file writes, git data API for multi-file commits (same shape as split-storage.test.js).
class Github {
  constructor() {
    const rel = (id, kind, status) => [{ id, kind, status, by: 'claude@alex', at: '2026-10-02T08:00:00.000Z', score: 1 }];
    this.files = { 'tasks.json': text(root),
      'cards/t_one.json': text(card('t_one', 1, 'Send Acme the revised plan', { client: 'Acme', details: 'Plan v2.', todos: [{ id: 'd_a', text: 'Draft', done: false }], related: rel('t_two', 'duplicate', 'possible') })),
      'cards/t_two.json': text(card('t_two', 2, 'Send Acme the revised plan', { client: 'Acme', created: '2026-10-02T08:00:00.000Z', details: 'Casey asked twice.', todos: [{ id: 'd_b', text: 'Check figures', done: false }], labels: ['urgent'], related: rel('t_one', 'duplicate', 'possible') })),
      'cards/t_three.json': text(card('t_three', 3, 'Write notes')) };
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
    const status = (id, other) => ((api.card(id).related || []).find(r => r.id === other) || {}).status;

    // the chip on both cards, and the drawer section with its three answers
    assert.equal(await page.locator('.card .relchip').count(), 2, 'both cards show the possible duplicate');
    await shot(page, 'related-board');
    await page.locator('.card', { hasText: 'Send Acme' }).nth(1).locator('.t').click();
    await page.waitForSelector('#cRelSec:not([hidden])');
    const num = await page.locator('#dNum').textContent(); await page.locator('#cRelSec').scrollIntoViewIfNeeded(); await shot(page, 'related-drawer');
    const acts = await page.locator('#cRelList button[data-act]').allTextContents();
    assert.deepEqual(acts, [num.includes('2') ? 'Merge into #1' : 'Merge #2 here', 'Link', 'Not related']);

    // Link: confirmed on both cards
    await page.locator('#cRelList button[data-act=link]').click();
    await page.waitForFunction(() => !document.querySelector('#cRelList button[data-act=link]'));
    for (let i = 0; i < 50 && status('t_one', 't_two') !== 'confirmed'; i++) await page.waitForTimeout(100);
    assert.equal(status('t_one', 't_two'), 'confirmed'); assert.equal(status('t_two', 't_one'), 'confirmed');
    assert.equal(await page.locator('.card .relchip').count(), 0, 'a confirmed link is not a question any more');

    // Merge: the newer card goes into the older one and is archived; nothing is deleted
    await page.locator('#cRelList button[data-act=merge]').click();
    await page.locator('dialog.ui-sheet--alert[open] button', { hasText: 'Merge' }).click();
    for (let i = 0; i < 100 && api.card('t_two'); i++) await page.waitForTimeout(100);
    assert.equal(api.card('t_two'), null, 't_two left the live board');
    const arch = Object.keys(api.files).find(f => f.startsWith('archive/'));
    assert(arch && JSON.parse(api.files[arch]).tasks.some(t => t.id === 't_two'), 't_two is in the archive');
    const kept = api.card('t_one');
    assert.match(kept.details, /Merged from #2/); assert.match(kept.details, /Casey asked twice/);
    assert.deepEqual(kept.todos.map(d => d.text), ['Draft', 'Check figures']);
    assert.deepEqual(kept.labels, ['urgent']);
    assert.equal(status('t_one', 't_two'), 'merged');

    // adding a close card from the board marks both cards and does not stop the add
    await page.keyboard.press('Escape'); await page.waitForTimeout(300);
    const add = page.locator('input[placeholder="Add a task…"]').first(); await add.fill('Send Acme the revised plan'); await add.press('Enter');
    let added = null; for (let i = 0; i < 100 && !added; i++) { await page.waitForTimeout(100); added = Object.keys(api.files).map(f => f.startsWith('cards/') ? JSON.parse(api.files[f]) : null).find(c => c && !['t_one', 't_three'].includes(c.id)); }
    assert(added, 'the new card was saved');
    assert.deepEqual((added.related || []).map(r => [r.id, r.kind, r.status]), [['t_one', 'duplicate', 'possible']]);
    for (let i = 0; i < 50 && status('t_one', added.id) !== 'possible'; i++) await page.waitForTimeout(100);
    assert.equal(status('t_one', added.id), 'possible');
    assert.equal(api.card('t_three').related, undefined, 'an unrelated card is left alone');

    // Not related: kept on both cards, so the check never asks about the pair again
    await page.locator('.card', { hasText: 'Send Acme' }).filter({ has: page.locator('.relchip') }).first().locator('.t').click();
    await page.waitForSelector('#cRelSec:not([hidden])');
    await page.locator('#cRelList button[data-act=dismiss]').first().click();
    for (let i = 0; i < 50 && status('t_one', added.id) !== 'not-related'; i++) await page.waitForTimeout(100);
    assert.equal(status('t_one', added.id), 'not-related'); assert.equal(status(added.id, 't_one'), 'not-related');
    await page.waitForSelector('#cRelSec[hidden]', { state: 'attached' });

    assert.deepEqual(errors, []);
    console.log('related-cards: all checks passed');
  } finally { await browser.close(); server.close(); }
})().catch(e => { console.error(e); process.exit(1); });

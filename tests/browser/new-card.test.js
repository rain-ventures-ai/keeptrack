'use strict';
// The new-card form (kit v59) on a writable board with a faked GitHub API: quick add still saves a title-only card on
// Enter; the lane's pencil, Shift+Enter, an empty Add, the lane's ＋ and the phone ＋ open the form; the form saves every
// field (details, column, client, project, priority, due, assignee, labels, checklist, links) in one card; a new
// client and a new label join the board's lists; a bad link line or an empty title stops the save with a message.
// Run: node new-card.test.js   (SHOTS=<folder> also saves screenshots)

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
const root = { version: 4, layout: 'split', settings: { title: 'New card test' }, columns: [{ id: 'todo', name: 'To do' }, { id: 'done', name: 'Done' }], people: [{ github: 'alex', name: 'Alex' }, { github: 'sam', name: 'Sam' }], agents: [], clients: ['Acme'], labels: [{ name: 'urgent', color: '#dce1e7' }], client_info: {}, next_num: 4, archive: { files: {} } };
const card = (id, num, title, extra) => ({ id, num, title, column: 'todo', client: '', priority: 'medium', due: '', labels: [], assignees: [], details: '', links: [], contacts: [], todos: [], comments: [], history: [], claim: null, created: '2026-10-01T08:00:00.000Z', updated: '2026-10-01T08:00:00.000Z', rank: 'a' + num, ...extra });

// A small GitHub: contents API for reads and single-file writes, git data API for multi-file commits (same shape as split-storage.test.js).
class Github {
  constructor() {
    this.files = { 'tasks.json': text(root), 'cards/t_one.json': text(card('t_one', 1, 'Send Acme the revised plan', { client: 'Acme' })), 'cards/t_three.json': text(card('t_three', 3, 'Write notes')),
      'projects/pr_web.json': text({ id: 'pr_web', client: 'Acme', name: 'Website', north_star: '', status: 'active', links: [], people: [] }), 'projects/pr_ops.json': text({ id: 'pr_ops', client: 'Other', name: 'Ops', north_star: '', status: 'active', links: [], people: [] }) };
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

const cards = api => Object.keys(api.files).filter(f => f.startsWith('cards/')).map(f => JSON.parse(api.files[f]));
async function waitFor(fn, what) { for (let i = 0; i < 100; i++) { const v = fn(); if (v) return v; await new Promise(r => setTimeout(r, 100)); } throw new Error('timed out: ' + what); }

(async () => {
  await new Promise(ok => server.listen(0, '127.0.0.1', ok)); const base = `http://127.0.0.1:${server.address().port}`;
  const browser = await chromium.launch({ headless: true });
  try {
    const api = new Github();
    const open = async viewport => {
      const page = await browser.newPage({ viewport }); page.errors = []; page.on('pageerror', e => page.errors.push(e.message));
      await page.addInitScript(() => { localStorage.setItem('kb_repo', 'acme/board'); localStorage.setItem('kb_branch', 'main'); localStorage.setItem('kb_path', 'board/tasks.json'); localStorage.setItem('kb_token', 'test'); localStorage.setItem('kb_me', 'alex'); localStorage.setItem('kb_api', 'https://api.test'); localStorage.setItem('kb_layout', 'classic'); localStorage.setItem('kb_tour_seen', '1'); sessionStorage.setItem('kb_view', 'board'); });
      await page.route('https://api.test/**', r => api.route(r)); await page.goto(base + '/board/index.html'); await page.waitForSelector('.card'); return page;
    };
    const page = await open({ width: 1280, height: 900 });
    const lane = page.locator('.col[data-col="todo"]'), quick = lane.locator('.add input');

    // 1. quick add is unchanged: Enter saves a title-only card and the form does not open
    await quick.fill('Book the venue'); await quick.press('Enter');
    const q = await waitFor(() => cards(api).find(c => c.title === 'Book the venue'), 'quick add saved');
    assert.equal(q.column, 'todo'); assert.equal(q.details, ''); assert.deepEqual(q.assignees, ['alex'], 'quick add still assigns you');
    assert.equal(await page.locator('#dlgNewCard').count(), 0, 'Enter never opens the form');

    // 2. Shift+Enter opens the form with the typed text as the title; Escape closes it and saves nothing
    const before = Object.keys(api.files).length;
    await quick.fill('Draft the summary'); await quick.press('Shift+Enter');
    await page.waitForSelector('#dlgNewCard[open]');
    assert.equal(await page.locator('#ncTitle').inputValue(), 'Draft the summary');
    assert.equal(await page.locator('#ncCol').inputValue(), 'todo'); assert.equal(await page.locator('#ncWho').inputValue(), 'alex');
    await page.keyboard.press('Escape'); await page.waitForSelector('#dlgNewCard', { state: 'detached' });
    assert.equal(Object.keys(api.files).length, before, 'cancel saves nothing');

    // 3. an empty Add, the lane pencil and the lane ＋ open the form too
    for (const sel of ['.add button.primary', '.add .addform', 'h2 .hadd']) {
      await lane.locator(sel).click(); await page.waitForSelector('#dlgNewCard[open]', { timeout: 3000 });
      await page.locator('#dlgNewCard .ui-sheet__head button[aria-label="Close"]').click(); await page.waitForSelector('#dlgNewCard', { state: 'detached' });
    }

    // 4. the full form: an empty title and a bad link line stop the save with a message
    await lane.locator('.add .addform').click(); await page.waitForSelector('#dlgNewCard[open]');
    await page.locator('#ncSave').click(); assert.match(await page.locator('#ncErr').textContent(), /title/);
    await page.locator('#ncTitle').fill('Send Globex the signed contract');
    await page.locator('#ncDetails').fill('Globex signed on Friday. Done when the PDF is in their portal.');
    await page.locator('#ncClient').fill('Acme');
    assert.deepEqual(await page.locator('#ncProject option').allTextContents(), ['No project', 'Website'], 'the client filters the projects');
    await page.locator('#ncClient').fill('Globex');
    assert.deepEqual(await page.locator('#ncProject option').allTextContents(), ['No project', 'Website · Acme', 'Ops · Other'], 'an unknown client shows every project');
    await page.locator('#ncCol').selectOption('done'); await page.locator('#ncPrio').selectOption('high');
    await page.locator('#ncDue').fill('2026-11-02'); await page.locator('#ncWho').selectOption('sam');
    await page.locator('#ncLabels').fill('URGENT, legal , legal');
    await page.locator('#ncTodos').fill('Print the contract\n\nUpload the PDF\n');
    await page.locator('#ncLinks').fill('not a link');
    await page.locator('#ncSave').click(); assert.match(await page.locator('#ncErr').textContent(), /not a link/);
    assert.equal(await page.locator('#dlgNewCard[open]').count(), 1, 'a bad link keeps the form open');
    await page.locator('#ncLinks').fill('Contract (Drive) | https://drive.example/contract\nhttps://globex.example/portal');
    await shot(page, 'new-card-form');
    await page.locator('#ncSave').click();
    await page.waitForSelector('#dlgNewCard', { state: 'detached' });
    const c = await waitFor(() => cards(api).find(x => x.title === 'Send Globex the signed contract'), 'form card saved');
    assert.equal(c.column, 'done'); assert.equal(c.client, 'Globex'); assert.equal(c.project, ''); assert.equal(c.priority, 'high');
    assert.equal(c.due, '2026-11-02'); assert.deepEqual(c.assignees, ['sam']); assert.equal(c.details, 'Globex signed on Friday. Done when the PDF is in their portal.');
    assert.deepEqual(c.labels, ['urgent', 'legal'], 'labels match the board spelling and repeat once');
    assert.deepEqual(c.todos.map(t => [t.text, t.done]), [['Print the contract', false], ['Upload the PDF', false]]);
    assert.deepEqual(c.links, [{ title: 'Contract (Drive)', url: 'https://drive.example/contract' }, { title: 'https://globex.example/portal', url: 'https://globex.example/portal' }]);
    assert.equal(c.createdBy, 'alex');
    const root2 = await waitFor(() => { const r = JSON.parse(api.files['tasks.json']); return r.clients.includes('Globex') && r; }, 'new client in the board list');
    assert.deepEqual(root2.labels.map(l => l.name).sort(), ['legal', 'urgent'], 'a new label joins the board list once');

    // 5. picking a project fills an empty client
    await lane.locator('h2 .hadd').click(); await page.waitForSelector('#dlgNewCard[open]');
    await page.locator('#ncTitle').fill('Refresh the homepage'); await page.locator('#ncProject').selectOption('pr_web');
    assert.equal(await page.locator('#ncClient').inputValue(), 'Acme');
    await page.locator('#ncClient').fill('Other'); assert.equal(await page.locator('#ncProject').inputValue(), '', 'another client drops a project that is not theirs');
    await page.locator('#ncClient').fill('Globex'); await page.locator('#ncProject').selectOption('pr_web');
    assert.equal(await page.locator('#ncClient').inputValue(), 'Acme', 'a project sets its client');
    await page.locator('#ncLinks').fill('Notes | ~/work/acme/notes');
    await page.locator('#ncTitle').press('Control+Enter'); await page.keyboard.press('Enter').catch(() => {});   // Ctrl+Enter bubbles to the sheet too: still one card
    const w = await waitFor(() => cards(api).find(x => x.title === 'Refresh the homepage'), 'project card saved');
    assert.equal(w.project, 'pr_web'); assert.equal(w.client, 'Acme'); assert.equal(w.column, 'todo');
    assert.deepEqual(w.links, [{ title: 'Notes', url: '~/work/acme/notes' }], 'a local path is a link, as in the drawer');
    await page.waitForTimeout(800); assert.equal(cards(api).filter(x => x.title === 'Refresh the homepage').length, 1, 'one card, never two');
    assert.deepEqual(page.errors, []);

    // 6. phones: the floating ＋ opens the form for the column on show
    const phone = await open({ width: 390, height: 800 });
    await phone.locator('#fab').click(); await phone.waitForSelector('#dlgNewCard[open]');
    assert.equal(await phone.locator('#ncCol').inputValue(), 'todo');
    const box = await phone.locator('#dlgNewCard').boundingBox(); assert(box.width <= 390, 'the form fits a phone');
    await phone.waitForTimeout(500); await shot(phone, 'new-card-phone');
    assert.deepEqual(phone.errors, []);
    console.log('new-card: all checks passed');
  } finally { await browser.close(); server.close(); }
})().catch(e => { console.error(e); process.exit(1); });

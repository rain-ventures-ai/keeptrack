'use strict';
// New cards use the card drawer (kit v61) on a writable board with a faked GitHub API: quick add still saves a
// title-only card on Enter; Shift+Enter and the lane's pencil save the typed title and open the card in the drawer;
// an empty Add, the pencil, the lane's ＋ and the phone ＋ ask for a title first (Cancel saves nothing).
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
    if (method !== 'GET' && this.failWrites) return json({ message: 'Server error' }, 500);
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

    const closeDrawer = async pg => { await pg.locator('#cClose').click(); await pg.waitForSelector('#dlgCard:not([open])', { state: 'attached' }); };
    const prompt = pg => pg.locator('dialog.ui-sheet--alert[open]');

    // 2. Shift+Enter saves the typed title and opens the card in the card drawer (the one card form)
    await quick.fill('Draft the summary'); await quick.press('Shift+Enter');
    await page.waitForSelector('#dlgCard[open]');
    assert.equal(await page.locator('#cTitle').inputValue(), 'Draft the summary');
    const s1 = await waitFor(() => cards(api).find(c => c.title === 'Draft the summary'), 'Shift+Enter card saved');
    assert.equal(s1.column, 'todo'); assert.deepEqual(s1.assignees, ['alex']);
    assert.equal(await quick.inputValue(), '', 'the box is cleared');
    await closeDrawer(page);

    // 3. the pencil with text: same as Shift+Enter
    await quick.fill('Call the printer'); await lane.locator('.add .addform').click();
    await page.waitForSelector('#dlgCard[open]'); assert.equal(await page.locator('#cTitle').inputValue(), 'Call the printer');
    await closeDrawer(page);

    // 4. an empty Add, the pencil and the lane ＋ ask for a title first; Cancel saves nothing
    const before = cards(api).length;
    for (const sel of ['.add button.primary', '.add .addform', 'h2 .hadd']) {
      await lane.locator(sel).click(); await prompt(page).waitFor();
      await prompt(page).locator('button', { hasText: 'Cancel' }).click(); await page.waitForSelector('dialog.ui-sheet--alert', { state: 'detached' });
    }
    assert.equal(cards(api).length, before, 'cancel saves nothing'); assert.equal(await page.locator('#dlgCard[open]').count(), 0);

    // 5. a title typed in the prompt: the card is saved and opens in the drawer, where the other fields are edited as usual
    await lane.locator('h2 .hadd').click(); await prompt(page).waitFor();
    await prompt(page).locator('input').fill('Refresh the homepage'); await prompt(page).locator('input').press('Enter');
    await page.waitForSelector('#dlgCard[open]'); assert.equal(await page.locator('#cTitle').inputValue(), 'Refresh the homepage');
    const w = await waitFor(() => cards(api).find(x => x.title === 'Refresh the homepage'), 'prompt card saved');
    assert.equal(w.column, 'todo');
    await page.locator('#cPrio').selectOption('high');
    await waitFor(() => cards(api).find(x => x.id === w.id && x.priority === 'high'), 'drawer edit saved on the new card');
    await shot(page, 'new-card-drawer');
    await closeDrawer(page);
    assert.equal(cards(api).filter(x => x.title === 'Refresh the homepage').length, 1, 'one card, never two');

    // a failed save puts the title back in the lane's box
    api.failWrites = true;
    await quick.fill('Order the banners'); await quick.press('Shift+Enter');
    for (let i = 0; i < 100 && (await quick.inputValue()) !== 'Order the banners'; i++) await page.waitForTimeout(100);
    assert.equal(await quick.inputValue(), 'Order the banners', 'the title is back in the box');
    assert.equal(await page.locator('#dlgCard[open]').count(), 0); api.failWrites = false;
    await quick.fill(''); page.errors = page.errors.filter(e => !/500|Server error/i.test(e));
    assert.deepEqual(page.errors, []);

    // 6. phones: the floating ＋ asks for a title, then opens the card for the column on show
    const phone = await open({ width: 390, height: 800 });
    await phone.locator('#fab').click(); await prompt(phone).waitFor();
    await prompt(phone).locator('input').fill('Text the venue'); await prompt(phone).locator('button', { hasText: 'Create and open' }).click();
    await phone.waitForSelector('#dlgCard[open]');
    const ph = await waitFor(() => cards(api).find(x => x.title === 'Text the venue'), 'phone card saved'); assert.equal(ph.column, 'todo');
    await phone.waitForTimeout(500); await shot(phone, 'new-card-phone');
    assert.deepEqual(phone.errors, []);
    console.log('new-card: all checks passed');
  } finally { await browser.close(); server.close(); }
})().catch(e => { console.error(e); process.exit(1); });

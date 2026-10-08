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

const root = { version: 4, layout: 'split', settings: { title: 'Test' }, columns: [{ id: 'todo', name: 'To do' }, { id: 'done', name: 'Done' }], people: [{ github: 'alex', name: 'Alex' }], agents: ['codex'], clients: ['Acme'], labels: [], client_info: {}, next_num: 3, archive: { files: {} } };
const cards = {
  'cards/t_one.json': { id: 't_one', num: 1, title: 'First', column: 'todo', client: 'Acme', priority: 'high', due: '', labels: [], assignees: ['alex'], details: '', links: [], contacts: [], todos: [], comments: [], history: [], claim: null, created: '2026-10-01T08:00:00.000Z', updated: '2026-10-01T08:00:00.000Z', rank: 'a0' },
  'cards/t_two.json': { id: 't_two', num: 2, title: 'Second', column: 'todo', client: '', priority: 'medium', due: '', labels: [], assignees: [], details: '', links: [], contacts: [], todos: [], comments: [], history: [], claim: null, created: '2026-10-02T08:00:00.000Z', updated: '2026-10-02T08:00:00.000Z', rank: 'a1' },
};
const person = { id: 'p_one', name: 'Casey Example', company: 'Acme', role: '', email: '', phone: '', linkedin: '', stage: 'New', value: '', source: '', notes: '', next: '', next_due: '', links: [], comments: [], history: [], created: '2026-10-01T08:00:00.000Z', updated: '2026-10-01T08:00:00.000Z' };
const text = x => JSON.stringify(x, null, 2) + '\n';

class Github {
  constructor(v4 = true) { this.v4 = v4; this.files = v4 ? { 'tasks.json': text(root), ...Object.fromEntries(Object.entries(cards).map(([k, v]) => [k, text(v)])), 'people/p_one.json': text(person) } : { 'tasks.json': text({ ...root, version: 3, layout: undefined, tasks: Object.values(cards), contacts: [person] }) }; this.head = 'head-1'; this.n = 1; this.calls = []; this.blobs = {}; this.pending = null; this.failPatch = false; }
  sha(p) { return 'sha-' + p.replace(/[^a-z0-9]/gi, '-'); }
  tree() { return Object.entries(this.files).map(([p, content]) => ({ path: p, type: 'blob', sha: this.sha(p), size: Buffer.byteLength(content) })); }
  async route(route) {
    const req = route.request(), u = new URL(req.url()), method = req.method(), p = u.pathname.replace('/repos/acme/board', ''); this.calls.push({ method, path: p + u.search, body: req.postDataJSON?.() });
    const json = (body, status = 200, headers = {}) => route.fulfill({ status, headers: { 'Content-Type': 'application/json', ...headers }, body: JSON.stringify(body) });
    if (p === '' && method === 'GET') return json({ full_name: 'acme/board', private: true, permissions: { push: true }, default_branch: 'main' });
    if (p.startsWith('/contents/board/tasks.json') && method === 'GET') return json({ sha: this.sha('tasks.json'), size: Buffer.byteLength(this.files['tasks.json']), encoding: 'base64', content: Buffer.from(this.files['tasks.json']).toString('base64') }, 200, { ETag: '"tasks"' });
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

async function openBoard(browser, api) {
  const page = await browser.newPage(); page.on('pageerror', e => console.error('page error:', e.message)); await page.addInitScript(() => { localStorage.setItem('kb_repo', 'acme/board'); localStorage.setItem('kb_branch', 'main'); localStorage.setItem('kb_path', 'board/tasks.json'); localStorage.setItem('kb_token', 'test'); localStorage.setItem('kb_me', 'alex'); localStorage.setItem('kb_api', 'https://api.test'); localStorage.setItem('kb_view', 'board'); });
  await page.route('https://api.test/**', r => api.route(r)); await page.goto(base + '/board/index.html'); try { await page.waitForSelector('.card'); } catch (e) { console.error('status:', await page.locator('#status').textContent().catch(() => '?'), 'calls:', api.calls); throw e; } return page;
}

let base;
(async () => {
  await new Promise(ok => server.listen(0, '127.0.0.1', ok)); base = `http://127.0.0.1:${server.address().port}`; const browser = await chromium.launch({ headless: true });
  try {
    const api = new Github(true), page = await openBoard(browser, api);
    assert.deepEqual(await page.locator('.card .t').allTextContents(), ['First', 'Second']);
    assert(!api.calls.some(x => /git\/trees\/root-.*recursive/.test(x.path)), 'must not read the whole repository tree');
    assert(api.calls.some(x => /git\/trees\/board-.*recursive/.test(x.path)), 'must read only the board subtree');

    api.calls = []; await page.locator('.card').first().dblclick(); await page.locator('#cTitle').fill('First edited'); const edited = page.waitForResponse(r => r.request().method() === 'PUT' && r.url().includes('/contents/board/cards/')); await page.locator('#cTitle').blur(); await edited;
    const puts = api.calls.filter(x => x.method === 'PUT'); assert.equal(puts.length, 1, JSON.stringify(api.calls, null, 2)); assert.equal(puts[0].path, '/contents/board/cards/t_one.json');

    await page.locator('#cClose').click(); api.calls = []; const add = page.locator('.col[data-col="todo"] .add input'); await add.fill('Third'); const added = page.waitForResponse(r => r.request().method() === 'PATCH' && r.url().includes('/git/refs/heads/main')); await add.press('Enter'); await added;
    assert.equal(api.calls.filter(x => x.path === '/git/refs/heads/main' && x.method === 'PATCH').length, 1); assert.equal(api.pending.filter(x => x.sha !== null).length, 2);

    api.calls = []; const dragged = page.waitForResponse(r => r.request().method() === 'PUT' && r.url().includes('/contents/board/cards/')); await page.evaluate(() => { const cards = document.querySelectorAll('.card'), dt = new DataTransfer(); dt.setData('text/plain', 't_two'); cards[0].dispatchEvent(new DragEvent('drop', { bubbles: true, cancelable: true, dataTransfer: dt })); }); await dragged;
    const dragPuts = api.calls.filter(x => x.method === 'PUT'); assert.equal(dragPuts.length, 1); assert.equal(dragPuts[0].path, '/contents/board/cards/t_two.json');
    await page.close();

    const racing = new Github(true); racing.failPatch = true; const retry = await openBoard(browser, racing); await retry.evaluate(() => { window.__statuses = []; new MutationObserver(() => window.__statuses.push(document.querySelector('#status').textContent)).observe(document.querySelector('#status'), { childList: true }); }); const input = retry.locator('.col[data-col="todo"] .add input'); await input.fill('Retry card'); const retried = retry.waitForResponse(r => r.request().method() === 'PATCH' && r.url().includes('/git/refs/heads/main') && r.status() === 200); await input.press('Enter'); await retried; assert.equal(racing.calls.filter(x => x.path === '/git/refs/heads/main' && x.method === 'PATCH').length, 2); assert((await retry.evaluate(() => window.__statuses)).some(x => x.includes('retrying')), 'the conflict retry must be shown'); await retry.close();

    const old = new Github(false), legacy = await openBoard(browser, old); old.calls = []; await legacy.locator('.card').first().dblclick(); await legacy.locator('#cTitle').fill('Legacy edit'); const legacySaved = legacy.waitForResponse(r => r.request().method() === 'PUT' && r.url().includes('/contents/board/tasks.json')); await legacy.locator('#cTitle').blur(); await legacySaved; const oldPuts = old.calls.filter(x => x.method === 'PUT'); assert.equal(oldPuts.length, 1); assert.equal(oldPuts[0].path, '/contents/board/tasks.json'); await legacy.close();
    console.log('split storage browser tests passed');
  } finally { await browser.close(); server.close(); }
})().catch(err => { console.error(err); server.close(); process.exitCode = 1; });

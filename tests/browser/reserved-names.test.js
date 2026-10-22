'use strict';
// Kit v89 (private-tasks card #287): every page save counts the places a client or company name is stored and refuses
// one that stores __proto__, constructor or prototype in one more place than the board had. An old board that already
// has "__proto__" as a client: picking it for a task from the client list is refused with advice, nothing is written,
// Object.prototype is untouched, and an ordinary pick still saves. Restoring an archived card with that client on a split
// board is refused the same way (kit v89 review).
// Run: node reserved-names.test.js

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
const root = { version: 4, layout: 'split', settings: { title: 'Reserved names test' }, columns: [{ id: 'todo', name: 'To do' }, { id: 'done', name: 'Done' }], people: [{ github: 'alex', name: 'Alex' }], agents: [], clients: ['Acme', '__proto__'], labels: [], client_info: {}, next_num: 3, archive: { files: {} } };
const card = (id, num, title, extra) => ({ id, num, title, column: 'todo', client: '', priority: 'medium', due: '', labels: [], assignees: [], details: '', links: [], contacts: [], todos: [], comments: [], history: [], claim: null, created: '2026-10-01T08:00:00.000Z', updated: '2026-10-01T08:00:00.000Z', rank: 'a' + num, ...extra });

class Github {
  constructor() {
    this.files = { 'tasks.json': text(root), 'cards/t_one.json': text(card('t_one', 1, 'First')), 'cards/t_two.json': text(card('t_two', 2, 'Second', { client: '__proto__' })) };
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
    const saved = () => page.waitForResponse(r => ['PUT', 'PATCH', 'DELETE'].includes(r.request().method()) && r.url().startsWith('https://api.test/repos/acme/board/'));
    const before = JSON.stringify(api.files);
    await page.evaluate(() => { location.hash = '#1'; }); await page.locator('#dlgCard[open]').waitFor();
    const pick = async name => { await page.locator('#cWorkPick').click(); const sheet = page.locator('dialog.dworksheet[open]'); await sheet.waitFor();
      await sheet.locator('.dworkcol').first().locator('.dworkchoice', { hasText: name }).first().click(); return sheet; };
    // the old reserved client is still listed (the board has it), but picking it for a task is refused at save
    let sheet = await pick('__proto__'); const writes = api.writes; await page.locator('#cWorkDone').click();
    const toast = page.locator('.ui-toast', { hasText: 'cannot be a client or company name' }); await toast.waitFor();
    assert.match(await toast.textContent(), /client-rename '__proto__' NEW/, 'the refusal says how to clean the old name up');
    assert.doesNotMatch(await toast.textContent(), /Companies/, 'the page has no company rename (kit v89 review round 2)');
    await page.waitForTimeout(300);
    assert.equal(api.writes, writes, 'nothing was written'); assert.equal(JSON.stringify(api.files), before);
    assert.equal(api.card('t_one').client, '');
    assert.deepEqual(await page.evaluate(() => [Object.keys(Object.prototype), ({}).stage, ({}).links]), [[], undefined, undefined], 'Object.prototype is untouched');
    // the sheet stays open: an ordinary client still saves; a card that already had the old name may keep it (no new use)
    assert.equal(await sheet.isVisible(), true, 'a refused pick keeps the choice open');
    await sheet.locator('.dworkcol').first().locator('.dworkchoice', { hasText: 'Acme' }).first().click(); let w = saved(); await page.locator('#cWorkDone').click(); await w; await sheet.waitFor({ state: 'detached' });
    assert.equal(api.card('t_one').client, 'Acme');
    w = saved(); await page.locator('#cPrio').selectOption('low'); await w; assert.equal(api.card('t_one').priority, 'low');
    await page.keyboard.press('Escape'); await page.locator('#dlgCard').waitFor({ state: 'hidden' });
    await page.locator('.card', { hasText: 'Second' }).click(); await page.locator('#dlgCard[open]').waitFor();
    await page.waitForFunction(() => document.getElementById('cTitle').value === 'Second'); await page.locator('#cPrio').waitFor({ state: 'visible' });
    await page.locator('#cPrio').selectOption('high');
    for (let i = 0; i < 100 && api.card('t_two').priority !== 'high'; i++) await page.waitForTimeout(100);
    assert.equal(api.card('t_two').priority, 'high', 'editing a card that already has the old name is not a new use');
    assert.deepEqual(errors, []);

    // kit v89 review: restoring an archived card on a split board saves directly (not through mutateNow), so it runs the
    // same check: a card whose client is the old reserved name stays archived, with the advice, and nothing is written
    const arch = new Github(), r0 = JSON.parse(arch.files['tasks.json']); r0.archive.files = { 2025: { tasks: 1, contacts: 0 } }; arch.files['tasks.json'] = text(r0);
    arch.files['archive/2025.json'] = text({ version: 4, archive: true, year: '2025', tasks: [card('t_three', 3, 'Third', { client: '__proto__', column: 'done' })], contacts: [] });
    const ap = await browser.newPage({ viewport: { width: 1280, height: 900 } }); ap.on('pageerror', e => errors.push(e.message));
    await ap.addInitScript(() => { localStorage.setItem('kb_repo', 'acme/board'); localStorage.setItem('kb_branch', 'main'); localStorage.setItem('kb_path', 'board/tasks.json'); localStorage.setItem('kb_token', 'test'); localStorage.setItem('kb_me', 'alex'); localStorage.setItem('kb_api', 'https://api.test'); localStorage.setItem('kb_layout', 'classic'); localStorage.setItem('kb_tour_seen', '1'); sessionStorage.setItem('kb_view', 'board'); });
    await ap.route('https://api.test/**', r => arch.route(r)); await ap.goto(base + '/board/index.html'); await ap.waitForSelector('.card');
    const archBefore = JSON.stringify(arch.files), archWrites = arch.writes;
    await ap.locator('#btnSearch').click(); await ap.locator('#qArch').check(); await ap.locator('#qQ').fill('Third'); await ap.locator('.qhit', { hasText: 'Third' }).click(); await ap.locator('#aRestore').click();
    const archToast = ap.locator('.ui-toast', { hasText: 'cannot be a client or company name' }); await archToast.waitFor();
    assert.match(await archToast.textContent(), /keeptrack\.py unarchive '#3' --client NEW/, 'the refused restore names a command that restores it (kit v89 review round 2)');
    assert.doesNotMatch(await archToast.textContent(), /Companies/, 'no page action that does not exist');
    await ap.waitForTimeout(300);
    assert.equal(arch.writes, archWrites, 'a refused restore writes nothing'); assert.equal(JSON.stringify(arch.files), archBefore);
    assert.equal(arch.card('t_three'), null, 'the card stays archived');
    assert.deepEqual(errors, []);
    console.log('reserved-names: ok');
  } finally { await browser.close(); server.close(); }
})().catch(e => { console.error(e); process.exit(1); });

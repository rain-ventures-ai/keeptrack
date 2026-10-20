'use strict';
// Archive from the Done lane: Done cards (and Done rows in List) have an Archive button on the card face. On desktop
// it shows on hover, on touch screens always; one click archives the card with no dialog, and the toast's Undo puts it back.
// Run: node quick-archive.test.js   (SHOTS=<dir> also saves screenshots)

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
    // desktop: hidden until hover, one click archives, Undo restores without opening the card
    { const api = new Github(), page = await browser.newPage({ viewport: { width: 1280, height: 860 } }), errors = []; page.on('pageerror', e => errors.push(e.message));
      await page.addInitScript(init, 'board'); await page.route('https://api.test/**', r => api.route(r)); await page.goto(base + '/board/index.html'); await page.waitForSelector('.card');
      const done = page.locator('.col[data-col="done"] .card', { hasText: 'Finished work' }), btn = done.locator('.quickarch');
      assert.equal(await page.locator('.col[data-col="todo"] .quickarch').count(), 0, 'no Archive button outside Done');
      assert.equal(await page.locator('.card', { hasText: 'Agent still on it' }).locator('.quickarch').count(), 0, 'no Archive button while an agent holds the card');
      assert.equal(await btn.getAttribute('aria-label'), 'Archive task #2');
      assert.equal(await opacity(btn), 0, 'hidden until hover');
      await done.hover(); await page.waitForTimeout(250); assert.ok(await opacity(btn) > 0.5, 'shown on hover'); await shot(page, 'desktop-hover');
      const before = api.card('t_two');
      await btn.click();
      const undo = page.getByRole('button', { name: 'Undo', exact: true }); await undo.waitFor();
      assert.equal(await page.locator('dialog[open]').count(), 0, 'no dialog'); assert.equal(api.card('t_two'), null, 'the card file is gone');
      const archiveFile = Object.keys(api.files).find(p => p.startsWith('archive/')); assert.deepEqual(JSON.parse(api.files[archiveFile]).tasks.map(t => t.id), ['t_two']);
      assert.equal(await page.locator('.card', { hasText: 'Finished work' }).count(), 0); await shot(page, 'desktop-toast');
      await undo.click();
      await page.locator('.col[data-col="done"] .card', { hasText: 'Finished work' }).waitFor();
      for (let i = 0; i < 50 && JSON.parse(api.files[archiveFile]).tasks.length; i++) await page.waitForTimeout(100);
      const back = api.card('t_two'); assert.ok(back, 'the card file is back');
      for (const key of ['title', 'column', 'details', 'comments', 'todos', 'links']) assert.deepEqual(back[key], before[key]);
      assert.deepEqual(back.history.slice(0, -1), before.history); assert.match(back.history.at(-1).text, /restored/);
      assert.deepEqual(JSON.parse(api.files[archiveFile]).tasks, []);
      assert.equal(await page.locator('#dlgCard[open]').count(), 0, 'Undo does not open the card');
      // Ctrl+Z while the toast shows takes back the archive too (split boards keep no undo entry for it)
      await page.locator('.col[data-col="done"] .card', { hasText: 'Finished work' }).locator('.quickarch').click(); await undo.waitFor();
      assert.equal(api.card('t_two'), null);
      await page.locator('#board').click({ position: { x: 900, y: 700 } }); await page.keyboard.press('Control+z');
      await page.locator('.col[data-col="done"] .card', { hasText: 'Finished work' }).waitFor();
      for (let i = 0; i < 50 && !api.card('t_two'); i++) await page.waitForTimeout(100);
      assert.ok(api.card('t_two'), 'Ctrl+Z puts the card back');
      // a card someone moved out of Done since this page drew it is not archived
      api.files['cards/t_two.json'] = text({ ...api.card('t_two'), column: 'todo' }); api.head = 'head-' + ++api.n;   // someone else's commit
      await page.locator('.col[data-col="done"] .card', { hasText: 'Finished work' }).locator('.quickarch').click();
      await page.getByText('#2 is no longer in Done', { exact: false }).waitFor();
      assert.equal(api.card('t_two').column, 'todo', 'the moved card stays on the board');
      // List view: Done rows have the button too
      await page.evaluate(() => { location.hash = 'view=list'; }); await page.waitForFunction(() => document.body.dataset.view === 'list'); await page.waitForSelector('.trow');
      assert.equal(await page.locator('.trow', { hasText: 'Finished work' }).locator('.quickarch').count(), 1);
      assert.equal(await page.locator('.trow', { hasText: 'Open work' }).locator('.quickarch').count(), 0);
      assert.deepEqual(errors, [], 'no page errors'); await page.close(); }

    // the card leaves at once, before GitHub has the commit; when the commit fails it comes back with a warning
    { const api = new Github(), page = await browser.newPage({ viewport: { width: 1280, height: 860 } }), errors = []; page.on('pageerror', e => errors.push(e.message));
      let hold = null, held = false, fail = false;
      await page.addInitScript(init, 'board');
      await page.route('https://api.test/**', async r => { const req = r.request();
        if (req.method() === 'PATCH' && req.url().endsWith('/git/refs/heads/main')) { if (fail) return r.fulfill({ status: 500, contentType: 'application/json', body: '{"message":"boom"}' }); if (!held) { held = true; await new Promise(ok => { hold = ok; }); } }
        return api.route(r); });
      await page.goto(base + '/board/index.html'); await page.waitForSelector('.card');
      const done = () => page.locator('.col[data-col="done"] .card', { hasText: 'Finished work' });
      await done().hover(); await done().locator('.quickarch').click();
      await page.waitForFunction(() => ![...document.querySelectorAll('.col[data-col="done"] .card')].some(c => c.textContent.includes('Finished work')), null, { timeout: 1000 });
      for (let i = 0; i < 50 && !hold; i++) await page.waitForTimeout(100);
      assert.ok(hold, 'the commit is still in flight'); assert.ok(api.card('t_two'), 'GitHub still has the card while it is hidden');
      hold(); await page.getByRole('button', { name: 'Undo', exact: true }).waitFor(); assert.equal(api.card('t_two'), null, 'archived once the commit lands');
      await page.getByRole('button', { name: 'Undo', exact: true }).click(); await done().waitFor();
      for (let i = 0; i < 50 && !api.card('t_two'); i++) await page.waitForTimeout(100);
      fail = true; await page.waitForTimeout(3000);   // let the Undo toast and status settle
      await done().hover(); await done().locator('.quickarch').click();
      await page.locator('.ui-toast__text', { hasText: 'Archive failed' }).waitFor();
      await done().waitFor(); assert.ok(api.card('t_two'), 'a failed archive leaves the card on GitHub'); assert.equal(await page.getByRole('button', { name: 'Undo', exact: true }).count(), 0, 'no Undo for an archive that did not happen');
      assert.deepEqual(errors, [], 'no page errors'); await page.close(); }

    // single-file board (no split layout): one click archives, Undo puts it back
    { const api = new Github(), cards = ['t_one', 't_two', 't_three'].map(id => api.card(id));
      api.files = { 'tasks.json': text({ ...root, layout: undefined, tasks: cards }) };
      const page = await browser.newPage({ viewport: { width: 1280, height: 860 } }), errors = []; page.on('pageerror', e => errors.push(e.message));
      await page.addInitScript(init, 'board'); await page.route('https://api.test/**', r => api.route(r)); await page.goto(base + '/board/index.html'); await page.waitForSelector('.card');
      const board = () => JSON.parse(api.files['tasks.json']), done = page.locator('.col[data-col="done"] .card', { hasText: 'Finished work' });
      await done.hover(); await done.locator('.quickarch').dblclick();
      const undo = page.getByRole('button', { name: 'Undo', exact: true }); await undo.waitFor();
      assert.ok(!board().tasks.some(t => t.id === 't_two'), 'archived from the board file');
      const archiveFile = Object.keys(api.files).find(p => p.startsWith('archive/')); assert.deepEqual(JSON.parse(api.files[archiveFile]).tasks.map(t => t.id), ['t_two'], 'a double click archives once');
      await undo.click(); await done.waitFor();
      for (let i = 0; i < 50 && JSON.parse(api.files[archiveFile]).tasks.length; i++) await page.waitForTimeout(100);
      assert.ok(board().tasks.some(t => t.id === 't_two' && t.column === 'done'), 'back on the board'); assert.deepEqual(JSON.parse(api.files[archiveFile]).tasks, []);
      assert.deepEqual(errors, [], 'no page errors'); await page.close(); }

    // phone (touch, no hover): always visible, and a tap archives without opening the card
    { const api = new Github(), ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true }), page = await ctx.newPage(), errors = []; page.on('pageerror', e => errors.push(e.message));
      await page.addInitScript(init, 'board'); await page.route('https://api.test/**', r => api.route(r)); await page.goto(base + '/board/index.html'); await page.waitForSelector('.col.active .card');
      assert.equal(await page.evaluate(() => matchMedia('(hover: none)').matches), true, 'the phone has no hover');
      const btn = page.locator('.col.active .card', { hasText: 'Finished work' }).locator('.quickarch');
      assert.ok(await opacity(btn) > 0.5, 'always shown on a phone'); await shot(page, 'phone');
      await btn.tap(); await page.getByRole('button', { name: 'Undo', exact: true }).waitFor();
      assert.equal(api.card('t_two'), null); assert.equal(await page.locator('#dlgCard[open]').count(), 0, 'the tap does not open the card');
      assert.deepEqual(errors, [], 'no page errors'); await ctx.close(); }

    // fast clicks on several Done cards while an archive commit is in flight: no "Busy, try again"; the waiting clicks go in one more commit
    { const api = new Github(); ['t_four', 't_five', 't_six'].forEach((id, i) => { api.files[`cards/${id}.json`] = text(card(id, 4 + i, `Shipped item ${4 + i}`, { column: 'done' })); });
      const page = await browser.newPage({ viewport: { width: 1280, height: 860 } }), errors = []; page.on('pageerror', e => errors.push(e.message));
      let hold = null, held = false, commits = 0;
      await page.addInitScript(init, 'board');
      await page.route('https://api.test/**', async r => { const req = r.request();
        if (req.method() === 'PATCH' && req.url().endsWith('/git/refs/heads/main')) { commits++; if (!held) { held = true; await new Promise(ok => { hold = ok; }); } }
        return api.route(r); });
      await page.goto(base + '/board/index.html'); await page.waitForSelector('.card');
      const doneCard = t => page.locator('.col[data-col="done"] .card', { hasText: t });
      await doneCard('Finished work').hover(); await doneCard('Finished work').locator('.quickarch').click();
      for (let i = 0; i < 50 && !hold; i++) await page.waitForTimeout(100);
      assert.ok(hold, 'the first archive commit is in flight');
      for (const t of ['Shipped item 4', 'Shipped item 5']) { await doneCard(t).hover(); await doneCard(t).locator('.quickarch').click(); }
      assert.equal(await doneCard('Shipped item 4').count() + await doneCard('Shipped item 5').count(), 0, 'queued cards leave the board at once');
      assert.equal(await page.locator('.ui-toast__text', { hasText: 'Busy' }).count(), 0, 'no Busy toast');
      hold();
      await page.getByText('Archived 3 cards', { exact: false }).waitFor();   // one rapid series of clicks: one toast, one Undo
      for (const id of ['t_two', 't_four', 't_five']) assert.equal(api.card(id), null, `${id} is archived`);
      assert.equal(commits, 2, 'the two waiting clicks were archived in one commit');
      const archiveFile = Object.keys(api.files).find(p => p.startsWith('archive/'));
      assert.deepEqual(JSON.parse(api.files[archiveFile]).tasks.map(t => t.id).sort(), ['t_five', 't_four', 't_two']);
      // Undo puts every card of the series back
      await page.getByRole('button', { name: 'Undo', exact: true }).click();
      for (let i = 0; i < 120 && (!api.card('t_two') || !api.card('t_four') || !api.card('t_five')); i++) await page.waitForTimeout(100);
      assert.ok(api.card('t_two') && api.card('t_four') && api.card('t_five'), 'Undo puts the whole series back');
      await doneCard('Shipped item 5').waitFor();
      // Archive all: asks first, Cancel does nothing, then one commit archives every Done card no agent holds
      await page.waitForTimeout(500); const before = commits;
      await page.locator('.col[data-col="done"] .harchall').click();
      const dlg = page.locator('dialog[open]'); await dlg.waitFor(); assert.match(await dlg.innerText(), /Archive 4 Done cards\?/); assert.match(await dlg.innerText(), /1 card an agent holds stays on the board/);
      await shot(page, 'archive-all-confirm');
      await dlg.getByRole('button', { name: 'Cancel' }).click(); await page.waitForTimeout(300); assert.equal(commits, before, 'Cancel archives nothing');
      await page.locator('.col[data-col="done"] .harchall').click(); await page.locator('dialog[open]').getByRole('button', { name: 'Archive all' }).click();
      await page.getByText('Archived 4 cards', { exact: false }).waitFor();
      for (const id of ['t_two', 't_four', 't_five', 't_six']) assert.equal(api.card(id), null, `${id} is archived`);
      assert.ok(api.card('t_three'), 'the card an agent holds stays'); assert.equal(commits, before + 1, 'Archive all is one commit');
      assert.equal(await page.locator('.col[data-col="todo"] .harchall').count(), 0, 'only the Done lane has Archive all');
      assert.deepEqual(errors, [], 'no page errors'); await page.close(); }

    // read-only demo board: no Archive buttons
    { const page = await browser.newPage({ viewport: { width: 1280, height: 860 } }); await page.addInitScript(() => { localStorage.setItem('kb_tour_seen', '1'); sessionStorage.setItem('kb_view', 'board'); }); await page.goto(base + '/board/index.html?demo=board'); await page.waitForSelector('.col[data-col="done"] .card');
      assert.equal(await page.locator('.quickarch').count(), 0, 'read-only boards have no Archive button'); assert.equal(await page.locator('.harchall').count(), 0, 'read-only boards have no Archive all'); await page.close(); }

    console.log('quick-archive: all checks passed');
  } finally { await browser.close(); server.close(); }
})().catch(e => { console.error(e); process.exit(1); });

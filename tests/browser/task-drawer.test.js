'use strict';
// The task drawer (#dlgCard) on a phone-width writable board with a faked GitHub API: every property, section and
// menu action saves the card, the layout never scrolls sideways at 390px, and read-only demo boards lock it.
// Run: node task-drawer.test.js   (SHOTS=<dir> also saves screenshots of the drawer)

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
const root = { version: 4, layout: 'split', settings: { title: 'Drawer test' }, columns: [{ id: 'todo', name: 'To do' }, { id: 'done', name: 'Done' }], people: [{ github: 'alex', name: 'Alex' }, { github: 'sam', name: 'Sam' }], agents: [], clients: ['Acme'], labels: [{ name: 'pale', color: '#dce1e7' }, { name: 'dark', color: '#334155' }], client_info: {}, next_num: 3, archive: { files: {} } };
const card = (id, num, title, extra) => ({ id, num, title, column: 'todo', client: '', priority: 'medium', due: '', labels: [], assignees: [], details: '', links: [], contacts: [], todos: [], comments: [], history: [], claim: null, created: '2026-10-01T08:00:00.000Z', updated: '2026-10-01T08:00:00.000Z', rank: 'a' + num, ...extra });

// A small GitHub: contents API for reads and single-file writes, git data API for multi-file commits (same shape as split-storage.test.js).
class Github {
  constructor() {
    this.files = { 'tasks.json': text(root), 'cards/t_one.json': text(card('t_one', 1, 'First', { client: 'Acme', priority: 'high', labels: ['pale', 'dark'], assignees: ['alex'] })), 'cards/t_two.json': text(card('t_two', 2, 'Second')) };
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
// the page must never scroll sideways, and every header control must sit inside the drawer
async function assertFits(page, where) {
  const m = await page.evaluate(() => {
    const d = document.getElementById('dlgCard'), r = d.getBoundingClientRect(), head = document.getElementById('cHead'), body = document.getElementById('cBody');
    const kids = [...head.children].filter(x => x.offsetParent !== null).map(x => { const b = x.getBoundingClientRect(); return { id: x.id || x.className, left: b.left, right: b.right, top: b.top, bottom: b.bottom }; });
    const hr = head.getBoundingClientRect();
    return { vw: window.innerWidth, docW: document.documentElement.scrollWidth, bodyScroll: body.scrollWidth - body.clientWidth, dRight: r.right, headH: hr.height, headTop: hr.top, kids };
  });
  assert(m.docW <= m.vw, `${where}: the page scrolls sideways (${m.docW} > ${m.vw})`);
  assert(m.bodyScroll <= 0, `${where}: the drawer body scrolls sideways by ${m.bodyScroll}px`);
  for (const k of m.kids) { assert(k.left >= 0 && k.right <= m.dRight + 0.5, `${where}: header item ${k.id} sticks out (${k.left}-${k.right})`); assert(k.top >= m.headTop - 0.5 && k.bottom <= m.headTop + m.headH + 0.5, `${where}: header item ${k.id} wraps to another line`); }
  assert(m.headH <= 64, `${where}: the header is one row (got ${m.headH}px)`);
}

(async () => {
  await new Promise(ok => server.listen(0, '127.0.0.1', ok)); base = `http://127.0.0.1:${server.address().port}`;
  const browser = await chromium.launch({ headless: true });
  try {
    const api = new Github();
    const page = await browser.newPage({ viewport: { width: 390, height: 844 } }); const errors = []; page.on('pageerror', e => errors.push(e.message));
    await page.addInitScript(() => { localStorage.setItem('kb_repo', 'acme/board'); localStorage.setItem('kb_branch', 'main'); localStorage.setItem('kb_path', 'board/tasks.json'); localStorage.setItem('kb_token', 'test'); localStorage.setItem('kb_me', 'alex'); localStorage.setItem('kb_api', 'https://api.test'); localStorage.setItem('kb_layout', 'classic'); localStorage.setItem('kb_tour_seen', '1'); sessionStorage.setItem('kb_view', 'board'); });
    await page.route('https://api.test/**', r => api.route(r)); await page.goto(base + '/board/index.html'); await page.waitForSelector('.card');
    await page.evaluate(() => { window.__copied = ''; Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText: async t => { window.__copied = t; } } }); });
    const saved = () => page.waitForResponse(r => ['PUT', 'PATCH', 'DELETE'].includes(r.request().method()) && r.url().startsWith('https://api.test/repos/acme/board/'));
    const confirmSheet = page.locator('dialog.ui-sheet--alert[open]');

    // a #number in the address opens the card
    await page.evaluate(() => { location.hash = '#1'; }); await page.locator('#dlgCard[open]').waitFor();
    assert.equal(await page.locator('#cTitle').inputValue(), 'First');
    assert.equal(await page.locator('#dNum').textContent(), '#1');
    assert.deepEqual(await page.locator('#cHead button').evaluateAll(xs => xs.map(x => x.getAttribute('aria-label'))), ['Task #1, copy link', 'Undo last board change', 'Copy for agent', 'More actions', 'Close']);
    assert.deepEqual(await page.locator('#cProps .ui-props__label').allTextContents(), ['Status', 'Priority', 'Due', 'People', 'Client', 'Project', 'Labels']);
    assert.deepEqual(await page.locator('#cSecs .ui-section__text').allTextContents(), ['Description', 'Checklist', 'Links', 'Contacts', 'Comments', 'History']);
    assert.equal(await page.locator('#cHist').isVisible(), false, 'History starts closed');
    await assertFits(page, 'opened'); await shot(page, 'phone-writable-top');

    // number pill copies a link to the card
    await page.locator('#dNum').click(); await page.waitForFunction(() => window.__copied);
    assert.match(await page.evaluate(() => window.__copied), /\/board\/index\.html#1$/);

    // priority (with its colour), due date (overdue is red), then clear it
    let w = saved(); await page.locator('#cPrio').selectOption('low'); await w; assert.equal(api.card().priority, 'low');
    assert.match(await page.locator('#cPrio').evaluate(x => x.parentElement.className), /ui-select--ok/);
    w = saved(); await page.locator('#cDue').fill('2026-01-05'); await w; assert.equal(api.card().due, '2026-01-05');
    assert.match(await page.locator('#cDuePill').getAttribute('class'), /ui-pill--danger/);
    assert.equal(await page.locator('#cDueBtn').innerText(), '5 Jan · overdue', 'the pill reads like every other date (ui.due), not the input locale format');
    assert.equal(await page.locator('#cDueClear').isVisible(), true);
    // the pill opens the native picker: by click and by keyboard; without showPicker the native field itself shows and takes the focus
    await page.evaluate(() => { window.__picks = 0; HTMLInputElement.prototype.showPicker = function () { window.__picks++; }; });
    await page.locator('#cDueBtn').click(); await page.locator('#cDueBtn').focus(); await page.keyboard.press('Enter');
    assert.equal(await page.evaluate(() => window.__picks), 2, 'click and Enter open the date picker');
    await page.evaluate(() => { HTMLInputElement.prototype.showPicker = function () { throw new Error('not allowed'); }; });
    await page.locator('#cDueBtn').click();
    assert.equal(await page.evaluate(() => document.activeElement.id), 'cDue', 'fallback: the native date field takes the focus');
    assert.match(await page.locator('#cDuePill').getAttribute('class'), /ddue--edit/);
    await page.locator('#cDueBtn').evaluate(() => document.activeElement.blur());
    assert.doesNotMatch(await page.locator('#cDuePill').getAttribute('class'), /ddue--edit/);
    w = saved(); await page.locator('#cDueClear').click(); await w; assert.equal(api.card().due, ''); assert.equal(await page.locator('#cDueClear').isVisible(), false);

    // people: the pill's x unassigns, the "+ Add" menu lists members and the agent options
    w = saved(); await page.locator('#cWho .ui-pill__remove').click(); await w; assert.deepEqual(api.card().assignees, []);
    await page.locator('#cWhoAdd').click(); const menu = page.locator('.ui-menu');
    assert.deepEqual(await menu.locator('[role=menuitem]').allTextContents(), ['Alex (@alex)', 'Sam (@sam)', 'Set up your Claude agent…']);
    w = saved(); await menu.locator('[role=menuitem]', { hasText: 'Sam' }).click(); await w; assert.deepEqual(api.card().assignees, ['sam']);
    assert.deepEqual(await page.locator('#cWho .ui-pill__text').allTextContents(), ['Sam']);

    // labels: remove asks first (Cancel keeps it), add with the inline field
    await page.locator('#cLabelChips [aria-label="Remove label pale"]').click(); await confirmSheet.waitFor();
    await confirmSheet.locator('button', { hasText: 'Cancel' }).click(); await confirmSheet.waitFor({ state: 'detached' }); assert.deepEqual(api.card().labels, ['pale', 'dark']);
    await page.locator('#cLabelChips [aria-label="Remove label pale"]').click(); w = saved(); await confirmSheet.locator('button', { hasText: 'Remove' }).click(); await w; assert.deepEqual(api.card().labels, ['dark']);
    await page.locator('#cLabelAdd').click(); await page.locator('#cLabelNew').fill('urgent'); w = saved(); await page.locator('#cLabelNew').press('Enter'); await w; assert.deepEqual(api.card().labels, ['dark', 'urgent']);
    assert.ok(JSON.parse(api.files['tasks.json']).labels.some(l => l.name === 'urgent'), 'a new label joins the board labels');

    // client and project: "New …" asks for a name in a sheet
    await page.locator('#cClient').selectOption('__new'); const prompt = page.locator('dialog.ui-sheet--alert[open]'); await prompt.waitFor();
    await prompt.locator('input').fill('Beta Ltd'); w = saved(); await prompt.locator('button', { hasText: 'Add client' }).click(); await w;
    assert.equal(api.card().client, 'Beta Ltd'); assert.ok(JSON.parse(api.files['tasks.json']).clients.includes('Beta Ltd'));
    await page.locator('#cProject').selectOption('__new'); await prompt.waitFor(); await prompt.locator('input').fill('Launch'); w = saved(); await prompt.locator('button', { hasText: 'Add project' }).click(); await w;
    const proj = api.card().project; assert.ok(proj, 'the task gets the new project'); assert.equal(await page.locator('#cProject').inputValue(), proj);

    // checklist, links and contacts: empty sections show one ghost add row
    for (const sec of ['#cTodoSec', '#cLinkSec', '#cContactSec']) { assert.equal(await page.locator(`${sec} .ui-addrow__ghost`).isVisible(), true); assert.equal(await page.locator(`${sec} .ui-addrow__form`).isVisible(), false); }
    await page.locator('#cTodoSec .ui-addrow__ghost').click(); await page.locator('#cTodoNew').fill('Write the test'); w = saved(); await page.locator('#cTodoNew').press('Enter'); await w;
    assert.deepEqual(api.card().todos.map(d => [d.text, d.done]), [['Write the test', false]]);
    await page.locator('#cTodos .dtodo').waitFor(); w = saved(); await page.locator('#cTodos input[type=checkbox]').check(); await w; assert.equal(api.card().todos[0].done, true);
    assert.equal(await page.locator('#cTodoCount').textContent(), '1/1');
    await page.locator('#cLinkSec .ui-addrow__ghost').click(); assert.equal(await page.locator('#cLinkSec .dhint').isVisible(), true, 'the link help shows while adding');
    await page.locator('#cLinkNew').fill('Spec | https://example.com/spec'); w = saved(); await page.locator('#cLinkNew').press('Enter'); await w;
    assert.deepEqual(api.card().links, [{ title: 'Spec', url: 'https://example.com/spec' }]);
    assert.equal(await page.locator('#cLinkList a.ui-listrow__main').getAttribute('href'), 'https://example.com/spec');
    await page.locator('#cLinkNew').fill('not a link'); await page.locator('#cLinkNew').press('Enter'); assert.equal(await page.locator('#cLinkNew').inputValue(), 'not a link', 'a bad link stays in the box');
    await page.locator('#cLinkNew').press('Escape'); assert.equal(await page.locator('#dlgCard').getAttribute('open'), '', 'Escape in an add row only closes the row');
    await page.locator('#cContactSec .ui-addrow__ghost').click(); await page.locator('#cContactNew').fill('Casey | buyer | casey@example.com'); w = saved(); await page.locator('#cContactNew').press('Enter'); await w;
    assert.deepEqual(api.card().contacts, [{ name: 'Casey', role: 'buyer', email: 'casey@example.com', phone: '' }]);
    assert.equal(await page.locator('#cContactList a[href="mailto:casey@example.com"]').count(), 1);
    await page.locator('#cLinkList [aria-label="Remove link Spec"]').click(); w = saved(); await confirmSheet.locator('button', { hasText: 'Remove' }).click(); await w; assert.deepEqual(api.card().links, []);

    // status last: moving to Done shows who completed it in the Status row
    w = saved(); await page.locator('#cCol').selectOption('done'); await w; assert.equal(api.card().column, 'done');
    await page.locator('#cCompletedBy').waitFor(); assert.match(await page.locator('#cCompletedBy').textContent(), /^Completed by /);

    // description and comments still save; History opens
    await page.locator('#cDescBtn').click(); await page.locator('#cDetails').fill('Some detail'); w = saved(); await page.locator('#cDescSave').click(); await w; assert.equal(api.card().details, 'Some detail');
    await page.locator('#cmText').fill('Looks good'); w = saved(); await page.locator('#cmPost').click(); await w; assert.equal(api.card().comments.at(-1).text, 'Looks good');
    assert.equal(await page.locator('#cmCount').textContent(), '1');
    await page.locator('#cHistWrap .ui-section__toggle').click(); assert.equal(await page.locator('#cHist').isVisible(), true);
    await page.locator('#cBody').evaluate(b => { b.scrollTop = b.scrollHeight; });
    await assertFits(page, 'after edits'); await shot(page, 'phone-writable-bottom');
    await page.locator('#cBody').evaluate(b => { b.scrollTop = 0; }); await shot(page, 'phone-writable-top-filled');
    if (SHOTS) { await page.setViewportSize({ width: 1280, height: 860 }); await shot(page, 'desktop-writable-top'); await page.locator('#cBody').evaluate(b => { b.scrollTop = b.scrollHeight; }); await shot(page, 'desktop-writable-bottom'); await page.setViewportSize({ width: 390, height: 844 }); await page.locator('#cBody').evaluate(b => { b.scrollTop = 0; }); }

    // the ⋯ menu
    await page.locator('#dMore').click();
    assert.deepEqual(await menu.locator('[role=menuitem]').allTextContents(), ['Copy link', 'Copy reference #1', 'Create GitHub issue', 'Copy as Markdown', 'Delete task']);
    await shot(page, 'phone-writable-menu');
    await menu.locator('[role=menuitem]', { hasText: 'Copy as Markdown' }).click(); await page.waitForFunction(() => /First/.test(window.__copied));
    await page.locator('#cAgent').click(); await page.waitForFunction(() => /You are working from the Keeptrack board|#1/.test(window.__copied) && !/^#/.test(window.__copied));

    // Escape closes the drawer and clears the address; the hash opens it again
    await page.keyboard.press('Escape'); await page.locator('#dlgCard').waitFor({ state: 'hidden' }); await page.waitForFunction(() => location.hash === '');   // the close event clears it a moment after the drawer hides
    await page.evaluate(() => { location.hash = '#1'; }); await page.locator('#dlgCard[open]').waitFor();
    assert.equal(await page.locator('#cTodoSec .ui-addrow__form').isVisible(), false, 'add rows start closed on every open');

    // delete: Cancel keeps the task, Delete removes its card file
    await page.locator('#dMore').click(); await menu.locator('[role=menuitem]', { hasText: 'Delete task' }).click(); await confirmSheet.waitFor();
    await confirmSheet.locator('button', { hasText: 'Cancel' }).click(); await confirmSheet.waitFor({ state: 'detached' }); assert.ok(api.card(), 'Cancel keeps the task');
    assert.equal(await page.locator('#dlgCard').getAttribute('open'), '');
    await page.locator('#dMore').click(); await menu.locator('[role=menuitem]', { hasText: 'Delete task' }).click(); await confirmSheet.waitFor();
    w = saved(); await confirmSheet.locator('button.ui-btn--danger').click(); await w; await page.waitForFunction(() => !document.getElementById('dlgCard').open);
    for (let i = 0; i < 50 && api.card(); i++) await page.waitForTimeout(100);
    assert.equal(api.card(), null, 'the deleted card file is gone');
    assert.deepEqual(await page.locator('.card .t').allTextContents(), ['Second']);
    assert.deepEqual(errors, [], 'no page errors');
    await page.close();

    // read-only demo board: fields are disabled, add/remove controls hidden, copy actions still work, no Delete
    for (const vp of [{ width: 390, height: 844 }, { width: 1280, height: 860 }]) {
      const demo = await browser.newPage({ viewport: vp }); await demo.addInitScript(() => { try { localStorage.setItem('kb_tour_seen', '1'); } catch {} });
      await demo.goto(base + '/board/index.html?demo=board'); await demo.locator('#roBar').waitFor();
      await demo.getByText('Fix the broken link on the pricing page').first().click(); await demo.locator('#dlgCard[open]').waitFor(); await demo.waitForTimeout(100);
      assert.equal(await demo.locator('#cCol').isDisabled(), true); assert.equal(await demo.locator('#cTitle').isDisabled(), true);
      assert.equal(await demo.locator('#cWhoAdd').isVisible(), false); assert.equal(await demo.locator('#cLabelAdd').isVisible(), false); assert.equal(await demo.locator('#dlgCard .ui-pill__remove:visible').count(), 0);
      assert.equal(await demo.locator('#cTodoSec').isVisible(), false, 'an empty checklist is hidden when nothing can be added');
      for (const id of ['dNum', 'cAgent', 'dMore', 'cClose']) assert.equal(await demo.locator('#' + id).isEnabled(), true, id + ' stays usable');
      await demo.locator('#dMore').click(); const items = await demo.locator('.ui-menu [role=menuitem]').allTextContents(); assert.ok(!items.includes('Delete task')); assert.ok(items.includes('Copy as Markdown'));
      assert.equal(await demo.locator('.ui-menu [role=menuitem]', { hasText: 'Copy link' }).isEnabled(), true);
      await demo.keyboard.press('Escape'); await assertFits(demo, `read-only ${vp.width}px`); await shot(demo, `readonly-${vp.width}`);
      await demo.close();
    }

    // Release claim while a different claim arrives (the confirm no longer blocks the page): the newer claim must survive.
    {
      const api = new Github(); const c = api.card(); const at = new Date().toISOString();
      c.claim = { agent: 'codex', on_behalf_of: 'alex', session_id: 'A', status: 'stuck', note: 'old', claimed_at: at, heartbeat_at: at }; api.files['cards/t_one.json'] = text(c);
      const page = await browser.newPage({ viewport: { width: 1280, height: 860 } });
      await page.addInitScript(() => { localStorage.setItem('kb_repo', 'acme/board'); localStorage.setItem('kb_branch', 'main'); localStorage.setItem('kb_path', 'board/tasks.json'); localStorage.setItem('kb_token', 'test'); localStorage.setItem('kb_me', 'alex'); localStorage.setItem('kb_api', 'https://api.test'); localStorage.setItem('kb_layout', 'classic'); localStorage.setItem('kb_tour_seen', '1'); sessionStorage.setItem('kb_view', 'board'); });
      await page.route('https://api.test/**', r => api.route(r)); await page.goto(base + '/board/index.html'); await page.waitForSelector('.card');
      await page.evaluate(() => { location.hash = '#1'; }); await page.locator('#dlgCard[open]').waitFor();
      await page.locator('#cRelease').click(); const sheet = page.locator('dialog.ui-sheet--alert[open]'); await sheet.waitFor();
      const c1 = api.card(), now = new Date().toISOString(); c1.claim = { agent: 'claude', on_behalf_of: 'sam', session_id: 'B', status: 'running', note: 'new run by sam', claimed_at: now, heartbeat_at: now }; c1.updated = now; api.files['cards/t_one.json'] = text(c1); api.head = 'head-' + ++api.n;   // a new commit, so the board's next poll picks it up
      await page.waitForFunction(() => /new run by sam/.test(document.getElementById('cClaimWrap').textContent), null, { timeout: 60000 });
      await sheet.locator('button', { hasText: 'Release claim' }).click();
      await page.locator('.ui-toast', { hasText: 'Nothing was released' }).waitFor();
      assert.equal(api.card().claim && api.card().claim.session_id, 'B', 'the newer claim is kept');
      await page.close();
    }


    // The Back button closes what was opened and returns to the board, never to the page before it.
    {
      const p = await browser.newPage({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true }); await p.addInitScript(() => { try { localStorage.setItem('kb_tour_seen', '1'); } catch {} });
      await p.goto(base + '/board/ui.html'); await p.goto(base + '/board/index.html?demo=board'); await p.locator('#roBar').waitFor({ state: 'visible' });
      const at = () => p.evaluate(() => ({ page: location.pathname.split('/').pop(), hash: location.hash, card: document.getElementById('dlgCard').open, len: history.length }));
      const openCard = async () => { await p.getByText('Fix the broken link on the pricing page').first().click(); await p.locator('#dlgCard[open]').waitFor(); };
      const len0 = (await at()).len;
      await openCard(); assert.match((await at()).hash, /^#\d+$/, 'an open card is in the address');
      await p.goBack(); await p.locator('#dlgCard').waitFor({ state: 'hidden' });
      assert.deepEqual(await at(), { page: 'index.html', hash: '', card: false, len: len0 + 1 }, 'Back closes the card and stays on the board');
      await openCard(); await p.keyboard.press('Escape'); await p.locator('#dlgCard').waitFor({ state: 'hidden' });
      await p.waitForFunction(() => !(history.state || {}).kbDlg);
      await openCard(); await p.locator('#cClose').click(); await p.locator('#dlgCard').waitFor({ state: 'hidden' }); await p.waitForFunction(() => !(history.state || {}).kbDlg);
      assert.equal((await at()).len, len0 + 1, 'closing with Escape or X leaves no extra history entries');
      await p.evaluate(() => document.getElementById('btnSettings').click()); await p.locator('#dlgSettings[open]').waitFor();
      await p.goBack(); await p.locator('#dlgSettings').waitFor({ state: 'hidden' }); assert.equal((await at()).page, 'index.html', 'Back closes Settings');
      await p.goto(base + '/board/index.html?demo=board#2'); await p.locator('#dlgCard[open]').waitFor();
      await p.goBack(); await p.locator('#dlgCard').waitFor({ state: 'hidden' });
      const d = await at(); assert.ok(d.page === 'index.html' && d.hash === '', 'Back from a #2 link goes to the board');
      await p.close();
    }

    console.log('task-drawer: all checks passed');
  } finally { await browser.close(); server.close(); }
})().catch(e => { console.error(e); process.exit(1); });

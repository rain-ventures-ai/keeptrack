'use strict';
// Card #290: Companies sort and contact filter, deep links to a company, person and project (#company=, #person=,
// #project=), a contact log entry's source link (opens in a new tab), and the person record's activity per project.
// Run: node crm-links.test.js   (SHOTS=<dir> also saves screenshots)

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
const stamp = '2026-10-01T08:00:00.000Z';
const root = { version: 4, layout: 'split', settings: { title: 'CRM links test' }, columns: [{ id: 'todo', name: 'To do' }, { id: 'done', name: 'Done' }], people: [{ github: 'alex', name: 'Alex' }], agents: [], clients: ['Acme'], labels: [],
  client_info: { Acme: { north_star: '', links: [] } }, next_num: 2, archive: { files: {} } };
const project = { id: 'pr_one', client: 'Acme', name: 'Launch', north_star: '', status: 'active', links: [], people: [], created: stamp, updated: stamp };
const card = { id: 't_one', num: 1, title: 'Kick-off', column: 'todo', client: 'Acme', project: 'pr_one', priority: 'medium', due: '', labels: [], assignees: [], details: '', links: [], contacts: [], todos: [], comments: [], history: [], claim: null, created: stamp, updated: stamp, rank: 'a1' };
const person = { id: 'p_one', name: 'Casey Example', company: 'Acme', role: 'Buyer', stage: 'New', value: '', source: '', notes: '', next: '', next_due: '', emails: [{ id: 'e1', label: 'Work', value: 'casey@acme.test' }], phones: [], links: [], comments: [], history: [], created: stamp, updated: stamp };

// A small GitHub: contents API for reads and single-file writes, git data API for multi-file commits (as in task-drawer.test.js).
class Github {
  constructor() { this.files = { 'tasks.json': text(root), 'cards/t_one.json': text(card), 'people/p_one.json': text(person), 'projects/pr_one.json': text(project) }; this.head = 'head-1'; this.n = 1; this.blobs = {}; this.pending = null; }
  sha(p) { return crypto.createHash('sha1').update(this.files[p] || '').digest('hex'); }
  async route(route) {
    const req = route.request(), u = new URL(req.url()), method = req.method(), p = u.pathname.replace('/repos/acme/board', '');
    const json = (body, status = 200, headers = {}) => route.fulfill({ status, headers: { 'Content-Type': 'application/json', ...headers }, body: JSON.stringify(body) });
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
  person() { return this.files['people/p_one.json'] ? JSON.parse(this.files['people/p_one.json']) : null; }
  root() { return JSON.parse(this.files['tasks.json']); }
  projects() { return [...(this.root().projects || []), ...Object.keys(this.files).filter(f => f.startsWith('projects/')).map(f => JSON.parse(this.files[f]))]; }   // split boards keep one file per project
  project(id = 'pr_one') { return this.projects().find(p => p.id === id) || null; }
}

let base;
const shot = async (page, name) => { if (SHOTS) { fs.mkdirSync(SHOTS, { recursive: true }); await page.waitForTimeout(250); await page.screenshot({ path: path.join(SHOTS, name + '.png') }); } };
const INIT = () => { window.__copied = ''; Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText: async t => { window.__copied = t; } } }); localStorage.setItem('kb_repo', 'acme/board'); localStorage.setItem('kb_branch', 'main'); localStorage.setItem('kb_path', 'board/tasks.json'); localStorage.setItem('kb_token', 'test'); localStorage.setItem('kb_me', 'alex'); localStorage.setItem('kb_api', 'https://api.test'); localStorage.setItem('kb_layout', 'classic'); localStorage.setItem('kb_tour', 'done'); localStorage.setItem('kb_tour_seen', '1'); sessionStorage.setItem('kb_view', 'companies'); };
const day = n => new Date(Date.now() - n * 86400000).toISOString();

(async () => {
  await new Promise(ok => server.listen(0, '127.0.0.1', ok)); base = `http://127.0.0.1:${server.address().port}`;
  const browser = await chromium.launch({ headless: true });
  try {
    const api = new Github();
    // Acme: contacted 2 days ago, changed 40 days ago. Beta: contacted 60 days ago, changed today. Zed Co: never contacted.
    api.files['people/p_one.json'] = text({ ...person, updated: day(40), comments: [{ id: 'c_mail', at: day(2), by: 'alex', channel: 'email', text: 'Email received: confirmed the call.', draft: false, url: 'https://mail.google.com/mail/u/0/?authuser=private%40example.test#inbox/18f2a01c9be0d4a1' },
      { id: 'c_call', at: day(3), by: 'alex', channel: 'call', text: 'Called about pricing.', draft: false }] });
    api.files['people/p_two.json'] = text({ ...person, id: 'p_two', name: 'Bo Beta', company: 'Beta', emails: [], updated: day(0), comments: [{ id: 'c_old', at: day(60), by: 'alex', channel: 'email', text: 'Old email', draft: false, url: 'javascript:alert(1)' }, { id: 'c_look', at: day(59), by: 'alex', channel: 'note', text: 'Look-alike', draft: false, url: 'https://mail.google.evil.example/x' }] });
    api.files['people/p_three.json'] = text({ ...person, id: 'p_three', name: 'Zoe Zed', company: 'Zed Co', emails: [], updated: day(10), comments: [] });
    api.files['projects/pr_one.json'] = text({ ...project, updated: day(40), people: ['casey@acme.test'] });
    api.files['cards/t_one.json'] = text({ ...card, updated: day(40), comments: [{ id: 'k1', at: day(1), by: 'alex', text: 'Sent the launch plan to Casey' }], history: [{ at: day(5), by: 'alex', text: 'created' }] });
    const page = await browser.newPage({ viewport: { width: 1280, height: 860 } }), errors = [], native = [];
    page.on('pageerror', e => errors.push(e.message)); page.on('dialog', d => { native.push(d.message()); d.dismiss().catch(() => {}); });
    await page.addInitScript(INIT); await page.route('https://api.test/**', r => api.route(r));
    await page.goto(base + '/board/index.html'); await page.waitForSelector('.crow');
    const names = () => page.locator('.crow .pwho b').allTextContents();
    const rows = n => page.waitForFunction(n => document.querySelectorAll('.crow').length === n, n);
    const saved = () => page.waitForResponse(r => ['PUT', 'PATCH', 'DELETE'].includes(r.request().method()) && r.url().startsWith('https://api.test/repos/acme/board/'));

    // ---- Companies: sort and contact filter ----
    assert.deepEqual(await page.locator('.companiesv .pbar select').evaluateAll(xs => xs.map(x => x.getAttribute('aria-label'))), ['Filter by stage', 'Filter by last contact', 'Sort companies']);
    const sort = page.locator('select[aria-label="Sort companies"]'), seen = page.locator('select[aria-label="Filter by last contact"]');
    assert.equal(await sort.inputValue(), 'stage', 'stage order by default, as before');
    await sort.selectOption('name'); await page.waitForFunction(() => document.querySelector('.crow .pwho b').textContent === 'Acme');
    assert.deepEqual(await names(), ['Acme', 'Beta', 'Zed Co']);
    await sort.selectOption('contacted'); assert.deepEqual(await names(), ['Acme', 'Beta', 'Zed Co'], 'most recently contacted first, never contacted last');
    await sort.selectOption('updated'); assert.deepEqual(await names(), ['Beta', 'Zed Co', 'Acme'], 'most recently changed first (people, tasks, projects)');
    assert.match(await page.locator('.crow[data-company="Beta"] .plast').textContent(), /^updated 0d ago$/);
    await seen.selectOption('never'); await rows(1); assert.deepEqual(await names(), ['Zed Co']);
    await seen.selectOption('30d'); await rows(1); assert.deepEqual(await names(), ['Acme']);
    await seen.selectOption('quiet'); await rows(1); assert.deepEqual(await names(), ['Beta']);
    await shot(page, 'companies-sort-filter-1280');
    await page.reload(); await page.waitForSelector('.crow');
    assert.equal(await page.locator('select[aria-label="Sort companies"]').inputValue(), 'updated', 'the sort is remembered');
    assert.equal(await page.locator('select[aria-label="Filter by last contact"]').inputValue(), 'quiet', 'and the contact filter');
    await page.locator('select[aria-label="Filter by last contact"]').selectOption(''); await rows(3);

    // ---- deep links: opening a record puts it in the address; the link opens it again ----
    await page.locator('.crow[data-company="Acme"] .pwho b').click(); await page.locator('#dlgClient[open]').waitFor();
    assert.equal(await page.evaluate(() => location.hash), '#company=Acme');
    await page.locator('#clMore').click(); await page.locator('.ui-menu [role=menuitem]', { hasText: 'Copy link' }).click();
    const coLink = await page.evaluate(() => window.__copied); assert.match(coLink, /\?repo=acme%2Fboard&branch=main&path=board%2Ftasks\.json.*#company=Acme$/);
    // the company record's activity: the email opens Gmail in a new tab; an unsafe link is never a link
    const open = page.locator('#clActivity a.tsrclink'); assert.equal(await open.count(), 1);
    assert.equal((await open.textContent()).trim(), 'Open in Gmail'); assert.equal(await open.getAttribute('target'), '_blank'); assert.equal(await open.getAttribute('rel'), 'noopener noreferrer');
    assert.equal(await open.getAttribute('href'), 'https://mail.google.com/mail/u/0/#all/18f2a01c9be0d4a1');
    await page.locator('#clPeople .dperson').first().click(); await page.locator('#dlgContact[open]').waitFor();
    assert.equal(await page.evaluate(() => location.hash), '#person=p_one', 'person → its own address');
    await page.locator('#pMore').click(); await page.locator('.ui-menu [role=menuitem]', { hasText: 'Copy link' }).click();
    assert.match(await page.evaluate(() => window.__copied), /#person=p_one$/);

    // ---- person record: source links and project activity ----
    assert.equal(await page.locator('#pTouches a.tsrclink').count(), 1);
    assert.equal(await page.locator('#pTouches .touch').nth(0).locator('button[aria-label^="Add source link"]').count(), 1, 'an entry without a link offers to add one');
    await page.locator('#pTouches .touch').nth(0).locator('button[aria-label^="Add source link"]').click();
    const sheet = page.locator('dialog.ui-sheet[open]'); await sheet.locator('input').fill('not a link'); await sheet.locator('button[type=submit], button', { hasText: 'Save' }).first().click();
    await page.waitForFunction(() => [...document.querySelectorAll('.ui-toast, .toast')].some(x => /https:/.test(x.textContent)));
    assert.equal(api.person().comments[1].url, undefined, 'a bad link is refused, nothing saved');
    await page.locator('#pTouches .touch').nth(0).locator('button[aria-label^="Add source link"]').click();
    await sheet.locator('input').fill('HTTPS://MAIL.GOOGLE.COM/mail/u/0/?authuser=private%40example.test#sent/FMfcgzABCDEFGHIJKLMNOPQRSTUVWXyz'); let w = saved(); await sheet.locator('button', { hasText: 'Save' }).first().click(); await w;
    assert.equal(api.person().comments[1].url, 'https://mail.google.com/mail/u/0/#all/FMfcgzABCDEFGHIJKLMNOPQRSTUVWXyz');
    await page.waitForFunction(() => document.querySelectorAll('#pTouches a.tsrclink').length === 2);
    assert.equal(await page.locator('#pProjActSec').isVisible(), true);
    assert.deepEqual(await page.locator('#pProjAct .projact .ui-listrow__text').allTextContents(), ['Launch']);
    const evs = await page.locator('#pProjAct .projact__ev').allTextContents();
    assert.equal(evs.length, 2); assert.match(evs[0], /^#1alex: Sent the launch plan to Casey1d/); assert.match(evs[1], /^#1created/);
    await page.locator('#pProjActSec').scrollIntoViewIfNeeded(); await shot(page, 'person-project-activity-1280');
    await page.locator('#pProjAct .projact__ev').first().click(); await page.locator('#dlgCard[open]').waitFor();
    await page.keyboard.press('Escape'); await page.waitForFunction(() => !document.querySelector('#dlgCard[open]'));
    await page.evaluate(() => document.querySelectorAll('dialog[open]').forEach(d => d.close()));

    // ---- opening each link in a fresh page opens the record ----
    for (const [hash, dlg, check] of [['#company=Acme', 'dlgClient', p => p.locator('#clName').textContent()], ['#person=p_two', 'dlgContact', p => p.locator('#pName').inputValue()], ['#project=pr_one', 'dlgProject', p => p.locator('#prName').inputValue()]]) {
      const pg = await browser.newPage({ viewport: { width: 390, height: 844 } }); const errs = []; pg.on('pageerror', e => errs.push(e.message));
      await pg.addInitScript(INIT); await pg.route('https://api.test/**', r => api.route(r));
      await pg.goto(base + '/board/index.html?repo=acme%2Fboard&branch=main&path=board%2Ftasks.json' + hash); await pg.locator(`#${dlg}[open]`).waitFor();
      assert.equal(await check(pg), { '#company=Acme': 'Acme', '#person=p_two': 'Bo Beta', '#project=pr_one': 'Launch' }[hash], hash + ' opens its record');
      if (hash === '#person=p_two') { assert.equal(await pg.locator('#pTouches a.tsrclink').count(), 1, 'a javascript: link is never shown as a link'); assert.equal((await pg.locator('#pTouches a.tsrclink').textContent()).trim(), 'Open original', 'only mail.google.com itself reads Open in Gmail'); }
      if (hash === '#project=pr_one') { await pg.locator('#prMore').click(); await pg.locator('.ui-menu [role=menuitem]', { hasText: 'Copy link' }).waitFor(); await pg.keyboard.press('Escape'); }
      await shot(pg, 'deeplink-' + dlg + '-390');
      assert.equal(await pg.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true, hash + ' fits at 390px');
      assert.deepEqual(errs, [], hash + ': no page errors'); await pg.close();
    }
    { const pg = await browser.newPage({ viewport: { width: 390, height: 844 } }); await pg.addInitScript(INIT); await pg.route('https://api.test/**', r => api.route(r));
      await pg.goto(base + '/board/index.html#person=p_gone'); await pg.waitForFunction(() => [...document.querySelectorAll('.ui-toast, .toast')].some(x => /person was not found/.test(x.textContent)));
      assert.equal(await pg.locator('#dlgContact[open]').count(), 0); assert.match(await pg.evaluate(() => location.hash), /^#view=/, 'a missing record leaves the address'); await pg.goto(base + '/board/index.html'); await pg.waitForSelector('.crow');
      await shot(pg, 'companies-390'); assert.equal(await pg.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true, 'Companies bar fits at 390px'); await pg.close(); }
    // ---- Back from a record opened by its link goes to the board; X leaves no record in the address ----
    { const pg = await browser.newPage({ viewport: { width: 1280, height: 860 } }); const errs = []; pg.on('pageerror', e => errs.push(e.message));
      await pg.addInitScript(INIT); await pg.route('https://api.test/**', r => api.route(r));
      await pg.goto(base + '/board/index.html#company=Acme'); await pg.locator('#dlgClient[open]').waitFor(); await pg.waitForTimeout(300);
      assert.equal(await pg.evaluate(() => location.hash), '#company=Acme');
      await pg.goBack(); await pg.locator('#dlgClient').waitFor({ state: 'hidden' }); await pg.waitForTimeout(500);
      assert.equal(await pg.locator('#dlgClient[open]').count(), 0, 'Back closes the record and it stays closed');
      assert.match(await pg.evaluate(() => location.hash), /^#view=/, 'Back lands on the board');
      await pg.goForward(); await pg.locator('#dlgClient[open]').waitFor(); assert.equal(await pg.evaluate(() => location.hash), '#company=Acme', 'Forward opens it again');
      await pg.goto(base + '/board/index.html#person=p_one'); await pg.locator('#dlgContact[open]').waitFor(); await pg.waitForTimeout(300);
      await pg.locator('#pClose').click(); await pg.locator('#dlgContact').waitFor({ state: 'hidden' }); await pg.waitForTimeout(500);
      assert.match(await pg.evaluate(() => location.hash), /^#view=/, 'X leaves the board address, not the record');
      await pg.reload(); await pg.waitForSelector('.crow'); await pg.waitForTimeout(500);
      assert.equal(await pg.locator('#dlgContact[open]').count(), 0, 'a reload after X does not reopen it');
      assert.deepEqual(errs, [], 'Back/X: no page errors'); await pg.close(); }
    // Pagination, nested labels and search views are not individual Gmail threads.
    for (const fragment of ['label/Clients/0123456789abcdef', 'search/private/FMfcgzABCDEFGHIJKLMNOPQRSTUVWXyz', 'category/0123456789abcdef', 'inbox/p2/0123456789abcdef', 'all/0123456789abcdef/extra', 'all/0123456789abcdef/', 'inbox/p2', 'search/private%40example.test/p2', 'label/Clients/Acme', 'search/from%3Aacme/renewal', 'search/private/ImportantRenewalNotesFromPrivateClient']) {
      const pagination = new Github();
      pagination.files['people/p_one.json'] = text({ ...person, comments: [{ id: 'c_page', at: day(0), by: 'alex', channel: 'email', text: 'Original reference.' }] });
      const pg = await browser.newPage({ viewport: { width: 1280, height: 860 } });
      await pg.addInitScript(INIT); await pg.route('https://api.test/**', r => pagination.route(r));
      await pg.goto(base + '/board/index.html#person=p_one'); await pg.locator('#dlgContact[open]').waitFor();
      await pg.locator('#pTouches button[aria-label^="Add source link"]').click();
      const form = pg.locator('dialog.ui-sheet[open]');
      await form.locator('input').fill('https://mail.google.com/mail/u/0/#' + fragment);
      await form.locator('button', { hasText: 'Save' }).first().click();
      await pg.waitForFunction(() => [...document.querySelectorAll('.ui-toast, .toast')].some(x => /https:/.test(x.textContent)));
      assert.equal(pagination.person().comments[0].url, undefined, 'ambiguous Gmail views never become stored thread links');
      assert.equal(pagination.head, 'head-1', 'refusing a sensitive source does not silently write a URL-less edit');
      assert.equal(await pg.locator('#pTouches a.tsrclink').count(), 0);
      await pg.close();
    }
    // Canonical mailbox routes retain short legacy hexadecimal thread IDs too.
    for (const id of ['a', 'abc123']) {
      const canonical = new Github();
      canonical.files['people/p_one.json'] = text({ ...person, comments: [{ id: 'c_short', at: day(0), by: 'alex', channel: 'email', text: 'Reference.' }] });
      const pg = await browser.newPage(); await pg.addInitScript(INIT); await pg.route('https://api.test/**', r => canonical.route(r));
      await pg.goto(base + '/board/index.html#person=p_one'); await pg.locator('#dlgContact[open]').waitFor();
      await pg.locator('#pTouches button[aria-label^="Add source link"]').click();
      const form = pg.locator('dialog.ui-sheet[open]');
      await form.locator('input').fill('https://mail.google.com/mail/u/0/#inbox/' + id);
      const written = pg.waitForResponse(r => ['PUT', 'PATCH'].includes(r.request().method()) && r.url().startsWith('https://api.test/repos/acme/board/'));
      await form.locator('button', { hasText: 'Save' }).first().click();
      await pg.waitForFunction(() => document.querySelector('#pTouches a.tsrclink'));
      assert.equal(await pg.locator('#pTouches a.tsrclink').getAttribute('href'), 'https://mail.google.com/mail/u/0/#all/' + id);
      await written;
      assert.equal(canonical.person().comments[0].url, 'https://mail.google.com/mail/u/0/#all/' + id);
      await pg.close();
    }
    // Rejected old sources show a neutral warning without exposing private route text.
    {
      const old = new Github();
      old.files['people/p_one.json'] = text({ ...person, comments: [{ id: 'c_old', at: day(0), by: 'alex', channel: 'email', text: 'Reference.', url: 'https://mail.google.com/mail/#label/PrivateClient/0123456789abcdef' }] });
      const pg = await browser.newPage(); await pg.addInitScript(INIT); await pg.route('https://api.test/**', r => old.route(r));
      await pg.goto(base + '/board/index.html#person=p_one'); await pg.locator('#dlgContact[open]').waitFor();
      assert.equal(await pg.locator('#pTouches a.tsrclink').count(), 0);
      assert.match(await pg.locator('#pTouches').textContent(), /Source link unavailable/);
      assert.doesNotMatch(await pg.locator('#pTouches').textContent(), /PrivateClient/);
      assert.equal(old.head, 'head-1', 'displaying a rejected old URL does not rewrite it');
      await pg.close();
    }
    // A Forward entry for a deleted person must not keep an old drawer marker.
    {
      const missing = new Github(); missing.files = { ...api.files };
      const pg = await browser.newPage({ viewport: { width: 1280, height: 860 } });
      await pg.addInitScript(INIT); await pg.route('https://api.test/**', r => missing.route(r));
      await pg.goto(base + '/board/index.html#view=people');
      await pg.locator('.prow', { hasText: 'Casey Example' }).click();
      await pg.locator('#dlgContact[open]').waitFor();
      assert.equal((await pg.evaluate(() => history.state)).kbDlg, 'dlgContact');
      await pg.goBack(); await pg.locator('#dlgContact').waitFor({ state: 'hidden' });
      delete missing.files['people/p_one.json']; missing.head = 'head-person-removed';
      await pg.reload(); await pg.locator('.prow', { hasText: 'Bo Beta' }).waitFor();
      await pg.goForward();
      await pg.waitForFunction(() => [...document.querySelectorAll('.ui-toast, .toast')].some(x => /person was not found/.test(x.textContent)));
      assert.deepEqual(await pg.evaluate(() => history.state), { kbView: 'people' }, 'missing record clears old drawer/depth state');
      const length = await pg.evaluate(() => history.length);
      await pg.locator('.prow', { hasText: 'Bo Beta' }).click(); await pg.locator('#dlgContact[open]').waitFor();
      assert.equal(await pg.evaluate(() => history.length), length + 1, 'next person creates its own history entry');
      await pg.goBack(); await pg.locator('#dlgContact').waitFor({ state: 'hidden' });
      assert.equal(await pg.evaluate(() => location.hash), '#view=people');
      await pg.close();
    }
    assert.deepEqual(errors, [], 'no page errors'); assert.deepEqual(native, [], 'no native dialogs');
    console.log('crm-links: all checks passed');
  } finally { await browser.close(); server.close(); }
})().catch(e => { console.error(e); process.exit(1); });

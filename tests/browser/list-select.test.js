'use strict';
// List multi-select, last activity, and the description under the title (kit v97–v98).
// One tick box selects rows. The bar can move them, mark them done, copy "#150 #96" and clear.
// The description is plain text under the title (markdown and line breaks joined, two lines).
// Activity is the newest of updated, comments and history (ago2); 14 days with nothing marks the row.
// Run: node list-select.test.js

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

const DAY = 864e5;
const ago = ms => new Date(Date.now() - ms).toISOString();
const text = x => JSON.stringify(x, null, 2) + '\n';
const root = { version: 4, layout: 'split', settings: { title: 'List select', modes: ['tasks'] }, columns: [{ id: 'todo', name: 'To do' }, { id: 'in-progress', name: 'In progress' }, { id: 'done', name: 'Done' }], people: [{ github: 'alex', name: 'Alex' }], agents: [], clients: ['Acme'], labels: [], client_info: {}, next_num: 200, archive: { files: {} } };
function card(id, num, title, column, rank, extra) {
  return { id, num, title, column, client: 'Acme', priority: 'medium', due: '', labels: [], assignees: ['alex'], details: 'A useful outcome for this fictional task, long enough to wrap in the description.', links: [], contacts: [], todos: [], comments: [], history: [], claim: null, created: ago(30 * DAY), updated: ago(20 * DAY), rank, ...extra };
}
function files() {
  const cards = {
    'cards/t_a.json': card('t_a', 150, 'Write the spring newsletter', 'todo', 'a0', { details: '# Now\n\n**Then** the real outcome for this fictional task.\n- A later bullet that must stay visible', comments: [{ id: 'c1', at: ago(3 * DAY), by: 'alex', text: 'Draft is with the client' }], history: [{ at: ago(10 * DAY), by: 'alex', text: 'moved to To do' }] }),
    'cards/t_b.json': card('t_b', 96, 'Fix the contact form', 'todo', 'a1', { updated: ago(2 * 60 * 60 * 1000) }),
    'cards/t_c.json': card('t_c', 12, 'Retire the old landing page', 'todo', 'a2'),
    'cards/t_d.json': card('t_d', 7, 'Confirm the workshop date', 'in-progress', 'a3', { comments: [{ id: 'c2', at: ago(8 * DAY), by: 'alex', text: 'Asked Sam' }], history: [{ at: ago(DAY), by: 'alex', text: 'note added' }] }),
  };
  const person = { id: 'p_alex', name: 'Alex', github: 'alex', company: 'Acme', role: '', emails: [], phones: [], links: [], comments: [], history: [], stage: 'New', created: ago(30 * DAY), updated: ago(DAY) };
  return { 'tasks.json': text(root), ...Object.fromEntries(Object.entries(cards).map(([k, v]) => [k, text(v)])), 'people/p_alex.json': text(person) };
}

class Github {
  constructor() { this.files = files(); this.head = 'head-1'; this.n = 1; this.blobs = {}; this.pending = null; }
  sha(p) { return crypto.createHash('sha1').update(this.files[p] || '').digest('hex'); }
  tree() { return Object.entries(this.files).map(([p, content]) => ({ path: p, type: 'blob', sha: this.sha(p), size: Buffer.byteLength(content) })); }
  async route(route) {
    const req = route.request(), u = new URL(req.url()), method = req.method(), p = u.pathname.replace('/repos/acme/board', '');
    const json = (body, status = 200, headers = {}) => route.fulfill({ status, headers: { 'Content-Type': 'application/json', ...headers }, body: JSON.stringify(body) });
    if (p === '/user' && method === 'GET') return json({ login: 'alex' });
    if (p.startsWith('/contents/board/KIT_VERSION') && method === 'GET') return route.fulfill({ status: 200, body: '98' });
    if (p.startsWith('/user/repos') && method === 'GET') return json([]);
    if (p === '' && method === 'GET') return json({ full_name: 'acme/board', private: true, permissions: { push: true }, default_branch: 'main' });
    if (p.startsWith('/contents/README.md')) return json({ message: 'Not Found' }, 404);
    if (p.startsWith('/contents/board/tasks.json') && method === 'GET') return json({ sha: this.sha('tasks.json'), size: Buffer.byteLength(this.files['tasks.json']), encoding: 'base64', content: Buffer.from(this.files['tasks.json']).toString('base64') }, 200, { ETag: '"tasks"' });
    if (p.startsWith('/contents/board/') && method === 'PUT') { const rel = p.slice('/contents/board/'.length), b = req.postDataJSON(); this.files[rel] = Buffer.from(b.content, 'base64').toString(); this.head = 'head-' + ++this.n; return json({ content: { sha: this.sha(rel) }, commit: { sha: this.head } }); }
    if (p === '/git/ref/heads/main' && method === 'GET') return json({ object: { sha: this.head } }, 200, { ETag: '"' + this.head + '"' });
    if (p.startsWith('/git/commits/') && method === 'GET') return json({ tree: { sha: 'root-' + this.n } });
    if (p.startsWith('/git/trees/root-') && method === 'GET') return json({ tree: [{ path: 'board', type: 'tree', sha: 'board-' + this.n }] });
    if (p.startsWith('/git/trees/board-') && method === 'GET') return json({ truncated: false, tree: this.tree() });
    if (p.startsWith('/git/blobs/') && method === 'GET') { const sha = p.split('/').pop(), rel = Object.keys(this.files).find(x => this.sha(x) === sha); return json({ encoding: 'base64', content: Buffer.from(this.files[rel] || '').toString('base64') }); }
    if (p === '/git/blobs' && method === 'POST') { const sha = 'new-blob-' + ++this.n; this.blobs[sha] = req.postDataJSON().content; return json({ sha }); }
    if (p === '/git/trees' && method === 'POST') { this.pending = req.postDataJSON().tree; return json({ sha: 'new-tree-' + ++this.n }); }
    if (p === '/git/commits' && method === 'POST') return json({ sha: 'new-commit-' + ++this.n });
    if (p === '/git/refs/heads/main' && method === 'PATCH') { for (const e of this.pending || []) { const rel = e.path.replace(/^board\//, ''); if (e.sha === null) delete this.files[rel]; else this.files[rel] = this.blobs[e.sha]; } this.head = req.postDataJSON().sha; return json({ object: { sha: this.head } }); }
    return json({ message: 'not mocked: ' + method + ' ' + p }, 404);
  }
}

const seed = () => {
  localStorage.setItem('kb_repo', 'acme/board'); localStorage.setItem('kb_branch', 'main'); localStorage.setItem('kb_path', 'board/tasks.json'); localStorage.setItem('kb_token', 'test'); localStorage.setItem('kb_me', 'alex'); localStorage.setItem('kb_api', 'https://api.test'); localStorage.setItem('kb_layout', 'classic'); localStorage.setItem('kb_theme', 'light'); localStorage.setItem('kb_tour', 'done'); sessionStorage.setItem('kb_view', 'list');
};

let base;
(async () => {
  await new Promise(ok => server.listen(0, '127.0.0.1', ok)); base = 'http://127.0.0.1:' + server.address().port;
  const browser = await chromium.launch({ headless: true });
  const shots = process.env.SHOTS || '/tmp';
  try {
    const api = new Github();
    const page = await browser.newPage({ viewport: { width: 1280, height: 860 } });
    await page.context().grantPermissions(['clipboard-read', 'clipboard-write']);
    const errors = []; page.on('pageerror', e => errors.push(e.message));
    await page.addInitScript(seed);
    await page.route('https://api.test/**', route => api.route(route));
    await page.goto(base + '/board/index.html');
    await page.locator('#listPrioritise').waitFor();
    await page.locator('[data-list-task="t_a"]').waitFor();

    assert.equal(await page.locator('[data-list-task] .donetick').count(), 0, 'List has no per-row mark-done control');
    assert.equal(await page.locator('.trow .c-check').count(), 0, 'the select box is the only box');
    assert.equal(await page.locator('.circ').count(), 0);
    const blurb = page.locator('[data-list-task="t_a"] .ldesc');
    assert.match(await blurb.innerText(), /Now Then the real outcome for this fictional task\. A later bullet that must stay visible/);
    assert.equal(await blurb.evaluate(el => getComputedStyle(el).webkitLineClamp), '2');
    assert.match(await page.locator('.trow.thead .c-activity').first().innerText(), /Activity/);
    assert.equal(/Description/.test(await page.locator('.trow.thead').first().innerText()), false);

    const activity = id => page.locator(`[data-list-task="${id}"] .c-activity .lact`).innerText();
    assert.equal(await activity('t_a'), '3d ago', 'newest of comment, history and updated');
    assert.equal(await activity('t_b'), '2h ago');
    assert.equal(await activity('t_c'), '20d ago');
    assert.equal(await activity('t_d'), '1d ago', 'history newer than the comment and the edit');
    assert.equal(await page.locator('[data-list-task="t_c"]').evaluate(el => el.classList.contains('is-stale')), true);
    assert.equal(await page.locator('[data-list-task="t_a"]').evaluate(el => el.classList.contains('is-stale')), false, 'a newer comment keeps the row fresh');
    assert.match(await page.locator('[data-list-task="t_a"] .c-activity time').getAttribute('title'), /^Last activity \d{4}-\d{2}-\d{2} /);

    await page.locator('[data-list-task="t_a"] .lt').click();
    await page.locator('#dlgCard').waitFor({ state: 'visible' });
    await page.keyboard.press('Escape');
    await page.locator('#dlgCard').waitFor({ state: 'hidden' });
    await page.locator('[data-list-task="t_a"] [data-list-select]').click();
    assert.equal(await page.locator('#dlgCard').isVisible(), false, 'selecting a row does not open it');
    await page.locator('[data-list-task="t_b"] [data-list-select]').click();
    await page.locator('.lbulk').waitFor();
    assert.match(await page.locator('.lbulk__count').innerText(), /2 selected/);
    await page.screenshot({ path: path.join(shots, 'kt-v97-list-desktop.png') });

    await page.locator('[data-list-bulk="copy"]').click();
    await page.waitForFunction(() => /Copied #150 #96/.test(document.body.textContent));
    assert.equal(await page.evaluate(() => navigator.clipboard.readText()), '#150 #96');

    const all = page.locator('[data-list-select-all="l:todo"]');
    await all.click();
    assert.equal(await page.locator('[data-list-task="t_a"] [data-list-select], [data-list-task="t_b"] [data-list-select], [data-list-task="t_c"] [data-list-select]').evaluateAll(els => els.every(el => el.checked)), true);
    assert.match(await page.locator('.lbulk__count').innerText(), /3 selected/);
    await all.click();
    assert.equal(await page.locator('.lbulk').count(), 0, 'clearing the header box clears that table');

    await page.locator('[data-list-task="t_a"] [data-list-select]').click();
    await page.locator('[data-list-task="t_b"] [data-list-select]').click();
    await page.locator('[data-list-bulk="clear"]').click();
    assert.equal(await page.locator('.lbulk').count(), 0);

    await page.locator('[data-list-task="t_a"] [data-list-select]').click();
    await page.locator('[data-list-task="t_b"] [data-list-select]').click();
    const before = api.head;
    await page.locator('[data-list-bulk="move"]').selectOption('in-progress');
    await page.waitForFunction(() => /^Saved /.test(document.getElementById('status').textContent));
    assert.notEqual(api.head, before);
    assert.equal(JSON.parse(api.files['cards/t_a.json']).column, 'in-progress');
    assert.equal(JSON.parse(api.files['cards/t_b.json']).column, 'in-progress');
    assert.equal(await page.locator('.lbulk').count(), 0, 'a move clears the selection');
    assert.equal(await page.locator('[data-col="in-progress"] [data-list-task="t_a"]').count(), 1);

    const doneHead = api.head;
    await page.locator('[data-list-task="t_c"] [data-list-select]').click();
    await page.locator('[data-list-bulk="done"]').click();
    for (let i = 0; i < 100 && api.head === doneHead; i++) await page.waitForTimeout(50);
    assert.notEqual(api.head, doneHead, 'mark done commits');
    await page.waitForFunction(() => /^Saved /.test(document.getElementById('status').textContent));
    assert.equal(JSON.parse(api.files['cards/t_c.json']).column, 'done');

    await page.locator('[data-list-task="t_d"] [data-list-select]').click();
    await page.locator('.lbulk').waitFor();
    await page.locator('#viewSw [data-view="board"]').click();
    await page.waitForFunction(() => document.body.dataset.view === 'board');
    await page.locator('#viewSw [data-view="list"]').click();
    await page.locator('#listPrioritise').waitFor();
    assert.equal(await page.locator('.lbulk').count(), 0, 'leaving List clears the selection');
    assert.equal(await page.locator('[data-list-task="t_d"] [data-list-select]').isChecked(), false);
    assert.deepEqual(errors, []);

    const phone = await browser.newPage({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
    const phoneErrors = []; phone.on('pageerror', e => phoneErrors.push(e.message));
    const phoneApi = new Github();
    await phone.addInitScript(seed);
    await phone.route('https://api.test/**', route => phoneApi.route(route));
    await phone.goto(base + '/board/index.html');
    await phone.locator('[data-list-task="t_a"]').waitFor();
    assert.equal(await phone.locator('[data-list-task="t_a"] .c-activity').evaluate(el => getComputedStyle(el).display), 'none');
    assert.equal(await phone.locator('[data-list-task="t_a"] .lmeta .lact').innerText(), '3d ago');
    assert.equal(await phone.locator('[data-list-task="t_c"] .lmeta .lact').innerText(), '20d ago');
    assert.equal(await phone.locator('[data-list-task="t_c"] .lmeta .lact').evaluate(el => el.classList.contains('stale')), true);
    assert.equal(await phone.locator('[data-list-task="t_a"] .lmeta').evaluate(el => getComputedStyle(el).display), 'flex', 'activity sits in the phone meta row');
    await phone.locator('[data-list-task="t_d"] [data-list-select]').click();
    await phone.locator('.lbulk').waitFor();
    await phone.screenshot({ path: path.join(shots, 'kt-v97-list-phone.png') });
    assert.deepEqual(phoneErrors, []);
    await phone.close();

    const roPage = await browser.newPage({ viewport: { width: 1280, height: 860 } });
    const roErrors = []; roPage.on('pageerror', e => roErrors.push(e.message));
    const roApi = new Github();
    await roPage.addInitScript(() => { localStorage.setItem('kb_ro:acme/board', '1'); });
    await roPage.addInitScript(seed);
    await roPage.route('https://api.test/**', route => roApi.route(route));
    await roPage.goto(base + '/board/index.html');
    await roPage.locator('[data-list-task="t_a"]').waitFor();
    await roPage.locator('[data-list-task="t_a"] [data-list-select]').click();
    await roPage.locator('.lbulk').waitFor();
    assert.equal(await roPage.locator('[data-list-bulk="move"]').isDisabled(), true);
    assert.equal(await roPage.locator('[data-list-bulk="done"]').isDisabled(), true);
    assert.equal(await roPage.locator('[data-list-bulk="copy"]').isDisabled(), false);
    assert.equal(await roPage.locator('[data-list-bulk="clear"]').isDisabled(), false);
    assert.deepEqual(roErrors, []);
    await roPage.close();
    await page.close();
  } finally {
    await browser.close();
    server.close();
  }
  console.log('list-select ok');
})().catch(err => { console.error(err); process.exit(1); });

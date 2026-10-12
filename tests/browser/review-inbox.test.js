'use strict';
// Review Inbox (kit v41): proposals live in board/proposals/<id>.json and never reach the live board until accepted.
// GitHub is mocked with content SHAs, commit parents and fast-forward-only ref updates, so races behave like GitHub.

const assert = require('node:assert/strict');
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { chromium } = require('playwright');

const ROOT = path.resolve(__dirname, '../..');
const mime = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json', '.svg': 'image/svg+xml', '.webmanifest': 'application/manifest+json' };
const server = http.createServer((req, res) => {
  const rel = decodeURIComponent(new URL(req.url, 'http://local').pathname).replace(/^\/+/, '') || 'board/index.html';
  const file = path.resolve(ROOT, rel); if (!file.startsWith(ROOT + path.sep)) { res.writeHead(403).end(); return; }
  fs.readFile(file, (err, data) => { if (err) res.writeHead(404).end(); else { res.setHeader('Content-Type', mime[path.extname(file)] || 'application/octet-stream'); res.end(data); } });
});

const text = x => JSON.stringify(x, null, 2) + '\n';
const T0 = '2026-10-01T08:00:00.000Z';
const root = (enabled = true) => ({ version: 4, layout: 'split', settings: { title: 'Acme board', review_inbox: { enabled } }, columns: [{ id: 'todo', name: 'To do' }, { id: 'done', name: 'Done' }],
  people: [{ github: 'alex', name: 'Alex' }, { github: 'sam', name: 'Sam' }], agents: ['codex'], clients: ['Acme'], labels: [], client_info: {}, next_num: 3, archive: { files: {} } });
const card = (id, num, title, extra = {}) => ({ id, num, title, column: 'todo', client: 'Acme', priority: 'medium', due: '', labels: [], assignees: [], details: '', links: [], contacts: [], todos: [], comments: [], history: [], claim: null, created: T0, updated: T0, rank: 'a' + num, ...extra });
const person = { id: 'p_casey', name: 'Casey Example', company: 'Acme', role: '', email: 'casey@example.invalid', phone: '', linkedin: '', stage: 'New', value: '', source: '', notes: '', next: '', next_due: '', links: [], comments: [], history: [], created: T0, updated: T0 };
const meeting = { kind: 'meeting', id: 'doc-acme-weekly', revision: '7', title: 'Acme weekly', date: '2026-10-08', url: 'https://example.invalid/notes/acme-weekly' };
const email = { kind: 'email', id: 'rfc822:' + 'b'.repeat(64), revision: '1', title: '', date: '2026-10-09', url: '' };
const prop = (id, kind, title, extra = {}) => ({ id, version: 1, kind, status: 'pending', title, source: meeting, run: { routine: 'meeting-notes', run_id: 'run-1', at: '2026-10-08T18:00:00Z' },
  action_key: 'ak-' + id, work_key: 'wk-' + id, reason: 'Agreed in the meeting.', target: null, change: { title }, likely_duplicates: [], decision: null,
  history: [{ at: '2026-10-08T18:00:00Z', by: 'codex@alex', text: 'proposed' }], created: '2026-10-08T18:00:00Z', createdBy: 'codex@alex', ...extra });

function fixture({ enabled = true } = {}) {
  const files = {
    'tasks.json': root(enabled),
    'cards/t_first.json': card('t_first', 1, 'First'),
    'cards/t_second.json': card('t_second', 2, 'Second', { comments: [{ id: 'c_old', at: T0, by: 'alex', text: 'Existing comment' }], todos: [{ id: 'd_old', text: 'Existing item', done: true }], history: [{ at: T0, by: 'alex', text: 'created' }] }),
    'people/p_casey.json': person,
    'proposals/r_create0001.json': prop('r_create0001', 'task.create', 'Send the revised plan', { change: { title: 'Send the revised plan', client: 'Acme', owner: 'alex', due: '2026-10-20' }, reviewer: 'alex' }),
    'proposals/r_update0001.json': prop('r_update0001', 'task.update', 'Raise priority of First', { target: { type: 'task', id: 't_first', base: { priority: 'medium' } }, change: { priority: 'high' } }),
    'proposals/r_merge00001.json': prop('r_merge00001', 'task.create', 'Second', { change: { title: 'Second', comments: [{ text: 'From the meeting' }], todos: [{ text: 'Book the room' }] }, likely_duplicates: [{ type: 'task', id: 't_second', why: 'same title and client' }] }),
    'proposals/r_editme0001.json': prop('r_editme0001', 'task.create', 'Draft the summary', { change: { title: 'Draft the summary', client: 'Acme' } }),
    'proposals/r_touch00001.json': prop('r_touch00001', 'contact.touch', 'Email from Casey Example, 9 Oct', { source: email, reason: '', run: { routine: 'contact-email', run_id: 'run-9', at: '2026-10-09T07:00:00Z' }, target: { type: 'person', id: 'p_casey', base: {} }, change: { text: '', channel: 'email', source_id: email.id } }),
    'proposals/r_ignored001.json': prop('r_ignored001', 'task.create', 'An old idea', { status: 'ignored', decision: { action: 'ignore', by: 'sam', at: '2026-10-02T09:00:00Z', result: null, commit: null } }),
  };
  return Object.fromEntries(Object.entries(files).map(([k, v]) => [k, text(v)]));
}

// A GitHub with real commit parents: a ref update that is not a fast-forward is refused (422), like force:false.
class Github {
  constructor(files) { this.files = files; this.head = 'c1'; this.n = 1; this.calls = []; this.blobs = {}; this.trees = {}; this.commits = { c1: { files: { ...files } } }; }
  sha(p) { return crypto.createHash('sha1').update(this.files[p] || '').digest('hex'); }
  bump() { this.head = 'c' + ++this.n; this.commits[this.head] = { files: { ...this.files } }; }
  writes() { return this.calls.filter(c => ['PUT', 'PATCH', 'DELETE', 'POST'].includes(c.method)); }
  edit(rel, fn) { const o = JSON.parse(this.files[rel]); fn(o); this.files[rel] = text(o); this.bump(); }   // someone else commits
  json(rel) { return JSON.parse(this.files[rel]); }
  async route(route) {
    const req = route.request(), u = new URL(req.url()), method = req.method(), p = u.pathname.replace('/repos/acme/board', ''); this.calls.push({ method, path: p, body: req.postDataJSON?.() });
    const json = (body, status = 200, headers = {}) => route.fulfill({ status, headers: { 'Content-Type': 'application/json', ...headers }, body: JSON.stringify(body) });
    if (p === '/user') return json({ login: 'alex' });
    if (p.startsWith('/user/repos')) return json([]);
    if (p === '' && method === 'GET') return json({ full_name: 'acme/board', private: true, permissions: { push: true }, default_branch: 'main' });
    if (p.startsWith('/contents/board/tasks.json') && method === 'GET') return json({ sha: this.sha('tasks.json'), size: this.files['tasks.json'].length, encoding: 'base64', content: Buffer.from(this.files['tasks.json']).toString('base64') });
    if (p.startsWith('/contents/board/') && method === 'PUT') { const rel = p.slice('/contents/board/'.length), b = req.postDataJSON();
      if ((b.sha || null) !== (this.files[rel] ? this.sha(rel) : null)) return json({ message: 'sha does not match' }, 409);
      const parent = this.head; this.files[rel] = Buffer.from(b.content, 'base64').toString(); this.bump(); return json({ content: { sha: this.sha(rel) }, commit: { sha: this.head, parents: [{ sha: parent }], tree: { sha: 'root-' + this.head } } }); }
    if (p.startsWith('/contents/')) return json({ message: 'Not Found' }, 404);
    if (p === '/git/ref/heads/main' && method === 'GET') return json({ object: { sha: this.head } }, 200, { ETag: '"' + this.head + '"' });
    if (p.startsWith('/git/commits/') && method === 'GET') return json({ tree: { sha: 'root-' + p.split('/').pop() } });
    if (p.startsWith('/git/trees/root-') && method === 'GET') return json({ tree: [{ path: 'board', type: 'tree', sha: 'board-' + p.split('root-')[1] }] });
    if (p.startsWith('/git/trees/board-') && method === 'GET') { const c = this.commits[p.split('board-')[1].split('?')[0]] || { files: this.files }, f = c.files;
      return json({ truncated: false, tree: Object.entries(f).map(([k, v]) => ({ path: k, type: 'blob', sha: crypto.createHash('sha1').update(v).digest('hex'), size: Buffer.byteLength(v) })) }); }
    if (p.startsWith('/git/blobs/') && method === 'GET') { const sha = p.split('/').pop(), all = Object.values(this.commits).flatMap(c => Object.values(c.files)).concat(Object.values(this.files));
      const v = all.find(x => crypto.createHash('sha1').update(x).digest('hex') === sha); return json({ encoding: 'base64', content: Buffer.from(v).toString('base64') }); }
    if (p === '/git/blobs' && method === 'POST') { const b = req.postDataJSON(), sha = 'blob-' + Object.keys(this.blobs).length; this.blobs[sha] = b.content; return json({ sha }); }
    if (p === '/git/trees' && method === 'POST') { const b = req.postDataJSON(), sha = 'tree-' + Object.keys(this.trees).length; this.trees[sha] = b.tree; return json({ sha }); }
    if (p === '/git/commits' && method === 'POST') { const b = req.postDataJSON(), sha = 'new-' + crypto.randomBytes(4).toString('hex'); this.commits[sha] = { parent: b.parents[0], tree: this.trees[b.tree] }; return json({ sha }); }
    if (p === '/git/refs/heads/main' && method === 'PATCH') { const b = req.postDataJSON(), c = this.commits[b.sha];
      if (!c || c.parent !== this.head) return json({ message: 'Update is not a fast forward' }, 422);
      for (const e of c.tree) { const rel = e.path.replace(/^board\//, ''); if (e.sha === null) delete this.files[rel]; else this.files[rel] = this.blobs[e.sha]; }
      this.head = b.sha; c.files = { ...this.files }; return json({ object: { sha: this.head } }); }
    return json({ message: 'not mocked: ' + method + ' ' + p }, 404);
  }
}

let base;
async function openBoard(browser, api, opts = {}) {
  const page = await browser.newPage(opts.viewport ? { viewport: opts.viewport, isMobile: !!opts.mobile, hasTouch: !!opts.mobile } : {});
  page.on('pageerror', e => console.error('page error:', e.message));
  await page.addInitScript(([view, me]) => { localStorage.setItem('kb_repo', 'acme/board'); localStorage.setItem('kb_branch', 'main'); localStorage.setItem('kb_path', 'board/tasks.json'); localStorage.setItem('kb_token', 'test'); localStorage.setItem('kb_me', me); localStorage.setItem('kb_api', 'https://api.test'); localStorage.setItem('kb_layout', 'classic'); sessionStorage.setItem('kb_view', view); }, [opts.view || 'board', opts.me || 'alex']);
  await page.route('https://api.test/**', r => api.route(r)); await page.goto(base + '/board/index.html');
  await page.waitForFunction(() => /Synced/.test(document.querySelector('#status').textContent));
  return page;
}
const inbox = async page => { await page.locator('#btnInbox').click(); await page.waitForSelector('#board.v-inbox .inbox'); };
const propCard = (page, id) => page.locator(`article.prop[data-id="${id}"]`);
const clearLive = page => page.evaluate(() => { const l = document.querySelector('#inboxLive'); if (l) l.textContent = ''; });
const said = (page, re) => page.waitForFunction(r => { const l = document.querySelector('#inboxLive'); return l && new RegExp(r).test(l.textContent); }, re.source);
async function decide(page, id, act, re = /Accepted|Ignored|Merged|Already|Not saved/) { await clearLive(page); await propCard(page, id).locator(`[data-act="${act}"]`).click(); await said(page, re); }

(async () => {
  await new Promise(ok => server.listen(0, '127.0.0.1', ok)); base = `http://127.0.0.1:${server.address().port}`;
  const browser = await chromium.launch({ headless: true });
  try {
    // Off by default: no Inbox button, and proposal files never become cards.
    { const api = new Github(fixture({ enabled: false })), page = await openBoard(browser, api);
      assert.equal(await page.locator('#btnInbox').isHidden(), true, 'the Inbox stays hidden while the board has it off');
      assert.deepEqual((await page.locator('.card .t').allTextContents()).sort(), ['First', 'Second']);
      await page.close(); }

    const api = new Github(fixture()), page = await openBoard(browser, api);
    // Pending proposals are not live work: Kanban shows only the two real cards, with a count of 2.
    assert.deepEqual((await page.locator('.card .t').allTextContents()).sort(), ['First', 'Second']);
    assert.equal(await page.locator('.col[data-col="todo"] h2 .ui-count').first().textContent(), '2');
    assert.equal(await page.locator('#btnInbox').isVisible(), true);
    assert.equal(await page.locator('#inboxBadge').textContent(), '5', 'five proposals are pending');
    assert(!api.calls.some(c => /git\/trees\/root-.*recursive/.test(c.path)), 'never reads the whole repository tree');

    await inbox(page);
    const groups = await page.locator('.inbox__src').allTextContents();
    assert.equal(groups.length, 2, 'grouped by source: the meeting and the email'); assert(groups.some(g => /Meeting: Acme weekly/.test(g))); assert(groups.some(g => /Email: an email/.test(g)));
    assert.equal(await page.locator('.inbox__run').count(), 2, 'and by extraction run');
    const createCard = propCard(page, 'r_create0001');
    assert.match(await createCard.textContent(), /Owner\s*alex/); assert.match(await createCard.textContent(), /Due\s*2026-10-20/);
    assert.match(await propCard(page, 'r_editme0001').textContent(), /OwnerNot stated/, 'an owner that the source did not state is shown as not stated');
    assert.match(await propCard(page, 'r_merge00001').textContent(), /Looks like: Second/);
    assert.match(await propCard(page, 'r_update0001').locator('table').textContent(), /priority\s*medium\s*high/, 'updates show current against proposed');
    // Filters: type and source.
    await page.selectOption('[data-filter="kind"]', 'contact.touch'); assert.equal(await page.locator('article.prop').count(), 1); await page.selectOption('[data-filter="kind"]', '');
    await page.selectOption('[data-filter="source"]', 'email'); assert.equal(await page.locator('article.prop').count(), 1); await page.selectOption('[data-filter="source"]', '');
    await page.selectOption('[data-filter="status"]', 'ignored'); assert.equal(await page.locator('article.prop').count(), 1); await page.selectOption('[data-filter="status"]', 'pending');

    // A second reviewer has the Inbox open on the same revision.
    const other = await openBoard(browser, api, { view: 'inbox', me: 'sam' }); await other.waitForSelector('article.prop');

    // Accept: exactly one new card, and the card and the decided proposal arrive in ONE fast-forward commit.
    api.calls = []; await decide(page, 'r_create0001', 'accept');
    const patches = api.calls.filter(c => c.method === 'PATCH'); assert.equal(patches.length, 1, JSON.stringify(api.writes().map(c => c.method + ' ' + c.path)));
    const committed = api.calls.filter(c => c.path === '/git/trees' && c.method === 'POST').pop().body.tree.map(e => e.path).sort();
    const created = api.json('proposals/r_create0001.json');
    assert.equal(created.status, 'accepted'); assert.equal(created.decision.by, 'alex'); assert.match(created.decision.result.id, /^t_[0-9a-z]{10}$/);
    assert(committed.includes('board/proposals/r_create0001.json') && committed.includes(`board/cards/${created.decision.result.id}.json`), committed.join(','));
    const newCard = api.json(`cards/${created.decision.result.id}.json`);
    assert.equal(newCard.title, 'Send the revised plan'); assert.deepEqual(newCard.assignees, ['alex']); assert.equal(newCard.due, '2026-10-20');
    assert.equal(Object.keys(api.files).filter(k => k.startsWith('cards/')).length, 3, 'exactly one card was added');

    // The other reviewer accepts the same proposal: nothing is written twice.
    api.calls = []; await propCard(other, 'r_create0001').locator('[data-act="accept"]').click();
    await other.waitForFunction(() => /Already accepted by alex/.test(document.querySelector('#inboxLive').textContent));
    assert.equal(api.writes().length, 0, 'a decided proposal is never applied again');
    assert.equal(Object.keys(api.files).filter(k => k.startsWith('cards/')).length, 3);
    await other.close();

    // Undo the accept (Undo button): the card goes, the proposal is pending again; nothing else changes.
    await page.locator('#btnUndo').click(); await page.waitForFunction(() => /pending again/.test(document.querySelector('#inboxLive') ? document.querySelector('#inboxLive').textContent : ''));
    assert.equal(api.json('proposals/r_create0001.json').status, 'pending'); assert(!api.files[`cards/${created.decision.result.id}.json`], 'undo removed the created card');

    // Accept again after someone edited the card meanwhile: undo is refused, later edits stay.
    await decide(page, 'r_create0001', 'accept'); const again = api.json('proposals/r_create0001.json').decision.result.id;
    assert.equal(again, created.decision.result.id, 'the result id comes from the proposal id, so a retry can never make a second card');
    api.edit(`cards/${again}.json`, t => { t.details = 'Edited later by Sam'; t.updated = '2026-10-10T10:00:00.000Z'; });
    await page.selectOption('[data-filter="status"]', 'accepted'); await propCard(page, 'r_create0001').locator('[data-act="undo"]').click();
    await page.waitForFunction(() => /changed after it was accepted/.test(document.querySelector('#inboxLive').textContent));
    assert.equal(api.json(`cards/${again}.json`).details, 'Edited later by Sam'); await page.selectOption('[data-filter="status"]', 'pending');

    // A changed target: the reviewer sees the conflict, and Cancel writes nothing.
    api.edit('cards/t_first.json', t => { t.priority = 'low'; });
    api.calls = []; await propCard(page, 'r_update0001').locator('[data-act="accept"]').click();
    const conf = page.getByRole('alertdialog'); await conf.waitFor(); assert.match(await conf.textContent(), /priority.*medium.*low.*high/s);
    await conf.getByRole('button', { name: 'Cancel' }).click(); await page.waitForFunction(() => /still pending/.test(document.querySelector('#inboxLive').textContent));
    assert.equal(api.writes().length, 0); assert.equal(api.json('cards/t_first.json').priority, 'low');
    // ... and choosing "Proposed" applies it on the newest revision.
    await propCard(page, 'r_update0001').locator('[data-act="accept"]').click(); await conf.waitFor();
    await clearLive(page); await conf.getByLabel('Proposed').check(); await conf.getByRole('button', { name: 'Accept with these choices' }).click(); await said(page, /Accepted/);
    assert.equal(api.json('cards/t_first.json').priority, 'high'); assert.equal(api.json('proposals/r_update0001.json').status, 'accepted');

    // Edit & accept: the edited values are saved and recorded.
    await propCard(page, 'r_editme0001').locator('[data-act="edit"]').click();
    const form = propCard(page, 'r_editme0001').locator('form'); await form.getByLabel('title').fill('Draft the Acme summary');
    await form.getByRole('button', { name: 'Accept edited' }).click(); await page.waitForFunction(() => /with your edits/.test(document.querySelector('#inboxLive').textContent));
    const ed = api.json('proposals/r_editme0001.json'); assert.equal(ed.decision.action, 'edit'); assert.deepEqual(ed.decision.edited, { title: 'Draft the Acme summary' });
    assert.equal(api.json(`cards/${ed.decision.result.id}.json`).title, 'Draft the Acme summary');

    // Merge into the likely duplicate: existing comments, checklist and history stay; the new ones are added.
    await propCard(page, 'r_merge00001').locator('[data-act="merge"]').click();
    const mform = propCard(page, 'r_merge00001').locator('form'); assert.equal(await mform.locator('select').inputValue(), 't_second', 'the likely duplicate is offered first');
    await mform.getByRole('button', { name: 'Merge' }).click(); await page.waitForFunction(() => /Merged into Second/.test(document.querySelector('#inboxLive').textContent));
    const merged = api.json('cards/t_second.json');
    assert.deepEqual(merged.comments.map(c => c.text), ['Existing comment', 'From the meeting']); assert.deepEqual(merged.todos.map(c => c.text), ['Existing item', 'Book the room']);
    assert.equal(merged.history[0].text, 'created'); assert(merged.history.some(h => /merged from proposal r_merge00001/.test(h.text)));
    assert.equal(merged.todos[0].done, true, 'existing checklist state is kept');

    // Keyboard only: focus the list, move with j, ignore with i. The ignored proposal stays decided.
    await page.locator('article.prop').first().focus(); assert.equal(await page.evaluate(() => document.activeElement.dataset.id), 'r_touch00001');
    await page.keyboard.press('i'); await page.waitForFunction(() => /Ignored/.test(document.querySelector('#inboxLive').textContent));
    assert.equal(api.json('proposals/r_touch00001.json').status, 'ignored'); assert.equal(api.json('people/p_casey.json').comments.length, 0, 'an ignored interaction is never logged');
    assert.equal(await page.locator('#inboxBadge').isHidden(), true, 'nothing is pending now');
    await page.close();

    // Phone width: no sideways scrolling, buttons large enough to tap, every control named.
    const phoneApi = new Github(fixture()), phone = await openBoard(browser, phoneApi, { viewport: { width: 390, height: 800 }, mobile: true, view: 'inbox' });
    await phone.waitForSelector('article.prop');
    assert(await phone.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1), 'the Inbox fits a 390px screen');
    const heights = await phone.locator('.prop__actions button').evaluateAll(bs => bs.map(b => b.getBoundingClientRect().height));
    assert(heights.length && heights.every(h => h >= 44), 'decision buttons are at least 44px tall on a phone: ' + heights.join(','));
    const unnamed = await phone.evaluate(() => [...document.querySelectorAll('#board button, #board select, #board a, #board article')].filter(e => !(e.getAttribute('aria-label') || e.getAttribute('aria-labelledby') || e.textContent.trim() || (e.labels && e.labels.length))).length);
    assert.equal(unnamed, 0, 'every control in the Inbox has a name');
    assert.equal(await phone.locator('#inboxLive[aria-live="polite"]').count(), 1, 'results are announced');
    await phone.close();

    console.log('review inbox browser tests passed');
  } finally { await browser.close(); server.close(); }
})().catch(err => { console.error(err); server.close(); process.exitCode = 1; });

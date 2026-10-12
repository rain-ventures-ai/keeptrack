'use strict';
// Review Inbox (kit v42): proposals live in board/proposals/<id>.json and never reach the live board until accepted.
// GitHub is mocked with content SHAs, commit parents and fast-forward-only ref updates, so races behave like GitHub.

const assert = require('node:assert/strict');
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { chromium } = require('playwright');

const ROOT = path.resolve(__dirname, '../..');
const KIT = JSON.parse(fs.readFileSync(path.join(ROOT, 'board/kit/manifest.json'), 'utf8')).version;
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
    'proposals/r_race000001.json': prop('r_race000001', 'task.create', 'Book the venue', { change: { title: 'Book the venue', client: 'Acme' } }),
    'proposals/r_ignored001.json': prop('r_ignored001', 'task.create', 'An old idea', { status: 'ignored', decision: { action: 'ignore', by: 'sam', at: '2026-10-02T09:00:00Z', result: null, commit: null } }),
  };
  return Object.fromEntries(Object.entries(files).map(([k, v]) => [k, text(v)]));
}

// Honest, fictional Today fixtures: current kit, member CRM identity, and more proposals than the preview limit.
function todayFixture() {
  const files = fixture();
  files['people/p_alex.json'] = text({ ...person, id: 'p_alex', name: 'Alex Example', github: 'alex' });
  for (let n = 1; n <= 4; n++) {
    const id = 'r_today0000' + n;
    files[`proposals/${id}.json`] = text(prop(id, 'task.create', `Prepare fictional deliverable ${n}`, {
      change: { title: `Prepare fictional deliverable ${n}`, details: 'Review the proposed deliverable before adding it to the board.' },
      source: { ...meeting, date: '2026-10-10' }, created: `2026-10-10T08:0${n}:00.000Z`,
    }));
  }
  const update = JSON.parse(files['proposals/r_update0001.json']);
  update.likely_duplicates = [{ type: 'task', id: 't_first', why: 'target record' }, { type: 'task', id: 't_second', why: 'related outcome' }];
  files['proposals/r_update0001.json'] = text(update);
  return files;
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
    if (p === '' && method === 'GET') return json({ full_name: 'acme/board', private: true, permissions: { push: this.pushAllowed !== false }, default_branch: 'main' });
    if (p === '/contents/board/KIT_VERSION' && method === 'GET') return route.fulfill({ status: 200, body: `${KIT}\n` });
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
    if (p.startsWith('/git/blobs/') && method === 'GET') { const sha = p.split('/').pop(), all = Object.values(this.commits).flatMap(c => c.files ? Object.values(c.files) : []).concat(Object.values(this.files), Object.values(this.blobs));
      const v = all.find(x => crypto.createHash('sha1').update(x).digest('hex') === sha); return json({ encoding: 'base64', content: Buffer.from(v).toString('base64') }); }
    if (p === '/git/blobs' && method === 'POST') { const b = req.postDataJSON(), sha = 'blob-' + Object.keys(this.blobs).length; this.blobs[sha] = b.content; return json({ sha }); }
    if (p === '/git/trees' && method === 'POST') { const b = req.postDataJSON(), sha = 'tree-' + Object.keys(this.trees).length; this.trees[sha] = b.tree; return json({ sha }); }
    if (p === '/git/commits' && method === 'POST') { const b = req.postDataJSON(), sha = 'new-' + crypto.randomBytes(4).toString('hex'); this.commits[sha] = { parent: b.parents[0], tree: this.trees[b.tree] }; return json({ sha }); }
    if (p === '/git/refs/heads/main' && method === 'PATCH') { if (this.failRefOnce) { this.failRefOnce = false; return json({ message: 'Fixture write failure' }, 500); }
      if (this.hold) { this.hold = false; this.held = true; await new Promise(r => { this.release = r; }); }   // hold one ref update to interleave two reviewers
      const b = req.postDataJSON(), c = this.commits[b.sha];
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
  await page.addInitScript(([view, me, readonly]) => { localStorage.setItem('kb_repo', 'acme/board'); localStorage.setItem('kb_branch', 'main'); localStorage.setItem('kb_path', 'board/tasks.json'); localStorage.setItem('kb_token', 'test'); localStorage.setItem('kb_me', me); localStorage.setItem('kb_api', 'https://api.test'); localStorage.setItem('kb_layout', 'classic'); if (readonly) localStorage.setItem('kb_ro:acme/board', '1'); sessionStorage.setItem('kb_view', view); }, [opts.view || 'board', opts.me || 'alex', !!opts.readonly]);
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
    // Kit v44: always on. An old `review_inbox.enabled: false` is ignored, and proposal files still never become cards.
    { const api = new Github(fixture({ enabled: false })), page = await openBoard(browser, api);
      assert.equal(await page.locator('#btnInbox').isVisible(), true, 'the Inbox shows even where the old setting said off');
      assert.equal(await page.locator('#sInbox').count(), 0, 'there is no on/off switch in Settings');
      assert.deepEqual((await page.locator('.card .t').allTextContents()).sort(), ['First', 'Second']);
      await page.close(); }

    const api = new Github(fixture()), page = await openBoard(browser, api);
    // Pending proposals are not live work: Kanban shows only the two real cards, with a count of 2.
    assert.deepEqual((await page.locator('.card .t').allTextContents()).sort(), ['First', 'Second']);
    assert.equal(await page.locator('.col[data-col="todo"] h2 .ui-count').first().textContent(), '2');
    assert.equal(await page.locator('#btnInbox').isVisible(), true);
    // Today exposes decisions only after opening the evidence inline.
    await page.locator('#viewSw [data-view="today"]').first().click(); await page.waitForSelector('.today .treview');
    assert.match(await page.locator('.todayhead h2').textContent(), /6 to review/);
    assert.equal(await page.locator('.treview .trow').count(), 5, 'Today lists the five newest proposals');
    assert.match(await page.locator('.treview').textContent(), /Possible duplicate/, 'shared pills warn about real duplicate candidates');
    assert.equal(await page.locator('.treview .trow button').count(), 5, 'each preview has just one safe Review action');
    assert.equal(await page.locator('.treview').getByRole('button', { name: 'Accept', exact: true }).count(), 0, 'cannot accept without seeing the proposal');
    const writesBeforeReview = api.writes().length;
    await page.locator('.treview .trow button').first().focus(); await page.keyboard.press('Enter');
    await page.waitForSelector('.treview article.prop');
    assert.equal(await page.locator('#board.v-inbox').count(), 0, 'Review stays on Today');
    assert.equal(api.writes().length, writesBeforeReview, 'keyboard Review never writes to GitHub');
    assert.match(await page.locator('.tgo[data-go="inbox"]').textContent(), /6 to review/);
    if (process.env.INBOX_SCREENSHOT) await page.screenshot({ path: process.env.INBOX_SCREENSHOT, fullPage: true });
    await page.locator('.treview button', { hasText: /Review all 6/ }).click(); await page.waitForSelector('#board.v-inbox');
    await page.locator('#viewSw [data-view="board"]').first().click();
    assert.equal(await page.locator('#inboxBadge').textContent(), '6', 'six proposals are pending');
    const todayTab = page.locator('#viewSw .ui-tab[data-view="today"]').first();
    assert.equal(await todayTab.locator('.todaycount').textContent(), '6', 'the Today tab counts pending proposals');
    assert.equal(await todayTab.getAttribute('aria-label'), 'Today, 6 to review');
    assert(!api.calls.some(c => /git\/trees\/root-.*recursive/.test(c.path)), 'never reads the whole repository tree');

    await inbox(page);
    const groups = await page.locator('.inbox__src').allTextContents();
    assert.equal(groups.length, 2, 'grouped by source: the meeting and the email'); assert(groups.some(g => /Acme weekly/.test(g))); assert(groups.some(g => /Email/.test(g)));
    assert.equal(await page.locator('.inbox__technical').filter({ hasText: 'Source revision: 7' }).getAttribute('open'), null, 'revision retained behind collapsed import details');
    if (process.env.INBOX_REVIEW_SCREENSHOT) await page.screenshot({ path: process.env.INBOX_REVIEW_SCREENSHOT, fullPage: true });
    const createCard = propCard(page, 'r_create0001');
    assert.match(await createCard.textContent(), /Owner\s*alex/); assert.match(await createCard.textContent(), /Due\s*2026-10-20/);
    assert.match(await propCard(page, 'r_editme0001').textContent(), /OwnerUnassigned/, 'new tasks explicitly unassigned');
    assert.match(await propCard(page, 'r_update0001').textContent(), /OwnerUnchanged/, 'omitted update owner stays unchanged');
    assert.match(await propCard(page, 'r_merge00001').textContent(), /Looks like: Second/);
    assert.match(await propCard(page, 'r_update0001').locator('table').textContent(), /priority\s*medium\s*high/, 'updates show current against proposed');
    api.edit('proposals/r_update0001.json', p => { p.source.revision = 'long-technical-revision-' + 'x'.repeat(120); p.change.comments = [{ text: 'Share the revised client summary with the team.' }]; });
    api.edit('cards/t_first.json', t => { t.comments = [{ text: 'Earlier context remains available. '.repeat(30) }]; });
    await page.locator('#btnRefresh').click(); await page.waitForTimeout(250); await inbox(page);
    const addition = propCard(page, 'r_update0001');
    assert.match(await addition.textContent(), /Add comments/); assert.match(await addition.textContent(), /Existing entries are kept/);
    assert.equal(await addition.locator('.prop__context').getAttribute('open'), null);
    if (process.env.INBOX_REVIEW_SCREENSHOT) {
      await addition.scrollIntoViewIfNeeded(); await page.screenshot({ path: process.env.INBOX_REVIEW_SCREENSHOT, fullPage: true });
      await page.evaluate(() => window.kbTheme.set('dark')); await page.waitForTimeout(250); await page.screenshot({ path: process.env.INBOX_REVIEW_SCREENSHOT.replace('.png', '-dark.png'), fullPage: true }); await page.evaluate(() => window.kbTheme.set('light'));
    }
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

    // Keyboard only. j and k move, Enter on a proposal with no record yet moves to its first action, e opens the edit form.
    const order = await page.locator('article.prop').evaluateAll(a => a.map(x => x.dataset.id));
    await page.locator('article.prop').first().focus(); await page.keyboard.press('j');
    assert.equal(await page.evaluate(() => document.activeElement.dataset.id), order[1]); await page.keyboard.press('k');
    assert.equal(await page.evaluate(() => document.activeElement.dataset.id), order[0]);
    const raceAt = order.indexOf('r_race000001'); for (let i = 0; i < raceAt; i++) await page.keyboard.press('j');
    await page.keyboard.press('Enter'); assert.equal(await page.evaluate(() => document.activeElement.dataset.act), 'accept', 'Enter moves to Accept');
    await page.locator('article.prop[data-id="r_race000001"]').focus(); await page.keyboard.press('e');
    assert.equal(await page.evaluate(() => document.activeElement.tagName), 'INPUT', 'e opens the edit form and focuses its first field');
    await propCard(page, 'r_race000001').getByRole('button', { name: 'Cancel' }).click();
    assert.equal(await propCard(page, 'r_touch00001').locator('[data-act="edit"]').count(), 0, 'a private email proposal (metadata only) cannot be edited into a summary');
    // ... and i ignores the focused proposal. The ignored proposal stays decided.
    await page.locator('article.prop[data-id="r_touch00001"]').focus(); assert.equal(await page.evaluate(() => document.activeElement.dataset.id), 'r_touch00001');
    await page.keyboard.press('i'); await page.waitForFunction(() => /Ignored/.test(document.querySelector('#inboxLive').textContent));
    assert.equal(api.json('proposals/r_touch00001.json').status, 'ignored'); assert.equal(api.json('people/p_casey.json').comments.length, 0, 'an ignored interaction is never logged');
    assert.equal(await page.locator('#inboxBadge').textContent(), '1', 'only the race proposal is still pending');
    assert.equal(await page.locator('#viewSw .ui-tab[data-view="today"] .todaycount').textContent(), '1', 'the Today count follows each decision');
    await page.close();

    // Today is a stable, inline review surface, not a redirect or an automatic approval workflow.
    { const todayApi = new Github(todayFixture()), today = await openBoard(browser, todayApi, { view: 'today' });
      await today.waitForSelector('.treview .trow');
      const rows = () => today.locator('.treview .trow[data-id]');
      const row = id => today.locator(`.treview .trow[data-id="${id}"]`);
      const order = () => rows().evaluateAll(es => es.map(e => e.dataset.id));
      const initial = await order();
      assert.equal(initial.length, 5, 'ten pending suggestions start with a five-row preview');
      assert.equal(todayApi.writes().length, 0, 'loading Today never decides anything');
      assert.equal(await today.locator('.treview [data-act="accept"]').count(), 0, 'no Accept until evidence is expanded');
      const badgePage = await openBoard(browser, todayApi, { view: 'inbox' }); await badgePage.waitForSelector('article.prop');
      const targeted = propCard(badgePage, 'r_update0001');
      assert.match(await targeted.textContent(), /View #1/);
      assert(!/Looks like: First/.test(await targeted.textContent()), 'an update target is not its own duplicate');
      assert.match(await targeted.textContent(), /Looks like: Second/, 'a different duplicate candidate is still visible');
      await badgePage.locator('#viewSw [data-view="today"]').first().click();
      // The target badge is on the compact Today row, distinct from the full card's View link.
      const badgeFiles = fixture(); const badgeUpdate = JSON.parse(badgeFiles['proposals/r_update0001.json']);
      badgeUpdate.source.date = '2026-10-12'; badgeFiles['proposals/r_update0001.json'] = text(badgeUpdate);
      const targetToday = await openBoard(browser, new Github(badgeFiles), { view: 'today' });
      assert.match(await targetToday.locator('.treview .trow[data-id="r_update0001"]').textContent(), /Updates #1/);
      await targetToday.close();
      await badgePage.close();
      const first = initial[0], second = initial[1];
      await row(first).getByRole('button', { name: /^Review:/ }).click();
      await row(second).getByRole('button', { name: /^Review:/ }).click();
      await row(second).locator('article.prop').waitFor();
      assert.equal(await today.locator('#board.v-inbox').count(), 0, 'both cards expand without leaving Today');
      assert.equal(todayApi.writes().length, 0, 'expansion is read-only');
      const inlineSource = row(second).locator('a', { hasText: 'Open the source' });
      assert.equal(await inlineSource.getAttribute('href'), meeting.url, 'expanded evidence links to its source');
      assert.match(await inlineSource.getAttribute('rel'), /noopener/, 'new-tab source links cannot control the board');
      await row(second).locator('[data-act="accept"]').focus();
      await today.evaluate(() => {
        const b = document.querySelector('#board'); window.refreshTrace = [];
        window.refreshSnapshot = phase => ({ phase, at: performance.now(), scroll: b.scrollTop, height: b.clientHeight, extent: b.scrollHeight,
          focus: document.activeElement.id || document.activeElement.dataset.act || document.activeElement.tagName,
          rows: [...b.querySelectorAll('.treview .trow')].map(r => ({ id: r.dataset.id, top: r.getBoundingClientRect().top, height: r.getBoundingClientRect().height, expanded: !!r.querySelector('article.prop') })) });
        document.querySelector('#btnRefresh').addEventListener('click', () => window.refreshTrace.push(window.refreshSnapshot('click-capture')), true);
        b.addEventListener('scroll', () => window.refreshTrace.push(window.refreshSnapshot('scroll')));
      });
      const beforeRefresh = await today.evaluate(() => window.refreshSnapshot('before-click'));
      todayApi.files['proposals/r_newer0001.json'] = text(prop('r_newer0001', 'task.create', 'New arrival should not displace the current review', { source: { ...meeting, date: '2026-10-13' } })); todayApi.bump();
      await today.locator('#btnRefresh').click();
      await today.evaluate(() => window.refreshTrace.push(window.refreshSnapshot('after-click')));
      await today.waitForFunction(() => document.querySelector('#inboxBadge')?.textContent === '11');
      await today.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
      assert.deepEqual(await order(), initial, 'a newer remote proposal does not reorder the five displayed rows');
      assert.equal(await row(second).locator('article.prop').count(), 1, 'refresh preserves a second expanded review');
      const afterRefresh = await today.evaluate(() => window.refreshSnapshot('after-render'));
      // The explicit Refresh click owns focus, while the viewport remains on the same reading position.
      assert(Math.abs(afterRefresh.scroll - beforeRefresh.scroll) < 40, `remote refresh preserves the reading position: ${JSON.stringify({ beforeRefresh, afterRefresh, trace: await today.evaluate(() => window.refreshTrace.slice(-12)) })}`);
      if (process.env.TODAY_INLINE_SCREENSHOT) {
        for (const width of [1280, 350]) {
          await today.setViewportSize({ width, height: 850 });
          for (const theme of ['light', 'dark']) {
            await today.evaluate(t => window.kbTheme.set(t), theme);
            await today.waitForTimeout(300);
            assert(await today.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), `Today fits ${width}px in ${theme}`);
            assert.equal(await today.locator('#readOnlyBanner:visible, .member-onboard:visible').count(), 0, 'fictional fixture is writable and has its member record');
            if (width === 350) assert((await row(second).locator('.prop__actions button').evaluateAll(bs => bs.map(b => b.getBoundingClientRect().height))).every(h => h >= 44), 'expanded decision controls have 44px touch targets');
            await row(second).evaluate(e => { const b = document.querySelector('#board'); b.scrollTop += e.getBoundingClientRect().top - b.getBoundingClientRect().top - 12; });
            await today.waitForTimeout(100);
            await today.screenshot({ path: `${process.env.TODAY_INLINE_SCREENSHOT}-${width}-${theme}.png` });
          }
        }
        await today.setViewportSize({ width: 1280, height: 850 }); await today.evaluate(() => window.kbTheme.set('light'));
      }
      await row(first).locator('[data-act="accept"]').click();
      await said(today, /Accepted/);
      assert.equal(todayApi.json(`proposals/${first}.json`).status, 'accepted');
      const afterAccept = await order();
      assert.equal(afterAccept.length, 5, 'the next pending suggestion fills the vacancy');
      assert.deepEqual(afterAccept.slice(0, 4), initial.slice(1), 'remaining rows keep their order');
      assert.equal(await row(second).locator('article.prop').count(), 1, 'another expanded proposal remains expanded');
      assert.equal(await today.locator('#board.v-inbox').count(), 0, 'successful Accept stays on Today');
      assert.equal(await today.evaluate(() => document.activeElement.closest('.trow')?.dataset.id), second, 'focus moves to the next review, not the page top');

      // A failed write keeps the proposal in place and pending; a retry is still an explicit decision.
      todayApi.failRefOnce = true; await clearLive(today);
      await row(second).locator('[data-act="accept"]').click();
      await said(today, /Not saved|failed|failure/i);
      assert.equal(todayApi.json(`proposals/${second}.json`).status, 'pending');
      assert.deepEqual(await order(), afterAccept, 'failed decision does not move the row');
      assert.equal(await row(second).locator('article.prop').count(), 1, 'failed proposal stays open');
      await clearLive(today); await row(second).locator('[data-act="ignore"]').click(); await said(today, /Ignored/);
      assert.equal(todayApi.json(`proposals/${second}.json`).status, 'ignored');
      await clearLive(today); await today.locator('#btnUndo').click(); await said(today, /pending again/);
      assert.equal(todayApi.json(`proposals/${second}.json`).status, 'pending');
      assert(await order().then(ids => ids.includes(second)), 'Undo restores the suggestion to the Today preview');
      if (!(await row(second).locator('article.prop').count())) await row(second).getByRole('button', { name: /^Review:/ }).click();
      todayApi.edit(`proposals/${second}.json`, p => { p.reason = 'New evidence from another reviewer.'; p.change.title = 'Changed after the original review'; });
      const beforeStaleWrites = todayApi.writes().length; await clearLive(today);
      await row(second).locator('[data-act="accept"]').click(); await said(today, /proposal changed|latest evidence/);
      assert.equal(todayApi.writes().length, beforeStaleWrites, 'changed evidence is never accepted from the stale expanded snapshot');
      assert.equal(todayApi.json(`proposals/${second}.json`).status, 'pending');
      assert.equal(await row(second).locator('article.prop').count(), 0, 'changed evidence requires an explicit new review');
      await row(second).getByRole('button', { name: /^Review:/ }).click();
      assert.match(await row(second).locator('article.prop').textContent(), /Changed after the original review/);
      await today.close();

      const roApi = new Github(todayFixture()); roApi.pushAllowed = false;
      const readonly = await openBoard(browser, roApi, { view: 'today', readonly: true }); await readonly.waitForSelector('.treview .trow');
      await readonly.locator('.treview .trow').first().getByRole('button', { name: /^Review:/ }).click();
      assert.equal(await readonly.locator('.treview [data-act="accept"]').first().isDisabled(), true);
      assert.equal(await readonly.locator('.treview [data-act="ignore"]').first().isDisabled(), true);
      assert.equal(roApi.writes().length, 0, 'read-only review causes no write requests');
      await readonly.close();

      // Evidence changes after the decision's first read but before its ref update: the retry must not silently
      // accept the newer proposal. The first non-fast-forward attempt cannot publish either record.
      const retryApi = new Github(todayFixture()), retryPage = await openBoard(browser, retryApi, { view: 'today' });
      await retryPage.waitForSelector('.treview .trow');
      const retryRow = retryPage.locator('.treview .trow').first(), retryId = await retryRow.getAttribute('data-id');
      await retryRow.getByRole('button', { name: /^Review:/ }).click(); retryApi.hold = true;
      await retryRow.locator('[data-act="accept"]').click();
      for (let n = 0; !retryApi.held && n < 100; n++) await new Promise(r => setTimeout(r, 20));
      assert(retryApi.held, 'fixture pauses the first ref update');
      retryApi.edit(`proposals/${retryId}.json`, p => { p.change.title = 'Remote replacement during commit'; p.evidence = 'Changed after the first read'; });
      retryApi.release(); await said(retryPage, /proposal changed|latest evidence/);
      assert.equal(retryApi.json(`proposals/${retryId}.json`).status, 'pending');
      assert.equal(Object.keys(retryApi.files).filter(k => k.startsWith('cards/')).length, 2, 'no card published from stale evidence');
      assert.equal(retryApi.calls.filter(c => c.method === 'PATCH').length, 1, 'retry guard aborts before another write');
      await retryPage.close();

      const emptyApi = new Github(todayFixture()), emptyPage = await openBoard(browser, emptyApi, { view: 'today' });
      await emptyPage.waitForSelector('.treview .trow');
      for (const key of Object.keys(emptyApi.files).filter(k => k.startsWith('proposals/'))) emptyApi.edit(key, p => { p.status = 'ignored'; });
      await emptyPage.locator('#btnRefresh').click(); await emptyPage.waitForFunction(() => !document.querySelector('.treview'));
      emptyApi.files['proposals/r_return0001.json'] = text(prop('r_return0001', 'task.create', 'A later suggestion after the queue emptied')); emptyApi.bump();
      await emptyPage.locator('#btnRefresh').click(); await emptyPage.waitForSelector('.treview .trow[data-id="r_return0001"]');
      assert.equal(emptyApi.writes().length, 0, 'external empty/refill never triggers decisions');
      await emptyPage.close();
    }

    // Two reviewers accept the same proposal at the same moment: both start from pending, one commit wins, the other
    // is refused by GitHub (not a fast-forward), re-reads and stops. Exactly one card.
    { const race = new Github(fixture()), a = await openBoard(browser, race, { view: 'inbox' }), b = await openBoard(browser, race, { view: 'inbox', me: 'sam' });
      await a.waitForSelector('article.prop'); await b.waitForSelector('article.prop');
      race.hold = true; await clearLive(a); await clearLive(b);
      await propCard(a, 'r_race000001').locator('[data-act="accept"]').click();
      while (!race.held) await new Promise(r => setTimeout(r, 20));
      await propCard(b, 'r_race000001').locator('[data-act="accept"]').click(); await said(b, /Accepted/);
      race.release(); await said(a, /Already accepted by sam/);
      const decided = race.json('proposals/r_race000001.json'); assert.equal(decided.decision.by, 'sam');
      assert.equal(Object.entries(race.files).filter(([k, t]) => k.startsWith('cards/') && /"title": "Book the venue"/.test(t)).length, 1, 'exactly one card');
      await a.close(); await b.close(); }

    // Phone width: no sideways scrolling, buttons large enough to tap, every control named.
    const phoneFiles = fixture(); phoneFiles['people/p_alex.json'] = text({ ...person, id: 'p_alex', name: 'Alex Example', github: 'alex' });
    const update = JSON.parse(phoneFiles['proposals/r_update0001.json']); update.change.comments = [{ text: 'Share the revised client summary with the team.' }]; update.change.links = [{ title: 'Meeting notes', url: 'https://example.invalid/notes/team' }]; phoneFiles['proposals/r_update0001.json'] = text(update);
    const oldCard = JSON.parse(phoneFiles['cards/t_first.json']); oldCard.comments = [{ text: 'Earlier context remains available. '.repeat(30) }]; phoneFiles['cards/t_first.json'] = text(oldCard);
    const phoneApi = new Github(phoneFiles), phone = await openBoard(browser, phoneApi, { viewport: { width: 390, height: 800 }, mobile: true, view: 'inbox' });
    await phone.waitForSelector('article.prop');
    await phone.evaluate(() => window.kbLayout.set('dock'));
    await phone.locator('#dock [data-grp="today"]').click();
    await phone.waitForSelector('.treview');
    await phone.locator('#btnInbox').click(); await phone.waitForSelector('article.prop');
    await phone.setViewportSize({ width: 350, height: 800 });
    assert(await phone.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1), 'Inbox fits 350px');
    if (process.env.INBOX_REVIEW_PHONE_SCREENSHOT) {
      await phone.screenshot({ path: process.env.INBOX_REVIEW_PHONE_SCREENSHOT.replace('.png', '-header.png') });
      await propCard(phone, 'r_update0001').evaluate(e => document.querySelector('#board').scrollTop += e.getBoundingClientRect().top - document.querySelector('#board').getBoundingClientRect().top - 12);
      await phone.screenshot({ path: process.env.INBOX_REVIEW_PHONE_SCREENSHOT }); await phone.evaluate(() => window.kbTheme.set('dark')); await phone.waitForTimeout(250); await phone.screenshot({ path: process.env.INBOX_REVIEW_PHONE_SCREENSHOT.replace('.png', '-dark.png') });
      await propCard(phone, 'r_update0001').locator('.prop__actions').scrollIntoViewIfNeeded(); await phone.screenshot({ path: process.env.INBOX_REVIEW_PHONE_SCREENSHOT.replace('.png', '-actions-dark.png') }); await phone.evaluate(() => window.kbTheme.set('light'));
    }
    await phone.getByRole('button', { name: 'Back to Today', exact: true }).click();
    await phone.waitForSelector('.treview');
    await phone.locator('#btnInbox').click(); await phone.waitForSelector('article.prop');
    await phone.evaluate(() => window.kbLayout.set('classic'));
    assert.equal(await phone.evaluate(() => { const old = localStorage.getItem('kb_branch'); localStorage.setItem('kb_branch', 'example-branch'); const branch = new URL(window.kbNavigation.link()).searchParams.get('branch'); localStorage.setItem('kb_branch', old); return branch; }), 'example-branch', 'links use the active board branch');
    assert(await phone.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1), 'the Inbox fits a 390px screen');
    const heights = await phone.locator('.prop__actions button').evaluateAll(bs => bs.map(b => b.getBoundingClientRect().height));
    assert(heights.length && heights.every(h => h >= 44), 'decision buttons are at least 44px tall on a phone: ' + heights.join(','));
    await phone.locator('#viewSw [data-view="today"]').first().click(); await phone.waitForSelector('.treview');
    assert(await phone.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1), 'Today preview fits a phone');
    assert((await phone.locator('.treview .trow button').evaluateAll(bs => bs.map(b => b.getBoundingClientRect().height))).every(h => h >= 44), 'Review has a touch-sized target');
    if (process.env.INBOX_PHONE_SCREENSHOT) await phone.screenshot({ path: process.env.INBOX_PHONE_SCREENSHOT, fullPage: true });
    await phone.locator('#btnInbox').click(); await phone.waitForSelector('article.prop');
    const unnamed = await phone.evaluate(() => [...document.querySelectorAll('#board button, #board select, #board a, #board article')].filter(e => !(e.getAttribute('aria-label') || e.getAttribute('aria-labelledby') || e.textContent.trim() || (e.labels && e.labels.length))).length);
    assert.equal(unnamed, 0, 'every control in the Inbox has a name');
    assert.equal(await phone.locator('#inboxLive[aria-live="polite"]').count(), 1, 'results are announced');
    await phone.close();

    // Kit v44 questions: choose, approve (decider only) and a free-text question. Answers write only the proposal file.
    { const files = fixture(), q = (id, kind, title, change, extra = {}) => text(prop(id, kind, title, { source: { kind: 'other', id: 'agent-1', revision: '1', title: 'Agent questions', date: '2026-10-11' }, run: null, reason: '', change: { question: title, ...change }, ...extra }));
      files['proposals/r_askpick001.json'] = q('r_askpick001', 'ask.choose', 'Which design do you prefer?', { task: 't_first', allow_other: true, options: [{ key: 'a', label: 'Design A', url: 'https://example.invalid/a.png' }, { key: 'b', label: 'Design B' }] });
      files['proposals/r_askmail001.json'] = q('r_askmail001', 'ask.approve', 'Send this reply to Casey?', { content_hash: 'sha256:' + 'c'.repeat(64), subject: { type: 'email', url: 'https://mail.example.invalid/d/1', summary: 'Reply with the revised plan' } }, { decider: 'alex' });
      files['proposals/r_asksam0001.json'] = q('r_asksam0001', 'ask.approve', 'Merge the pricing PR?', { content_hash: 'sha256:' + 'd'.repeat(64), subject: { type: 'pr', url: 'https://example.invalid/pr/1' } }, { decider: 'sam' });
      files['proposals/r_asktext001.json'] = q('r_asktext001', 'ask.question', 'What budget should the proposal use?', {});
      files['proposals/r_askrace001.json'] = q('r_askrace001', 'ask.question', 'Which day suits the workshop?', {});
      const api = new Github(files), page = await openBoard(browser, api, { view: 'inbox' }); await page.waitForSelector('article.prop');
      const cardsBefore = Object.keys(api.files).filter(k => k.startsWith('cards/')).map(k => api.files[k]);
      const pick = propCard(page, 'r_askpick001');
      assert.equal(await pick.locator('[data-act="accept"], [data-act="edit"], [data-act="merge"]').count(), 0, 'a question has no accept, edit or merge');
      await clearLive(page); await pick.locator('.ask__note').fill('Darker header'); await pick.getByRole('button', { name: 'Design B', exact: true }).click(); await said(page, /Answered/);
      let saved = api.json('proposals/r_askpick001.json'); assert.equal(saved.status, 'answered'); assert.deepEqual(saved.decision.answer, { choice: 'b', note: 'Darker header' });
      assert.deepEqual(Object.keys(api.files).filter(k => k.startsWith('cards/')).map(k => api.files[k]), cardsBefore, 'answering never changes a card');
      assert.equal(await propCard(page, 'r_asksam0001').getByRole('button', { name: 'Approve', exact: true }).isDisabled(), true, 'only the named person can answer');
      assert.equal(await propCard(page, 'r_asksam0001').locator('[data-act="ignore"]').isDisabled(), true, 'or dismiss it');
      await clearLive(page); await propCard(page, 'r_askmail001').getByRole('button', { name: 'Approve', exact: true }).click(); await said(page, /Answered/);
      assert.deepEqual(api.json('proposals/r_askmail001.json').decision.answer, { approved: true });
      await clearLive(page); await propCard(page, 'r_asktext001').locator('textarea').fill('Use 12,000'); await propCard(page, 'r_asktext001').getByRole('button', { name: 'Send answer' }).click(); await said(page, /Answered/);
      assert.equal(api.json('proposals/r_asktext001.json').decision.answer.text, 'Use 12,000');
      // Someone answered first: the page refuses and never overwrites their answer.
      api.edit('proposals/r_askrace001.json', o => { o.status = 'answered'; o.decision = { action: 'answer', by: 'sam', at: '2026-10-12T09:00:00Z', answer: { text: 'Tuesday' }, result: null, commit: null }; });
      await clearLive(page); await propCard(page, 'r_askrace001').locator('textarea').fill('Friday'); await propCard(page, 'r_askrace001').getByRole('button', { name: 'Send answer' }).click(); await said(page, /Already answered by sam/);
      assert.equal(api.json('proposals/r_askrace001.json').decision.answer.text, 'Tuesday');
      // Change an answer before the agent acted: it is pending again.
      await page.selectOption('[data-filter="status"]', 'answered'); await page.waitForSelector('article.prop[data-id="r_askpick001"]');
      await clearLive(page); await propCard(page, 'r_askpick001').locator('[data-act="reopen"]').click(); await said(page, /Reopened|pending/);
      assert.equal(api.json('proposals/r_askpick001.json').status, 'pending');
      api.edit('proposals/r_askmail001.json', o => { o.decision.done = { at: '2026-10-12T10:00:00Z', by: 'claude@alex', note: 'sent' }; });
      await page.reload(); await page.waitForFunction(() => /Synced/.test(document.querySelector('#status').textContent));
      await page.locator('#btnInbox').click(); await page.selectOption('[data-filter="status"]', 'answered'); await page.waitForSelector('article.prop[data-id="r_askmail001"]');
      assert.equal(await propCard(page, 'r_askmail001').locator('[data-act="reopen"]').count(), 0, 'an answer the agent acted on cannot be changed');
      assert.match(await propCard(page, 'r_askmail001').textContent(), /Acted on by claude@alex/);
      await page.close(); }

    console.log('review inbox browser tests passed');
  } finally { await browser.close(); server.close(); }
})().catch(err => { console.error(err); server.close(); process.exitCode = 1; });

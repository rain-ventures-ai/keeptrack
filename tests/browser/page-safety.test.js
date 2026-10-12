'use strict';
// Web-page safety (kit v44 review fixes), with a faked GitHub that has real commit parents (a ref update that is not a fast-forward is refused):
//  1. two tabs on different boards share localStorage: each tab keeps saving into its own board (and the CSP lets the real api.github.com through)
//  2. settings.min_kit above this page's kit makes the board read-only with a banner, also when it rises between load and save
//  3. the agent-claim limit and clearing a wait are decided again on the board as saved, and the claim is one whole-board commit
//  4. accepting a proposal re-checks its field allow-list
//  5. Undo keeps at most 5 entries and persists only what fits the size limit
//  6. the settings code leaves tokens out unless "Include tokens and keys" is ticked
// Run: node page-safety.test.js

const assert = require('node:assert/strict');
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { chromium } = require('playwright');

const ROOT = path.resolve(__dirname, '../..');
const KIT = JSON.parse(fs.readFileSync(path.join(ROOT, 'board/kit/manifest.json'), 'utf8')).version;
const mime = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json', '.svg': 'image/svg+xml', '.webmanifest': 'application/manifest+json', '.png': 'image/png' };
const server = http.createServer((req, res) => {
  const rel = decodeURIComponent(new URL(req.url, 'http://local').pathname).replace(/^\/+/, '') || 'board/index.html';
  const file = path.resolve(ROOT, rel); if (!file.startsWith(ROOT + path.sep)) { res.writeHead(403).end(); return; }
  fs.readFile(file, (err, data) => { if (err) res.writeHead(404).end(); else { res.setHeader('Content-Type', mime[path.extname(file)] || 'application/octet-stream'); res.end(data); } });
});

const text = x => JSON.stringify(x, null, 2) + '\n';
const T0 = '2026-10-01T08:00:00.000Z';
const rootFile = (title, settings = {}) => ({ version: 4, layout: 'split', settings: { title, ...settings }, columns: [{ id: 'todo', name: 'To do' }, { id: 'done', name: 'Done' }],
  people: [{ github: 'alex', name: 'Alex' }, { github: 'sam', name: 'Sam' }], agents: [], clients: ['General'], labels: [], client_info: {}, next_num: 3, archive: { files: {} } });
const card = (id, num, title, extra = {}) => ({ id, num, title, column: 'todo', client: '', priority: 'medium', due: '', labels: [], assignees: ['alex'], details: '', links: [], contacts: [], todos: [], comments: [], history: [], claim: null, created: T0, updated: T0, rank: 'a' + num, ...extra });
const running = (agent, who) => { const now = new Date().toISOString(); return { agent, on_behalf_of: who, session_id: 's-' + agent + who, session_url: '', host: 'test', status: 'running', note: 'working', claimed_at: now, heartbeat_at: now }; };
const board = (title, settings, cards, extra = {}) => Object.fromEntries(Object.entries({ 'tasks.json': rootFile(title, settings), ...Object.fromEntries(cards.map(c => [`cards/${c.id}.json`, c])), ...extra }).map(([k, v]) => [k, text(v)]));

// One fake repo: contents API for reads and one-file writes, git data API (with parents) for multi-file commits.
class Github {
  constructor(repo, files) { this.repo = repo; this.files = files; this.head = 'c1'; this.n = 1; this.calls = []; this.blobs = {}; this.trees = {}; this.commits = { c1: { files: { ...files } } }; }
  sha(p) { return crypto.createHash('sha1').update(this.files[p] || '').digest('hex'); }
  bump() { this.head = 'c' + ++this.n; this.commits[this.head] = { files: { ...this.files } }; }
  edit(rel, fn) { const o = JSON.parse(this.files[rel]); fn(o); this.files[rel] = text(o); this.bump(); }   // someone else commits
  json(rel) { return this.files[rel] ? JSON.parse(this.files[rel]) : null; }
  writes() { return this.calls.filter(c => c.method !== 'GET'); }
  owns(url) { return new URL(url).pathname.startsWith(`/repos/${this.repo}`) || /\/user(\/|$)/.test(new URL(url).pathname); }
  async route(route) {
    const req = route.request(), u = new URL(req.url()), method = req.method(), p = u.pathname.replace(`/repos/${this.repo}`, '');
    this.calls.push({ method, path: p, auth: req.headers().authorization || '' });
    const json = (body, status = 200, headers = {}) => route.fulfill({ status, headers: { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*', ...headers }, body: JSON.stringify(body) });
    if (p === '/user') return json({ login: 'alex' });
    if (p.startsWith('/user/repos')) return json([]);
    if (p === '' && method === 'GET') return json({ full_name: this.repo, private: true, permissions: { push: true }, default_branch: 'main' });
    if (p === '/contents/board/KIT_VERSION') return route.fulfill({ status: 200, headers: { 'Access-Control-Allow-Origin': '*' }, body: `${KIT}\n` });
    if (p.startsWith('/contents/board/tasks.json') && method === 'GET') return json({ sha: this.sha('tasks.json'), size: this.files['tasks.json'].length, encoding: 'base64', content: Buffer.from(this.files['tasks.json']).toString('base64') });
    if (p.startsWith('/contents/board/') && method === 'PUT') { const rel = p.slice('/contents/board/'.length), b = req.postDataJSON();
      if ((b.sha || null) !== (this.files[rel] ? this.sha(rel) : null)) return json({ message: 'sha does not match' }, 409);
      const parent = this.head; this.files[rel] = Buffer.from(b.content, 'base64').toString(); this.bump(); return json({ content: { sha: this.sha(rel) }, commit: { sha: this.head, parents: [{ sha: parent }], tree: { sha: 'root-' + this.head } } }); }
    if (p.startsWith('/contents/')) return json({ message: 'Not Found' }, 404);
    if (p === '/git/ref/heads/main' && method === 'GET') return json({ object: { sha: this.head } }, 200, { ETag: '"' + this.head + '"' });
    if (p.startsWith('/git/commits/') && method === 'GET') return json({ tree: { sha: 'root-' + p.split('/').pop() } });
    if (p.startsWith('/git/trees/root-') && method === 'GET') return json({ tree: [{ path: 'board', type: 'tree', sha: 'board-' + p.split('root-')[1] }] });
    if (p.startsWith('/git/trees/board-') && method === 'GET') { const c = this.commits[p.split('board-')[1].split('?')[0]] || { files: this.files };
      return json({ truncated: false, tree: Object.entries(c.files).map(([k, v]) => ({ path: k, type: 'blob', sha: crypto.createHash('sha1').update(v).digest('hex'), size: Buffer.byteLength(v) })) }); }
    if (p.startsWith('/git/blobs/') && method === 'GET') { const sha = p.split('/').pop(), all = Object.values(this.commits).flatMap(c => c.files ? Object.values(c.files) : []).concat(Object.values(this.files));
      const v = all.find(x => crypto.createHash('sha1').update(x).digest('hex') === sha); return json({ encoding: 'base64', content: Buffer.from(v).toString('base64') }); }
    if (p === '/git/blobs' && method === 'POST') { const sha = 'blob-' + Object.keys(this.blobs).length; this.blobs[sha] = req.postDataJSON().content; return json({ sha }); }
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
const SETTINGS = { kb_branch: 'main', kb_path: 'board/tasks.json', kb_me: 'alex', kb_layout: 'classic', kb_tour_seen: '1' };
const watch = (page, errors) => {
  page.on('pageerror', e => errors.push('page error: ' + e.message));
  page.on('console', m => { if (/Content Security Policy/i.test(m.text())) errors.push('CSP: ' + m.text()); });
};
async function openBoard(browser, api, extra = {}, cron = null) {
  const page = await browser.newPage({ viewport: { width: 1280, height: 860 } }), errors = page.errors = [];
  watch(page, errors);
  await page.addInitScript(s => { for (const k in s) localStorage.setItem(k, s[k]); sessionStorage.setItem('kb_view', 'board'); },
    { ...SETTINGS, kb_repo: api.repo, kb_token: 'test', kb_api: 'https://api.test', ...extra });
  await page.route('https://api.test/**', r => api.route(r));
  if (cron) await page.route('https://cron.test/**', route => { cron.push(route.request().method() + ' ' + new URL(route.request().url()).pathname); return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(route.request().method() === 'PUT' ? { jobId: 7 } : { history: [] }) }); });
  await page.goto(base + '/board/index.html'); await page.waitForFunction(() => /Synced/.test(document.querySelector('#status').textContent));
  await page.evaluate(() => { window.__copied = ''; Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText: async t => { window.__copied = t; } } }); });
  return page;
}
const synced = page => page.waitForFunction(() => /^Saved/.test(document.querySelector('#status').textContent));
const addTask = async (page, title) => { const i = page.locator('.col[data-col="todo"] .add input'); await i.fill(title); await i.press('Enter'); };
const titles = api => Object.keys(api.files).filter(k => k.startsWith('cards/')).map(k => api.json(k).title).sort();
const CLAUDE = { kb_agents: 'claude', kb_claude_url: 'https://api.anthropic.com/v1/claude_code/routines/trig_Test123/fire', kb_claude_token: 'routine-token', kb_cron_key: 'cron-key', kb_cron_api: 'https://cron.test', kb_cron_fast: '1' };

(async () => {
  await new Promise(ok => server.listen(0, '127.0.0.1', ok)); base = `http://127.0.0.1:${server.address().port}`;
  const browser = await chromium.launch({ headless: true });
  try {
    // ---- 1. two tabs, two boards, one localStorage: tab 1 keeps saving into its own board after tab 2 switches ----
    {
      const one = new Github('acme/one', board('One', {}, [card('t_a', 1, 'One card')])), two = new Github('acme/two', board('Two', {}, [card('t_b', 1, 'Two card')]));
      const ctx = await browser.newContext({ viewport: { width: 1280, height: 860 } }), errors = [];
      await ctx.route('https://api.github.com/**', r => (one.owns(r.request().url()) && !r.request().url().includes('/repos/acme/two') ? one : two).route(r));   // the real API origin: the CSP must allow it
      const a = await ctx.newPage(); watch(a, errors);
      await a.goto(base + '/board/kit/manifest.json');   // same origin: seed this browser's settings with both boards saved
      await a.evaluate(s => { for (const k in s) localStorage.setItem(k, s[k]); sessionStorage.setItem('kb_view', 'board'); }, { ...SETTINGS, kb_repo: 'acme/one', kb_token: 'token-one',
        kb_boards: JSON.stringify({ 'acme/one': { branch: 'main', path: 'board/tasks.json', token: 'token-one' }, 'acme/two': { branch: 'main', path: 'board/tasks.json', token: 'token-two' } }) });
      await a.goto(base + '/board/index.html?repo=acme/one&branch=main&path=board/tasks.json'); await a.locator('.card', { hasText: 'One card' }).waitFor();
      const b = await ctx.newPage(); watch(b, errors);
      await b.addInitScript(() => sessionStorage.setItem('kb_view', 'board'));
      await b.goto(base + '/board/index.html?repo=acme/two&branch=main&path=board/tasks.json'); await b.locator('.card', { hasText: 'Two card' }).waitFor();
      assert.equal(await a.evaluate(() => localStorage.getItem('kb_repo')), 'acme/two', 'tab 2 switched the shared default board');
      one.calls = []; two.calls = [];
      await addTask(a, 'Added in tab one'); await synced(a);
      assert.deepEqual(titles(one), ['Added in tab one', 'One card'], 'tab 1 saves into its own board');
      assert.deepEqual(titles(two), ['Two card'], 'and never into the board tab 2 switched to');
      assert.equal(two.writes().length, 0); assert.ok(one.writes().every(c => c.auth === 'Bearer token-one'), 'with its own token');
      await addTask(b, 'Added in tab two'); await synced(b);
      assert.deepEqual(titles(two), ['Added in tab two', 'Two card']); assert.deepEqual(titles(one), ['Added in tab one', 'One card']);
      // a token change for tab 1's own board in another tab is followed; tab 1's board entry in kb_boards keeps its values
      assert.equal(JSON.parse(await a.evaluate(() => localStorage.getItem('kb_boards')))['acme/one'].token, 'token-one');
      await a.reload(); await a.locator('.card', { hasText: 'Added in tab one' }).waitFor();
      assert.match(a.url(), /repo=acme\/one/, 'a reload keeps the tab on its board');
      assert.deepEqual(errors, [], 'no page errors or CSP violations: ' + errors.join('; '));
      await ctx.close();
    }

    // ---- 2. settings.min_kit above this page's kit: read-only with a banner; reads still work; an odd min_kit never blocks ----
    {
      const api = new Github('acme/board', board('Kit', { min_kit: KIT + 1 }, [card('t_a', 1, 'First')])), page = await openBoard(browser, api);
      assert.equal(await page.evaluate(() => document.body.classList.contains('ro')), true, 'read-only');
      assert.match(await page.locator('#roBar').textContent(), new RegExp(`needs board tools kit v${KIT + 1} or newer \\(settings\\.min_kit\\), and this page is kit v${KIT}`));
      assert.equal(await page.locator('.card', { hasText: 'First' }).count(), 1, 'the board is still shown');
      assert.equal(api.writes().length, 0); assert.deepEqual(page.errors, []); await page.close();
    }
    for (const odd of ['99', 4.5, null]) {
      const api = new Github('acme/board', board('Kit', { min_kit: odd }, [card('t_a', 1, 'First')])), page = await openBoard(browser, api);
      assert.equal(await page.evaluate(() => document.body.classList.contains('ro')), false, `min_kit ${JSON.stringify(odd)} never blocks`);
      await addTask(page, 'Saved'); await synced(page); assert.ok(titles(api).includes('Saved')); await page.close();
    }
    { // min_kit rises between the page's read and its save: nothing is written and the page turns read-only
      const api = new Github('acme/board', board('Kit', {}, [card('t_a', 1, 'First')])), page = await openBoard(browser, api);
      api.edit('tasks.json', r => { r.settings.min_kit = KIT + 2; }); api.calls = [];
      await addTask(page, 'Too late'); await page.waitForFunction(() => document.body.classList.contains('ro'));
      assert.equal(api.writes().length, 0, 'no write'); assert.ok(!titles(api).includes('Too late'));
      assert.match(await page.locator('#roBar').textContent(), new RegExp(`kit v${KIT + 2}`)); await page.close();
    }

    // ---- 3. the agent limit is decided on the board as saved; clearing a wait too ----
    {
      const api = new Github('acme/board', board('Limit', { max_agent_claims: 1 }, [card('t_a', 1, 'First'), card('t_b', 2, 'Second')])), cron = [];
      const page = await openBoard(browser, api, CLAUDE, cron);
      api.edit('cards/t_b.json', c => { c.claim = running('codex', 'sam'); }); api.calls = [];   // an agent claims #2 after this page read the board
      await page.locator('.col[data-col="todo"] .hcinema').click();
      const first = page.locator('.cinema-col .card', { hasText: 'First' }); await first.locator('.quickassign summary').click();
      assert.equal(await first.locator('.quickagent').isDisabled(), false, 'the page still thinks there is room');
      await first.locator('.quickagent').click();
      await page.locator('.ui-toast', { hasText: 'agent run already going (#2)' }).waitFor();
      assert.equal(api.json('cards/t_a.json').claim, null, 'no claim on #1'); assert.equal(cron.filter(c => c.startsWith('PUT')).length, 0, 'no cron job');
      assert.equal(api.writes().length, 0, 'nothing written'); await page.close();
    }
    {
      const api = new Github('acme/board', board('Limit', { max_agent_claims: 2 }, [card('t_a', 1, 'First'), card('t_b', 2, 'Second')])), cron = [];
      const page = await openBoard(browser, api, CLAUDE, cron);
      api.edit('cards/t_b.json', c => { c.claim = running('codex', 'sam'); }); api.calls = [];
      await page.locator('.col[data-col="todo"] .hcinema').click();
      const first = page.locator('.cinema-col .card', { hasText: 'First' }); await first.locator('.quickassign summary').click();
      const relay = page.waitForRequest(r => r.method() === 'PUT' && r.url() === 'https://cron.test/jobs'); await first.locator('.quickagent').click(); await relay;
      assert.equal(api.json('cards/t_a.json').claim.agent, 'claude', 'with room on the newer board, Claude is assigned');
      const w = api.writes().map(c => c.method + ' ' + c.path);
      assert.ok(w.includes('PATCH /git/refs/heads/main'), 'one commit on the head that was read: ' + w.join(', '));
      assert.ok(!w.some(x => x.startsWith('PUT /contents/')), 'never a one-file Contents PUT for an agent claim'); await page.close();
    }
    {
      const blocked = { ...running('claude', 'alex'), status: 'blocked', blocked_by_wait: true, note: 'waiting on Acme' };
      const api = new Github('acme/board', board('Wait', { max_agent_claims: 1, min_kit: 43 }, [card('t_a', 1, 'First', { claim: blocked, waiting: { on: 'Acme', who: '', since: '2026-10-01', nudge: '', note: '', by: 'alex', by_session: '' } }), card('t_b', 2, 'Second')]));
      const page = await openBoard(browser, api);
      api.edit('cards/t_b.json', c => { c.claim = running('codex', 'sam'); });   // the limit fills after this page read the board
      await page.evaluate(() => { location.hash = '#1'; }); await page.locator('#dlgCard[open]').waitFor(); await page.locator('#cWaitPill').waitFor();
      api.calls = []; await page.locator('#cWaitPill .ui-pill__remove').click();
      await page.locator('.ui-toast', { hasText: 'the claim stays blocked' }).waitFor();
      const c = api.json('cards/t_a.json'); assert.equal(c.waiting, null, 'the wait is cleared'); assert.equal(c.claim.status, 'blocked', 'the claim stays blocked'); assert.equal(c.claim.blocked_by_wait, true);
      assert.ok(api.writes().some(x => x.method === 'PATCH'), 'a whole-board commit'); assert.deepEqual(page.errors, []); await page.close();
    }

    // ---- 4. a proposal file written by hand that sets a field proposals may not change is refused at accept ----
    {
      const prop = { id: 'r_bad0000001', version: 1, kind: 'task.update', status: 'pending', title: 'Take over First', source: { kind: 'other', id: 'x', revision: '1', title: 'x', date: '2026-10-08', url: '' },
        run: { routine: 'r', run_id: '1', at: T0 }, action_key: 'ak', work_key: 'wk', reason: 'r', target: { type: 'task', id: 't_a', base: {} }, change: { priority: 'high', claim: running('claude', 'mallory') },
        likely_duplicates: [], decision: null, history: [], created: T0, createdBy: 'routine' };
      const api = new Github('acme/board', board('Inbox', { review_inbox: { enabled: true } }, [card('t_a', 1, 'First')], { 'proposals/r_bad0000001.json': prop }));
      const page = await openBoard(browser, api); await page.locator('#btnInbox').click(); await page.waitForSelector('#board.v-inbox .inbox');
      api.calls = []; await page.locator('article.prop[data-id="r_bad0000001"] [data-act="accept"]').click();
      await page.waitForFunction(() => /may not set claim/.test(document.querySelector('#inboxLive').textContent));
      assert.equal(api.writes().length, 0); assert.equal(api.json('cards/t_a.json').claim, null); assert.equal(api.json('proposals/r_bad0000001.json').status, 'pending');
      assert.deepEqual(page.errors, []); await page.close();
    }

    // ---- 5. Undo: at most 5 entries in memory and in IndexedDB; none persisted past the size limit ----
    {
      const undoSaved = page => page.evaluate(() => new Promise(ok => { const r = indexedDB.open('keeptrack', 1); r.onsuccess = () => { const g = r.result.transaction('kv').objectStore('kv').get('kb_undo:acme/board:main:board/tasks.json'); g.onsuccess = () => ok(g.result); }; }));
      const api = new Github('acme/board', board('Undo', {}, [card('t_a', 1, 'First')])), page = await openBoard(browser, api);
      for (let i = 1; i <= 7; i++) { await addTask(page, 'Task ' + i); await synced(page); }
      await page.waitForFunction(() => /Add task: Task 7/.test(document.getElementById('btnUndo').title));
      await page.waitForTimeout(200); const saved = await undoSaved(page);
      assert.deepEqual(saved.map(e => e.message), [3, 4, 5, 6, 7].map(i => 'Add task: Task ' + i), 'the newest 5 are kept');
      for (let i = 0; i < 6; i++) { if (await page.evaluate(() => document.getElementById('btnUndo').disabled)) break; await page.evaluate(() => document.activeElement && document.activeElement.blur()); await page.keyboard.press('Control+z'); await page.waitForFunction(() => !/Saving/.test(document.querySelector('#status').textContent)); await page.waitForTimeout(150); }
      assert.deepEqual(titles(api), ['First', 'Task 1', 'Task 2'], 'five undos, then nothing older is kept in memory');
      await page.close();
      const small = new Github('acme/board', board('Undo', {}, [card('t_a', 1, 'First')])), p2 = await openBoard(browser, small, { kb_undo_bytes: '500' });
      await addTask(p2, 'Big'); await synced(p2); await p2.waitForTimeout(200);
      assert.deepEqual(await undoSaved(p2), [], 'over the size limit: nothing persisted');
      assert.equal(await p2.locator('#btnUndo').isDisabled(), false, 'Undo still works in this tab'); await p2.close();
    }

    // ---- 6. the settings code leaves tokens and keys out unless the box is ticked ----
    {
      const api = new Github('acme/board', board('Code', {}, [card('t_a', 1, 'First')])), page = await openBoard(browser, api, CLAUDE);
      const decode = code => JSON.parse(Buffer.from(code.replace(/^kbcfg1\./, '').replace(/-/g, '+').replace(/_/g, '/'), 'base64').toString());
      const copy = async () => { await page.evaluate(() => { window.__copied = ''; }); await page.locator('#xCode').click(); await page.getByRole('alertdialog').locator('button', { hasText: 'Copy settings code' }).click(); await page.waitForFunction(() => /^kbcfg1\./.test(window.__copied)); return decode(await page.evaluate(() => window.__copied)); };
      await page.evaluate(() => window.kbSettings.open('move'));
      assert.equal(await page.locator('#xSecrets').isChecked(), false, 'off by default');
      let o = await copy();
      assert.equal(o.repo, 'acme/board'); for (const k of ['token', 'claude_token', 'cron_key']) assert.equal(o[k], undefined, k + ' left out');
      assert.deepEqual(Object.values(JSON.parse(o.boards)).map(e => [e.token, e.claude_token]), [[undefined, undefined]], 'and out of every saved board');
      assert.equal(o.claude_url, CLAUDE.kb_claude_url, 'non-secret settings travel');
      await page.locator('#xSecrets').check(); o = await copy();
      assert.equal(o.token, 'test'); assert.equal(o.claude_token, 'routine-token'); assert.equal(o.cron_key, 'cron-key'); assert.equal(JSON.parse(o.boards)['acme/board'].token, 'test');
      assert.deepEqual(page.errors, []); await page.close();
    }
    console.log('page-safety: all checks passed');
  } catch (e) { console.error(e); process.exitCode = 1; }
  finally { await browser.close(); server.close(); }
})();

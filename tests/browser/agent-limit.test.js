'use strict';
// Agent capacity and outcomes on the web board, with a faked GitHub API and a faked cron-job.org relay:
//  - settings.max_agent_claims: a full board refuses to send work to Claude (no claim written, no cron job, a message, a relay-log line)
//    and disables the quick-assign entries; with room, it sends, and the routine text no longer says --force and explains done --note / --cancel.
//  - a card closed as cancelled shows a "cancelled" pill, an "Outcome: cancelled" line in the drawer and the same in the Markdown export.
// Run: node agent-limit.test.js

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
const root = { version: 4, layout: 'split', settings: { title: 'Limit test', max_agent_claims: 2 }, columns: [{ id: 'todo', name: 'To do' }, { id: 'done', name: 'Done' }], people: [{ github: 'alex', name: 'Alex' }, { github: 'sam', name: 'Sam' }], agents: [], clients: [], labels: [], client_info: {}, next_num: 7, archive: { files: {} } };
const card = (id, num, title, extra) => ({ id, num, title, column: 'todo', client: '', priority: 'medium', due: '', labels: [], assignees: [], details: '', links: [], contacts: [], todos: [], comments: [], history: [], claim: null, created: '2026-10-01T08:00:00.000Z', updated: '2026-10-01T08:00:00.000Z', rank: 'a' + num, ...extra });

// A small GitHub: contents API for reads and single-file writes, git data API for multi-file commits (same shape as split-storage.test.js).
class Github {
  constructor() {
    const now = new Date().toISOString(), run = (agent, who, extra) => ({ agent, on_behalf_of: who, session_id: 's-' + agent + who, session_url: '', host: 'test', status: 'running', note: 'working', claimed_at: now, heartbeat_at: now, ...extra });
    const cards = [
      card('t_one', 1, 'First', { assignees: ['alex'] }),
      card('t_two', 2, 'Second', { claim: run('claude', 'sam') }),
      card('t_three', 3, 'Third', { claim: run('codex', 'sam') }),
      card('t_four', 4, 'Fourth', { column: 'done', outcome: 'cancelled', last_run: { agent: 'claude', on_behalf_of: 'sam', session_id: 's-old', status: 'done', outcome: 'cancelled', note: 'Dropped: duplicate of #1', claimed_at: now, finished_at: now } }),
      card('t_five', 5, 'Fifth', { claim: run('claude', 'sam', { attended: true }) }),   // attended claims do not count against the limit
      card('t_six', 6, 'Sixth', { column: 'done', outcome: 'completed', last_run: { agent: 'claude', on_behalf_of: 'sam', session_id: 's-ok', status: 'done', outcome: 'completed', note: 'All good', claimed_at: now, finished_at: now } })];
    this.files = { 'tasks.json': text(root) }; for (const c of cards) this.files[`cards/${c.id}.json`] = text(c);
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
const errors = [];
let cronSession = null;   // when set, the mocked cron-job.org reports the routine's reply with this claude.ai session link
async function openBoard(browser, api, cron) {
  const page = await browser.newPage({ viewport: { width: 1280, height: 860 } });
  page.on('pageerror', e => errors.push(e.message));
  await page.addInitScript(() => {
    const s = { kb_repo: 'acme/board', kb_branch: 'main', kb_path: 'board/tasks.json', kb_token: 'test', kb_me: 'alex', kb_api: 'https://api.test', kb_layout: 'classic', kb_tour_seen: '1', kb_agents: 'claude',
      kb_claude_url: 'https://api.anthropic.com/v1/claude_code/routines/trig_Test123/fire', kb_claude_token: 'routine-token', kb_cron_key: 'cron-key', kb_cron_api: 'https://cron.test', kb_cron_fast: '1' };
    for (const k in s) localStorage.setItem(k, s[k]);
    sessionStorage.setItem('kb_view', 'board');
  });
  await page.route('https://api.test/**', r => api.route(r));
  await page.route('https://cron.test/**', route => {
    const req = route.request(), u = new URL(req.url()), send = x => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(x) });
    cron.push({ method: req.method(), path: u.pathname });
    if (req.method() === 'PUT' && u.pathname === '/jobs') return send({ jobId: 77 });
    if (u.pathname.endsWith('/history')) return send({ history: cronSession ? [{ identifier: 'h1', status: 1, httpStatus: 200, date: Math.floor(Date.now() / 1000) }] : [] });
    if (u.pathname.endsWith('/history/h1')) return send({ jobHistoryDetails: { body: cronSession || '' } });
    return send({});
  });
  await page.goto(base + '/board/index.html'); await page.waitForSelector('.card');
  await page.evaluate(() => { window.__copied = ''; Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText: async t => { window.__copied = t; } } }); });
  return page;
}
const LIMIT_MSG = /^2 agent runs already going \(#2, #3\); the board's limit is 2\. Wait for one to finish, or raise it with keeptrack\.py settings-set --max-agent-claims N\./;

(async () => {
  await new Promise(ok => server.listen(0, '127.0.0.1', ok)); base = `http://127.0.0.1:${server.address().port}`;
  const browser = await chromium.launch({ headless: true });
  try {
    // ---- 1. the limit is full: 2 running agent claims on other cards (#2 claude, #3 codex); the attended claim on #5 does not count ----
    {
      const api = new Github(), cron = [], page = await openBoard(browser, api, cron);
      // quick-assign (cinema mode): the Claude entry is disabled and says why
      await page.locator('.col[data-col="todo"] .hcinema').click();
      const first = page.locator('.cinema-col .card', { hasText: 'First' }); await first.locator('.quickassign summary').click();
      const quick = first.locator('.quickagent'); assert.equal(await quick.isDisabled(), true, 'quick-assign is disabled when the limit is full');
      assert.match(await quick.getAttribute('title'), LIMIT_MSG);
      await page.keyboard.press('Escape');
      // the drawer's "+ Add" menu: the same
      await page.evaluate(() => { location.hash = '#1'; }); await page.locator('#dlgCard[open]').waitFor();
      await page.locator('#cWhoAdd').click();
      const item = page.locator('.ui-menu [role=menuitem]', { hasText: 'Claude' }); assert.equal(await item.isDisabled(), true); assert.match(await item.textContent(), /agent limit is full/);
      await page.keyboard.press('Escape');
      // an @claude comment: posted alone, no claim, no cron job, no "Send to Claude?" dialog, a message and a relay-log line
      const saved = page.waitForResponse(r => ['PUT', 'PATCH'].includes(r.request().method()) && r.url().startsWith('https://api.test/repos/acme/board/'));
      await page.locator('#cmText').fill('@claude please take this'); await page.locator('#cmPost').click(); await saved;
      const toast = page.locator('.ui-toast', { hasText: 'agent runs already going' }); await toast.waitFor(); assert.match(await toast.textContent(), LIMIT_MSG);
      assert.equal(await page.locator('#dlgSend[open]').count(), 0, 'no send dialog when the limit is full');
      const one = api.card('t_one'); assert.equal(one.comments.at(-1).text, '@claude please take this', 'the comment itself is still posted'); assert.equal(one.claim, null, 'no placeholder claim is written');
      assert.equal(cron.filter(c => c.method === 'PUT').length, 0, 'no cron-job.org job is created');
      const log = await page.evaluate(() => JSON.parse(localStorage.getItem('kb_relay_log') || '[]'));
      assert.equal(log.length, 1); assert.equal(log[0].ev, 'Not sent'); assert.equal(log[0].num, 1); assert.match(log[0].detail, /2 agent runs already going \(#2, #3\)/);
      await page.close();
    }

    // ---- 1b. kit v43: a waiting card is never sent to Claude, even with room under the limit; the Waiting filter finds it ----
    {
      const api = new Github(), cron = []; { const r = JSON.parse(api.files['tasks.json']); r.settings.max_agent_claims = 3; api.files['tasks.json'] = text(r); }
      { const c = api.card('t_one'); c.waiting = { on: 'Acme finance', who: 'sam', since: '2026-10-01', nudge: '', note: '', by: 'alex', by_session: '' }; api.files['cards/t_one.json'] = text(c); }
      const page = await openBoard(browser, api, cron);
      await page.locator('.col[data-col="todo"] .hcinema').click();
      const first = page.locator('.cinema-col .card', { hasText: 'First' }); await first.locator('.quickassign summary').click();
      const quick = first.locator('.quickagent'); assert.equal(await quick.isDisabled(), true, 'quick-assign is off on a waiting card');
      assert.match(await quick.getAttribute('title'), /waiting on Acme finance/);
      await page.keyboard.press('Escape');
      await page.evaluate(() => { location.hash = '#1'; }); await page.locator('#dlgCard[open]').waitFor();
      await page.locator('#cWhoAdd').click();
      const item = page.locator('.ui-menu [role=menuitem]', { hasText: 'Claude' }); assert.equal(await item.isDisabled(), true); assert.match(await item.textContent(), /waiting/);
      await page.keyboard.press('Escape');
      const saved = page.waitForResponse(r => ['PUT', 'PATCH'].includes(r.request().method()) && r.url().startsWith('https://api.test/repos/acme/board/'));
      await page.locator('#cmText').fill('@claude please take this'); await page.locator('#cmPost').click(); await saved;
      await page.locator('.ui-toast', { hasText: 'is waiting on Acme finance' }).waitFor();
      assert.equal(await page.locator('#dlgSend[open]').count(), 0, 'no send dialog on a waiting card');
      assert.equal(api.card('t_one').claim, null, 'no placeholder claim on a waiting card'); assert.ok(api.card('t_one').waiting, 'the wait is kept');
      assert.equal(cron.filter(c => c.method === 'PUT').length, 0, 'no cron-job.org job is created');
      await page.locator('#cClose').click();
      await page.evaluate(() => { const f = document.getElementById('fWaiting'); f.checked = true; f.dispatchEvent(new Event('change')); });
      assert.deepEqual(await page.locator('.card .t').allTextContents(), ['First'], 'the Waiting filter shows only waiting cards');
      await page.close();
    }

    // ---- 2. room under the limit: the same board with max_agent_claims 3 sends, and the routine text matches the new CLI rules ----
    {
      const api = new Github(), cron = []; { const r = JSON.parse(api.files['tasks.json']); r.settings.max_agent_claims = 3; api.files['tasks.json'] = text(r); }
      { const c = api.card('t_one'); c.assignees = []; api.files['cards/t_one.json'] = text(c); }   // not yet assigned: sending it to Claude assigns it to the sender
      const page = await openBoard(browser, api, cron);
      await page.locator('.col[data-col="todo"] .hcinema').click();
      const first = page.locator('.cinema-col .card', { hasText: 'First' }); await first.locator('.quickassign summary').click();
      assert.equal(await first.locator('.quickagent').isDisabled(), false, 'quick-assign works with room under the limit');
      cronSession = 'https://claude.ai/code/session_ABC123';   // the routine's reply is already there when the page first polls: before the routine has claimed
      const saved = page.waitForResponse(r => ['PUT', 'PATCH'].includes(r.request().method()) && r.url().startsWith('https://api.test/repos/acme/board/')), relay = page.waitForRequest(r => r.method() === 'PUT' && r.url() === 'https://cron.test/jobs');
      await first.locator('.quickagent').click(); const [, req] = await Promise.all([saved, relay]);
      assert.equal(api.card('t_one').claim.agent, 'claude'); assert.match(api.card('t_one').claim.session_id, /^pending-/);
      assert.deepEqual(api.card('t_one').assignees, ['alex'], 'the card is assigned to the person whose routine will claim it');
      { // the routine's reply arrives before the routine has claimed: the page records the link but keeps its placeholder, so the routine's own claim still replaces it
        const deadline = Date.now() + 15000; while (Date.now() < deadline && !(api.card('t_one').claim || {}).session_url) await new Promise(r => setTimeout(r, 200));
        const c = api.card('t_one').claim; assert.equal(c.session_url, cronSession, 'the session link is recorded on the claim');
        assert.match(c.session_id, /^pending-/, 'the claim stays a placeholder: the link id is never the owning session id');
        assert.ok(api.card('t_one').comments.some(m => m.type === 'activity' && /session_ABC123/.test(m.text)), 'the activity line carries the link');
        cronSession = null;
      }
      const routine = JSON.parse(req.postDataJSON().job.extendedData.body).text;
      assert.doesNotMatch(routine, /--force/, 'the routine no longer claims with --force');
      assert.match(routine, /keeptrack\.py claim '#1' --for alex --agent claude --session <a short random id you generate for this run> --note "working"/);
      assert.match(routine, /done '#1' --note "<result>"/); assert.match(routine, /open checklist items/); assert.match(routine, /todo-done/); assert.match(routine, /done '#1' --cancel --note "<why>"/);
      await page.close();
    }

    // ---- 3. a cancelled outcome: pill on the Done card, line in the drawer, line in the Markdown export ----
    {
      const api = new Github(), cron = [], page = await openBoard(browser, api, cron);
      const four = page.locator('.col[data-col="done"] .card', { hasText: 'Fourth' }), six = page.locator('.col[data-col="done"] .card', { hasText: 'Sixth' });
      assert.equal(await four.locator('.chip.cancelledchip').count(), 1); assert.equal((await four.locator('.chip.cancelledchip').textContent()).trim(), 'cancelled');
      assert.equal(await six.locator('.chip.cancelledchip').count(), 0, 'a completed card has no cancelled pill');
      assert.equal(await page.locator('.col[data-col="todo"] .chip.cancelledchip').count(), 0);
      await four.dblclick(); await page.locator('#dlgCard[open]').waitFor();
      const lr = page.locator('#cLastRun'); await lr.waitFor(); assert.match(await lr.textContent(), /Outcome: cancelled · Dropped: duplicate of #1/);
      await page.locator('#cHead [aria-label="More actions"]').click(); await page.locator('.ui-menu [role=menuitem]', { hasText: 'Copy as Markdown' }).click();
      await page.waitForFunction(() => window.__copied); const md = await page.evaluate(() => window.__copied);
      assert.match(md, /- \*\*Outcome:\*\* cancelled · "Dropped: duplicate of #1"/);
      { // reopening the card from the drawer clears its outcome, on the card and in its run record, as keeptrack.py move does
        const w = page.waitForResponse(r => ['PUT', 'PATCH'].includes(r.request().method()) && r.url().startsWith('https://api.test/repos/acme/board/'));   // a move may save through the git data API
        await page.locator('#cCol').selectOption('todo'); await w;
        const c = api.card('t_four'); assert.equal(c.column, 'todo'); assert.equal(c.outcome, undefined, 'reopening clears the outcome'); assert.equal((c.last_run || {}).outcome, undefined, 'and the run record');
        assert.equal(await page.locator('.col[data-col="todo"] .chip.cancelledchip').count(), 0);
      }
      await page.locator('#dlgCard').evaluate(d => d.close());
      await six.dblclick(); await page.locator('#dlgCard[open]').waitFor(); assert.doesNotMatch(await page.locator('#cLastRun').textContent(), /Outcome: cancelled/);
      await page.close();
    }

    assert.deepEqual(errors, [], 'no page errors: ' + errors.join('; '));
    console.log('agent-limit: all checks passed');
  } catch (e) { console.error(e); process.exitCode = 1; }
  finally { await browser.close(); server.close(); }
})();

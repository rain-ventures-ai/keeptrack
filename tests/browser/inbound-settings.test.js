'use strict';
// kit v122: Settings → Board → Inbound edits the sources and the drain schedule with the rules of keeptrack.py inbound-source / inbound-schedule,
// and lists the waiting and failed items as text. Run: node inbound-settings.test.js

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

const stampForTest=()=> '2020-01-01T00:00:00Z';
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
    if (p.startsWith('/contents/board/') && method === 'PUT') { const rel = p.slice('/contents/board/'.length), b = req.postDataJSON(); if (b.sha && b.sha!==this.sha(rel)) { this.staleWrites=(this.staleWrites||0)+1; return json({message:'sha does not match'},409); } this.files[rel] = Buffer.from(b.content, 'base64').toString(); this.head = 'head-' + ++this.n; return json({ content: { sha: this.sha(rel) }, commit: { sha: this.head, tree: { sha: 'root-' + this.n } } }); }
    if (p.startsWith('/contents/board/') && method === 'DELETE') { delete this.files[p.slice('/contents/board/'.length)]; this.head = 'head-' + ++this.n; return json({ commit: { sha: this.head, tree: { sha: 'root-' + this.n } } }); }
    if (p === '/git/ref/heads/main' && method === 'GET') return json({ object: { sha: this.head } });
    if (p.startsWith('/git/commits/') && method === 'GET') return json({ tree: { sha: 'root-' + this.n } });
    if (p.startsWith('/git/trees/root-') && method === 'GET') return json({ tree: [{ path: 'board', type: 'tree', sha: 'board-' + this.n }] });
    if (p.startsWith('/git/trees/board-') && method === 'GET') return json({ truncated: false, tree: Object.entries(this.files).map(([f, c]) => ({ path: f, type: 'blob', sha: this.sha(f), size: Buffer.byteLength(c) })) });
    if (p.startsWith('/git/blobs/') && method === 'GET') { const sha = p.split('/').pop(), rel = Object.keys(this.files).find(x => this.sha(x) === sha); return json({ encoding: 'base64', content: Buffer.from(this.files[rel]).toString('base64') }); }
    if (p === '/git/blobs' && method === 'POST') { const content=req.postDataJSON().content, sha=crypto.createHash('sha1').update(content).digest('hex'); this.n++; this.blobs[sha]=content; return json({ sha }); }
    if (p === '/git/trees' && method === 'POST') { this.pending = req.postDataJSON().tree; return json({ sha: 'new-tree-' + ++this.n }); }
    if (p === '/git/commits' && method === 'POST') return json({ sha: 'new-commit-' + ++this.n });
    if (p === '/git/refs/heads/main' && method === 'PATCH') { for (const e of this.pending || []) { const rel = e.path.replace(/^board\//, ''); if (e.sha === null) delete this.files[rel]; else this.files[rel] = this.blobs[e.sha]; } this.head = req.postDataJSON().sha; return json({ object: { sha: this.head } }); }
    return json({ message: 'not mocked: ' + method + ' ' + p }, 404);
  }
  card(id = 't_one') { return this.files[`cards/${id}.json`] ? JSON.parse(this.files[`cards/${id}.json`]) : null; }
}
let base;
const init = () => { localStorage.setItem('kb_repo', 'acme/board'); localStorage.setItem('kb_branch', 'main'); localStorage.setItem('kb_path', 'board/tasks.json'); localStorage.setItem('kb_token', 'test'); localStorage.setItem('kb_me', 'alex'); localStorage.setItem('kb_api', 'https://api.test'); localStorage.setItem('kb_layout', 'classic'); localStorage.setItem('kb_tour_seen', '1'); sessionStorage.setItem('kb_view', 'board'); };
const settings = api => JSON.parse(api.files['tasks.json']).settings || {};

(async () => {
  await new Promise(ok => server.listen(0, '127.0.0.1', ok)); base = `http://127.0.0.1:${server.address().port}`;
  const browser = await chromium.launch({ headless: true });
  try {
    const api = new Github(), waiting = '20261030T170000Z-rainshift-contact-a.json', bad = '20261030T170100Z-rainshift-contact-b.json', evil = '20261030T170200Z-x<img src=x onerror=window.__pwned=1>.json';
    const r = JSON.parse(api.files['tasks.json']);
    r.settings = { title: 'Test', inbound: { 'rainshift-contact': { mode: 'review', handler: 'board-intake/plan.py' } } };
    r.inbound = { failed: { [bad]: { error: '<b>bold</b> bad JSON', since: '2026-10-30T17:02:00.000Z' } }, last_run: { at: '2026-10-30T09:08:01.000Z', handled: 0, failed: 0 } };
    api.files['tasks.json'] = text(r); [waiting, bad, evil].forEach(n => { api.files['inbound/' + n] = '{}'; });
    const page = await browser.newPage(); page.on('pageerror', e => console.error('page error:', e.message));
    await page.addInitScript(init); await page.route('https://api.test/**', route => api.route(route));
    await page.goto(base + '/board/index.html'); await page.waitForSelector('.card'); await page.waitForFunction(() => window.kbSettings);
    const until = async (fn, what) => { for (let i = 0; i < 100; i++) { if (fn()) return; await page.waitForTimeout(100); } assert.fail('timed out: ' + what); };
    await page.evaluate(() => window.kbSettings.open('inbound'));
    const box = page.locator('#inboundBox'); await box.waitFor({ state: 'visible' });
    // the items: names and errors are text, never markup
    const words = await box.textContent();
    assert.match(words, /rainshift-contact-a\.json/); assert.match(words, /failed: <b>bold<\/b> bad JSON/); assert.match(words, /Last drain run: Fri 30 Oct 09:08 \(UTC\)/);
    assert.equal(await box.locator('img, b').count(), 0, 'no markup from item names or errors'); assert.equal(await page.evaluate(() => window.__pwned), undefined);
    if (SHOTS) { fs.mkdirSync(SHOTS, { recursive: true }); await page.locator('#secInbound').screenshot({ path: path.join(SHOTS, 'inbound-settings.png') }); }
    // the schedule: a bad one is refused, a good one is saved with the stored shape
    const times = box.getByLabel('Run times'); await times.fill('25:00'); await box.locator('.inbdays input[value=mon]').check();
    await box.getByRole('button', { name: 'Save schedule' }).click(); await page.waitForTimeout(300);
    assert.equal(settings(api).inbound_schedule, undefined, 'a bad time saves nothing');
    for (const d of ['mon', 'tue', 'wed', 'thu', 'fri']) await box.locator(`.inbdays input[value=${d}]`).check();
    await times.fill('09:07'); for (const z of ['+05:30', 'Nowhere/Land', 'asia/nowhere']) {   // an offset, an unknown name: refused
      await box.getByLabel('Time zone').fill(z); await box.getByRole('button', { name: 'Save schedule' }).click(); await page.waitForTimeout(250);
      assert.equal(settings(api).inbound_schedule, undefined, z + ' is refused');
    }
    await box.getByLabel('Time zone').fill('Asia/Kolkata'); await box.getByRole('button', { name: 'Save schedule' }).click();   // kept as typed: ICU would rename it to Asia/Calcutta, which Python may not know
    await until(() => settings(api).inbound_schedule, 'a zone is saved as typed'); assert.equal(settings(api).inbound_schedule.tz, 'Asia/Kolkata');
    await box.getByLabel('Time zone').fill(''); await box.getByRole('button', { name: 'Save schedule' }).click();   // empty: a zone is still stored, never left to each reader
    await until(() => settings(api).inbound_schedule.tz === 'UTC', 'an empty zone stores UTC');
    await times.fill('11:07, 9:07'); await box.getByLabel('Time zone').fill('europe/london');
    await box.getByRole('button', { name: 'Save schedule' }).click();
    await until(() => (settings(api).inbound_schedule || {}).tz === 'Europe/London', 'the schedule is saved');
    assert.deepEqual(settings(api).inbound_schedule, { days: ['mon', 'tue', 'wed', 'thu', 'fri'], times: ['09:07', '11:07'], tz: 'Europe/London', grace_minutes: 30 });
    assert.deepEqual(Object.keys(settings(api).inbound), ['rainshift-contact'], 'other settings are kept');
    // a source: card mode asks first, then saves the fields as keeptrack.py inbound-source would
    const src = box.locator('details.inbsrc', { hasText: 'rainshift-contact' }); await src.locator('summary').click();
    const form = src.locator('.inbfield');
    await src.locator('select').first().selectOption('card');
    await form.filter({ hasText: 'Assign to' }).locator('input').fill('JezHub, @osouthgate'); await form.filter({ hasText: 'Labels' }).locator('input').fill('enquiry, enquiry');
    await form.filter({ hasText: 'Checklist' }).locator('textarea').fill('Reply within one day\n\n  Add to   CRM  '); await form.filter({ hasText: 'Column' }).locator('select').selectOption('todo');
    await src.getByRole('button', { name: 'Save source' }).click();
    await page.getByRole('button', { name: 'Set card mode' }).waitFor(); assert.equal(settings(api).inbound['rainshift-contact'].mode, 'review', 'not saved before the confirmation');
    await page.getByRole('button', { name: 'Set card mode' }).click();
    await until(() => settings(api).inbound['rainshift-contact'].mode === 'card', 'card mode is saved');
    assert.deepEqual(settings(api).inbound['rainshift-contact'], { assign: ['JezHub', 'osouthgate'], column: 'todo', handler: 'board-intake/plan.py', labels: ['enquiry'], mode: 'card', todos: ['Reply within one day', 'Add to CRM'] });
    // a handler outside the rules is refused
    const open2 = box.locator('details.inbsrc', { hasText: 'rainshift-contact' }); if (!(await open2.evaluate(e => e.open))) await open2.locator('summary').click();
    for (const h of ['../evil.py', '/etc/x.py', 'board/inbound/x.py', 'plan.sh']) {
      await open2.locator('.inbfield', { hasText: 'Handler' }).locator('input').fill(h); await open2.getByRole('button', { name: 'Save source' }).click(); await page.waitForTimeout(250);
      assert.equal(settings(api).inbound['rainshift-contact'].handler, 'board-intake/plan.py', h + ' is refused');
    }
    await open2.locator('.inbfield', { hasText: 'Handler' }).locator('input').fill('board-intake/other.py'); await open2.getByRole('button', { name: 'Save source' }).click();
    await page.getByRole('button', { name: 'Use handler' }).waitFor(); assert.equal(settings(api).inbound['rainshift-contact'].handler, 'board-intake/plan.py', 'not saved before the confirmation');
    await page.getByRole('button', { name: 'Use handler' }).click(); await until(() => settings(api).inbound['rainshift-contact'].handler === 'board-intake/other.py', 'the handler is saved after the confirmation');
    // a new source starts in review mode, and can be removed
    await box.getByLabel('New source name').fill('Bad Name'); await box.getByRole('button', { name: 'Add source' }).click(); await page.waitForTimeout(250);
    assert.equal(settings(api).inbound['Bad Name'], undefined);
    await box.getByLabel('New source name').fill('booking'); await box.getByRole('button', { name: 'Add source' }).click();
    await until(() => settings(api).inbound.booking, 'the new source is saved'); assert.deepEqual(settings(api).inbound.booking, { mode: 'review' });
    await box.locator('details.inbsrc', { hasText: 'booking' }).locator('summary').click();
    await box.locator('details.inbsrc', { hasText: 'booking' }).getByRole('button', { name: 'Remove source' }).click(); await page.getByRole('contentinfo').getByRole('button', { name: 'Remove' }).click();
    await until(() => !settings(api).inbound.booking, 'the source is removed'); assert.ok(settings(api).inbound['rainshift-contact'], 'the other source stays');
    await box.getByRole('button', { name: 'Clear schedule' }).click(); await until(() => !settings(api).inbound_schedule, 'the schedule is cleared');
    await page.close();
    // a hand-edited source with values of the wrong type must not break the Board tab
    const bad2 = JSON.parse(api.files['tasks.json']); bad2.settings.inbound = { odd: { assign: 'alex', labels: 5, todos: { a: 1 }, handler: 7, mode: 'card' } }; api.files['tasks.json'] = text(bad2);
    const p2 = await browser.newPage(); const errors = []; p2.on('pageerror', e => errors.push(e.message));
    await p2.addInitScript(init); await p2.route('https://api.test/**', route => api.route(route)); await p2.goto(base + '/board/index.html'); await p2.waitForSelector('.card'); await p2.waitForFunction(() => window.kbSettings);
    await p2.evaluate(() => window.kbSettings.open('inbound')); await p2.locator('#inboundBox details.inbsrc', { hasText: 'odd' }).waitFor(); assert.deepEqual(errors, [], 'no page error'); await p2.locator('#archBox').waitFor();
    await p2.close();
    console.log('inbound settings: ok');
  } finally { await browser.close(); server.close(); }
})().catch(e => { console.error(e); process.exit(1); });

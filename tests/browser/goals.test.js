'use strict';
// Goals (kit v83): the Goals bar above the board shows each active goal with its target, progress, days left and open
// cards; a click filters the board to that goal, "No goal" to the open cards that link to none. The card drawer's Goal
// field links a card; the Goals sheet adds and edits goals. Run: node goals.test.js (SHOTS=dir also saves screenshots)

const assert = require('node:assert/strict');
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { chromium } = require('playwright');

const ROOT = path.resolve(__dirname, '../..');
const SHOTS = process.env.SHOTS || '';   // a folder: also save screenshots
const shot = async (page, name) => { if (SHOTS) { fs.mkdirSync(SHOTS, { recursive: true }); await page.screenshot({ path: path.join(SHOTS, name + '.png') }); } };
const mime = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json', '.svg': 'image/svg+xml' };
const server = http.createServer((req, res) => {
  const rel = decodeURIComponent(new URL(req.url, 'http://local').pathname).replace(/^\/+/, '') || 'board/index.html';
  const file = path.resolve(ROOT, rel); if (!file.startsWith(ROOT + path.sep)) { res.writeHead(403).end(); return; }
  fs.readFile(file, (err, data) => { if (err) res.writeHead(404).end(); else { res.setHeader('Content-Type', mime[path.extname(file)] || 'application/octet-stream'); res.end(data); } });
});


const day = n => { const d = new Date(Date.now() + n * 864e5); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`; };
const soon = day(5);
const text = x => JSON.stringify(x, null, 2) + '\n';
const root = { version: 4, layout: 'split', settings: { title: 'Goals test' }, columns: [{ id: 'todo', name: 'To do' }, { id: 'done', name: 'Done' }], people: [{ github: 'alex', name: 'Alex' }], agents: [], clients: ['Acme'], labels: [], client_info: {}, next_num: 4, archive: { files: {} } };
const card = (id, num, title, extra) => ({ id, num, title, column: 'todo', client: '', priority: 'medium', due: '', labels: [], assignees: [], details: '', links: [], contacts: [], todos: [], comments: [], history: [], claim: null, created: '2026-10-01T08:00:00.000Z', updated: '2026-10-01T08:00:00.000Z', rank: 'a' + num, ...extra });

// A small GitHub: contents API for reads and single-file writes, git data API for multi-file commits (same shape as split-storage.test.js).
class Github {
  constructor({ goals = true } = {}) {
    this.files = { 'tasks.json': text({ ...root, next_num: 4, goals: [
        { id: 'g_revenue001', title: 'Monthly revenue', metric: 'revenue per month', target: '£10,000', current: '£4,200', end: soon, status: 'active' },
        { id: 'g_pilots0001', title: 'Three paying pilots with a much longer goal name that wraps', metric: 'signed pilots', target: '3', end: '2099-03-31', status: 'active' },
        { id: 'g_oldgoal001', title: 'Old goal', metric: 'm', target: '1', end: '2020-01-01', status: 'done' }] }),
      'cards/t_one.json': text(card('t_one', 1, 'Send the proposal to Acme', { goal: 'g_revenue001' })),
      'cards/t_two.json': text(card('t_two', 2, 'Book the workshop room')),
      'cards/t_three.json': text(card('t_three', 3, 'Call the second pilot', { goal: 'g_pilots0001' })) };
    if (!goals) { const r = JSON.parse(this.files['tasks.json']); delete r.goals; this.files['tasks.json'] = text(r); delete this.files['cards/t_one.json']; delete this.files['cards/t_three.json']; }
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


async function open(browser, base, { view = 'board', viewport = { width: 1280, height: 900 }, theme = '', goals = true } = {}) {
  const api = new Github({ goals }), page = await browser.newPage({ viewport }), errors = []; page.on('pageerror', e => errors.push(e.message));
  await page.addInitScript(([v, th]) => { localStorage.setItem('kb_repo', 'acme/board'); localStorage.setItem('kb_branch', 'main'); localStorage.setItem('kb_path', 'board/tasks.json'); localStorage.setItem('kb_token', 'test'); localStorage.setItem('kb_me', 'alex'); localStorage.setItem('kb_api', 'https://api.test'); localStorage.setItem('kb_tour', 'done'); if (th) localStorage.setItem('kb_theme', th); sessionStorage.setItem('kb_view', v); }, [view, theme]);
  await page.route('https://api.test/**', r => api.route(r)); await page.goto(base + '/board/index.html');
  await page.waitForFunction(v => document.body.dataset.view === v && document.getElementById('board').childElementCount > 0, view);
  page.errors = errors; page.api = api; return page;
}
const cardCount = page => page.locator('#board .card').count();

(async () => {
  await new Promise(ok => server.listen(0, '127.0.0.1', ok)); const base = `http://127.0.0.1:${server.address().port}`;
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await open(browser, base);
    await page.waitForSelector('#goalBar:not([hidden]) .goalchip');
    const chips = await page.locator('#goalBar .goalchip').evaluateAll(cs => cs.map(c => ({ goal: c.dataset.goal, text: c.textContent, bar: c.querySelector('.goalchip__bar > span') ? c.querySelector('.goalchip__bar > span').style.width : null, soon: c.classList.contains('soon') })));
    assert.deepEqual(chips.map(c => c.goal), ['g_revenue001', 'g_pilots0001', '__none'], 'active goals by end date, then No goal; a done goal is not in the bar');
    assert.match(chips[0].text, /£4,200 of £10,000 revenue per month · 5 days left · 1 open/);
    assert.equal(chips[0].bar, '42%'); assert.equal(chips[0].soon, true, 'ends within a week and not reached');
    assert.equal(chips[1].bar, null, 'no current value: no progress bar'); assert.match(chips[2].text, /No goal1 open/);
    assert.equal(await cardCount(page), 3);
    await shot(page, 'goals-board-light');
    await page.locator('#goalBar .goalchip[data-goal="g_revenue001"]').click();
    await page.waitForFunction(() => document.querySelectorAll('#board .card').length === 1);
    assert.equal(await page.locator('#fGoal').inputValue(), 'g_revenue001'); assert.match(page.url(), /[?&]goal=g_revenue001/);
    assert.equal(await page.locator('#goalBar .goalchip.on').count(), 1);
    await page.locator('#goalBar .goalchip[data-goal="__none"]').click();
    await page.waitForFunction(() => document.querySelectorAll('#board .card').length === 1 && /Book the workshop room/.test(document.querySelector('#board .card').textContent));
    await page.locator('#goalBar .goalchip[data-goal="__none"]').click();
    await page.waitForFunction(() => document.querySelectorAll('#board .card').length === 3);
    // the card drawer: link card #2 to the revenue goal; only active goals are offered
    await page.evaluate(() => { location.hash = '#2'; }); await page.locator('#dlgCard[open]').waitFor();
    assert.equal(await page.locator('#cGoalRow').isHidden(), false);
    assert.deepEqual(await page.locator('#cGoal option').evaluateAll(o => o.map(x => x.value)), ['', 'g_revenue001', 'g_pilots0001']);
    await page.locator('#cGoal').selectOption('g_revenue001');
    await page.waitForFunction(() => /Saved/.test(document.getElementById('status').textContent));
    assert.equal(page.api.card('t_two').goal, 'g_revenue001');
    await shot(page, 'goals-drawer');
    await page.locator('#cGoal').selectOption('');
    await page.waitForFunction(() => /Saved/.test(document.getElementById('status').textContent) && !document.getElementById('status').textContent.includes('Saving'));
    assert.equal(page.api.card('t_two').goal, undefined, 'No goal takes the link off');
    await page.locator('#cClose').click(); await page.locator('#dlgCard').waitFor({ state: 'hidden' });
    // the Goals sheet: add a goal; the form refuses one with no end date
    await page.locator('#goalEdit').click(); await page.locator('#dlgGoals[open]').waitFor();
    assert.equal(await page.locator('#dlgGoals .goalrow').count(), 3, 'the sheet lists every goal, done ones too');
    await shot(page, 'goals-sheet');
    await page.locator('#goalAdd').click();
    await page.locator('#goalTitle').fill('Newsletter'); await page.locator('#goalMetric').fill('subscribers'); await page.locator('#goalTarget').fill('500');
    await page.locator('#goalSave').click(); assert.equal(await page.locator('#goalErr').textContent(), 'A goal needs an end date.');
    await page.locator('#goalEnd').fill('2099-12-31'); await page.locator('#goalCurrent').fill('120');
    await shot(page, 'goals-form');
    await page.locator('#goalSave').click();
    await page.waitForFunction(() => document.querySelectorAll('#dlgGoals .goalrow').length === 4);
    const saved = JSON.parse(page.api.files['tasks.json']).goals.find(g => g.title === 'Newsletter');
    assert.ok(saved && /^g_[a-z0-9]{10}$/.test(saved.id), JSON.stringify(saved));
    assert.deepEqual([saved.metric, saved.target, saved.current, saved.end, saved.status, saved.updatedBy], ['subscribers', '500', '120', '2099-12-31', 'active', 'alex']);
    assert.ok(!('start' in saved), 'an empty start date is not stored');
    // edit: mark the pilots goal done, then it leaves the bar
    await page.locator('#dlgGoals .goalrow[data-goal="g_pilots0001"] button').click();
    await page.locator('#goalStatus').selectOption('done'); await page.locator('#goalSave').click();
    await page.waitForFunction(() => !document.getElementById('goalTitle'));
    assert.equal(JSON.parse(page.api.files['tasks.json']).goals.find(g => g.id === 'g_pilots0001').status, 'done');
    await page.keyboard.press('Escape'); await page.locator('#dlgGoals').waitFor({ state: 'detached' });
    assert.deepEqual(await page.locator('#goalBar .goalchip').evaluateAll(cs => cs.map(c => c.dataset.goal)), ['g_revenue001', saved.id, '__none'], 'a done goal leaves the bar');
    assert.deepEqual(page.errors, []); await page.close();

    for (const [name, viewport, theme] of [['goals-phone-light', { width: 390, height: 800 }, 'light'], ['goals-phone-dark', { width: 390, height: 800 }, 'dark'], ['goals-board-dark', { width: 1280, height: 900 }, 'dark']]) {
      const p = await open(browser, base, { viewport, theme }); await p.waitForSelector('#goalBar:not([hidden]) .goalchip');
      const scroll = await p.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth); assert.ok(scroll <= 0, name + ': no sideways page scroll');
      await shot(p, name); assert.deepEqual(p.errors, []); await p.close();
    }
    // a board with no goals shows no bar, no Goal filter and no Goal field on a card that has none
    { const p = await open(browser, base, { goals: false }); await p.waitForSelector('#board .card');
      assert.equal(await p.locator('#goalBar').isHidden(), true); assert.equal(await p.locator('#fGoalWrap').isHidden(), true);
      await p.evaluate(() => { location.hash = '#2'; }); await p.locator('#dlgCard[open]').waitFor(); assert.equal(await p.locator('#cGoalRow').isHidden(), true);
      await p.locator('#cClose').click(); await p.locator('#dlgCard').waitFor({ state: 'hidden' });
      await p.locator('#btnFilter').click(); await p.locator('#fGoals').click(); await p.locator('#dlgGoals[open]').waitFor();   // the first goal: reachable on a wide screen
      await p.locator('#goalAdd').click(); await p.locator('#goalTitle').fill('First'); await p.locator('#goalMetric').fill('m'); await p.locator('#goalTarget').fill('1'); await p.locator('#goalEnd').fill('2099-01-01');
      await p.locator('#goalSave').click(); await p.waitForFunction(() => document.querySelectorAll('#dlgGoals .goalrow').length === 1);
      assert.equal(JSON.parse(p.api.files['tasks.json']).goals[0].title, 'First');
      assert.deepEqual(p.errors, []); await p.close(); }
    console.log('goals: all checks passed');
  } finally { await browser.close(); server.close(); }
})().catch(e => { console.error(e); process.exit(1); });

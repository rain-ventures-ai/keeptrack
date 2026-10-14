'use strict';
// Today "Prep for call": a brief for a call with another board member, built from board data only.
const assert = require('node:assert/strict');
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { chromium } = require('playwright');

const ROOT = path.resolve(__dirname, '../..');
const SHOTS = process.env.SHOTS || '';
const mime = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json', '.svg': 'image/svg+xml', '.md': 'text/markdown' };
const server = http.createServer((req, res) => {
  const rel = decodeURIComponent(new URL(req.url, 'http://local').pathname).replace(/^\/+/, '') || 'board/index.html';
  const file = path.resolve(ROOT, rel); if (!file.startsWith(ROOT + path.sep)) return res.writeHead(403).end();
  fs.readFile(file, (error, data) => { if (error) res.writeHead(404).end(); else { res.setHeader('Content-Type', mime[path.extname(file)] || 'application/octet-stream'); res.end(data); } });
});

const now = new Date(), iso = d => d.toISOString(), day = n => iso(new Date(now.getTime() + n * 864e5)).slice(0, 10);
const task = (id, num, title, column, extra = {}) => ({ id, num, title, column, client: '', priority: 'medium', due: '', labels: [], assignees: ['alex'], details: '', links: [], contacts: [], todos: [], comments: [], history: [], claim: null, created: '2026-10-01T08:00:00Z', updated: '2026-10-01T08:00:00Z', ...extra });
const board = {
  version: 3, settings: { title: 'Prep test', stale_after_minutes: 30 },
  columns: [{ id: 'backlog', name: 'Backlog' }, { id: 'todo', name: 'To do' }, { id: 'in-progress', name: 'In progress' }, { id: 'done', name: 'Done' }],
  people: [{ github: 'alex', name: 'Alexander' }, { github: 'sam', name: 'Sam' }, { github: 'kim', name: 'Kim' }], agents: ['claude'], clients: [], labels: [], contacts: [], projects: [], client_info: {},
  tasks: [
    task('t_goal', 1, 'GOAL: £5k a month by December', 'in-progress', { assignees: ['alex', 'sam'] }),
    task('t_talk', 2, 'Discuss pricing page with Alex', 'todo', { assignees: ['sam'] }),
    task('t_late', 3, 'Send the proposal to a fictional client', 'todo', { assignees: ['sam'], due: day(-3) }),
    task('t_ask', 4, 'Draft the onboarding email', 'todo', { assignees: ['alex'], comments: [{ id: 'c1', at: iso(now), by: 'claude@sam', text: '@alex can you check the subject line?' }] }),
    task('t_shared', 5, 'Plan the workshop', 'in-progress', { assignees: ['alex', 'sam'] }),
    task('t_done', 6, 'Fix the invoice template', 'done', { assignees: ['sam'], history: [{ at: iso(now), by: 'sam', text: 'done' }] }),
    task('t_other', 7, 'Discuss travel with Alex', 'todo', { assignees: ['kim'] }),
    task('t_mine', 9, 'Agree the budget with Kim', 'todo', { assignees: ['alex'] }),
    task('t_old', 8, 'Shared idea in backlog', 'backlog', { assignees: ['alex', 'sam'] })
  ]
};
const encoded = value => ({ sha: crypto.createHash('sha1').update(value).digest('hex'), size: Buffer.byteLength(value), encoding: 'base64', content: Buffer.from(value).toString('base64') });
async function route(r) {
  const url = new URL(r.request().url()), p = url.pathname.replace('/repos/acme/board', '');
  const json = (value, status = 200, headers = {}) => r.fulfill({ status, headers: { 'Content-Type': 'application/json', ...headers }, body: JSON.stringify(value) });
  if (p === '') return json({ private: true, permissions: { push: true }, default_branch: 'main' });
  if (p === '/contents/board/tasks.json') return json(encoded(JSON.stringify(board)), 200, { ETag: '"board"' });
  if (p === '/contents/board/KIT_VERSION') return r.fulfill({ status: 200, contentType: 'text/plain', body: '999' });
  return json({ message: 'Not Found' }, 404);
}
async function open(browser, base, viewport, theme) {
  const phone = viewport.width < 700, page = await browser.newPage({ viewport, isMobile: phone, hasTouch: phone, colorScheme: theme }), errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.addInitScript(() => {
    localStorage.setItem('kb_repo', 'acme/board'); localStorage.setItem('kb_branch', 'main'); localStorage.setItem('kb_path', 'board/tasks.json'); localStorage.setItem('kb_token', 'secret-test-token');
    localStorage.setItem('kb_me', 'alex'); localStorage.setItem('kb_api', 'https://api.test'); localStorage.setItem('kb_layout', 'dock'); localStorage.setItem('kb_tour', 'done'); sessionStorage.setItem('kb_view', 'today');
  });
  await page.route('https://api.test/**', route);
  await page.goto(base + '/board/index.html'); await page.waitForSelector('.todayhead'); page.errors = errors; return page;
}

(async () => {
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve)); const base = `http://127.0.0.1:${server.address().port}`;
  const browser = await chromium.launch({ headless: true });
  try {
    for (const [viewport, theme] of [[{ width: 1280, height: 900 }, 'light'], [{ width: 390, height: 844 }, 'dark']]) {
      const page = await open(browser, base, viewport, theme);
      assert.equal(await page.locator('.tprep').count(), 0, 'closed until asked');
      await page.locator('.tgo', { hasText: 'Prep for call' }).click(); await page.locator('.tprep').waitFor();
      await page.locator('.tprep select').selectOption('sam');
      const heads = await page.locator('.tprep__h span:not(.muted)').allTextContents();
      assert.deepEqual(heads, ['Goals', 'To discuss', 'Overdue or stuck', 'Asked of each other this week', 'Shared cards', 'Done in the last 7 days']);
      const rows = await page.locator('.tprep__row b').allTextContents();
      assert.deepEqual(rows, ['#1 GOAL: £5k a month by December', '#2 Discuss pricing page with Alex', '#3 Send the proposal to a fictional client', '#4 Draft the onboarding email', '#5 Plan the workshop', '#6 Fix the invoice template']);
      assert.ok(!rows.some(r => /Kim|backlog/.test(r)), 'other people and backlog cards stay out');
      if (SHOTS) { fs.mkdirSync(SHOTS, { recursive: true }); await page.locator('.tprep').screenshot({ path: path.join(SHOTS, `prep-call-${viewport.width}-${theme}.png`) }); }
      const wide = await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth); assert.ok(wide, 'no sideways scroll');
      await page.locator('.tprep__row', { hasText: 'Discuss pricing page' }).click(); await page.locator('#dlgCard[open]').waitFor();
      assert.equal(await page.locator('#cTitle').inputValue(), 'Discuss pricing page with Alex');
      assert.deepEqual(page.errors, []); await page.close();
    }
    const page = await open(browser, base, { width: 1280, height: 900 }, 'light');
    await page.locator('.tgo', { hasText: 'Prep for call' }).click(); await page.locator('.tprep select').selectOption('kim');
    assert.deepEqual(await page.locator('.tprep__row b').allTextContents(), ['#1 GOAL: £5k a month by December', '#7 Discuss travel with Alex', '#9 Agree the budget with Kim'], 'goals show for every call');
    assert.equal(await page.evaluate(() => localStorage.getItem('kb_prep:acme/board:main:board/tasks.json') || Object.entries(localStorage).find(([k]) => k.startsWith('kb_prep:'))[1]), 'kim', 'last person is remembered');
    await page.locator('.tprep button', { hasText: 'Close' }).click(); assert.equal(await page.locator('.tprep').count(), 0);
    assert.deepEqual(page.errors, []);
    console.log('prep-call: all checks passed');
  } finally { await browser.close(); server.close(); }
})().catch(error => { console.error(error); process.exit(1); });

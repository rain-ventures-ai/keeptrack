'use strict';
// Board-owned Today widgets: the manifest comes only from the active board folder, renders on phone and desktop,
// opens native cards, and a weather request carries no GitHub credential.
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

const task = (id, num, title, column, created, extra = {}) => ({ id, num, title, column, client: '', priority: 'medium', due: '', labels: [], assignees: ['alex'], details: '', links: [], contacts: [], todos: [], comments: [], history: [], claim: null, created, updated: created, rank: 'a' + num, ...extra });
const board = {
  version: 3, settings: { title: 'Widget test', stale_after_minutes: 30 },
  columns: [{ id: 'backlog', name: 'Backlog' }, { id: 'todo', name: 'To do' }, { id: 'in-progress', name: 'In progress' }, { id: 'done', name: 'Done' }],
  people: [{ github: 'alex', name: 'Alex' }], agents: ['claude'], clients: [], labels: [], contacts: [], projects: [], client_info: {},
  tasks: [
    task('t_old', 1, 'Older backlog item', 'backlog', '2026-10-01T08:00:00Z'),
    task('t_new', 2, 'Newest to-do item', 'todo', '2026-10-12T08:00:00Z', { priority: 'high' }),
    task('t_agent', 3, 'Agent is researching', 'in-progress', '2026-10-10T08:00:00Z', { claim: { agent: 'claude', on_behalf_of: 'alex', status: 'running', claimed_at: new Date().toISOString(), heartbeat_at: new Date().toISOString() } })
  ]
};
const widgetFile = {
  version: 1,
  widgets: [
    { id: 'recent', slot: 'today.after-shortcuts', type: 'task-strip', title: 'Latest backlog and to-do', query: { columns: ['backlog', 'todo'], sort: 'created-desc', limit: 6 }, appearance: { density: 'thin', show: ['priority', 'number', 'title', 'column'] } },
    { id: 'weather', slot: 'today.after-shortcuts', type: 'weather', title: 'Outside now', location: { name: 'London', latitude: 51.5072, longitude: -0.1276 }, units: 'celsius' },
    { id: 'pulse', slot: 'today.after-shortcuts', type: 'board-pulse', title: 'Work pulse' }
  ]
};
const encoded = value => ({ sha: crypto.createHash('sha1').update(value).digest('hex'), size: Buffer.byteLength(value), encoding: 'base64', content: Buffer.from(value).toString('base64') });

class Api {
  constructor(widgets = widgetFile) { this.widgets = widgets; this.calls = []; this.weatherAuth = null; }
  async route(route) {
    const req = route.request(), url = new URL(req.url());
    if (url.hostname === 'api.open-meteo.com') {
      this.weatherAuth = req.headers().authorization || '';
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ current: { temperature_2m: 14.2, apparent_temperature: 13, weather_code: 2, wind_speed_10m: 11 }, daily: { temperature_2m_min: [9], temperature_2m_max: [16], precipitation_probability_max: [35] } }) });
    }
    const p = url.pathname.replace('/repos/acme/board', ''); this.calls.push(p);
    const json = (value, status = 200, headers = {}) => route.fulfill({ status, headers: { 'Content-Type': 'application/json', ...headers }, body: JSON.stringify(value) });
    if (p === '') return json({ private: true, permissions: { push: true }, default_branch: 'main' });
    if (p === '/contents/board/tasks.json') return json(encoded(JSON.stringify(board)), 200, { ETag: '"board"' });
    if (p === '/contents/board/widgets.json') return json(encoded(JSON.stringify(this.widgets)), 200, { ETag: '"widgets"' });
    if (p === '/contents/board/KIT_VERSION') return route.fulfill({ status: 200, contentType: 'text/plain', body: '999' });
    return json({ message: 'Not Found' }, 404);
  }
}

async function open(browser, base, api, viewport) {
  const phone = viewport.width < 700, page = await browser.newPage({ viewport, isMobile: phone, hasTouch: phone }), errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.addInitScript(() => {
    localStorage.setItem('kb_repo', 'acme/board'); localStorage.setItem('kb_branch', 'main'); localStorage.setItem('kb_path', 'board/tasks.json'); localStorage.setItem('kb_token', 'secret-test-token'); localStorage.setItem('kb_me', 'alex'); localStorage.setItem('kb_api', 'https://api.test'); localStorage.setItem('kb_layout', 'dock'); localStorage.setItem('kb_tour', 'done'); sessionStorage.setItem('kb_view', 'today');
  });
  await page.route('https://api.test/**', r => api.route(r)); await page.route('https://api.open-meteo.com/**', r => api.route(r));
  await page.goto(base + '/board/index.html'); await page.waitForSelector('.todayhead');
  page.errors = errors; return page;
}

(async () => {
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve)); const base = `http://127.0.0.1:${server.address().port}`;
  const browser = await chromium.launch({ headless: true });
  try {
    for (const viewport of [{ width: 390, height: 844 }, { width: 1280, height: 860 }]) {
      const api = new Api(), page = await open(browser, base, api, viewport);
      await page.waitForSelector('.kbwidgets'); await page.waitForSelector('.kwwweatherbody >> text=London');
      if (SHOTS) { fs.mkdirSync(SHOTS, { recursive: true }); await page.screenshot({ path: path.join(SHOTS, `widgets-${viewport.width}.png`), fullPage: true }); }
      assert.deepEqual(await page.locator('.kbwidget').evaluateAll(xs => xs.map(x => x.dataset.widget)), ['recent', 'weather', 'pulse']);
      assert.deepEqual(await page.locator('.kwwtask .kwwtitle').allTextContents(), ['Newest to-do item', 'Older backlog item']);
      const ys = await page.locator('.kwwtask').evaluateAll(xs => xs.map(x => Math.round(x.getBoundingClientRect().top))); assert.equal(new Set(ys).size, 1, 'task strip stays on one line');
      assert.match(await page.locator('.kwwweatherbody').textContent(), /14°C/); assert.match(await page.locator('.kwwweatherbody').textContent(), /35% rain/); assert.equal(api.weatherAuth, '', 'weather never receives the GitHub token');
      assert.deepEqual(await page.locator('.kwwmetric strong').allTextContents(), ['1', '1', '0', '0']);
      await page.locator('.kwwtask').first().click(); await page.locator('#dlgCard[open]').waitFor(); assert.equal(await page.locator('#cTitle').inputValue(), 'Newest to-do item');
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1), true, 'widgets do not add page-level sideways scroll');
      assert.deepEqual(page.errors, []); assert(api.calls.includes('/contents/board/widgets.json')); await page.close();
    }

    const bad = new Api({ version: 2, widgets: [] }), page = await open(browser, base, bad, { width: 390, height: 844 });
    await page.locator('.kwwproblem').waitFor(); assert.match(await page.locator('.kwwproblem').textContent(), /version 1/); assert.equal(await page.locator('.todayhead').count(), 1, 'a bad widget file does not stop Today'); await page.close();
    console.log('widgets: all checks passed');
  } finally { await browser.close(); server.close(); }
})().catch(error => { console.error(error); process.exit(1); });

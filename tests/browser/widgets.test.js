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
  columns: [{ id: 'backlog', name: 'Backlog' }, { id: 'todo', name: 'To do' }, { id: 'in-progress', name: 'In progress' }, { id: 'pending-review', name: 'Pending review' }, { id: 'done', name: 'Done' }],
  people: [{ github: 'alex', name: 'Alex' }], agents: ['claude'], clients: [], labels: [], contacts: [], projects: [], client_info: {},
  tasks: [
    task('t_old', 1, 'Older backlog item', 'backlog', '2026-10-01T08:00:00Z'),
    task('t_new', 2, 'Newest to-do item', 'todo', '2026-10-12T08:00:00Z', { priority: 'high' }),
    task('t_review', 4, 'Research done, decision open', 'pending-review', '2026-10-09T08:00:00Z'),   // kit v64: counted in the pulse
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
  constructor(widgets = widgetFile) { this.widgets = widgets; this.calls = []; this.weatherAuth = null; this.weatherRequests = []; }
  async route(route) {
    const req = route.request(), url = new URL(req.url());
    if (url.hostname === 'api.open-meteo.com') {
      this.weatherAuth = req.headers().authorization || '';
      this.weatherRequests.push({ latitude: url.searchParams.get('latitude'), longitude: url.searchParams.get('longitude'), headers: req.headers() });
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

async function open(browser, base, api, viewport, enabled = true, options = {}) {
  const phone = viewport.width < 700, page = await browser.newPage({ viewport, isMobile: phone, hasTouch: phone }), errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.addInitScript(([enabled, options]) => {
    if (enabled) localStorage.setItem(`kb_widgets:acme/board:${options.branch || 'main'}:board/tasks.json`, '1');
    localStorage.setItem('kb_widgets:acme/other:main:board/tasks.json', '1');
    localStorage.setItem('kb_repo', 'acme/board'); localStorage.setItem('kb_branch', options.branch || 'main'); localStorage.setItem('kb_path', 'board/tasks.json'); localStorage.setItem('kb_token', 'secret-test-token'); localStorage.setItem('kb_me', 'alex'); localStorage.setItem('kb_api', 'https://api.test'); localStorage.setItem('kb_layout', 'dock'); localStorage.setItem('kb_tour', 'done'); sessionStorage.setItem('kb_view', 'today');
    Object.entries(options.saved || {}).forEach(([key, value]) => localStorage.setItem(key, value));
    window.__geoRequests = 0;
    Object.defineProperty(navigator, 'geolocation', { configurable: true, value: { getCurrentPosition(success, error, settings) { window.__geoRequests++; window.__geoSuccess = success; window.__geoError = error; window.__geoOptions = settings; } } });
  }, [enabled, options]);
  await page.route('https://api.test/**', r => api.route(r)); await page.route('https://api.open-meteo.com/**', r => api.route(r));
  await page.goto(base + '/board/index.html'); await page.waitForSelector('.todayhead');
  page.errors = errors; return page;
}

(async () => {
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve)); const base = `http://127.0.0.1:${server.address().port}`;
  const browser = await chromium.launch({ headless: true });
  try {
    const offApi = new Api(), off = await open(browser, base, offApi, { width: 1280, height: 860 }, false);
    assert.equal(await off.locator('.kbwidget').count(), 0);
    assert.equal(offApi.calls.includes('/contents/board/widgets.json'), false, 'default off does not fetch board customisations');
    await off.locator('#dockMenu').click(); await off.locator('#dockPop [data-head-action="btnSettings"]').click();
    await off.locator('#sTheme').selectOption('sand');
    await off.locator('#sBoardAppearance').check();
    await off.locator('#sTheme').selectOption('dark'); await off.locator('#sStyle').selectOption('colorful');
    assert.equal(await off.evaluate(() => localStorage.getItem('kb_theme')), 'sand', 'board appearance does not replace browser theme');
    assert.equal(await off.evaluate(() => localStorage.getItem('kb_style')), null, 'board appearance does not replace browser style');
    await off.evaluate(() => window.kbTheme.useBoard({ repo: 'acme/other', branch: 'main', path: 'board/tasks.json' }));
    assert.equal(await off.locator('html').getAttribute('data-theme'), 'sand', 'another board uses browser default');
    assert.equal(await off.locator('html').getAttribute('data-style'), 'classic');
    await off.evaluate(() => window.kbTheme.useBoard({ repo: 'acme/board', branch: 'main', path: 'board/tasks.json' }));
    assert.equal(await off.locator('html').getAttribute('data-theme'), 'dark');
    assert.equal(await off.locator('html').getAttribute('data-style'), 'colorful');
    await off.locator('#sBoardAppearance').uncheck();
    assert.equal(await off.locator('html').getAttribute('data-theme'), 'sand');
    await off.locator('#sBoardAppearance').check();
    assert.equal(await off.locator('html').getAttribute('data-theme'), 'dark', 'disabled profile is preserved');
    await off.evaluate(() => window.kbDesignMd.apply({ paper: '#101010', ink: '#eeeeee', hero: '#cc4400', mode: 'dark', name: 'Board palette' }));
    assert.equal(await off.evaluate(() => localStorage.getItem('kb_custom')), null, 'imported board palette does not replace browser palette');
    await off.locator('#sBoardAppearance').uncheck();
    assert.equal(await off.locator('html').getAttribute('data-theme'), 'sand');
    await off.locator('#sBoardAppearance').check();
    assert.equal(await off.locator('html').getAttribute('data-theme'), 'custom');
    assert.equal(await off.locator('html').evaluate(x => x.style.getPropertyValue('--paper')), '#101010');
    for (const paper of ['url(https://attacker.invalid/pixel)', {}, 'garbage']) {
      assert.equal(await off.evaluate(paper => window.kbTheme.validateCustom({ paper, ink: '#eeeeee', hero: '#cc4400' }), paper), false);
      assert.equal(await off.evaluate(paper => { try { window.kbTheme.saveCustom({ paper, ink: '#eee', hero: '#c40' }); return false; } catch { return true; } }, paper), true);
    }
    await off.evaluate(() => { localStorage.setItem('kb_appearance:acme/bad:main:board/tasks.json', JSON.stringify({ enabled: true, theme: 'custom', custom: JSON.stringify({ paper: 'url(https://attacker.invalid/pixel)', ink: '#eee', hero: '#c40' }) })); window.kbTheme.useBoard({ repo: 'acme/bad', branch: 'main', path: 'board/tasks.json' }); });
    assert.equal(await off.locator('html').getAttribute('data-theme'), 'auto');
    assert.equal(await off.locator('html').evaluate(x => x.style.getPropertyValue('--paper')), '', 'invalid profile clears previous inline palette');
    await off.evaluate(() => window.kbTheme.useBoard({ repo: 'acme/board', branch: 'main', path: 'board/tasks.json' }));
    await off.locator('#sWidgets').check();
    await off.locator('.kbwidgets').waitFor();
    await off.locator('#sWidgets').uncheck();
    await off.waitForFunction(() => !document.querySelector('.kbwidgets'));
    assert.equal(await off.evaluate(() => localStorage.getItem('kb_widgets:acme/board:main:board/tasks.json')), '0');
    if (SHOTS) { fs.mkdirSync(SHOTS, { recursive: true }); await off.locator('#secWidgets').scrollIntoViewIfNeeded(); await off.screenshot({ path: path.join(SHOTS, 'keeptrack-board-customisations.png') }); }
    await off.evaluate(() => {
      localStorage.setItem('kb_appearance:acme/board:dev:other/tasks.json', JSON.stringify({ enabled: true, theme: 'iris', style: 'classic' }));
      document.getElementById('sBranch').value = 'dev'; document.getElementById('sPath').value = 'other/tasks.json'; document.getElementById('sSave').click();
    });
    await off.waitForFunction(() => document.documentElement.getAttribute('data-theme') === 'iris');
    await off.evaluate(() => window.kbTheme.set('forest'));
    assert.equal(await off.evaluate(() => JSON.parse(localStorage.getItem('kb_appearance:acme/board:dev:other/tasks.json')).theme), 'forest');
    assert.equal(await off.evaluate(() => JSON.parse(localStorage.getItem('kb_appearance:acme/board:main:board/tasks.json')).theme), 'custom', 'connection changes must not write to old appearance profile');
    await off.close();
    for (const viewport of [{ width: 390, height: 844 }, { width: 1280, height: 860 }]) {
      const api = new Api(), page = await open(browser, base, api, viewport);
      await page.waitForSelector('.kbwidgets'); await page.waitForSelector('.kwwweatherbody >> text=London');
      if (SHOTS) { fs.mkdirSync(SHOTS, { recursive: true }); await page.screenshot({ path: path.join(SHOTS, `widgets-${viewport.width}.png`), fullPage: true }); }
      assert.deepEqual(await page.locator('.kbwidget').evaluateAll(xs => xs.map(x => x.dataset.widget)), ['recent', 'weather', 'pulse']);
      assert.deepEqual(await page.locator('.kwwtask .kwwtitle').allTextContents(), ['Newest to-do item', 'Older backlog item']);
      const ys = await page.locator('.kwwtask').evaluateAll(xs => xs.map(x => Math.round(x.getBoundingClientRect().top))); assert.equal(new Set(ys).size, 1, 'task strip stays on one line');
      assert.match(await page.locator('.kwwweatherbody').textContent(), /14°C/); assert.match(await page.locator('.kwwweatherbody').textContent(), /35% rain/); assert.equal(api.weatherAuth, '', 'weather never receives the GitHub token');
      assert.equal(await page.evaluate(() => window.__geoRequests), 0, 'fixed-city weather never asks location on load');
      assert.deepEqual(await page.locator('.kwwmetric strong').allTextContents(), ['1', '1', '0', '0', '1']);
      await page.locator('.kwwtask').first().click(); await page.locator('#dlgCard[open]').waitFor(); assert.equal(await page.locator('#cTitle').inputValue(), 'Newest to-do item');
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1), true, 'widgets do not add page-level sideways scroll');
      assert.deepEqual(page.errors, []); assert(api.calls.includes('/contents/board/widgets.json')); await page.close();
    }

    // Browser-only widgets require an explicit choice, keep coarse coordinates local, and tolerate denial/off/switch.
    const browserWeather = { version: 1, widgets: [{ id: 'nearby', slot: 'today.after-shortcuts', type: 'weather', location: { mode: 'browser' } }] };
    const locationKey = 'kb_weather_location:acme/board:main:board/tasks.json:nearby';
    {
      const api = new Api(browserWeather), page = await open(browser, base, api, { width: 390, height: 844 });
      await page.waitForSelector('.kwwweathercontrols'); assert.equal(api.weatherRequests.length, 0); assert.equal(await page.evaluate(() => window.__geoRequests), 0);
      await page.getByRole('button', { name: 'Use approximate location', exact: true }).click();
      assert.equal(await page.evaluate(() => window.__geoRequests), 1);
      assert.equal(await page.evaluate(() => window.__geoOptions.enableHighAccuracy), false);
      await page.evaluate(() => window.__geoSuccess({ coords: { latitude: 51.567891, longitude: -0.178912 } }));
      await page.getByText('Approximate location', { exact: true }).waitFor();
      assert.deepEqual(await page.evaluate(key => JSON.parse(localStorage.getItem(key)), locationKey), { latitude: 51.6, longitude: -0.2 });
      assert.deepEqual([api.weatherRequests[0].latitude, api.weatherRequests[0].longitude], ['51.6', '-0.2']);
      assert.equal(api.weatherRequests[0].headers.authorization, undefined); assert.equal(api.weatherRequests[0].headers.cookie, undefined); assert.equal(api.weatherRequests[0].headers.referer, undefined);
      assert.equal(api.calls.every(p => !p.includes('51.567891') && !p.includes('-0.178912')), true, 'no coordinates go to GitHub');
      await page.reload(); await page.getByText('Approximate location', { exact: true }).waitFor();
      assert.equal(await page.evaluate(() => window.__geoRequests), 0, 'saved coarse location never starts tracking or requests permission again');
      await page.getByRole('button', { name: 'Forget location', exact: true }).click();
      assert.equal(await page.evaluate(key => localStorage.getItem(key), locationKey), null);
      await page.getByRole('button', { name: 'Use approximate location', exact: true }).click(); await page.evaluate(() => window.__geoError({ code: 1 }));
      await page.getByText(/Location permission was not granted/).waitFor(); assert.equal(await page.evaluate(key => localStorage.getItem(key), locationKey), null);
      await page.getByRole('button', { name: 'Use approximate location', exact: true }).click();
      await page.evaluate(() => window.kbSettings.open('prefs')); await page.locator('#sWidgets').uncheck();
      const requests = api.weatherRequests.length; await page.evaluate(() => window.__geoSuccess({ coords: { latitude: 42.123456, longitude: 10.987654 } }));
      assert.equal(api.weatherRequests.length, requests); assert.equal(await page.evaluate(key => localStorage.getItem(key), locationKey), null, 'late permission result is discarded after widgets disabled');
      assert.deepEqual(page.errors, []); await page.close();
    }
    {
      const otherWidget = JSON.parse(JSON.stringify(browserWeather)); otherWidget.widgets[0].id = 'other-weather';
      const api = new Api(otherWidget), page = await open(browser, base, api, { width: 390, height: 844 }, true, { saved: { [locationKey]: JSON.stringify({ latitude: 51.6, longitude: -0.2 }) } });
      await page.waitForSelector('.kwwweathercontrols'); assert.equal(api.weatherRequests.length, 0, 'another widget does not inherit saved coordinates');
      await page.getByRole('button', { name: 'Use approximate location', exact: true }).click(); await page.evaluate(() => window.__geoSuccess({ coords: { latitude: NaN, longitude: 1 } }));
      await page.getByText(/Browser location is unavailable/).waitFor();
      assert.equal(await page.evaluate(() => localStorage.getItem('kb_weather_location:acme/board:main:board/tasks.json:other-weather')), null, 'invalid browser coordinates are never saved');
      assert.equal(api.weatherRequests.length, 0); await page.close();
    }
    {
      const api = new Api(browserWeather), page = await open(browser, base, api, { width: 1280, height: 860 }, true, { branch: 'dev', saved: { [locationKey]: JSON.stringify({ latitude: 51.6, longitude: -0.2 }) } });
      await page.waitForSelector('.kwwweathercontrols'); assert.equal(api.weatherRequests.length, 0, 'another branch does not reuse location');
      await page.getByRole('button', { name: 'Use approximate location', exact: true }).click();
      await page.evaluate(() => window.kbSettings.open('conn'));
      await page.evaluate(() => { document.getElementById('sBranch').value = 'newbranch'; document.getElementById('sSave').click(); });
      await page.waitForFunction(() => localStorage.getItem('kb_branch') === 'newbranch');
      await page.evaluate(() => window.__geoSuccess({ coords: { latitude: 40.123456, longitude: 3.987654 } }));
      assert.equal(api.weatherRequests.length, 0); assert.equal(await page.evaluate(() => localStorage.getItem('kb_weather_location:acme/board:dev:board/tasks.json:nearby')), null, 'late location is discarded on board-context change');
      await page.close();
    }
    for (const error of [1, 2, 3]) {
      const api = new Api(), page = await open(browser, base, api, { width: 1280, height: 860 });
      await page.getByText('London', { exact: true }).waitFor(); await page.getByRole('button', { name: 'Use approximate location', exact: true }).click(); await page.evaluate(code => window.__geoError({ code }), error);
      await page.getByText(/Using London/).waitFor(); assert.equal(await page.evaluate(() => Object.keys(localStorage).some(k => k.startsWith('kb_weather_location:'))), false);
      assert.equal(await page.locator('.kwwweatherbody').getByText('London', { exact: true }).count(), 1); assert.deepEqual(page.errors, []); await page.close();
    }

    const bad = new Api({ version: 2, widgets: [] }), page = await open(browser, base, bad, { width: 390, height: 844 });
    await page.locator('.kwwproblem').waitFor(); assert.match(await page.locator('.kwwproblem').textContent(), /version 1/); assert.equal(await page.locator('.todayhead').count(), 1, 'a bad widget file does not stop Today'); await page.close();
    console.log('widgets: all checks passed');
  } finally { await browser.close(); server.close(); }
})().catch(error => { console.error(error); process.exit(1); });

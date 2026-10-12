'use strict';

const assert = require('node:assert/strict');
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const { execSync } = require('node:child_process');
const { chromium } = require('playwright');

const ROOT = path.resolve(__dirname, '../..');
const FIXTURE = path.join(ROOT, 'tests/fixtures/v4_kit17');
const mime = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json' };

function walkBoard(relDir = '') {
  const dir = path.join(FIXTURE, relDir);
  const out = {};
  for (const name of fs.readdirSync(dir)) {
    if (name === 'fixture.json') continue;
    const rel = relDir ? `${relDir}/${name}` : name;
    const full = path.join(dir, name);
    if (fs.statSync(full).isDirectory()) Object.assign(out, walkBoard(rel));
    else out[rel] = fs.readFileSync(full, 'utf8');
  }
  return out;
}

const server = http.createServer((req, res) => {
  const rel = decodeURIComponent(new URL(req.url, 'http://local').pathname).replace(/^\/+/, '') || 'board/index.html';
  const file = path.resolve(ROOT, rel);
  if (!file.startsWith(ROOT + path.sep)) { res.writeHead(403).end(); return; }
  fs.readFile(file, (err, data) => {
    if (err) res.writeHead(404).end();
    else { res.setHeader('Content-Type', mime[path.extname(file)] || 'application/octet-stream'); res.end(data); }
  });
});

class Github {
  constructor(files) {
    this.files = { ...files };
    this.head = 'head-1';
    this.n = 1;
    this.blobs = {};
    this.pending = null;
  }
  sha(p) { return require('node:crypto').createHash('sha1').update(this.files[p] || '').digest('hex'); }
  tree() { return Object.entries(this.files).map(([p, content]) => ({ path: p, type: 'blob', sha: this.sha(p), size: Buffer.byteLength(content) })); }
  async route(route) {
    const req = route.request(), u = new URL(req.url()), method = req.method(), p = u.pathname.replace('/repos/acme/board', '');
    const json = (body, status = 200) => route.fulfill({ status, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    if (p === '/user' && method === 'GET') return json({ login: 'alex' });
    if (p === '' && method === 'GET') return json({ full_name: 'acme/board', private: true, permissions: { push: true }, default_branch: 'main' });
    if (p.startsWith('/contents/board/') && method === 'GET') {
      const rel = p.slice('/contents/board/'.length);
      if (!this.files[rel]) return json({ message: 'Not Found' }, 404);
      const content = this.files[rel];
      return json({ sha: this.sha(rel), size: Buffer.byteLength(content), encoding: 'base64', content: Buffer.from(content).toString('base64') });
    }
    if (p.startsWith('/contents/board/') && method === 'PUT') {
      const rel = p.slice('/contents/board/'.length);
      const b = req.postDataJSON();
      this.files[rel] = Buffer.from(b.content, 'base64').toString();
      this.head = 'head-' + ++this.n;
      return json({ content: { sha: this.sha(rel) }, commit: { sha: this.head, tree: { sha: 'root-' + this.n } } });
    }
    if (p.startsWith('/contents/board/') && method === 'DELETE') {
      const rel = p.slice('/contents/board/'.length);
      delete this.files[rel];
      this.head = 'head-' + ++this.n;
      return json({ commit: { sha: this.head, tree: { sha: 'root-' + this.n } } });
    }
    if (p === '/git/ref/heads/main' && method === 'GET') return json({ object: { sha: this.head } });
    if (p.startsWith('/git/commits/') && method === 'GET') return json({ tree: { sha: 'root-' + this.n } });
    if (p.startsWith('/git/trees/root-') && method === 'GET') return json({ tree: [{ path: 'board', type: 'tree', sha: 'board-' + this.n }] });
    if (p.startsWith('/git/trees/board-') && method === 'GET') return json({ truncated: false, tree: this.tree() });
    if (p.startsWith('/git/blobs/') && method === 'GET') {
      const sha = p.split('/').pop();
      const rel = Object.keys(this.files).find(x => this.sha(x) === sha);
      return json({ encoding: 'base64', content: Buffer.from(this.files[rel]).toString('base64') });
    }
    if (p === '/git/blobs' && method === 'POST') { const b = req.postDataJSON(); const sha = 'blob-' + ++this.n; this.blobs[sha] = b.content; return json({ sha }); }
    if (p === '/git/trees' && method === 'POST') { this.pending = req.postDataJSON().tree; return json({ sha: 'new-tree-' + ++this.n }); }
    if (p === '/git/commits' && method === 'POST') return json({ sha: 'new-commit-' + ++this.n });
    if (p === '/git/refs/heads/main' && method === 'PATCH') {
      for (const e of this.pending || []) {
        const rel = e.path.replace(/^board\//, '');
        if (e.sha === null) delete this.files[rel];
        else this.files[rel] = this.blobs[e.sha];
      }
      this.head = req.postDataJSON().sha;
      return json({ object: { sha: this.head } });
    }
    return json({ message: 'not mocked: ' + method + ' ' + p }, 404);
  }
}

// ---- a page and assets from different deploys (browser and GitHub Pages caches) -----------------------------------
// PREV is the last release before the markup handshake (index.html kbMarkup / board.js KB_MARKUP). Each mix must either
// run the board or show the "being published" message after at most one automatic reload; never a page error or a blank page.
const PREV = 'b1ce7d2';
const prev = f => execSync(`git show ${PREV}:board/${f}`, { cwd: ROOT, encoding: 'utf8' });
const cur = f => fs.readFileSync(path.join(ROOT, 'board', f), 'utf8');
const TYPES = { html: 'text/html', js: 'text/javascript', css: 'text/css' };

async function mixPage(browser, base, files, opts = {}) {
  // These cases isolate the page's own HTTP-cache/asset handshake. A service worker would become a second cache layer
  // and bypass Playwright's per-page route fixtures, so block it in this focused test.
  const page = await browser.newPage({ viewport: { width: 1280, height: 860 }, serviceWorkers: 'block' }), errors = [], seen = {};
  let loads = 0;
  page.on('pageerror', e => errors.push(e.message));
  page.on('load', () => loads++);
  await page.addInitScript(() => { localStorage.setItem('kb_tour', 'done'); sessionStorage.setItem('kb_view', 'board'); });
  if (opts.init) await page.addInitScript(opts.init);
  await page.route(/\/board\/[\w.]+\.(html|js|css)(\?.*)?$/, route => {
    const req = route.request(), name = new URL(req.url()).pathname.split('/').pop();
    seen[name] = (seen[name] || 0) + 1;
    if (opts.fail && opts.fail(req, name, seen[name])) return route.abort();
    const body = name in files ? files[name] : cur(name);
    return route.fulfill({ status: 200, contentType: TYPES[name.split('.').pop()], body });
  });
  await page.goto(base + '/board/index.html?demo=board');
  await page.waitForFunction(() => document.getElementById('kbStale') || document.querySelector('.card'), null, { timeout: 15000 });
  await page.waitForTimeout(1500);   // let a pending reload happen
  await page.waitForFunction(() => document.getElementById('kbStale') || document.querySelector('.card'), null, { timeout: 15000 });
  const r = await page.evaluate(() => ({ stale: !!document.getElementById('kbStale'), cards: document.querySelectorAll('.card').length,
    shown: getComputedStyle(document.body).visibility !== 'hidden' }));
  return Object.assign(r, { page, errors, loads });
}
async function expectStale(browser, base, name, files, opts) {
  const r = await mixPage(browser, base, files, opts);
  assert.ok(r.stale, name + ': shows the "being published" message');
  assert.ok(r.shown, name + ': the page is visible');
  assert.equal(r.cards, 0, name + ': the board is not wired to the wrong markup');
  assert.ok(r.loads <= 2, name + ': at most one automatic reload (' + r.loads + ' loads)');
  if (!opts || !opts.allowErrors) assert.deepEqual(r.errors, [], name + ': no page errors');
  assert.match(await r.page.locator('#kbStale').innerText(), /new version of the board is being published/);
  assert.equal(await r.page.locator('#kbStale button').innerText(), 'Reload');
  await r.page.close();
}
async function expectBoard(browser, base, name, files, opts) {
  const r = await mixPage(browser, base, files, opts);
  assert.ok(!r.stale && r.cards > 0, name + ': the board runs');
  assert.deepEqual(r.errors, [], name + ': no page errors');
  return r;
}

async function mixes(browser, base) {
  // (a) a cached index.html from the previous release; its loader fetches the current board.js and board.css fresh
  await expectStale(browser, base, 'old index.html + new assets', { 'index.html': prev('index.html') });
  // (b) the current index.html, but the network fetch fails and the browser's cache still has the previous board.js/board.css:
  // the loader reads them, sees the old markup version and does not run them
  const old = { 'board.js': prev('board.js'), 'board.css': prev('board.css') };
  await expectStale(browser, base, 'new index.html + cached old board.js', old,
    { fail: (req, name, n) => /^board\.(js|css)$/.test(name) && n === 1 });
  await expectStale(browser, base, 'new index.html + old board.js from the server', old);
  // the last-resort <script src> path (no fetch at all): the old file runs and fails, then the page shows the message
  await expectStale(browser, base, 'new index.html + old board.js by script tag', old,
    { fail: req => req.resourceType() === 'fetch' && /\/board\/[\w.]+\.(js|css)$/.test(new URL(req.url()).pathname), allowErrors: true });
  // a newer board.js (higher markup version) with this index.html
  await expectStale(browser, base, 'board.js for newer markup', { 'board.js': cur('board.js').replace(/\bconst KB_MARKUP = (\d+);/, (m, n) => `const KB_MARKUP = ${+n + 1};`) });
  const lastRelease = name => execSync(`git show 47cd545:board/${name}`, { cwd: ROOT, encoding: 'utf8' });
  await expectStale(browser, base, 'previous released markup without widget controls', { 'index.html': lastRelease('index.html') });
  await expectStale(browser, base, 'new markup with previous released board script', { 'board.js': lastRelease('board.js') });
  // the same versions work, on both loader paths
  (await expectBoard(browser, base, 'current page', {})).page.close();
  (await expectBoard(browser, base, 'current page by script tag', {},
    { fail: req => req.resourceType() === 'fetch' && /\/board\/[\w.]+\.(js|css)$/.test(new URL(req.url()).pathname) })).page.close();
  // storage blocked: no automatic reload loop, just the message
  await expectStale(browser, base, 'old index.html, sessionStorage blocked', { 'index.html': prev('index.html') },
    { init: () => { Object.defineProperty(window, 'sessionStorage', { get() { throw new Error('blocked'); } }); } });

  // (c) theme.js and designmd.js load as plain tags: a cached theme.js (no paintCustom) with the current designmd.js,
  // and the other way round. A custom theme still paints and clearing it removes every colour.
  const custom = { paper: '#101820', surface: '#18222c', line: '#2a3a48', ink: '#e8eef4', hero: '#ff7a00', onHero: '#000000', mode: 'dark' };
  for (const [name, files] of [['old theme.js + new designmd.js', { 'theme.js': prev('theme.js') }], ['new theme.js + old designmd.js', { 'designmd.js': prev('designmd.js') }]]) {
    const r = await expectBoard(browser, base, name, files);
    await r.page.waitForFunction(() => window.kbDesignMd && window.kbTheme);
    const painted = await r.page.evaluate(t => { window.kbDesignMd.apply(t, false); const s = document.documentElement.style; return { hero: s.getPropertyValue('--hero'), theme: document.documentElement.dataset.theme }; }, custom);
    assert.deepEqual(painted, { hero: '#ff7a00', theme: 'custom' }, name + ': custom theme paints');
    const left = await r.page.evaluate(() => { window.kbTheme.set('light'); return document.documentElement.getAttribute('style') || ''; });
    if (name.startsWith('new theme')) assert.equal(left.trim(), '', name + ': switching back clears the custom colours');
    assert.deepEqual(r.errors, [], name + ': no page errors');
    await r.page.close();
  }
}

(async () => {
  const legacyJs = execSync('git show 400c9bc:board/board.js', { cwd: ROOT, encoding: 'utf8' });
  // An old page is the old HTML, CSS and JS together (the current HTML no longer has every element the old script looks up).
  const legacyHtml = execSync('git show 400c9bc:board/index.html', { cwd: ROOT, encoding: 'utf8' }), legacyCss = execSync('git show 400c9bc:board/board.css', { cwd: ROOT, encoding: 'utf8' });
  await new Promise(ok => server.listen(0, '127.0.0.1', ok));
  const base = `http://127.0.0.1:${server.address().port}`;
  const browser = await chromium.launch({ headless: true });
  try {
    const api = new Github(walkBoard());
    const page = await browser.newPage();
    await page.addInitScript(() => {
      localStorage.setItem('kb_repo', 'acme/board');
      localStorage.setItem('kb_branch', 'main');
      localStorage.setItem('kb_path', 'board/tasks.json');
      localStorage.setItem('kb_token', 'test');
      localStorage.setItem('kb_me', 'alex');
      localStorage.setItem('kb_api', 'https://api.test');
      localStorage.setItem('kb_view', 'board');
    });
    await page.route('https://api.test/**', r => api.route(r));
    await page.route('**/board/board.js', route => route.fulfill({ status: 200, contentType: 'text/javascript', body: legacyJs }));
    await page.route('**/board/index.html', route => route.fulfill({ status: 200, contentType: 'text/html', body: legacyHtml }));
    await page.route('**/board/board.css', route => route.fulfill({ status: 200, contentType: 'text/css', body: legacyCss }));
    await page.goto(base + '/board/index.html');
    await page.waitForSelector('.card');
    assert.ok(api.files['projects/pr_pilot01ab.json'], 'project file present before edit');
    await page.locator('.card').first().dblclick();
    await page.locator('#cTitle').fill('Call Acme (legacy page edit)');
    const saved = page.waitForResponse(r => ['PUT', 'PATCH'].includes(r.request().method()) && r.url().includes('/repos/acme/board/'));
    await page.locator('#cTitle').blur();
    await saved;
    assert.ok(api.files['projects/pr_pilot01ab.json'], 'project file must survive a v16 web save');
    const proj = JSON.parse(api.files['projects/pr_pilot01ab.json']);
    assert.equal(proj.name, 'Pilot rollout');
    const card = JSON.parse(api.files['cards/t_first.json']);
    assert.match(card.title, /legacy page edit/);
    await page.close();

    const current = await browser.newPage();
    await current.addInitScript(() => {
      localStorage.setItem('kb_repo', 'acme/board');
      localStorage.setItem('kb_branch', 'main');
      localStorage.setItem('kb_path', 'board/tasks.json');
      localStorage.setItem('kb_token', 'test');
      localStorage.setItem('kb_me', 'alex');
      localStorage.setItem('kb_api', 'https://api.test');
      sessionStorage.setItem('kb_view', 'board');   // the current page starts on Today unless this tab chose a view
    });
    await current.route('https://api.test/**', r => api.route(r));
    await current.goto(base + '/board/index.html');
    await current.waitForSelector('.card');
    assert.ok(await current.locator('.card').filter({ hasText: 'legacy page edit' }).count());
    await current.close();

    await mixes(browser, base);
    console.log('mixed-versions: ok');
  } finally {
    await browser.close();
    server.close();
  }
})().catch(e => { console.error(e); process.exit(1); });

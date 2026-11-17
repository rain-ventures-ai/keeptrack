'use strict';
// Sign in with GitHub on the web board (docs/help/github-signin.md), with a faked GitHub API, a faked authorize page and a faked
// exchange Worker. Covered:
//  1. a board with no github_app_signin (and no page default) is exactly as before: no sign-in UI, the pasted token is the bearer
//  2. a malformed github_app_signin is ignored with a visible note, and the token still works
//  3. with sign-in configured Settings offers both methods; the choice is remembered; a board may not name another GitHub App (client_id must be the page's)
//  4. the sign-in round trip: random state, authorize URL, state checked, code stripped from the address, one POST to /exchange,
//     the app token used for api calls, the pasted token untouched
//  5. a wrong or missing state never reaches the Worker; the address is cleaned
//  6. an app token near expiry is refreshed first; the refresh token goes only to the Worker
//  7. a 401 refreshes once and retries; a refused refresh clears the app tokens (not the pasted token)
//  8. Sign out clears the app tokens only
// Run: node github-signin.test.js

const assert = require('node:assert/strict');
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { chromium } = require('playwright');

const ROOT = path.resolve(__dirname, '../..');
const mime = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json', '.svg': 'image/svg+xml', '.webmanifest': 'application/manifest+json', '.png': 'image/png' };
const server = http.createServer((req, res) => {
  const rel = decodeURIComponent(new URL(req.url, 'http://local').pathname).replace(/^\/+/, '') || 'board/index.html';
  const file = path.resolve(ROOT, rel); if (!file.startsWith(ROOT + path.sep)) { res.writeHead(403).end(); return; }
  fs.readFile(file, (err, data) => { if (err) res.writeHead(404).end(); else { res.setHeader('Content-Type', mime[path.extname(file)] || 'application/octet-stream'); res.end(data); } });
});

const text = x => JSON.stringify(x, null, 2) + '\n';
const root = settings => ({ version: 4, layout: 'split', settings: { title: 'Sign-in test', ...settings }, columns: [{ id: 'todo', name: 'To do' }, { id: 'done', name: 'Done' }], people: [{ github: 'alex', name: 'Alex' }], agents: [], clients: ['Acme'], labels: [], client_info: {}, next_num: 2, archive: { files: {} } });
const card = (id, num, title) => ({ id, num, title, column: 'todo', client: '', priority: 'medium', due: '', labels: [], assignees: ['alex'], details: '', links: [], contacts: [], todos: [], comments: [], history: [], claim: null, created: '2026-10-01T08:00:00.000Z', updated: '2026-10-01T08:00:00.000Z', rank: 'a' + num });
const CORS = { 'Access-Control-Allow-Origin': '*' };

class Github {
  constructor(settings) { this.files = { 'tasks.json': text(root(settings)), 'cards/t_one.json': text(card('t_one', 1, 'First')) }; this.head = 'head-1'; this.calls = []; this.reject = null; }
  sha(p) { return crypto.createHash('sha1').update(this.files[p] || '').digest('hex'); }
  async route(route) {
    const req = route.request(), u = new URL(req.url()), method = req.method(), p = u.pathname.replace('/repos/acme/board', ''), auth = req.headers().authorization || '';
    this.calls.push({ method, path: p, auth, body: req.postData() || '' });
    const json = (body, status = 200) => route.fulfill({ status, headers: { 'Content-Type': 'application/json', ...CORS }, body: JSON.stringify(body) });
    if (this.reject && auth === 'Bearer ' + this.reject) return json({ message: 'Bad credentials' }, 401);
    if (p === '/user' && method === 'GET') return json({ login: 'alex' });
    if (p.startsWith('/user/repos')) return json([]);
    if (p === '/rate_limit') return json({ resources: { core: { remaining: 4900, limit: 5000 } } });
    if (p === '' && method === 'GET') return json({ full_name: 'acme/board', private: true, permissions: { push: true }, default_branch: 'main' });
    if (p === '/branches/main') return json({ name: 'main' });
    if (p.startsWith('/contents/board/KIT_VERSION')) return route.fulfill({ status: 200, headers: { 'Content-Type': 'text/plain', ...CORS }, body: '999' });
    if (p.startsWith('/contents/board/tasks.json') && method === 'GET') return json({ sha: this.sha('tasks.json'), size: Buffer.byteLength(this.files['tasks.json']), encoding: 'base64', content: Buffer.from(this.files['tasks.json']).toString('base64') });
    if (p === '/git/ref/heads/main' && method === 'GET') return json({ object: { sha: this.head } });
    if (p.startsWith('/git/commits/') && method === 'GET') return json({ tree: { sha: 'root-1' } });
    if (p.startsWith('/git/trees/root-') && method === 'GET') return json({ tree: [{ path: 'board', type: 'tree', sha: 'board-1' }] });
    if (p.startsWith('/git/trees/board-') && method === 'GET') return json({ truncated: false, tree: Object.entries(this.files).map(([f, c]) => ({ path: f, type: 'blob', sha: this.sha(f), size: Buffer.byteLength(c) })) });
    if (p.startsWith('/git/blobs/') && method === 'GET') { const sha = p.split('/').pop(), rel = Object.keys(this.files).find(x => this.sha(x) === sha); return json({ encoding: 'base64', content: Buffer.from(this.files[rel]).toString('base64') }); }
    return json({ message: 'not mocked: ' + method + ' ' + p }, 404);
  }
  bearers() { return this.calls.map(c => c.auth); }
}

let base;
const PAGE_DEFAULT = { client_id: 'Iv23liPAGEDEFAULT', exchange_url: 'https://signin.test' };
const BOARD_CFG = { client_id: PAGE_DEFAULT.client_id, exchange_url: 'https://signin.test' };   // a board must name the page's own app
const OTHER_APP_CFG = { client_id: 'Iv23liSOMEONEELSE', exchange_url: 'https://signin.test' };
const GOOD_TOKENS = (n, extra = {}) => ({ access_token: 'ghu_' + n, expires_in: 28800, refresh_token: 'ghr_' + n, refresh_token_expires_in: 15811200, token_type: 'bearer', ...extra });

async function open(browser, { settings = {}, meta = null, token = 'test', seed = null, method = null, query = '', authorize = 'ok', exchange = [GOOD_TOKENS(1)], refreshReply = [GOOD_TOKENS(2)], configure } = {}) {
  const api = new Github(settings), page = await browser.newPage({ viewport: { width: 1280, height: 860 }, serviceWorkers: 'block' }), errors = [];   // blocked: the app shell's service worker would serve a reload without the test's meta
  page.errors = errors; page.api = api; page.worker = []; page.authorizeCalls = [];
  page.on('pageerror', e => errors.push(e.message)); page.on('dialog', d => { errors.push('native dialog: ' + d.message()); d.dismiss(); });
  await page.addInitScript(([token, seed, method]) => {
    localStorage.setItem('kb_repo', 'acme/board'); localStorage.setItem('kb_branch', 'main'); localStorage.setItem('kb_path', 'board/tasks.json'); localStorage.setItem('kb_me', 'alex'); localStorage.setItem('kb_api', 'https://api.test');
    if (token) localStorage.setItem('kb_token', token);
    localStorage.setItem('kb_layout', 'classic'); localStorage.setItem('kb_tour_seen', '1'); sessionStorage.setItem('kb_view', 'board');
    if (!sessionStorage.getItem('seeded')) { sessionStorage.setItem('seeded', '1');
      if (seed) localStorage.setItem('kb_signin_app:acme/board', JSON.stringify(seed));
      if (method) localStorage.setItem('kb_signin_method:acme/board', method); }
  }, [token, seed, method]);
  await page.route('https://api.test/**', r => api.route(r));
  // the page owner's meta goes in front of the policy script, as docs/help/github-signin.md describes
  await page.route(/\/board\/index\.html(\?.*)?$/, async r => {
    const headers = { ...r.request().headers() }; delete headers['if-none-match']; delete headers['if-modified-since'];   // a reload must get the whole page, not a 304
    const resp = await r.fetch({ headers }); let body = await resp.text();
    if (meta) body = body.replace('<meta charset="UTF-8">', `<meta charset="UTF-8">\n<meta name="kb-github-app-signin" content='${JSON.stringify(meta)}'>`);
    await r.fulfill({ response: resp, body });
  });
  const queue = { exchange: [...exchange], refresh: [...refreshReply] };
  await page.route('https://signin.test/**', async r => {
    const req = r.request(), p = new URL(req.url()).pathname;
    if (req.method() === 'OPTIONS') return r.fulfill({ status: 204, headers: { ...CORS, 'Access-Control-Allow-Methods': 'POST', 'Access-Control-Allow-Headers': 'Content-Type' } });
    page.worker.push({ path: p, body: req.postDataJSON() });
    const next = queue[p.slice(1)].shift();
    if (next && next.http) return r.fulfill({ status: next.http, headers: { 'Content-Type': 'application/json', ...CORS }, body: '{}' });
    if (!next) return r.fulfill({ status: 400, headers: { 'Content-Type': 'application/json', ...CORS }, body: JSON.stringify({ error: 'bad_refresh_token' }) });
    return r.fulfill({ status: next.error ? 400 : 200, headers: { 'Content-Type': 'application/json', ...CORS }, body: JSON.stringify(next) });
  });
  await page.route('https://github.com/login/oauth/authorize**', r => {
    const u = new URL(r.request().url()); page.authorizeCalls.push(u);
    const back = new URL(u.searchParams.get('redirect_uri')); back.searchParams.set('code', 'CODE1');
    if (authorize !== 'nostate') back.searchParams.set('state', authorize === 'wrongstate' ? 'cd'.repeat(32) : u.searchParams.get('state'));
    // a page that sends the browser back (a 302 to the board would skip this test's route that adds the page owner's meta)
    return r.fulfill({ status: 200, contentType: 'text/html', body: `<!doctype html><title>GitHub</title><script>location.replace(${JSON.stringify(back.href)})</script>` });
  });
  if (configure) await configure(page);
  await page.goto(base + '/board/index.html' + query);
  await page.waitForTimeout(900);
  return page;
}
const stored = (page, key) => page.evaluate(k => localStorage.getItem(k), key);
const openConn = async page => { await page.evaluate(() => window.kbSettings.open('conn')); await page.waitForTimeout(150); };
const visible = (page, sel) => page.evaluate(s => { const e = document.querySelector(s); return !!e && !e.hidden && !!e.offsetParent; }, sel);
const search = page => page.evaluate(() => location.search);
const noOAuth = async page => { const q = new URLSearchParams(await search(page)); return !['code', 'state', 'error'].some(k => q.has(k)); };
const hasCard = page => page.evaluate(() => !!document.querySelector('.card'));

(async () => {
  await new Promise(ok => server.listen(0, '127.0.0.1', ok)); base = `http://127.0.0.1:${server.address().port}`;
  const browser = await chromium.launch({ headless: true });
  try {
    // 1. no configuration: as before
    { const page = await open(browser);
      assert.ok(await hasCard(page), 'the board loads with the pasted token');
      await openConn(page);
      assert.equal(await visible(page, '#sSignin'), false, 'no sign-in block without configuration');
      assert.equal(await visible(page, '#sToken'), true, 'the token box is there');
      assert.ok(page.api.bearers().every(b => b === 'Bearer test'), 'every call used the pasted token: ' + [...new Set(page.api.bearers())]);
      assert.equal(page.worker.length, 0); assert.deepEqual(page.errors, []); await page.close(); }

    // 2. malformed block: ignored, noted, token still works
    { const page = await open(browser, { settings: { github_app_signin: { client_id: 'x' } }, meta: PAGE_DEFAULT });
      assert.ok(await hasCard(page), 'the token still opens the board');
      await openConn(page);
      assert.equal(await visible(page, '#sSignin'), true);
      assert.match(await page.locator('#sSigninNote').innerText(), /github_app_signin .*ignored/);
      assert.equal(await visible(page, '#sSigninChoice'), true, 'the page default is still on offer');
      assert.equal(await visible(page, '#sToken'), true);
      assert.deepEqual(page.errors, []); await page.close(); }

    // 2b. a board naming another GitHub App is ignored with a note; the page's own app is still the one used
    { const page = await open(browser, { settings: { github_app_signin: OTHER_APP_CFG }, meta: PAGE_DEFAULT });
      await openConn(page);
      assert.match(await page.locator('#sSigninNote').innerText(), /client_id is not the GitHub App this page is set up for/);
      await page.locator('#sAuthApp').check(); await page.waitForTimeout(300);
      await page.locator('#sSigninGo').click(); await page.waitForFunction(() => localStorage.getItem('kb_signin_app:acme/board'), null, { timeout: 8000 });
      assert.equal(page.authorizeCalls.length, 1);
      assert.equal(page.authorizeCalls[0].searchParams.get('client_id'), PAGE_DEFAULT.client_id, 'never the board\'s other app');
      assert.ok(!page.authorizeCalls.some(u => u.href.includes('SOMEONEELSE')));
      await page.close(); }

    // 2c. no page meta at all: the board's block is ignored with a note and the whole pasted-token form is visible
    { const page = await open(browser, { settings: { github_app_signin: BOARD_CFG } });
      assert.ok(await hasCard(page)); await openConn(page);
      assert.equal(await visible(page, '#sSignin'), true); assert.equal(await visible(page, '#sSigninChoice'), false);
      assert.match(await page.locator('#sSigninNote').innerText(), /ignored/);
      assert.equal(await visible(page, '#sToken'), true); assert.equal(await visible(page, '#patLink'), true, 'the Make a token link is visible');
      assert.equal(await page.evaluate(() => !document.getElementById('sTokenReuse').hidden && !document.getElementById('patLink').closest('p').hidden), true);
      await page.close(); }

    // 3. both methods on offer; the board's own client_id; the choice is remembered
    { const page = await open(browser, { settings: { github_app_signin: BOARD_CFG }, meta: PAGE_DEFAULT });
      await openConn(page);
      assert.equal(await visible(page, '#sSigninChoice'), true);
      assert.equal(await page.locator('#sAuthPat').isChecked(), true, 'a browser that already has a token stays on it');
      assert.match(await page.locator('#sSigninState').innerText(), /Active: fine-grained token/);
      assert.equal(await visible(page, '#sToken'), true);
      await page.locator('#sAuthApp').check(); await page.waitForTimeout(300);
      assert.equal(await stored(page, 'kb_signin_method:acme/board'), 'app', 'remembered for this board');
      assert.match(await page.locator('#sSigninState').innerText(), /Active: sign in with GitHub/);
      assert.equal(await visible(page, '#sToken'), false, 'the token box is out of the way while sign-in is chosen');
      assert.equal(await visible(page, '#sSigninGo'), true);
      assert.equal(await stored(page, 'kb_token'), 'test', 'the pasted token is kept');
      await page.reload(); await page.waitForTimeout(600); await openConn(page);
      assert.equal(await page.locator('#sAuthApp').isChecked(), true, 'the choice survives a reload');
      await page.locator('#sAuthPat').check(); await page.waitForTimeout(400);
      assert.equal(await stored(page, 'kb_signin_method:acme/board'), 'pat');
      assert.ok(await hasCard(page), 'back on the token the board loads again');
      assert.deepEqual(page.errors, []); await page.close(); }

    // 4. the round trip
    { const page = await open(browser, { settings: { github_app_signin: BOARD_CFG }, meta: PAGE_DEFAULT, query: '?repo=acme/board&branch=main&path=board/tasks.json' });
      assert.ok(await hasCard(page), 'first the pasted token reads the board, which is where its own sign-in settings come from');
      await openConn(page); await page.locator('#sAuthApp').check(); await page.waitForTimeout(400);
      assert.equal(await hasCard(page), false, 'signed out: the pasted token is not used behind the user\'s back');
      const used = page.api.calls.length; await page.waitForTimeout(300); assert.equal(page.api.calls.length, used);
      await page.locator('#sSigninGo').click();
      await page.waitForFunction(() => localStorage.getItem('kb_signin_app:acme/board'), null, { timeout: 8000 });
      await page.waitForFunction(() => document.querySelector('.card')); await page.waitForTimeout(500);
      assert.equal(page.authorizeCalls.length, 1);
      const a = page.authorizeCalls[0];
      assert.equal(a.searchParams.get('client_id'), BOARD_CFG.client_id);
      assert.equal(a.searchParams.get('code_challenge_method'), 'S256');
      const challenge = a.searchParams.get('code_challenge'); assert.match(challenge, /^[A-Za-z0-9_-]{43}$/);
      assert.equal(a.searchParams.get('redirect_uri'), base + '/board/index.html', 'the callback has no query');
      assert.match(a.searchParams.get('state'), /^[0-9a-f]{64}$/);
      assert.equal(page.worker.length, 1);
      const sent = page.worker[0];   // PKCE: the verifier goes to the Worker, only its hash went to github.com
      assert.equal(sent.path, '/exchange'); assert.deepEqual(Object.keys(sent.body).sort(), ['code', 'code_verifier', 'redirect_uri']);
      assert.equal(sent.body.code, 'CODE1'); assert.equal(sent.body.redirect_uri, base + '/board/index.html');
      assert.equal(crypto.createHash('sha256').update(sent.body.code_verifier).digest('base64url'), challenge, 'the challenge is the S256 hash of the verifier');
      assert.ok(!a.href.includes(sent.body.code_verifier));
      const q = new URLSearchParams(await search(page));   // the page adds its own view parameters; the board's query is back and code/state are gone
      assert.deepEqual([q.get('repo'), q.get('branch'), q.get('path'), q.has('code'), q.has('state')], ['acme/board', 'main', 'board/tasks.json', false, false]);
      assert.ok(page.api.bearers().includes('Bearer ghu_1'), 'api calls carry the app token');
      const rec = JSON.parse(await stored(page, 'kb_signin_app:acme/board')); assert.equal(rec.token, 'ghu_1'); assert.equal(rec.refresh, 'ghr_1');
      assert.equal(await stored(page, 'kb_token'), 'test', 'the pasted token is untouched');
      assert.equal(await page.evaluate(() => sessionStorage.getItem('kb_oauth')), null, 'the pending state is single use');
      const sentToApi = page.api.calls.map(c => c.auth + c.body).join(' '); assert.ok(!sentToApi.includes('ghr_1') && !sentToApi.includes('CODE1'), 'neither the refresh token nor the code goes to GitHub\'s API');
      await openConn(page); assert.match(await page.locator('#sSigninState').innerText(), /signed in with GitHub/);
      assert.deepEqual(page.errors, []); await page.close(); }

    // 5. wrong or missing state never reaches the Worker
    for (const authorize of ['wrongstate', 'nostate']) {
      const page = await open(browser, { settings: { github_app_signin: BOARD_CFG }, meta: PAGE_DEFAULT, method: 'app', authorize });
      await openConn(page); await page.locator('#sSigninGo').click(); await page.waitForTimeout(1200);
      assert.equal(page.authorizeCalls.length, 1, authorize);
      assert.equal(page.worker.length, 0, authorize + ': nothing was sent to the exchange ' + JSON.stringify(page.worker) + ' ' + page.url());
      assert.equal(await noOAuth(page), true, authorize + ': the address is clean');
      assert.equal(await stored(page, 'kb_signin_app:acme/board'), null);
      await page.close();
    }
    { const page = await open(browser, { settings: { github_app_signin: BOARD_CFG }, meta: PAGE_DEFAULT, method: 'app', query: '?code=abc&state=' + 'ab'.repeat(32) });
      assert.equal(page.worker.length, 0, 'a code with no sign-in in progress is dropped');
      assert.equal(await noOAuth(page), true); assert.deepEqual(page.errors, []); await page.close(); }

    // 6. refresh before expiry
    { const seed = { token: 'ghu_old', exp: Date.now() + 2 * 60 * 1000, refresh: 'ghr_old', rexp: Date.now() + 1e10 };
      const page = await open(browser, { settings: { github_app_signin: BOARD_CFG }, meta: PAGE_DEFAULT, method: 'app', seed });
      assert.ok(await hasCard(page), 'the board loads after a refresh');
      assert.deepEqual(page.worker, [{ path: '/refresh', body: { refresh_token: 'ghr_old' } }]);
      assert.ok(!page.api.bearers().includes('Bearer ghu_old'), 'the near-expiry token was not used');
      assert.ok(page.api.bearers().includes('Bearer ghu_2'));
      const rec = JSON.parse(await stored(page, 'kb_signin_app:acme/board')); assert.equal(rec.token, 'ghu_2'); assert.equal(rec.refresh, 'ghr_2', 'the new refresh token replaces the old one');
      assert.ok(!page.api.calls.map(c => c.auth + c.body).join(' ').includes('ghr_'), 'no refresh token reached the GitHub API');
      assert.deepEqual(page.errors, []); await page.close(); }

    // 7. a 401 refreshes once and retries; a refused refresh clears the app tokens
    { const seed = { token: 'ghu_old', exp: Date.now() + 3600 * 1000, refresh: 'ghr_old', rexp: Date.now() + 1e10 };
      const page = await open(browser, { settings: { github_app_signin: BOARD_CFG }, meta: PAGE_DEFAULT, method: 'app', seed, configure: p => { p.api.reject = 'ghu_old'; } });
      assert.ok(await hasCard(page), 'the retry with the new token loaded the board');
      assert.equal(page.worker.filter(w => w.path === '/refresh').length, 1, 'refreshed once, not once per request');
      assert.ok(page.api.bearers().includes('Bearer ghu_old') && page.api.bearers().includes('Bearer ghu_2'));
      assert.deepEqual(page.errors, []); await page.close(); }
    { const seed = { token: 'ghu_old', exp: Date.now() + 3600 * 1000, refresh: 'ghr_old', rexp: Date.now() + 1e10 };
      const page = await open(browser, { settings: { github_app_signin: BOARD_CFG }, meta: PAGE_DEFAULT, method: 'app', seed, refreshReply: [{ error: 'bad_refresh_token' }], configure: p => { p.api.reject = 'ghu_old'; } });
      assert.equal(page.worker.filter(w => w.path === '/refresh').length, 1);
      assert.equal(await stored(page, 'kb_signin_app:acme/board'), null, 'a refused refresh clears the app tokens');
      assert.equal(await stored(page, 'kb_token'), 'test', 'but not the pasted token');
      assert.equal(await hasCard(page), false);
      await openConn(page); assert.equal(await visible(page, '#sSigninGo'), true, 'sign in is offered again');
      await page.close(); }

    // 8. sign out
    { const seed = { token: 'ghu_ok', exp: Date.now() + 3600 * 1000, refresh: 'ghr_ok', rexp: Date.now() + 1e10 };
      const page = await open(browser, { settings: { github_app_signin: BOARD_CFG }, meta: PAGE_DEFAULT, method: 'app', seed });
      assert.ok(await hasCard(page)); await openConn(page);
      assert.equal(await page.evaluate(() => document.getElementById('sForgetRow').hidden), true, 'app mode: Forget token is hidden, Sign out is the control');
      assert.equal(await page.evaluate(() => !document.getElementById('sTokenReuse').hidden || !document.getElementById('patLink').closest('p').hidden), false, 'the pasted-token form is out of the way');
      await page.evaluate(() => document.getElementById('sForget').click()); await page.waitForTimeout(300);   // even if it were reached
      assert.equal(await stored(page, 'kb_token'), 'test', 'Forget never deletes the pasted token in app mode');
      assert.ok(await stored(page, 'kb_signin_app:acme/board'), 'and does not sign out either');
      assert.equal(await page.evaluate(() => !!document.querySelector('dialog[open]:not(#dlgSettings)')), false, 'no Forget confirmation opened');
      await page.locator('#sSigninOut').click(); await page.waitForTimeout(400);
      assert.equal(await stored(page, 'kb_signin_app:acme/board'), null);
      assert.equal(await stored(page, 'kb_token'), 'test', 'sign out leaves a pasted token alone');
      assert.equal(page.worker.length, 0, 'signing out needs no server');
      assert.equal(await visible(page, '#sSigninGo'), true);
      assert.deepEqual(page.errors, []); await page.close(); }
    // 9. back on the token, Forget token is there again and works on the pasted token only
    { const seed = { token: 'ghu_ok', exp: Date.now() + 3600 * 1000, refresh: 'ghr_ok', rexp: Date.now() + 1e10 };
      const page = await open(browser, { settings: { github_app_signin: BOARD_CFG }, meta: PAGE_DEFAULT, method: 'pat', seed });
      await openConn(page);
      assert.equal(await page.evaluate(() => document.getElementById('sForgetRow').hidden), false, 'token mode keeps Forget token');
      assert.ok(await stored(page, 'kb_signin_app:acme/board'), 'the app sign-in is kept while the token method is chosen');
      await page.close(); }

    // 11. a failed refresh (5xx) is not retried for a minute; the still-valid token keeps working
    { const seed = { token: 'ghu_old', exp: Date.now() + 2 * 60 * 1000, refresh: 'ghr_old', rexp: Date.now() + 1e10 };
      const page = await open(browser, { settings: { github_app_signin: BOARD_CFG }, meta: PAGE_DEFAULT, method: 'app', seed, refreshReply: [{ http: 503 }, GOOD_TOKENS(2)] });
      assert.ok(await hasCard(page), 'the near-expiry token still opens the board');
      assert.ok(page.api.calls.length > 3, 'several API calls were made');
      assert.equal(page.worker.filter(w => w.path === '/refresh').length, 1, 'one attempt, then a minute of quiet, not one per request');
      assert.ok(page.api.bearers().every(b => b === 'Bearer ghu_old'), 'the current token was used throughout');
      assert.ok(await stored(page, 'kb_signin_app:acme/board'), 'a passing failure does not sign out');
      assert.deepEqual(page.errors, []); await page.close(); }
    console.log('github-signin: ok');
  } finally { await browser.close(); server.close(); }
})().catch(e => { console.error(e); process.exit(1); });

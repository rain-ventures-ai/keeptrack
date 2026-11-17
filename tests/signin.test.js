// Sign in with GitHub: the pure parts of board/board.js (settings parsing, state check, URL cleanup, token choice, refresh timing).
// Run: node --test tests/signin.test.js   (Node built-ins only; board.js exports these when loaded as a module)
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const source = fs.readFileSync(path.join(__dirname, '..', 'board', 'board.js'), 'utf8');
const k = require('../board/board.js');

const WORKER = 'https://signin.example.workers.dev';
const ALLOWED = [WORKER];
const GOOD = { client_id: 'Iv23liHHNoIZpe3JyJWH', exchange_url: WORKER };
const NOW = 1_800_000_000_000;
const STATE = 'ab'.repeat(32);
const VERIFIER = 'Vv'.repeat(22);
const pending = (over = {}) => ({ state: STATE, verifier: VERIFIER, repo: 'acme/board', search: '?repo=acme/board&path=board/tasks.json', t: NOW - 1000, ...over });

test('settings: absent is unchanged and silent', () => {
  assert.deepEqual(k.parseSigninConfig(undefined, ALLOWED, GOOD.client_id), { config: null, note: '' });
});

test('settings: a good block parses, and the exchange_url is normalised', () => {
  assert.deepEqual(k.parseSigninConfig(GOOD, ALLOWED, GOOD.client_id).config, GOOD);
  assert.equal(k.parseSigninConfig({ ...GOOD, exchange_url: WORKER + '/' }, ALLOWED, GOOD.client_id).config.exchange_url, WORKER);
  assert.equal(k.parseSigninConfig({ ...GOOD, exchange_url: WORKER + '/v1/' }, ALLOWED, GOOD.client_id).config.exchange_url, WORKER + '/v1');
});

test('settings: malformed is ignored with a visible note that keeps the token path open', () => {
  const cases = [null, 'text', 5, [], {}, { client_id: GOOD.client_id }, { exchange_url: WORKER },
    { ...GOOD, client_id: 'x' }, { ...GOOD, client_id: 7 }, { ...GOOD, exchange_url: 7 },
    { ...GOOD, exchange_url: 'not a url' }, { ...GOOD, exchange_url: 'http://signin.example.workers.dev' },
    { ...GOOD, exchange_url: 'https://user:pw@signin.example.workers.dev' }, { ...GOOD, exchange_url: WORKER + '?x=1' }, { ...GOOD, exchange_url: WORKER + '#x' },
    { ...GOOD, exchange_url: 'https://evil.example' }, { ...GOOD, exchange_url: 'javascript:alert(1)' }];
  for (const raw of cases) {
    const r = k.parseSigninConfig(raw, ALLOWED, GOOD.client_id);
    assert.equal(r.config, null, JSON.stringify(raw));
    assert.match(r.note, /github_app_signin .*ignored/, JSON.stringify(raw));
    assert.match(r.note, /token/);
  }
});

test('settings: an origin the page does not list is refused, even if well formed', () => {
  assert.equal(k.parseSigninConfig(GOOD, [], GOOD.client_id).config, null);
  assert.equal(k.parseSigninConfig({ ...GOOD, exchange_url: 'https://signin.example.workers.dev.evil.example' }, ALLOWED, GOOD.client_id).config, null);
  assert.deepEqual(k.parseSigninConfig({ ...GOOD, exchange_url: 'http://localhost:8787' }, ['http://localhost:8787'], GOOD.client_id).config?.exchange_url, 'http://localhost:8787');
});

test('page default: only listed origins count; a bad meta is no default', () => {
  const p = k.parsePageSignin(JSON.stringify({ ...GOOD, origins: ['https://other.example', 'http://insecure.example', 'https://a.example/path', 5] }));
  assert.deepEqual(p.def, GOOD);
  assert.deepEqual(p.origins.sort(), ['https://other.example', WORKER].sort());
  for (const text of [undefined, '', 'not json', '[]', 'null', '{}']) assert.deepEqual(k.parsePageSignin(text), { origins: [], def: null, clientId: '' }, String(text));
  assert.equal(k.parsePageSignin(JSON.stringify({ client_id: 'short', exchange_url: WORKER })).def, null);
});

test('exchange_url and client_id are never taken from the page address', () => {
  assert.doesNotMatch(source, /\.get\(\s*['"](exchange_url|client_id)['"]\s*\)/);
  assert.doesNotMatch(source, /searchParams\.get\(\s*['"]exchange/);
  assert.equal([...source.matchAll(/conf\.exchange_url \+ '\/(\w+)'/g)].map(m => m[1]).sort().join(), 'exchange,refresh', 'the only calls to the exchange service are /exchange and /refresh');
});

test('state: 64 hex characters from the random source, different each time', () => {
  let n = 0;
  const rnd = a => { for (let i = 0; i < a.length; i++) a[i] = (n++ * 37) % 256; return a; };
  const a = k.newOAuthState(rnd), b = k.newOAuthState(rnd);
  assert.match(a, /^[0-9a-f]{64}$/); assert.notEqual(a, b);
});

test('authorize URL and redirect URI: the callback has no query or fragment', () => {
  assert.equal(k.signinRedirectUri('https://pages.example/keeptrack/board/?repo=a/b&code=x#settings=conn'), 'https://pages.example/keeptrack/board/');
  const u = new URL(k.authorizeUrl(GOOD, 'https://pages.example/keeptrack/board/', STATE));
  assert.equal(u.origin + u.pathname, 'https://github.com/login/oauth/authorize');
  assert.equal(u.searchParams.get('client_id'), GOOD.client_id);
  assert.equal(u.searchParams.get('redirect_uri'), 'https://pages.example/keeptrack/board/');
  assert.equal(u.searchParams.get('state'), STATE);
});

test('return: no sign-in params means nothing to do', () => {
  assert.deepEqual(k.checkOAuthReturn('', pending(), NOW), { kind: 'none' });
  assert.deepEqual(k.checkOAuthReturn('?repo=a/b&path=x', null, NOW), { kind: 'none' });
});

test('return: a matching state yields the code and restores the board query', () => {
  const r = k.checkOAuthReturn(`?code=abc123&state=${STATE}`, pending(), NOW);
  assert.deepEqual(r, { kind: 'ok', code: 'abc123', verifier: VERIFIER, repo: 'acme/board', search: '?repo=acme/board&path=board/tasks.json' });
});

test('return: a mismatched, missing, short, or case-changed state never yields a code', () => {
  const bad = [`?code=abc123&state=${'cd'.repeat(32)}`, '?code=abc123', `?code=abc123&state=${STATE.toUpperCase()}`, `?code=abc123&state=${STATE}x`, '?code=abc123&state=', `?state=${STATE}`];
  for (const search of bad) {
    const r = k.checkOAuthReturn(search, pending(), NOW);
    assert.equal(r.kind, 'error', search);
    assert.equal(r.code, undefined);
    assert.doesNotMatch(r.search, /code=|state=/, 'the address is cleaned either way');
  }
});

test('return: no pending record, a stale one, or a malformed one is refused', () => {
  const q = `?code=abc123&state=${STATE}`;
  for (const p of [null, undefined, 'x', {}, { state: 'short', t: NOW }, pending({ t: NOW - 11 * 60 * 1000 }), pending({ t: NOW + 60000 }), pending({ t: 'now' })]) {
    assert.equal(k.checkOAuthReturn(q, p, NOW).kind, 'error', JSON.stringify(p));
  }
});

test('return: GitHub errors need the right state too, and a denied sign-in says so', () => {
  assert.match(k.checkOAuthReturn(`?error=access_denied&state=${STATE}`, pending(), NOW).message, /cancelled/);
  assert.match(k.checkOAuthReturn(`?error=access_denied&state=${'cd'.repeat(32)}`, pending(), NOW).message, /did not match/);
  assert.equal(k.checkOAuthReturn(`?state=${STATE}&code=`, pending(), NOW).kind, 'error');
  assert.equal(k.checkOAuthReturn(`?state=${STATE}&code=${'a'.repeat(300)}`, pending(), NOW).kind, 'error');
  assert.equal(k.checkOAuthReturn(`?state=${STATE}&code=a/b`, pending(), NOW).kind, 'error');
});

test('URL cleanup: code, state and error fields go, everything else stays in order', () => {
  assert.equal(k.stripOAuthParams('?code=1&state=2&repo=a/b&error=x&error_description=y&error_uri=z&path=p'), '?repo=a/b&path=p');
  assert.equal(k.stripOAuthParams('?%63ode=1&repo=a&sta%74e=2'), '?repo=a', 'encoded names are caught too');
  assert.equal(k.stripOAuthParams('?code=1&state=2'), '');
  assert.equal(k.stripOAuthParams(''), '');
  const evil = k.checkOAuthReturn(`?code=abc&state=${STATE}`, pending({ search: 'javascript:1' }), NOW);
  assert.equal(evil.search, '', 'a pending record cannot smuggle in anything but a query string');
});

test('method: without configuration it is always the token', () => {
  assert.equal(k.resolveAuthMethod({ configured: false, stored: 'app', hasPat: false }), 'pat');
  assert.equal(k.resolveAuthMethod({ configured: false, stored: undefined, hasPat: true }), 'pat');
});

test('method: a saved choice wins; otherwise a saved token keeps being used, and a new browser starts with sign-in', () => {
  assert.equal(k.resolveAuthMethod({ configured: true, stored: 'app', hasPat: true }), 'app');
  assert.equal(k.resolveAuthMethod({ configured: true, stored: 'pat', hasPat: false }), 'pat');
  assert.equal(k.resolveAuthMethod({ configured: true, stored: null, hasPat: true }), 'pat');
  assert.equal(k.resolveAuthMethod({ configured: true, boardConfigured: true, stored: null, hasPat: false }), 'app', 'only the boards own settings start it on sign-in');
  assert.equal(k.resolveAuthMethod({ configured: true, boardConfigured: true, stored: 'weird', hasPat: false }), 'app');
});

test('token choice: the active method decides, and the other method is never used as a fallback', () => {
  const app = { token: 'ghu_app', exp: NOW + 3600_000, refresh: 'ghr', rexp: NOW + 9e9 };
  assert.deepEqual(k.chooseToken({ method: 'pat', pat: 'github_pat_x', app, now: NOW }), { source: 'pat', token: 'github_pat_x' });
  assert.deepEqual(k.chooseToken({ method: 'pat', pat: '', app, now: NOW }), { source: 'pat', token: '' });
  assert.deepEqual(k.chooseToken({ method: 'app', pat: 'github_pat_x', app, now: NOW }), { source: 'app', token: 'ghu_app' });
  assert.deepEqual(k.chooseToken({ method: 'app', pat: 'github_pat_x', app: null, now: NOW }), { source: 'app', token: '' });
  const dead = { token: 'ghu_old', exp: NOW - 1, refresh: 'ghr', rexp: NOW - 1 };
  assert.equal(k.chooseToken({ method: 'app', pat: 'p', app: dead, now: NOW }).token, '', 'expired and not renewable: signed out');
  assert.equal(k.chooseToken({ method: 'app', pat: 'p', app: { ...dead, rexp: NOW + 1000 }, now: NOW }).token, 'ghu_old', 'expired but renewable: the request path renews it');
  assert.equal(k.chooseToken({ method: 'app', pat: '', app: { token: 't', exp: 0, refresh: '', rexp: 0 }, now: NOW }).token, 't', 'a token that never expires stays');
});

test('refresh timing: renew inside the 5 minute margin, sign in again when it cannot be renewed', () => {
  const rec = (over = {}) => ({ token: 't', exp: NOW + 3600_000, refresh: 'r', rexp: NOW + 9e9, ...over });
  assert.equal(k.refreshDecision(rec(), NOW), 'none');
  assert.equal(k.refreshDecision(rec({ exp: NOW + 5 * 60_000 + 1 }), NOW), 'none');
  assert.equal(k.refreshDecision(rec({ exp: NOW + 5 * 60_000 }), NOW), 'refresh');
  assert.equal(k.refreshDecision(rec({ exp: NOW + 1000 }), NOW), 'refresh');
  assert.equal(k.refreshDecision(rec({ exp: NOW - 1000 }), NOW), 'refresh');
  assert.equal(k.refreshDecision(rec({ exp: NOW + 1000, refresh: '' }), NOW), 'none', 'still valid, nothing to renew with');
  assert.equal(k.refreshDecision(rec({ exp: NOW - 1000, refresh: '' }), NOW), 'signin');
  assert.equal(k.refreshDecision(rec({ exp: NOW - 1000, rexp: NOW - 1 }), NOW), 'signin');
  assert.equal(k.refreshDecision(rec({ exp: 0, refresh: '' }), NOW), 'none', 'never expires');
  assert.equal(k.refreshDecision(null, NOW), 'signin');
  assert.equal(k.refreshDecision({ token: '' }, NOW), 'signin');
  assert.equal(k.refreshDecision(rec({ exp: NOW + 100_000 }), NOW, 60_000), 'none', 'the margin can be given');
});

test('exchange answer: kept as absolute times; anything without an access token is refused', () => {
  const r = k.appRecordFromExchange({ access_token: 'ghu_a', expires_in: 28800, refresh_token: 'ghr_b', refresh_token_expires_in: 15811200, token_type: 'bearer' }, NOW);
  assert.deepEqual(r, { token: 'ghu_a', exp: NOW + 28800_000, refresh: 'ghr_b', rexp: NOW + 15811200_000 });
  assert.deepEqual(k.appRecordFromExchange({ access_token: 'ghu_a' }, NOW), { token: 'ghu_a', exp: 0, refresh: '', rexp: 0 });
  for (const bad of [null, {}, { access_token: '' }, { access_token: 5 }, { access_token: 'x', token_type: 'mac' }, 'x']) assert.equal(k.appRecordFromExchange(bad, NOW), null, JSON.stringify(bad));
  assert.equal(k.appRecordFromExchange({ access_token: 'x', expires_in: -5 }, NOW).exp, 0);
});

test('invariants in the source: the refresh token only goes to exchange_url; the exchange runs only after the state check', () => {
  assert.equal([...source.matchAll(/refresh_token: rec\.refresh/g)].length, 1, 'the refresh token is read in exactly one place');
  const sendsRefresh = source.slice(source.indexOf('function refreshApp'), source.indexOf('// Every request to the GitHub API that carries an app token'));
  assert.match(sendsRefresh, /window\.fetch\(conf\.exchange_url \+ '\/refresh'/);
  const ret = source.slice(source.indexOf('if (SIGNIN_ON) (() => {'), source.indexOf('async function finishSignin'));
  assert.ok(ret.indexOf('checkOAuthReturn') < ret.indexOf('finishSignin('), 'the state check comes first');
  assert.match(ret, /r\.kind === 'error'[^\n]*return;/, 'an error never reaches finishSignin');
  assert.doesNotMatch(source, /localStorage\.setItem\([^)]*refresh/i, 'the refresh token is stored only inside the app record');
});

test('client_id: a board may only use the GitHub App the page is set up for (no consent phishing)', () => {
  const other = { ...GOOD, client_id: 'Iv23liSOMEONEELSE' };
  const r = k.parseSigninConfig(other, ALLOWED, GOOD.client_id);
  assert.equal(r.config, null);
  assert.match(r.note, /github_app_signin .*ignored.*client_id is not the GitHub App this page is set up for.*token/);
  assert.equal(k.parseSigninConfig(GOOD, ALLOWED, undefined).config, null, 'a page with no client_id accepts nothing from a board');
  assert.equal(k.parseSigninConfig(GOOD, ALLOWED, '').config, null);
  assert.deepEqual(k.parseSigninConfig(GOOD, ALLOWED, GOOD.client_id).config, GOOD);
  const page = k.parsePageSignin(JSON.stringify({ client_id: GOOD.client_id, origins: [WORKER] }));
  assert.equal(page.clientId, GOOD.client_id, 'an origins-only meta still names the app');
  assert.equal(page.def, null);
  assert.equal(k.parsePageSignin('{}').clientId, '');
});

test('PKCE: verifier is 43 URL-safe characters, the challenge is its S256 hash, and the authorize URL carries only the challenge', async () => {
  const crypto = require('node:crypto');
  const rnd = a => crypto.randomFillSync(a);
  const v = k.newCodeVerifier(rnd);
  assert.match(v, /^[A-Za-z0-9_-]{43}$/);
  assert.notEqual(v, k.newCodeVerifier(rnd));
  const c = await k.codeChallenge(v, crypto.webcrypto.subtle);
  assert.equal(c, crypto.createHash('sha256').update(v).digest('base64url'));
  assert.equal(await k.codeChallenge('dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk', crypto.webcrypto.subtle), 'E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM', 'RFC 7636 appendix B vector');
  const u = new URL(k.authorizeUrl(GOOD, 'https://pages.example/keeptrack/board/', STATE, c));
  assert.equal(u.searchParams.get('code_challenge'), c);
  assert.equal(u.searchParams.get('code_challenge_method'), 'S256');
  assert.ok(![...u.searchParams.values()].includes(v), 'the verifier never goes to github.com');
});

test('PKCE: a return without the stored verifier is refused; a good one hands it to the exchange', () => {
  const q = `?code=abc123&state=${STATE}`;
  for (const verifier of [undefined, '', 'short', 'x'.repeat(129), 'has space ' + 'v'.repeat(40), 5]) assert.equal(k.checkOAuthReturn(q, pending({ verifier }), NOW).kind, 'error', String(verifier));
  assert.equal(k.checkOAuthReturn(q, pending(), NOW).verifier, VERIFIER);
});

test('refresh hold: after a passing failure the Worker is left alone for a minute', () => {
  assert.equal(k.SIGNIN_REFRESH_HOLD_MS, 60_000);
  assert.equal(k.refreshHeld(0, NOW), false);
  assert.equal(k.refreshHeld(undefined, NOW), false);
  assert.equal(k.refreshHeld(NOW + 59_999, NOW), true);
  assert.equal(k.refreshHeld(NOW + k.SIGNIN_REFRESH_HOLD_MS, NOW + k.SIGNIN_REFRESH_HOLD_MS - 1), true);
  assert.equal(k.refreshHeld(NOW + 60_000, NOW + 60_000), false, 'it ends');
});

test('source: token is a lazy getter, PAT-only pages do no sign-in storage reads, Forget cannot delete a hidden pasted token', () => {
  assert.match(source, /get token\(\) \{ return effectiveToken\(\); \}/);
  assert.match(source, /!PAGE_SIGNIN\.origins\.length \|\| !\(PAGE_SIGNIN\.def/, 'no meta: authMethod answers before touching storage');
  const forget = source.slice(source.indexOf("$('sForget').onclick"), source.indexOf("$('sForget').onclick") + 400);
  assert.ok(forget.indexOf("authMethod(cfg().repo) === 'app'") > -1 && forget.indexOf("authMethod(cfg().repo) === 'app'") < forget.indexOf('ask('), 'the handler checks the method before it asks or deletes');
  assert.equal([...source.matchAll(/code_verifier: verifier/g)].length, 1, 'the verifier is sent in exactly one place');
  assert.match(source, /refreshHeld\(refreshHold, Date\.now\(\)\)/);
});

test('default method (owner decision): the pasted token is the default; only a board\'s own settings start on sign-in', () => {
  const r = o => k.resolveAuthMethod({ configured: true, boardConfigured: false, stored: null, hasPat: false, ...o });
  assert.equal(r({}), 'pat', 'a page meta alone makes sign-in a choice, not the default');
  assert.equal(r({ boardConfigured: true }), 'app', 'a valid github_app_signin in the board settings starts on sign-in');
  assert.equal(r({ boardConfigured: true, hasPat: true }), 'pat', 'a saved token keeps the token');
  assert.equal(r({ boardConfigured: true, hasPat: true, stored: 'app' }), 'app', 'a stored choice wins over everything');
  assert.equal(r({ stored: 'app' }), 'app');
  assert.equal(r({ boardConfigured: true, stored: 'pat' }), 'pat');
  assert.equal(r({ configured: false, boardConfigured: true, stored: 'app' }), 'pat', 'no configuration at all: always the token');
  assert.match(source, /boardConfigured: !!boardSigninConfig\(repo\)/);
});

test('callback: a page opened as .../board/index.html sends .../board/', () => {
  const want = 'https://rain-ventures-ai.github.io/keeptrack/board/';
  for (const href of [want + 'index.html', want + 'index.html?repo=a/b#x', want, want + '?code=1', 'https://rain-ventures-ai.github.io/keeptrack/board/index.html?code=x&state=y'])
    assert.equal(k.signinRedirectUri(href), want, href);
  assert.equal(k.signinRedirectUri('https://pages.example/x/myindex.html'), 'https://pages.example/x/myindex.html', 'only a real index.html is folded');
  assert.equal(k.signinRedirectUri('http://127.0.0.1:5000/board/index.html'), 'http://127.0.0.1:5000/board/');
});

test('refresh failures: only GitHub\'s real refusals end the sign-in; 5xx, 429 and the Worker\'s own errors hold', () => {
  for (const [status, data] of [[500, {}], [503, { error: 'bad_refresh_token' }], [502, { error: 'github_unreachable' }], [429, { error: 'rate_limited' }], [429, { error: 'bad_refresh_token' }],
    [500, { error: 'not_configured' }], [400, { error: 'not_configured' }], [400, { error: 'redirect_not_allowed' }], [400, { error: 'bad_request' }], [400, { error: 'github_error' }],
    [403, { error: 'origin_not_allowed' }], [415, { error: 'json_only' }], [400, null], [400, 'x'], [400, {}], [400, { error: 5 }]])
    assert.equal(k.refreshFailureKind(status, data), 'transient', status + ' ' + JSON.stringify(data));
  for (const error of ['bad_refresh_token', 'bad_verification_code', 'incorrect_client_credentials', 'redirect_uri_mismatch', 'unverified_user_email', 'access_denied', 'application_suspended'])
    assert.equal(k.refreshFailureKind(400, { error }), 'refused', error);
  // the page's list is a subset of the Worker's GitHub error list, so a Worker code can never be mistaken for a GitHub refusal
  const worker = fs.readFileSync(path.join(__dirname, '..', 'signin-worker', 'worker.js'), 'utf8');
  const listed = /new Set\(\[([^\]]*)\]\)/.exec(worker.slice(worker.indexOf('GITHUB_ERRORS')))[1].match(/'[a-z_]+'/g).map(x => x.slice(1, -1));
  for (const e of listed) assert.equal(k.refreshFailureKind(400, { error: e }), 'refused', 'Worker passes through ' + e);
  assert.match(source, /refreshFailureKind\(res\.status, data\) === 'transient'/);
});

test('origins: the default exchange origin comes first and the page and the policy cap at 8 the same way', () => {
  const many = Array.from({ length: 12 }, (_, i) => `https://w${i}.example`);
  const p = k.parsePageSignin(JSON.stringify({ ...GOOD, origins: many }));
  assert.equal(p.origins.length, k.SIGNIN_MAX_ORIGINS); assert.equal(k.SIGNIN_MAX_ORIGINS, 8);
  assert.equal(p.origins[0], WORKER, 'the exchange_url origin survives the cap');
  assert.deepEqual(p.origins.slice(1), many.slice(0, 7));
  assert.deepEqual(p.def, GOOD, 'so the default still parses');
  assert.deepEqual(k.parsePageSignin(JSON.stringify({ ...GOOD, origins: [WORKER, WORKER] })).origins, [WORKER], 'no duplicates');
  // index.html's bootstrap (which builds the policy) applies the same order and cap
  const html = fs.readFileSync(path.join(__dirname, '..', 'board', 'index.html'), 'utf8');
  const m = /kb-github-app-signin"\]'\), sign = [\s\S]*?\n  \} catch \(_\) \{\}/.exec(html);
  assert.ok(m, 'bootstrap block found');
  const run = (meta) => { let content = "connect-src 'self'"; const policy = { get content() { return content; }, set content(v) { content = v; } };
    const document = { querySelector: () => ({ getAttribute: () => JSON.stringify(meta) }) };
    new Function('document', 'policy', 'URL', 'try {\n var meta = document.querySelector(\'meta[name="kb-github-app-signin"]\'), sign = meta ? JSON.parse(meta.getAttribute(\'content\')) : null, extra = [], list = [];' + m[0].split('list = [];')[1])(document, policy, URL);
    return content.replace("connect-src 'self'", '').trim().split(/\s+/).filter(Boolean); };
  const fromPolicy = run({ ...GOOD, origins: many });
  assert.deepEqual(fromPolicy, p.origins, 'the policy allows exactly the origins the page does');
  assert.deepEqual(run({ ...GOOD }), [WORKER]);
});

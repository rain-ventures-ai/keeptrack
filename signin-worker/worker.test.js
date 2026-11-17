// Run: node --test signin-worker/   (Node built-ins only; GitHub is a mock fetch)
import { test } from 'node:test';
import assert from 'node:assert/strict';
import worker, { handle } from './worker.js';

const ORIGIN = 'https://pages.example';
const REDIRECT = 'https://pages.example/keeptrack/board/';
const VERIFIER = 'v'.repeat(43);
const SECRET = 'client-secret-value-1234';
const ENV = { GITHUB_CLIENT_ID: 'Iv1.test', GITHUB_CLIENT_SECRET: SECRET, ALLOWED_ORIGINS: `${ORIGIN}, https://other.example`, ALLOWED_REDIRECTS: REDIRECT };

function mockGithub(payload, { status = 200, throws = false } = {}) {
  const calls = [];
  const fn = async (url, init) => {
    calls.push({ url, init, body: JSON.parse(init.body) });
    if (throws) throw new Error('network down');
    return new Response(JSON.stringify(payload), { status, headers: { 'Content-Type': 'application/json' } });
  };
  fn.calls = calls;
  return fn;
}
const GOOD = { access_token: 'ghu_abc', expires_in: 28800, refresh_token: 'ghr_def', refresh_token_expires_in: 15811200, token_type: 'bearer', scope: '', client_secret: 'leak', extra: 1 };

const post = (path, body, { origin = ORIGIN, headers = {}, raw } = {}) => new Request('https://worker.example' + path, {
  method: 'POST', body: raw !== undefined ? raw : JSON.stringify(body),
  headers: { ...(origin ? { Origin: origin } : {}), 'Content-Type': 'application/json', ...headers } });

test('an allowed origin gets its own origin back as CORS, and no caching', async () => {
  const res = await handle(post('/exchange', { code: 'abc123', redirect_uri: REDIRECT, code_verifier: VERIFIER }), ENV, mockGithub(GOOD));
  assert.equal(res.status, 200);
  assert.equal(res.headers.get('Access-Control-Allow-Origin'), ORIGIN);
  assert.equal(res.headers.get('Vary'), 'Origin');
  assert.equal(res.headers.get('Cache-Control'), 'no-store');
  const second = await handle(post('/exchange', { code: 'abc123', redirect_uri: REDIRECT, code_verifier: VERIFIER }, { origin: 'https://other.example' }), ENV, mockGithub(GOOD));
  assert.equal(second.headers.get('Access-Control-Allow-Origin'), 'https://other.example');
});

test('other origins, a missing origin and near-misses get 403 with no CORS headers and never reach GitHub', async () => {
  for (const origin of ['https://evil.example', 'https://pages.example/', 'http://pages.example', 'https://pages.example.evil.example', 'null', null]) {
    const gh = mockGithub(GOOD);
    const res = await handle(post('/exchange', { code: 'abc123', redirect_uri: REDIRECT, code_verifier: VERIFIER }, { origin }), ENV, gh);
    assert.equal(res.status, 403, String(origin));
    assert.equal(res.headers.get('Access-Control-Allow-Origin'), null);
    assert.equal(res.headers.get('Cache-Control'), 'no-store');
    assert.equal(gh.calls.length, 0);
  }
  const none = await handle(post('/exchange', {}, { origin: ORIGIN }), { ...ENV, ALLOWED_ORIGINS: '' }, mockGithub(GOOD));
  assert.equal(none.status, 403, 'an empty allow-list allows nobody');
});

test('preflight: allowed origin gets 204 with the allowed method and header; a disallowed one gets 403', async () => {
  const ok = await handle(new Request('https://worker.example/exchange', { method: 'OPTIONS', headers: { Origin: ORIGIN, 'Access-Control-Request-Method': 'POST' } }), ENV, mockGithub(GOOD));
  assert.equal(ok.status, 204);
  assert.equal(ok.headers.get('Access-Control-Allow-Origin'), ORIGIN);
  assert.equal(ok.headers.get('Access-Control-Allow-Methods'), 'POST');
  assert.equal(ok.headers.get('Access-Control-Allow-Headers'), 'Content-Type');
  const bad = await handle(new Request('https://worker.example/exchange', { method: 'OPTIONS', headers: { Origin: 'https://evil.example' } }), ENV, mockGithub(GOOD));
  assert.equal(bad.status, 403);
  assert.equal(bad.headers.get('Access-Control-Allow-Origin'), null);
});

test('only POST (and OPTIONS) on /exchange and /refresh', async () => {
  for (const method of ['GET', 'PUT', 'DELETE', 'PATCH']) {
    const res = await handle(new Request('https://worker.example/exchange', { method, headers: { Origin: ORIGIN } }), ENV, mockGithub(GOOD));
    assert.equal(res.status, 405, method);
    assert.equal(res.headers.get('Allow'), 'POST, OPTIONS');
  }
  const res = await handle(post('/elsewhere', {}), ENV, mockGithub(GOOD));
  assert.equal(res.status, 404);
});

test('redirect_uri must be an exact match from ALLOWED_REDIRECTS', async () => {
  for (const redirect_uri of ['https://pages.example/keeptrack/board', 'https://pages.example/keeptrack/board/?repo=a/b', 'https://evil.example/keeptrack/board/', 'https://pages.example/keeptrack/board/#x', '']) {
    const gh = mockGithub(GOOD);
    const res = await handle(post('/exchange', { code: 'abc123', redirect_uri }), ENV, gh);
    assert.equal(res.status, 400, redirect_uri);
    assert.deepEqual(await res.json(), { error: 'redirect_not_allowed' });
    assert.equal(gh.calls.length, 0);
  }
  const missing = await handle(post('/exchange', { code: 'abc123' }), ENV, mockGithub(GOOD));
  assert.equal(missing.status, 400);
});

test('exchange: calls GitHub with the secret and returns only the five token fields', async () => {
  const gh = mockGithub(GOOD);
  const res = await handle(post('/exchange', { code: 'abc123', redirect_uri: REDIRECT, code_verifier: VERIFIER, client_id: 'attacker', client_secret: 'x', grant_type: 'other' }), ENV, gh);
  assert.equal(res.status, 200);
  assert.deepEqual(await res.json(), { access_token: 'ghu_abc', expires_in: 28800, refresh_token: 'ghr_def', refresh_token_expires_in: 15811200, token_type: 'bearer' });
  assert.equal(gh.calls.length, 1);
  assert.equal(gh.calls[0].url, 'https://github.com/login/oauth/access_token');
  assert.deepEqual(gh.calls[0].body, { client_id: 'Iv1.test', client_secret: SECRET, code: 'abc123', redirect_uri: REDIRECT, code_verifier: VERIFIER }, 'the caller cannot choose the client id, secret or grant type');
});

test('GitHub errors become a fixed safe code, never GitHub text or the secret', async () => {
  const known = await handle(post('/exchange', { code: 'abc123', redirect_uri: REDIRECT, code_verifier: VERIFIER }), ENV,
    mockGithub({ error: 'bad_verification_code', error_description: `The code passed is incorrect or expired. ${SECRET}`, error_uri: 'https://x' }));
  assert.equal(known.status, 400);
  assert.deepEqual(await known.json(), { error: 'bad_verification_code' });
  const unknown = await handle(post('/exchange', { code: 'abc123', redirect_uri: REDIRECT, code_verifier: VERIFIER }), ENV, mockGithub({ error: `weird ${SECRET}`, error_description: SECRET }));
  const text = JSON.stringify(await unknown.json());
  assert.equal(text, '{"error":"github_error"}');
  assert.ok(!text.includes(SECRET));
  const down = await handle(post('/exchange', { code: 'abc123', redirect_uri: REDIRECT, code_verifier: VERIFIER }), ENV, mockGithub({}, { throws: true }));
  assert.equal(down.status, 502);
  assert.deepEqual(await down.json(), { error: 'github_unreachable' });
  const noToken = await handle(post('/exchange', { code: 'abc123', redirect_uri: REDIRECT, code_verifier: VERIFIER }), ENV, mockGithub({ token_type: 'bearer' }));
  assert.equal(noToken.status, 502);
  const html = await handle(post('/exchange', { code: 'abc123', redirect_uri: REDIRECT, code_verifier: VERIFIER }), ENV, async () => new Response('<html>' + SECRET, { status: 200 }));
  assert.equal(html.status, 502);
  assert.ok(!(await html.text()).includes(SECRET));
});

test('refresh: grant_type refresh_token, same output fields, no redirect_uri needed', async () => {
  const gh = mockGithub(GOOD);
  const res = await handle(post('/refresh', { refresh_token: 'ghr_old', redirect_uri: 'ignored' }), ENV, gh);
  assert.equal(res.status, 200);
  assert.deepEqual(Object.keys(await res.json()).sort(), ['access_token', 'expires_in', 'refresh_token', 'refresh_token_expires_in', 'token_type']);
  assert.deepEqual(gh.calls[0].body, { client_id: 'Iv1.test', client_secret: SECRET, grant_type: 'refresh_token', refresh_token: 'ghr_old' });
  const bad = await handle(post('/refresh', { refresh_token: 'ghr_old' }), ENV, mockGithub({ error: 'bad_refresh_token' }));
  assert.equal(bad.status, 400);
  assert.deepEqual(await bad.json(), { error: 'bad_refresh_token' });
  for (const body of [{}, { refresh_token: 5 }, { refresh_token: 'has space' }, { refresh_token: 'x'.repeat(513) }]) {
    assert.equal((await handle(post('/refresh', body), ENV, mockGithub(GOOD))).status, 400);
  }
});

test('JSON only, small bodies only', async () => {
  const gh = mockGithub(GOOD);
  const form = await handle(post('/exchange', null, { raw: 'code=abc&redirect_uri=x', headers: { 'Content-Type': 'application/x-www-form-urlencoded' } }), ENV, gh);
  assert.equal(form.status, 415);
  const text = await handle(post('/exchange', null, { raw: '{}', headers: { 'Content-Type': 'text/plain' } }), ENV, gh);
  assert.equal(text.status, 415);
  const big = await handle(post('/exchange', { code: 'a', redirect_uri: REDIRECT, pad: 'x'.repeat(5000) }), ENV, gh);
  assert.equal(big.status, 413);
  const lying = await handle(post('/exchange', null, { raw: JSON.stringify({ pad: 'x'.repeat(5000) }), headers: { 'Content-Length': '10' } }), ENV, gh);
  assert.ok([400, 413].includes(lying.status));
  for (const raw of ['not json', '[]', 'null', '"s"']) assert.equal((await handle(post('/exchange', null, { raw }), ENV, gh)).status, 400, raw);
  assert.equal(gh.calls.length, 0);
});

test('an unconfigured Worker refuses with a bare error', async () => {
  const res = await handle(post('/exchange', { code: 'abc123', redirect_uri: REDIRECT, code_verifier: VERIFIER }), { ...ENV, GITHUB_CLIENT_SECRET: '' }, mockGithub(GOOD));
  assert.equal(res.status, 500);
  assert.deepEqual(await res.json(), { error: 'not_configured' });
});

test('nothing is logged, whatever happens', async () => {
  const seen = [];
  const spies = ['log', 'info', 'warn', 'error', 'debug'].map(k => { const o = console[k]; console[k] = (...a) => seen.push(a); return () => { console[k] = o; }; });
  try {
    await handle(post('/exchange', { code: 'abc123', redirect_uri: REDIRECT, code_verifier: VERIFIER }), ENV, mockGithub(GOOD));
    await handle(post('/exchange', { code: 'abc123', redirect_uri: REDIRECT, code_verifier: VERIFIER }), ENV, mockGithub({}, { throws: true }));
    await handle(post('/refresh', { refresh_token: 'ghr_old' }), ENV, mockGithub({ error: 'bad_refresh_token' }));
  } finally { spies.forEach(undo => undo()); }
  assert.deepEqual(seen, []);
});

test('the default export turns a crash into a bare 500', async () => {
  const res = await worker.fetch(new Request('https://worker.example/exchange', { method: 'POST', headers: { Origin: ORIGIN, 'Content-Type': 'application/json' }, body: '{}' }), null);
  assert.equal(res.status, 500);
  assert.equal(res.headers.get('Access-Control-Allow-Origin'), null);
});

test('PKCE: /exchange refuses a missing or malformed code_verifier and never calls GitHub', async () => {
  for (const code_verifier of [undefined, '', 'short', 'v'.repeat(42), 'v'.repeat(129), 'has space ' + 'v'.repeat(40), 5, null]) {
    const gh = mockGithub(GOOD);
    const res = await handle(post('/exchange', { code: 'abc123', redirect_uri: REDIRECT, code_verifier }), ENV, gh);
    assert.equal(res.status, 400, String(code_verifier));
    assert.deepEqual(await res.json(), { error: 'code_verifier_required' });
    assert.equal(gh.calls.length, 0);
  }
  const gh = mockGithub(GOOD);
  const ok = await handle(post('/exchange', { code: 'abc123', redirect_uri: REDIRECT, code_verifier: 'A-._~' + 'z'.repeat(60) }), ENV, gh);
  assert.equal(ok.status, 200);
  assert.equal(gh.calls[0].body.code_verifier, 'A-._~' + 'z'.repeat(60), 'passed to GitHub unchanged');
  const refresh = await handle(post('/refresh', { refresh_token: 'ghr_old' }), ENV, mockGithub(GOOD));
  assert.equal(refresh.status, 200, 'refresh needs no verifier');
});

test('rate limit: used when the binding is present (keyed by IP), 429 over the limit, ignored when absent', async () => {
  const keys = [];
  const limiter = n => ({ limit: async ({ key }) => { keys.push(key); return { success: keys.length <= n }; } });
  const req = () => post('/exchange', { code: 'abc123', redirect_uri: REDIRECT, code_verifier: VERIFIER }, { headers: { 'CF-Connecting-IP': '203.0.113.9' } });
  const env = { ...ENV, SIGNIN_LIMIT: limiter(1) };
  assert.equal((await handle(req(), env, mockGithub(GOOD))).status, 200);
  const gh = mockGithub(GOOD);
  const over = await handle(req(), env, gh);
  assert.equal(over.status, 429);
  assert.equal(over.headers.get('Retry-After'), '60');
  assert.equal(over.headers.get('Access-Control-Allow-Origin'), ORIGIN, 'the page can read the 429');
  assert.deepEqual(await over.json(), { error: 'rate_limited' });
  assert.equal(gh.calls.length, 0);
  assert.deepEqual(keys, ['203.0.113.9', '203.0.113.9']);
  // not limited without the binding, and a failing limiter does not block sign-in
  for (let i = 0; i < 5; i++) assert.equal((await handle(req(), ENV, mockGithub(GOOD))).status, 200);
  const broken = { ...ENV, SIGNIN_LIMIT: { limit: async () => { throw new Error('down'); } } };
  assert.equal((await handle(req(), broken, mockGithub(GOOD))).status, 200);
  // a disallowed origin is refused before the limiter is touched
  const before = keys.length;
  await handle(post('/exchange', {}, { origin: 'https://evil.example' }), env, mockGithub(GOOD));
  assert.equal(keys.length, before);
});

test('the GitHub call uses a redirect mode Workers support, and a redirect is never followed', async () => {
  // Workers throw on redirect: 'error' (found live, 17 Nov), so every sign-in failed as github_unreachable.
  const gh = mockGithub(GOOD);
  await handle(post('/exchange', { code: 'abc123', redirect_uri: REDIRECT, code_verifier: VERIFIER }), ENV, gh);
  assert.ok(['follow', 'manual'].includes(gh.calls[0].init.redirect), 'Workers accept only follow or manual');
  assert.equal(gh.calls[0].init.redirect, 'manual');
  const moved = async () => new Response(JSON.stringify(GOOD), { status: 302, headers: { Location: 'https://evil.example/', 'Content-Type': 'application/json' } });
  const res = await handle(post('/exchange', { code: 'abc123', redirect_uri: REDIRECT, code_verifier: VERIFIER }), ENV, moved);
  assert.equal(res.status, 502);
  assert.deepEqual(await res.json(), { error: 'github_error' });
});

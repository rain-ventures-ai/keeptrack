// Keeptrack sign-in Worker: the one server-side step of "Sign in with GitHub" for the static board page.
//
// github.com/login/oauth/access_token sends no CORS headers and needs the GitHub App's client secret, so a browser
// cannot trade the OAuth code for a token by itself. This Worker does exactly that trade and nothing else:
//
//   POST /exchange  {code, redirect_uri}   -> {access_token, expires_in, refresh_token, refresh_token_expires_in, token_type}
//   POST /refresh   {refresh_token}        -> the same fields
//
// Invariants (tests: worker.test.js):
//   - The client secret exists only as the Worker secret GITHUB_CLIENT_SECRET. It is never returned or logged.
//   - Only origins in ALLOWED_ORIGINS (exact match) get an answer; any other origin, or none, gets 403 with no CORS headers.
//   - Only redirect URIs in ALLOWED_REDIRECTS (exact match) are passed to GitHub.
//   - Codes and tokens are never logged (this file has no logging at all) and no response is cacheable.
//   - Only the five token fields are returned. GitHub's error text is never echoed, only a fixed code from a short list.

const MAX_BODY_BYTES = 2048;
const TOKEN_URL = 'https://github.com/login/oauth/access_token';
const TOKEN_FIELDS = ['access_token', 'expires_in', 'refresh_token', 'refresh_token_expires_in', 'token_type'];
// Error codes GitHub documents for these two calls. Anything else is reported as 'github_error'.
const GITHUB_ERRORS = new Set(['bad_verification_code', 'bad_refresh_token', 'incorrect_client_credentials', 'redirect_uri_mismatch',
  'unverified_user_email', 'access_denied', 'application_suspended']);
const CODE_RE = /^[A-Za-z0-9_-]{1,256}$/;
const REFRESH_RE = /^[A-Za-z0-9_-]{1,512}$/;

const list = v => String(v || '').split(',').map(s => s.trim()).filter(Boolean);

function reply(status, body, origin, extra = {}) {
  const headers = { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff', ...extra };
  if (origin) { headers['Access-Control-Allow-Origin'] = origin; headers.Vary = 'Origin'; }   // only ever an allowed origin
  return new Response(body === null ? null : JSON.stringify(body), { status, headers });
}

// Reads at most `max` bytes of the body; null when it is longer (the rest is never read).
async function readLimited(request, max) {
  const declared = request.headers.get('Content-Length');
  if (declared !== null && (!/^\d+$/.test(declared) || +declared > max)) return null;
  if (!request.body) return '';
  const reader = request.body.getReader(), chunks = [];
  let size = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    size += value.byteLength;
    if (size > max) { try { await reader.cancel(); } catch { /* the body is being refused anyway */ } return null; }
    chunks.push(value);
  }
  const all = new Uint8Array(size); let at = 0;
  chunks.forEach(c => { all.set(c, at); at += c.byteLength; });
  return new TextDecoder().decode(all);
}

async function callGithub(fields, env, fetchImpl) {
  let res, data;
  try {
    res = await fetchImpl(TOKEN_URL, { method: 'POST', redirect: 'error',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json', 'User-Agent': 'keeptrack-signin-worker' },
      body: JSON.stringify({ client_id: env.GITHUB_CLIENT_ID, client_secret: env.GITHUB_CLIENT_SECRET, ...fields }) });
    data = await res.json();
  } catch { return { status: 502, body: { error: 'github_unreachable' } }; }
  if (!data || typeof data !== 'object') return { status: 502, body: { error: 'github_error' } };
  if (data.error) return { status: 400, body: { error: GITHUB_ERRORS.has(data.error) ? data.error : 'github_error' } };
  if (!res.ok || typeof data.access_token !== 'string' || !data.access_token) return { status: 502, body: { error: 'github_error' } };
  const out = {};
  TOKEN_FIELDS.forEach(k => { if (data[k] !== undefined && data[k] !== null) out[k] = data[k]; });
  return { status: 200, body: out };
}

export async function handle(request, env, fetchImpl = fetch) {
  const origin = request.headers.get('Origin');
  if (origin === null || !list(env.ALLOWED_ORIGINS).includes(origin)) return reply(403, { error: 'origin_not_allowed' }, null);
  const path = new URL(request.url).pathname;
  if (path !== '/exchange' && path !== '/refresh') return reply(404, { error: 'not_found' }, origin);
  if (request.method === 'OPTIONS') {
    return reply(204, null, origin, { 'Access-Control-Allow-Methods': 'POST', 'Access-Control-Allow-Headers': 'Content-Type', 'Access-Control-Max-Age': '600' });
  }
  if (request.method !== 'POST') return reply(405, { error: 'method_not_allowed' }, origin, { Allow: 'POST, OPTIONS' });
  if (!env.GITHUB_CLIENT_ID || !env.GITHUB_CLIENT_SECRET) return reply(500, { error: 'not_configured' }, origin);
  if (!/^application\/json\s*(;|$)/i.test(request.headers.get('Content-Type') || '')) return reply(415, { error: 'json_only' }, origin);
  const text = await readLimited(request, MAX_BODY_BYTES);
  if (text === null) return reply(413, { error: 'too_large' }, origin);
  let body; try { body = JSON.parse(text); } catch { body = null; }
  if (!body || typeof body !== 'object' || Array.isArray(body)) return reply(400, { error: 'bad_request' }, origin);

  let fields;
  if (path === '/exchange') {
    if (typeof body.code !== 'string' || !CODE_RE.test(body.code) || typeof body.redirect_uri !== 'string') return reply(400, { error: 'bad_request' }, origin);
    if (!list(env.ALLOWED_REDIRECTS).includes(body.redirect_uri)) return reply(400, { error: 'redirect_not_allowed' }, origin);
    fields = { code: body.code, redirect_uri: body.redirect_uri };
  } else {
    if (typeof body.refresh_token !== 'string' || !REFRESH_RE.test(body.refresh_token)) return reply(400, { error: 'bad_request' }, origin);
    fields = { grant_type: 'refresh_token', refresh_token: body.refresh_token };
  }
  const out = await callGithub(fields, env, fetchImpl);
  return reply(out.status, out.body, origin);
}

export default {
  async fetch(request, env) {
    try { return await handle(request, env); } catch { return reply(500, { error: 'server_error' }, null); }
  },
};

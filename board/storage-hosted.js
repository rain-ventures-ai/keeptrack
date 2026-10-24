/* Frozen keeptrack-cloud 8128b59 phase-0 storage; no credential or board persistence. */
(function (root) {
  'use strict';
  const copy = x => JSON.parse(JSON.stringify(x));
  const prefixes = { card: 'cards', person: 'people', project: 'projects', proposal: 'proposals' };
  const collections = { cards: 'tasks', people: 'contacts', projects: 'projects', proposals: 'proposals' };
  class HostedError extends Error {
    constructor(status, error) { super(`${error.code || 'http_error'}: ${error.message || 'Hosted request failed'}`); this.status = status; this.code = error.code; this.retryable = !!error.retryable; }
  }
  function localURL(value) {
    const u = new URL(value);
    if (u.username || u.password || u.search || u.hash || !['http:', 'https:'].includes(u.protocol) ||
        !['localhost', '127.0.0.1', '[::1]'].includes(u.hostname)) throw new Error('Phase 0 requires a loopback API/Auth URL');
    return u.href.replace(/\/$/, '');
  }
  // The hosted entry has no inline selector/bootstrap. This parser-blocking, same-origin script
  // installs its sole policy before any other asset or application script can run.
  const hostedPage = typeof document !== 'undefined' && document.documentElement.dataset.hosted === 'true';
  let pageAPI, connectionOrigins;
  if (hostedPage) {
    const query = new URLSearchParams(location.search);
    try { pageAPI = localURL(query.get('api') || 'http://localhost:3000'); } catch { pageAPI = location.origin; }
    connectionOrigins = new Set([location.origin, new URL(pageAPI).origin]);
    const policy = document.getElementById('hostedPolicy').content.querySelector('meta').cloneNode(true);
    policy.content = policy.content.replace("connect-src 'self'", "connect-src 'self'" +
      (new URL(pageAPI).origin === location.origin ? '' : ' ' + new URL(pageAPI).origin));
    document.head.append(policy);
    window.kbMarkup = Number(document.documentElement.dataset.kbMarkup);
    // board.js refuses mismatched markup before doing any work. Also catch a missing/older script.
    document.addEventListener('DOMContentLoaded', () => {
      if (window.kbBoardMarkup !== window.kbMarkup) {
        if (typeof window.kbStalePage === 'function') window.kbStalePage();
        else { document.getElementById('board').textContent = 'A new version of the board is being published. Reload in a minute.'; }
      }
      document.documentElement.classList.add('ready');
    });
  }
  function connectionURL(value) {
    const url = localURL(value);
    if (connectionOrigins && !connectionOrigins.has(new URL(url).origin)) {
      throw new Error('Hosted connections require the page or configured API origin. Use an auth proxy there, or reload with the new ?api= URL.');
    }
    return url;
  }
  class HostedAdapter {
    kind = 'hosted';
    capabilities = { casWrites: true, atomicMultiFile: true, changeFeed: true };
    #token = '';
    #hydrating = new WeakMap();
    constructor({ api, board, fetch: transport = globalThis.fetch.bind(globalThis) }) {
      this.apiURL = connectionURL(api);
      if (!/^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/.test(board)) throw new Error('A board UUID is required');
      this.board = board; this.transport = transport; this.files = new Map(); this.identity = null; this.cursor = null; this.claims = []; this.generation = 0;
    }
    async signIn({ auth, key, email, password }) {
      this.logout();
      const generation = this.generation;
      const endpoint = connectionURL(auth);
      const r = await this.transport(endpoint + '/auth/v1/token?grant_type=password', {
        method: 'POST', redirect: 'error', credentials: 'omit', referrerPolicy: 'no-referrer', cache: 'no-store',
        headers: { apikey: key, 'Content-Type': 'application/json' }, body: JSON.stringify({ email, password })
      });
      if (!r.ok) throw new HostedError(r.status, { code: 'invalid_credential', message: 'Sign-in failed' });
      const session = await r.json();
      if (typeof session.access_token !== 'string' || !session.access_token) throw new Error('Auth did not return an access token');
      if (generation !== this.generation) throw new Error('Session changed during sign-in');
      this.#token = session.access_token; // deliberately ignore refresh_token; reload requires another sign-in
      try { return await this.whoami(); } catch (e) { this.logout(); throw e; }
    }
    logout() { this.generation++; this.#token = ''; this.files.clear(); this.identity = null; this.cursor = null; this.claims = []; }
    get signedIn() { return !!this.#token; }
    route(suffix) { return '/v1/boards/' + this.board + suffix; }
    async request(method, route, body, key, etag) {
      if (!this.#token) throw new HostedError(401, { code: 'invalid_credential', message: 'Sign in again' });
      const generation = this.generation;
      const headers = { Authorization: 'Bearer ' + this.#token, Accept: 'application/json' };
      if (body !== undefined) headers['Content-Type'] = 'application/json';
      if (method !== 'GET') headers['Idempotency-Key'] = key || crypto.randomUUID();
      if (etag) headers['If-None-Match'] = etag;
      // Reuse the same request/key after uncertain delivery or retryable lock errors.
      const options = { method, headers, body: body === undefined ? undefined : JSON.stringify(body), redirect: 'error',
        cache: 'no-store', credentials: 'omit', referrerPolicy: 'no-referrer' };
      for (let attempt = 0; attempt < 3; attempt++) {
        let r;
        try { r = await this.transport(this.apiURL + route, { ...options, signal: AbortSignal.timeout(30000) }); }
        catch (e) { if (attempt < 2) continue; throw e; }
        if (generation !== this.generation) throw new Error('Session changed during request');
        if (r.status === 304) return { unchanged: true };
        const result = await r.json();
        if (!r.ok) {
          const error = new HostedError(r.status, result.error || {});
          if (r.status === 503 && error.retryable && attempt < 2) continue;
          throw error;
        }
        return result;
      }
    }
    async whoami() {
      const identity = await this.request('GET', '/v1/me');
      if (!identity.boards.some(b => b.id === this.board)) throw new HostedError(404, { code: 'not_found', message: 'Board is not accessible' });
      this.identity = identity; return identity;
    }
    async snapshot(etag) {
      const snap = await this.request('GET', this.route('/snapshot'), undefined, undefined, etag);
      if (snap.unchanged) return snap;
      if (snap.board_id !== this.board) throw new Error('Snapshot board mismatch');
      const files = new Map([['tasks.json', copy(snap.root)]]);
      for (const entity of snap.entities) {
        const path = `${prefixes[entity.kind]}/${entity.body.id}.json`, cached = this.files.get(path);
        files.set(path, cached?.rev === entity.rev && !cached.omitted?.length ? cached : copy(entity));
      }
      this.files = files; this.cursor = snap.cursor; this.claims = copy(snap.claims); this.serverCapabilities = snap.capabilities;
      return snap;
    }
    async read(path, rev) {
      const full = await this.request('GET', this.route('/files/' + encodeURIComponent(path)));
      if (rev !== undefined && full.rev !== rev) throw new HostedError(412, { code: 'revision_conflict', message: 'File changed during hydration; reload' });
      return full;
    }
    async revision(path, rev) {
      try {
        const meta = await this.request('GET', this.route('/file-revisions/' + encodeURIComponent(path)), undefined, undefined, rev ? '"' + rev + '"' : undefined);
        if (!meta.unchanged && (meta.path !== path || typeof meta.rev !== 'string' || !meta.rev)) throw new Error('Invalid file revision response');
        return meta;
      } catch (e) {
        if (e.status !== 404 && e.status !== 405 && e.status !== 501) throw e;
        // Older servers lack the metadata route. A full read also preserves a genuine missing-file error.
        const full = await this.read(path); return { path, rev: full.rev, full };
      }
    }
    async hydrate(paths, entries = this.files) {
      // Explicit demand only. Capture every entry before reading and publish the batch atomically.
      const captured = [...new Set(paths)].map(path => [path, entries.get(path)]).filter(([, file]) => file?.omitted?.length);
      const full = await Promise.all(captured.map(async ([path, file]) => {
        let pending = this.#hydrating.get(file);
        if (!pending) {
          pending = this.read(path, file.rev); this.#hydrating.set(file, pending);
          pending.catch(() => { this.#hydrating.delete(file); });
        }
        return [path, await pending];
      }));
      if (captured.some(([path, file]) => this.files.get(path) !== file && this.files.get(path)?.rev !== file.rev)) {
        throw new HostedError(412, { code: 'revision_conflict', message: 'File changed during hydration; reload' });
      }
      const files = new Map(this.files);
      for (const [path, file] of full) files.set(path, file);
      this.files = files; return this.model();
    }
    model() {
      if (!this.files.has('tasks.json')) throw new Error('Load a snapshot first');
      const out = copy(this.files.get('tasks.json').body);
      for (const coll of Object.values(collections)) out[coll] = [];
      for (const [path, file] of [...this.files].sort()) {
        const coll = collections[path.split('/')[0]]; if (coll) out[coll].push(copy(file.body));
      }
      return out;
    }
    commit(ops, key, fences) { return this.request('POST', this.route('/commits'), { ops, ...(fences ? { fences } : {}) }, key); }
    command(command, key) { return this.request('POST', this.route('/commands'), command, key); }
    changes(cursor) { return this.request('GET', this.route('/changes?after=' + encodeURIComponent(cursor) + '&limit=100')); }
    async poll() {
      if (!this.cursor) { await this.snapshot(); return true; }
      let changed = false;
      try {
        let page;
        do {
          page = await this.changes(this.cursor);
          // A page is applied atomically, then its cursor advances. Documents do not enter schema-4 files.
          const files = new Map(this.files); let claims = this.claims;
          for (const batch of page.batches) {
            for (const delta of batch.changes) {
              if (delta.resource === 'document') continue;
              if (delta.op === 'delete') files.delete(delta.path);
              else {
                // No body is an invalidation, never an empty replacement.
                const file = delta.body === undefined ? await this.read(delta.path, delta.rev) : copy(delta);
                files.set(delta.path, file);
              }
              changed = true;
            }
            if (batch.claims) { claims = copy(batch.claims); changed = true; }
          }
          this.files = files; this.claims = claims; this.cursor = page.through;
        } while (page.has_more);
        return changed;
      } catch (e) {
        if (e.status === 410 || e.status === 412) { await this.snapshot(); return true; }
        throw e;
      }
    }
    contents() { throw new Error('capability_unavailable: GitHub Contents is disabled in hosted mode'); }
    api() { throw new Error('capability_unavailable: GitHub API is disabled in hosted mode'); }
  }
  const exports = { HostedAdapter, HostedError, localURL, pageAPI };
  if (typeof module !== 'undefined' && module.exports) module.exports = exports;
  else root.KeeptrackHosted = exports;
})(globalThis);

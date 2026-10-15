'use strict';

const assert = require('node:assert/strict');
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');

const ROOT = path.resolve(__dirname, '../..');
const mime = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json', '.svg': 'image/svg+xml' };
const server = http.createServer((req, res) => {
  const rel = decodeURIComponent(new URL(req.url, 'http://local').pathname).replace(/^\/+/, '') || 'board/index.html';
  const file = path.resolve(ROOT, rel); if (!file.startsWith(ROOT + path.sep)) { res.writeHead(403).end(); return; }
  fs.readFile(file, (err, data) => { if (err) res.writeHead(404).end(); else { res.setHeader('Content-Type', mime[path.extname(file)] || 'application/octet-stream'); res.end(data); } });
});

const root = { version: 4, layout: 'split', settings: { title: 'GraphQL test' }, columns: [{ id: 'todo', name: 'To do' }], people: [], agents: [], clients: [], labels: [], client_info: {}, next_num: 31, archive: { files: {} } };
const files = { 'tasks.json': JSON.stringify(root) };
for (let i = 1; i <= 30; i++) files[`cards/t_${i}.json`] = JSON.stringify({ id: `t_${i}`, num: i, title: `GraphQL card ${i}`, column: 'todo', client: '', priority: 'medium', due: '', labels: [], assignees: [], details: '', links: [], contacts: [], todos: [], comments: [], history: [], claim: null, created: '2026-10-01T08:00:00.000Z', updated: '2026-10-01T08:00:00.000Z', rank: `a${i}` });
const sha = p => require('node:crypto').createHash('sha1').update(files[p]).digest('hex');
const bySha = Object.fromEntries(Object.keys(files).map(p => [sha(p), files[p]]));
const tree = Object.entries(files).map(([p, content]) => ({ path: p, type: 'blob', sha: sha(p), size: Buffer.byteLength(content) }));

(async () => {
  await new Promise(ok => server.listen(0, '127.0.0.1', ok)); const base = `http://127.0.0.1:${server.address().port}`;
  const browser = await chromium.launch({ headless: true });
  try {
    for (const mode of ['ok', 'denied', 'partial']) {
      const context = await browser.newContext(), page = await context.newPage(), calls = []; let broken = [];
      await page.addInitScript(() => { for (const [k, v] of Object.entries({ repo: 'acme/board', branch: 'main', path: 'board/tasks.json', token: 'test', me: 'alex', api: 'https://api.test', layout: 'classic' })) localStorage.setItem('kb_' + k, v); sessionStorage.setItem('kb_view', 'board'); });
      await page.route('https://api.test/**', async route => {
        const req = route.request(), p = new URL(req.url()).pathname.replace('/repos/acme/board', ''); calls.push(p);
        const json = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
        if (p === '/graphql') {
          assert.equal(req.method(), 'POST'); assert.equal(req.headers().authorization, 'Bearer test');
          const body = req.postDataJSON(); assert.deepEqual(body.variables, { owner: 'acme', name: 'board' });
          const oids = [...body.query.matchAll(/b(\d+):object\(oid:"([0-9a-f]{40})"\)/g)]; assert(oids.length > 8 && oids.length <= 40);
          if (mode === 'denied') return json({ message: 'Forbidden' }, 403);
          broken = mode === 'partial' ? oids.slice(0, 2).map(x => x[2]) : [];
          return json({ data: { repository: Object.fromEntries(oids.map(([_, i, oid]) => [`b${i}`, oid === broken[0] ? { text: 'incomplete', isTruncated: true, isBinary: false } : oid === broken[1] ? null : { text: bySha[oid], isBinary: false, isTruncated: false }])) } });
        }
        if (p === '/user') return json({ login: 'alex' });
        if (p === '') return json({ full_name: 'acme/board', private: true, permissions: { push: true }, default_branch: 'main' });
        if (p === '/contents/board/tasks.json') return json({ sha: sha('tasks.json'), encoding: 'base64', content: Buffer.from(files['tasks.json']).toString('base64') });
        if (p === '/git/ref/heads/main') return json({ object: { sha: 'head' } });
        if (p === '/git/commits/head') return json({ tree: { sha: 'root' } });
        if (p === '/git/trees/root') return json({ tree: [{ path: 'board', type: 'tree', sha: 'board' }] });
        if (p === '/git/trees/board') return json({ tree, truncated: false });
        if (p.startsWith('/git/blobs/')) return json({ encoding: 'base64', content: Buffer.from(bySha[p.split('/').pop()]).toString('base64') });
        return json({ message: 'Not Found' }, 404);
      });
      const synced = () => page.waitForFunction(() => /^Synced/.test(document.querySelector('#status').textContent));
      await page.goto(base + '/board/index.html'); await synced();
      for (let i = 1; i <= 30; i++) assert.equal(await page.getByText(`GraphQL card ${i}`, { exact: true }).count(), 1);
      assert.equal(calls.filter(p => p === '/graphql').length, 1);
      const rest = calls.filter(p => p.startsWith('/git/blobs/'));
      assert.equal(rest.length, mode === 'denied' ? 31 : mode === 'partial' ? 2 : 0);
      if (mode === 'partial') assert.deepEqual(rest.map(p => p.split('/').pop()).sort(), broken.sort());
      // Finish cache writes before testing another visit in the same browser.
      await page.evaluate(() => new Promise(ok => { const r = indexedDB.open('keeptrack', 1); r.onsuccess = () => { const t = r.result.transaction('kv', 'readonly'); t.objectStore('kv').getAll(); t.oncomplete = ok; }; }));
      calls.length = 0; await page.reload(); await synced();
      assert.equal(calls.filter(p => p === '/graphql').length, 0);
      assert.equal(calls.filter(p => p.startsWith('/git/blobs/')).length, 0);
      await context.close();
    }
    console.log('GraphQL read browser tests passed');
  } finally { await browser.close(); server.close(); }
})().catch(err => { console.error(err); server.close(); process.exitCode = 1; });

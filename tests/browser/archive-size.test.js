'use strict';
// Archive files are bounded at 900 KB (kit v102): packable years split atomically; unpackable envelopes stay held.
// Past 700 KB an unsplit archive is written and the toast warns. Run: node archive-size.test.js

const assert = require('node:assert/strict');
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { chromium } = require('playwright');

const ROOT = path.resolve(__dirname, '../..');
const SHOTS = process.env.SHOTS || '';
const mime = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json', '.svg': 'image/svg+xml' };
const server = http.createServer((req, res) => {
  const rel = decodeURIComponent(new URL(req.url, 'http://local').pathname).replace(/^\/+/, '') || 'board/index.html';
  const file = path.resolve(ROOT, rel); if (!file.startsWith(ROOT + path.sep)) { res.writeHead(403).end(); return; }
  fs.readFile(file, (err, data) => { if (err) res.writeHead(404).end(); else { res.setHeader('Content-Type', mime[path.extname(file)] || 'application/octet-stream'); res.end(data); } });
});

const stampForTest=()=> '2020-01-01T00:00:00Z';
const text = x => JSON.stringify(x, null, 2) + '\n';
const root = { version: 4, layout: 'split', settings: { title: 'Drawer test' }, columns: [{ id: 'todo', name: 'To do' }, { id: 'done', name: 'Done' }], people: [{ github: 'alex', name: 'Alex' }, { github: 'sam', name: 'Sam' }], agents: [], clients: ['Acme', 'Bluebell Events', 'Northwind Traders'], labels: [{ name: 'pale', color: '#dce1e7' }, { name: 'dark', color: '#334155' }], client_info: {}, next_num: 4, archive: { files: {} } };
const card = (id, num, title, extra) => ({ id, num, title, column: 'todo', client: '', priority: 'medium', due: '', labels: [], assignees: [], details: '', links: [], contacts: [], todos: [], comments: [], history: [], claim: null, created: '2026-10-01T08:00:00.000Z', updated: '2026-10-01T08:00:00.000Z', rank: 'a' + num, ...extra });

// A small GitHub: contents API for reads and single-file writes, git data API for multi-file commits (same shape as split-storage.test.js).
class Github {
  constructor() {
    this.files = { 'tasks.json': text(root), 'cards/t_one.json': text(card('t_one', 1, 'Open work')), 'cards/t_two.json': text(card('t_two', 2, 'Finished work', { column: 'done', history: [{ at: '2026-10-02T08:00:00.000Z', by: 'alex', text: 'moved to Done' }] })), 'cards/t_three.json': text(card('t_three', 3, 'Agent still on it', { column: 'done', claim: { agent: 'claude', on_behalf_of: 'alex', session: 'abcdef12', status: 'working', since: '2026-10-15T08:00:00.000Z', heartbeat: new Date().toISOString() } })) };
    this.files['people/p_craig.json'] = text({ id: 'p_craig', name: 'Craig Example', company: 'Acme', role: 'Director', emails: [{ label: 'Work', value: 'craig@example.com' }], phones: [], links: [], comments: [], history: [] });
    this.files['people/p_chris.json'] = text({ id: 'p_chris', name: 'Chris Example', company: 'Other', emails: [{ label: 'Work', value: 'chris@example.com' }], phones: [], links: [], comments: [], history: [] });
    this.head = 'head-1'; this.n = 1; this.blobs = {}; this.pending = null; this.writes = 0;
  }
  sha(p) { return crypto.createHash('sha1').update(this.files[p] || '').digest('hex'); }
  async route(route) {
    const req = route.request(), u = new URL(req.url()), method = req.method(), p = u.pathname.replace('/repos/acme/board', '');
    const json = (body, status = 200, headers = {}) => route.fulfill({ status, headers: { 'Content-Type': 'application/json', ...headers }, body: JSON.stringify(body) });
    if (method !== 'GET') this.writes++;
    if (p === '/user' && method === 'GET') return json({ login: 'alex' });
    if (p.startsWith('/user/repos')) return json([]);
    if (p === '' && method === 'GET') return json({ full_name: 'acme/board', private: true, permissions: { push: true }, default_branch: 'main' });
    if (p.startsWith('/contents/README.md')) return json({ message: 'Not Found' }, 404);
    if (p.startsWith('/contents/board/tasks.json') && method === 'GET') return json({ sha: this.sha('tasks.json'), size: Buffer.byteLength(this.files['tasks.json']), encoding: 'base64', content: Buffer.from(this.files['tasks.json']).toString('base64') });
    if (p.startsWith('/contents/board/') && method === 'GET') { const rel = p.slice('/contents/board/'.length); return this.files[rel] ? json({ sha: this.sha(rel), encoding: 'base64', content: Buffer.from(this.files[rel]).toString('base64') }) : json({ message: 'Not Found' }, 404); }
    if (p.startsWith('/contents/board/') && method === 'PUT') { const rel = p.slice('/contents/board/'.length), b = req.postDataJSON(); this.files[rel] = Buffer.from(b.content, 'base64').toString(); this.head = 'head-' + ++this.n; return json({ content: { sha: this.sha(rel) }, commit: { sha: this.head, tree: { sha: 'root-' + this.n } } }); }
    if (p.startsWith('/contents/board/') && method === 'DELETE') { delete this.files[p.slice('/contents/board/'.length)]; this.head = 'head-' + ++this.n; return json({ commit: { sha: this.head, tree: { sha: 'root-' + this.n } } }); }
    if (p === '/git/ref/heads/main' && method === 'GET') return json({ object: { sha: this.head } });
    if (p.startsWith('/git/commits/') && method === 'GET') return json({ tree: { sha: 'root-' + this.n } });
    if (p.startsWith('/git/trees/root-') && method === 'GET') return json({ tree: [{ path: 'board', type: 'tree', sha: 'board-' + this.n }] });
    if (p.startsWith('/git/trees/board-') && method === 'GET') return json({ truncated: false, tree: Object.entries(this.files).map(([f, c]) => ({ path: f, type: 'blob', sha: this.sha(f), size: Buffer.byteLength(c) })) });
    if (p.startsWith('/git/blobs/') && method === 'GET') { const sha = p.split('/').pop(), rel = Object.keys(this.files).find(x => this.sha(x) === sha); return json({ encoding: 'base64', content: Buffer.from(this.files[rel]).toString('base64') }); }
    if (p === '/git/blobs' && method === 'POST') { const sha = 'new-blob-' + ++this.n; this.blobs[sha] = req.postDataJSON().content; return json({ sha }); }
    if (p === '/git/trees' && method === 'POST') { this.pending = req.postDataJSON().tree; return json({ sha: 'new-tree-' + ++this.n }); }
    if (p === '/git/commits' && method === 'POST') return json({ sha: 'new-commit-' + ++this.n });
    if (p === '/git/refs/heads/main' && method === 'PATCH') { for (const e of this.pending || []) { const rel = e.path.replace(/^board\//, ''); if (e.sha === null) delete this.files[rel]; else this.files[rel] = this.blobs[e.sha]; } this.head = req.postDataJSON().sha; return json({ object: { sha: this.head } }); }
    return json({ message: 'not mocked: ' + method + ' ' + p }, 404);
  }
  card(id = 't_one') { return this.files[`cards/${id}.json`] ? JSON.parse(this.files[`cards/${id}.json`]) : null; }
}

let base;
const shot = async (page, name) => { if (SHOTS) { fs.mkdirSync(SHOTS, { recursive: true }); await page.screenshot({ path: path.join(SHOTS, name + '.png') }); } };
const init = view => { localStorage.setItem('kb_repo', 'acme/board'); localStorage.setItem('kb_branch', 'main'); localStorage.setItem('kb_path', 'board/tasks.json'); localStorage.setItem('kb_token', 'test'); localStorage.setItem('kb_me', 'alex'); localStorage.setItem('kb_api', 'https://api.test'); localStorage.setItem('kb_layout', 'classic'); localStorage.setItem('kb_tour_seen', '1'); localStorage.setItem('kb_tab', 'done'); sessionStorage.setItem('kb_view', view); };
const opacity = loc => loc.evaluate(e => Number(getComputedStyle(e).opacity));

(async () => {
  await new Promise(ok => server.listen(0, '127.0.0.1', ok)); base = `http://127.0.0.1:${server.address().port}`;
  const browser = await chromium.launch({ headless: true });
  try {
    // A packable oversized year is committed atomically with the live-card removal, for both layouts.
    for (const split of [true, false]) {
      const api = new Github(), year = String(new Date().getFullYear());
      api.files[`archive/${year}.json`] = text({ version:3, archive:true, year, custom:{keep:true},
        tasks:[card('t_old_a',20,'Old A',{details:'x'.repeat(350000)}),card('t_old_b',21,'Old B',{details:'x'.repeat(350000)})],contacts:[],history:{t_two:[{at:stampForTest(),text:'older evidence'}]} });
      const done = api.card('t_two'); done.details='x'.repeat(350000); api.files['cards/t_two.json']=text(done);
      const meta=JSON.parse(api.files['tasks.json']); meta.archive={files:{[year]:{tasks:2,contacts:0}}};
      if (!split) { delete meta.layout; meta.version=3; meta.tasks=Object.keys(api.files).filter(p=>p.startsWith('cards/')).map(p=>JSON.parse(api.files[p])); meta.contacts=[]; }
      api.files['tasks.json']=text(meta);
      if (!split) for (const key of Object.keys(api.files)) if (/^(cards|people)\//.test(key)) delete api.files[key];
      let archiveReads=0;
      const page=await browser.newPage({viewport:{width:1280,height:860}}), errors=[]; page.on('pageerror',e=>errors.push(e.message));
      await page.addInitScript(init,'board'); await page.route('https://api.test/**',r=>{
        const u=r.request().url(); if (r.request().method()==='GET' && (u.includes('/archive/') || u.endsWith('/git/blobs/'+api.sha(`archive/${year}.json`)))) archiveReads++;
        return api.route(r);
      });
      await page.goto(base+'/board/index.html'); await page.waitForSelector('.card');
      assert.equal(archiveReads,0,'normal board opening never downloads archive bodies');
      const shipped=page.locator('.col[data-col="done"] .card',{hasText:'Finished work'}); await shipped.hover(); await shipped.locator('.quickarch').click();
      await page.getByRole('button',{name:'Undo',exact:true}).waitFor();
      const after=JSON.parse(api.files['tasks.json']), keys=Object.keys(after.archive.files);
      assert.equal(after.settings.min_kit,102); assert.ok(keys.some(y=>y.startsWith(year+'-')));
      const records=keys.flatMap(y=>{assert.ok(Buffer.byteLength(api.files[`archive/${y}.json`])<=900*1024);return JSON.parse(api.files[`archive/${y}.json`]).tasks;});
      assert.deepEqual(records.map(x=>x.id).sort(),['t_old_a','t_old_b','t_two']);
      assert.deepEqual(JSON.parse(api.files[`archive/${year}.json`]).custom,{keep:true});
      assert.ok(api.pending.some(x=>/archive\/\d{4}-[1-9]/.test(x.path)),'part creation is in the same tree commit');
      assert.ok(split ? !api.card('t_two') : !after.tasks.some(x=>x.id==='t_two'));
      await page.getByRole('button',{name:'Undo',exact:true}).click();
      await page.waitForFunction(()=>document.querySelector('.col[data-col="done"]')?.textContent.includes('Finished work'));
      const restored=split?api.card('t_two'):JSON.parse(api.files['tasks.json']).tasks.find(x=>x.id==='t_two');
      assert.equal(restored.details,'x'.repeat(350000)); assert.ok(restored.history.some(x=>x.text==='older evidence'));
      assert.deepEqual(errors,[]); await page.close();
    }
    for (const [kb, held] of [[905, true], [710, false]]) {
      const api = new Github(), year = String(new Date().getFullYear());   // the quick archive writes to today's year, whatever the card's date
      api.files[`archive/${year}.json`] = text({ version: 3, archive: true, year, tasks: [], contacts: [], history: {}, pad: 'x'.repeat(kb * 1024) });
      api.files['tasks.json'] = text({ ...JSON.parse(api.files['tasks.json']), archive: { files: { [year]: { tasks: 0, contacts: 0 } } } });
      const page = await browser.newPage({ viewport: { width: 1280, height: 860 } }), errors = []; page.on('pageerror', e => errors.push(e.message));
      await page.addInitScript(init, 'board'); await page.route('https://api.test/**', r => api.route(r)); await page.goto(base + '/board/index.html'); await page.waitForSelector('.card');
      const snapshot = JSON.stringify(api.files), writes = api.writes;
      const done = page.locator('.col[data-col="done"] .card', { hasText: 'Finished work' }); await done.hover(); await done.locator('.quickarch').click();
      if (held) {
        await page.locator('.ui-toast__text', { hasText: 'Held back 1 item' }).waitFor();
        const t = await page.locator('.ui-toast__text', { hasText: 'Held back' }).first().textContent();
        assert.match(t, new RegExp(`archive/${year}\\.json`)); assert.match(t, /board owner/); assert.match(t, /stay on the board/);
        assert.equal(JSON.stringify(api.files), snapshot, 'not one file changed'); assert.equal(api.writes, writes, 'nothing was written to GitHub');
        assert.ok(api.card('t_two'), 'the card is still on the board');
      } else {
        await page.locator('.ui-toast__text', { hasText: 'doctor fails above 900 KB' }).waitFor();
        assert.equal(api.card('t_two'), null, 'the card left the board');
        assert.deepEqual(JSON.parse(api.files[`archive/${year}.json`]).tasks.map(t => t.id), ['t_two']);
        assert.ok(Buffer.byteLength(api.files[`archive/${year}.json`]) > 710 * 1024, 'the year file grew');
      }
      assert.deepEqual(errors, []); await page.close();
    }
    // A one-file board: one year over the limit is held back, a history-only year (today's) is written. The page must still
    // trim the history on the board, update the archive index and say what it did.
    for (const split of [false, true]) {
      const thisYear = String(new Date().getFullYear()), oldIso = new Date(Date.now() - 400 * 864e5).toISOString(), heldYear = oldIso.slice(0, 4);
      const hist = Array.from({ length: 30 }, (_, i) => ({ at: '2026-09-01T08:00:' + String(i).padStart(2, '0') + '.000Z', by: 'alex', text: 'step ' + i }));
      const api = new Github(), one = { ...root, layout: undefined, archive: { files: { [heldYear]: { tasks: 0, contacts: 0 } } }, contacts: [],
        tasks: [card('t_one', 1, 'Open work', { history: hist }), card('t_old', 2, 'Old finished work', { column: 'done', created: oldIso, updated: oldIso })] };
      delete one.layout; api.files = { 'tasks.json': text(one), [`archive/${heldYear}.json`]: text({ version: 3, archive: true, year: heldYear, tasks: [], contacts: [], history: {}, pad: 'x'.repeat(905 * 1024) }) };
      if (split) {
        const meta = { ...one, layout: 'split' }; delete meta.tasks; delete meta.contacts;
        api.files['tasks.json'] = text(meta);
        for (const task of one.tasks) api.files[`cards/${task.id}.json`] = text(task);
      }
      const heldBefore = api.files[`archive/${heldYear}.json`];
      const page = await browser.newPage({ viewport: { width: 1280, height: 860 } }), errors = []; page.on('pageerror', e => errors.push(e.message));
      await page.addInitScript(init, 'board'); await page.route('https://api.test/**', r => api.route(r)); await page.goto(base + '/board/index.html'); await page.waitForSelector('.card');
      await page.evaluate(() => window.kbSettings.open('archive'));
      const btn = page.locator('#archBox button', { hasText: /^Archive \d+ task/ }); await btn.waitFor(); await btn.click();
      await page.locator('dialog[open] button', { hasText: /^Archive$/ }).click();
      const toast = page.locator('.ui-toast__text', { hasText: 'Archived' }); await toast.first().waitFor();
      const t = await toast.first().textContent();
      assert.doesNotMatch(t, /Nothing archived/); assert.match(t, /Held back 1 item/); assert.match(t, new RegExp(`archive/${heldYear}\\.json`));
      assert.match(t, /0 done tasks, 0 Lost people and 10 old history lines/, 'the toast counts only what was written');
      const board = JSON.parse(api.files['tasks.json']);
      if (split) board.tasks = Object.entries(api.files).filter(([p]) => p.startsWith('cards/')).map(([,v]) => JSON.parse(v));
      assert.ok(board.tasks.some(x => x.id === 't_old'), 'the held card is still on the board');
      assert.equal(board.tasks.find(x => x.id === 't_one').history.length, 20, 'history trimmed on the board');
      assert.deepEqual(board.archive.files[thisYear], { tasks: 0, contacts: 0 }, 'the index lists the year that was written');
      assert.deepEqual(board.archive.files[heldYear], { tasks: 0, contacts: 0 }, 'the held year is unchanged in the index');
      assert.ok(board.archive.last_run, 'last_run is set');
      const written = JSON.parse(api.files[`archive/${thisYear}.json`]);
      assert.equal(written.history.t_one.length, 10, 'the old lines are in the archive');
      assert.equal(api.files[`archive/${heldYear}.json`], heldBefore, 'the held year file is not touched');
      assert.deepEqual(errors, []); await page.close();
    }
    console.log('archive-size browser tests passed');
  } finally { await browser.close(); server.close(); }
})().catch(e => { console.error(e); process.exit(1); });

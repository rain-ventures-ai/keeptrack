'use strict';
// The PRs panel and the relay-kit bar (card #82) on a faked GitHub: the panel reads each linked pull request once per open
// (batched GraphQL, cached, reads only), groups them (waiting on you, open, merged but card not Done, unknown), and the relay bar
// makes one update card for the upgrade owner and never a second. Run: node prs-panel.test.js   (SHOTS=<dir> saves screenshots)

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
class Github {
  constructor() {
    this.files = { 'tasks.json': text(root), 'cards/t_one.json': text(card('t_one', 1, 'First', { client: 'Acme', priority: 'high', labels: ['pale', 'dark'], assignees: ['alex'], agent_cleared: CLEARED })), 'cards/t_two.json': text(card('t_two', 2, 'Second')) };
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

const text = x => JSON.stringify(x, null, 2) + '\n';
const CLEARED = [];
const T = (d) => `2026-10-${d}T08:00:00.000Z`;
const root = { version: 4, layout: 'split', settings: { title: 'PRs test' }, columns: [{ id: 'todo', name: 'To do' }, { id: 'done', name: 'Done' }], people: [{ github: 'alex', name: 'Alex' }, { github: 'sam', name: 'Sam' }], agents: ['claude'], clients: ['Acme'], labels: [], client_info: {}, next_num: 10, archive: { files: {} } };
const card = (id, num, title, extra) => ({ id, num, title, column: 'todo', client: '', priority: 'medium', due: '', labels: [], assignees: [], details: '', links: [], contacts: [], todos: [], comments: [], history: [], claim: null, created: T('01'), updated: T('01'), rank: 'a' + num, ...extra });
const pr = (n, repo = 'web') => ({ title: 'PR link', url: `https://github.com/acme/${repo}/pull/${n}` });
const CARDS = [
  card('t_agent', 1, 'Agent work', { links: [pr(1)], assignees: ['alex'], claim: { agent: 'claude', on_behalf_of: 'alex', status: 'done', claimed_at: T('02') } }),
  card('t_review', 2, 'Needs my review', { links: [pr(2)] }),
  card('t_shipped', 3, 'Shipped but not done', { links: [pr(3)] }),
  card('t_done', 4, 'Done card', { column: 'done', links: [pr(4)] }),
  card('t_draft', 5, 'Draft work', { links: [pr(5), { title: 'Issue', url: 'https://github.com/acme/web/issues/9' }, { title: 'Files tab', url: 'https://github.com/acme/web/pull/7/files' }] }),
  card('t_hidden', 6, 'Hidden repo', { links: [pr(6, 'secret')] }),
  card('t_failing', 7, 'A very long title that keeps going so that the row has to wrap on a phone and still fit the drawer neatly', { links: [pr(8)] }),
];
const PRS = {   // number -> what GitHub says; absent = null (cannot read)
  1: { title: 'Add the thing', state: 'OPEN', isDraft: false, merged: false, updatedAt: T('09'), mergeable: 'MERGEABLE', author: { login: 'claude[bot]' }, reviewDecision: 'APPROVED', reviewRequests: { nodes: [] }, commits: { nodes: [{ commit: { statusCheckRollup: { state: 'SUCCESS' } } }] } },
  2: { title: 'Fix the other thing', state: 'OPEN', isDraft: false, merged: false, updatedAt: T('05'), mergeable: 'MERGEABLE', author: { login: 'sam' }, reviewDecision: 'REVIEW_REQUIRED', reviewRequests: { nodes: [{ requestedReviewer: { login: 'Alex' } }] }, commits: { nodes: [{ commit: { statusCheckRollup: { state: 'PENDING' } } }] } },
  3: { title: 'Ship it', state: 'MERGED', isDraft: false, merged: true, updatedAt: T('07'), mergeable: 'UNKNOWN', author: { login: 'sam' }, reviewDecision: null, reviewRequests: { nodes: [] }, commits: { nodes: [] } },
  4: { title: 'Old merged', state: 'MERGED', isDraft: false, merged: true, updatedAt: T('03'), mergeable: 'UNKNOWN', author: { login: 'sam' }, reviewDecision: null, reviewRequests: { nodes: [] }, commits: { nodes: [] } },
  5: { title: 'Draft: work in progress', state: 'OPEN', isDraft: true, merged: false, updatedAt: T('08'), mergeable: 'MERGEABLE', author: { login: 'sam' }, reviewDecision: null, reviewRequests: { nodes: [] }, commits: { nodes: [{ commit: { statusCheckRollup: { state: 'PENDING' } } }] } },
  8: { title: 'Broken build', state: 'OPEN', isDraft: false, merged: false, updatedAt: T('10'), mergeable: 'CONFLICTING', author: { login: 'sam' }, reviewDecision: 'CHANGES_REQUESTED', reviewRequests: { nodes: [] }, commits: { nodes: [{ commit: { statusCheckRollup: { state: 'FAILURE' } } }] } },
};

class Relay extends Github {
  constructor(opts = {}) {
    super(); this.gql = []; this.reads = []; this.relayHave = opts.have === undefined ? '0.7.10\n' : opts.have; this.relayWant = opts.want || '0.9.0\n';
    this.files['tasks.json'] = text(root); delete this.files['cards/t_one.json']; delete this.files['cards/t_two.json'];
    CARDS.forEach(c => { this.files[`cards/${c.id}.json`] = text(c); });
  }
  async route(route) {
    const req = route.request(), u = new URL(req.url()), method = req.method();
    const json = (body, status = 200) => route.fulfill({ status, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    if (u.pathname === '/graphql') {
      this.gql.push({ auth: req.headers().authorization, query: req.postDataJSON().query });
      const data = {}; [...req.postDataJSON().query.matchAll(/(p\d+): repository\(owner: "([^"]+)", name: "([^"]+)"\) \{ pullRequest\(number: (\d+)\)/g)].forEach(m => { data[m[1]] = { pullRequest: m[3] === 'web' ? PRS[m[4]] || null : null }; });
      return this.gqlFail ? json({ message: 'Bad credentials' }, 401) : json({ data });
    }
    if (u.pathname === '/repos/acme/board/contents/relay/KIT_VERSION') { this.reads.push(u.pathname); return this.relayHave == null ? json({ message: 'Not Found' }, 404) : route.fulfill({ status: 200, body: this.relayHave }); }
    if (u.pathname === '/repos/rain-ventures-ai/keeptrack-relay/contents/relay/KIT_VERSION') { this.reads.push(u.pathname); return route.fulfill({ status: 200, body: this.relayWant }); }
    return super.route(route);
  }
  titles() { return Object.keys(this.files).filter(f => f.startsWith('cards/')).map(f => JSON.parse(this.files[f])); }
}

let base;
const shot = async (page, name) => { if (SHOTS) { fs.mkdirSync(SHOTS, { recursive: true }); await page.screenshot({ path: path.join(SHOTS, name + '.png') }); } };
async function open(browser, api, { width = 1100, height = 900, me = 'alex' } = {}) {
  const page = await browser.newPage({ viewport: { width, height } }); const errors = []; page.on('pageerror', e => errors.push(e.message));
  await page.addInitScript(m => { localStorage.setItem('kb_repo', 'acme/board'); localStorage.setItem('kb_branch', 'main'); localStorage.setItem('kb_path', 'board/tasks.json'); localStorage.setItem('kb_token', 'test'); localStorage.setItem('kb_me', m); localStorage.setItem('kb_api', 'https://api.test'); localStorage.setItem('kb_layout', 'classic'); localStorage.setItem('kb_tour_seen', '1'); sessionStorage.setItem('kb_view', 'board'); }, me);
  await page.route('https://api.test/**', r => api.route(r)); await page.goto(base + '/board/index.html'); await page.waitForSelector('.card');
  page.errors = errors; return page;
}
const headings = page => page.locator('#prsBody h4').allTextContents();
const rowTitles = (page, i) => page.locator('#prsBody .prgroup').nth(i).locator('.prtitle').allTextContents();

(async () => {
  await new Promise(ok => server.listen(0, '127.0.0.1', ok)); base = `http://127.0.0.1:${server.address().port}`;
  const browser = await chromium.launch({ headless: true });
  try {
    // ---- the PRs panel ----
    const api = new Relay({ have: null }); const page = await open(browser, api);
    assert.equal(api.gql.length, 0, 'nothing is read from GraphQL until the panel opens');
    assert.equal(await page.locator('#btnPrs').isVisible(), true, 'a board with PR links shows the button');
    await page.locator('#btnPrs').click(); await page.locator('#dlgPrs[open]').waitFor(); await page.locator('#prsBody .prrow').first().waitFor();
    assert.equal(api.gql.length, 1, 'one batched query for every linked PR');
    assert.equal(api.gql[0].auth, 'Bearer test', 'reads with the board login');
    assert(!/mutation/i.test(api.gql[0].query), 'only reads');
    assert.equal((api.gql[0].query.match(/pullRequest\(number/g) || []).length, 7, 'only plain github.com pull URLs are asked for (not issues, not /files)');
    assert.deepEqual(await headings(page), ['Waiting on you (2)', 'Open (2)', 'Merged, card not Done (1)', 'Unknown (1)']);
    assert.deepEqual(await rowTitles(page, 0), ['Add the thing', 'Fix the other thing'], 'newest first inside a group');
    assert.deepEqual(await rowTitles(page, 1), ['Broken build', 'Draft: work in progress']);
    assert.deepEqual(await rowTitles(page, 2), ['Ship it']);
    assert.equal((await page.locator('#prsBody').innerText()).includes('Old merged'), false, 'a merged PR on a Done card is not listed');
    const waiting = page.locator('#prsBody .prgroup').nth(0);
    assert.match(await waiting.locator('.prrow').nth(0).innerText(), /Ready to merge[\s\S]*Open[\s\S]*Checks passing[\s\S]*Approved/);
    assert.match(await waiting.locator('.prrow').nth(1).innerText(), /Asks you for a review/);
    const open2 = page.locator('#prsBody .prgroup').nth(1);
    assert.match(await open2.locator('.prrow').nth(0).innerText(), /Checks failing[\s\S]*Changes requested[\s\S]*Has conflicts/);
    assert.match(await open2.locator('.prrow').nth(1).innerText(), /Draft/);
    assert.match(await page.locator('#prsBody .prgroup').nth(2).innerText(), /Merged[\s\S]*Can be finished[\s\S]*#3 Shipped but not done \(not Done yet\)/);
    assert.match(await page.locator('#prsBody .prgroup').nth(3).innerText(), /Unknown[\s\S]*Could not read/);
    assert.equal(await page.locator('#prsBody a.prtitle').first().getAttribute('href'), 'https://github.com/acme/web/pull/1');
    await shot(page, 'prs-panel-desktop');
    // the panel never moves a card; a card button opens that card
    await page.locator('#prsBody .prgroup').nth(2).locator('.prcard').click(); await page.locator('#dlgCard[open]').waitFor();
    assert.equal(await page.locator('#cTitle').inputValue(), 'Shipped but not done'); assert.equal(await page.locator('#dlgPrs[open]').count(), 0, 'the panel closes');
    assert.equal(api.titles().find(c => c.id === 't_shipped').column, 'todo', 'the card stays where it was');
    assert.equal(api.writes, 0, 'no write at all');
    await page.keyboard.press('Escape');
    // cached: opening again does not read again; Refresh does
    await page.locator('#btnPrs').click(); await page.locator('#prsBody .prrow').first().waitFor(); assert.equal(api.gql.length, 1, 'cached for a couple of minutes');
    await page.locator('#prsRefresh').click(); await page.waitForFunction(() => !document.getElementById('prsRefresh').disabled); assert.equal(api.gql.length, 2, 'Refresh reads again');
    assert.deepEqual(page.errors, []); await page.close();

    // somebody else's panel: no review asked of them, and an agent's PR is not theirs to merge
    const other = await open(browser, new Relay({ have: null }), { me: 'sam' });
    await other.locator('#btnPrs').click(); await other.locator('#prsBody .prrow').first().waitFor();
    assert.equal((await headings(other)).some(h => h.startsWith('Waiting on you')), false, 'nothing waits on a member who has no request or agent PR');
    await other.close();

    // GitHub refuses: everything says unknown, with the reason
    const bad = new Relay({ have: null }); bad.gqlFail = true; const bp = await open(browser, bad);
    await bp.locator('#btnPrs').click(); await bp.locator('#prsBody .prrow').first().waitFor();
    assert.deepEqual(await headings(bp), ['Unknown (7)']); assert.match(await bp.locator('#prsStatus').innerText(), /401/);
    await bp.close();

    // phone width: nothing scrolls sideways
    const ph = await open(browser, new Relay({ have: null }), { width: 390, height: 844 });
    await ph.locator('#btnMore').click(); await ph.locator('#morePop [data-head-action="btnPrs"]').click(); await ph.locator('#prsBody .prrow').first().waitFor();
    const fit = await ph.evaluate(() => { const d = document.getElementById('dlgPrs'); return { docW: document.documentElement.scrollWidth, vw: innerWidth, dW: d.scrollWidth - d.clientWidth }; });
    assert(fit.docW <= fit.vw && fit.dW <= 0, 'the panel fits a phone'); await shot(ph, 'prs-panel-phone'); await ph.close();

    // no PR link on any card: no button
    const none = new Relay({ have: null }); CARDS.forEach(c => { const o = JSON.parse(none.files[`cards/${c.id}.json`]); o.links = []; none.files[`cards/${c.id}.json`] = text(o); });
    const np = await open(browser, none); assert.equal(await np.locator('#btnPrs').isVisible(), false); await np.close();

    // ---- the relay kit bar ----
    const r1 = new Relay(); const rp = await open(browser, r1);
    await rp.locator('#relayBar button').waitFor();
    assert.match(await rp.locator('#relayBar').innerText(), /relay kit is out of date \(this repo 0\.7\.10, latest 0\.9\.0\)[\s\S]*You are the upgrade owner/);
    await shot(rp, 'relay-bar');
    await rp.locator('#relayBar button', { hasText: 'Make the relay update card' }).click(); await rp.locator('#dlgCard[open]').waitFor();
    const made = r1.titles().filter(c => c.title.startsWith('Update the relay kit')); assert.equal(made.length, 1);
    assert.equal(made[0].title, 'Update the relay kit to 0.9.0'); assert.deepEqual(made[0].assignees, ['alex']);
    assert.deepEqual(made[0].todos.map(t => t.text), ['kit-update on a branch (python3 relay/scripts/relay.py kit-update)', 'Read the listed prompt and code changes', 'Checks pass', 'Open and link the PR']);
    assert.match(made[0].details, /relay\.py kit-update/);
    await rp.keyboard.press('Escape');
    assert.match(await rp.locator('#relayBar').innerText(), /Update card #10 is with @alex/);
    assert.equal(await rp.locator('#relayBar button', { hasText: 'Make the relay update card' }).count(), 0, 'once only');
    await rp.reload(); await rp.waitForSelector('.card'); await rp.locator('#relayBar button').waitFor();
    assert.match(await rp.locator('#relayBar').innerText(), /Update card #10/); assert.equal(r1.titles().filter(c => c.title.startsWith('Update the relay kit')).length, 1, 'a reload makes no second card');
    await rp.close();
    // another member only sees who the owner is
    const sp = await open(browser, new Relay(), { me: 'sam' }); await sp.locator('#relayBar').getByText('The upgrade owner is @alex').waitFor();
    assert.equal(await sp.locator('#relayBar button').count(), 0); await sp.close();
    // current kit, no relay/ in the repo: no bar
    for (const o of [{ have: '0.9.0\n' }, { have: null }, { have: '0.10.0\n' }]) {
      const a = new Relay(o); const p = await open(browser, a); await p.waitForTimeout(400);
      assert.equal(await p.locator('#relayBar').isVisible(), false, 'no bar for ' + JSON.stringify(o)); await p.close();
    }
    console.log('prs-panel.test.js: ok');
  } finally { await browser.close(); server.close(); }
})().catch(e => { console.error(e); process.exit(1); });

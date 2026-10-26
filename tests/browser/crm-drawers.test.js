'use strict';
// The person (#dlgContact), client (#dlgClient) and project (#dlgProject) drawers on a phone-width writable board with a
// faked GitHub API: edits save, removals and Delete ask in-page first, the layout never scrolls sideways at 390px, the
// header stays one row, no native dialog is used, and a read-only demo board locks all three. Kit v84: the Companies tab,
// the company record (stage, owner, domain, value, notes, people, activity, open tasks), company links and the pipeline's
// People | Companies toggle with drag-to-set-stage.
// Run: node crm-drawers.test.js   (SHOTS=<dir> also saves screenshots: 390px and 1280px, light and dark, writable and read-only)

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

const text = x => JSON.stringify(x, null, 2) + '\n';
const stamp = '2026-10-01T08:00:00.000Z';
const root = { version: 4, layout: 'split', settings: { title: 'CRM drawer test' }, columns: [{ id: 'todo', name: 'To do' }, { id: 'done', name: 'Done' }], people: [{ github: 'alex', name: 'Alex' }], agents: [], clients: ['Acme'], labels: [],
  client_info: { Acme: { north_star: '', links: [] } }, next_num: 2, archive: { files: {} } };
const project = { id: 'pr_one', client: 'Acme', name: 'Launch', north_star: '', status: 'active', links: [], people: [], created: stamp, updated: stamp };
const card = { id: 't_one', num: 1, title: 'Kick-off', column: 'todo', client: 'Acme', project: 'pr_one', priority: 'medium', due: '', labels: [], assignees: [], details: '', links: [], contacts: [], todos: [], comments: [], history: [], claim: null, created: stamp, updated: stamp, rank: 'a1' };
const person = { id: 'p_one', name: 'Casey Example', company: 'Acme', role: 'Buyer', stage: 'New', value: '', source: '', notes: '', next: '', next_due: '', emails: [{ id: 'e1', label: 'Work', value: 'casey@acme.test' }], phones: [], links: [], comments: [], history: [], created: stamp, updated: stamp };

// A small GitHub: contents API for reads and single-file writes, git data API for multi-file commits (as in task-drawer.test.js).
class Github {
  constructor() { this.files = { 'tasks.json': text(root), 'cards/t_one.json': text(card), 'people/p_one.json': text(person), 'projects/pr_one.json': text(project) }; this.head = 'head-1'; this.n = 1; this.blobs = {}; this.pending = null; }
  sha(p) { return crypto.createHash('sha1').update(this.files[p] || '').digest('hex'); }
  async route(route) {
    const req = route.request(), u = new URL(req.url()), method = req.method(), p = u.pathname.replace('/repos/acme/board', '');
    const json = (body, status = 200, headers = {}) => route.fulfill({ status, headers: { 'Content-Type': 'application/json', ...headers }, body: JSON.stringify(body) });
    if (p === '/user' && method === 'GET') return json({ login: 'alex' });
    if (p.startsWith('/user/repos')) return json([]);
    if (p === '' && method === 'GET') return json({ full_name: 'acme/board', private: true, permissions: { push: true }, default_branch: 'main' });
    if (p.startsWith('/contents/README.md')) return json({ message: 'Not Found' }, 404);
    if (p.startsWith('/contents/board/tasks.json') && method === 'GET') return json({ sha: this.sha('tasks.json'), size: Buffer.byteLength(this.files['tasks.json']), encoding: 'base64', content: Buffer.from(this.files['tasks.json']).toString('base64') });
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
  person() { return this.files['people/p_one.json'] ? JSON.parse(this.files['people/p_one.json']) : null; }
  root() { return JSON.parse(this.files['tasks.json']); }
  projects() { return [...(this.root().projects || []), ...Object.keys(this.files).filter(f => f.startsWith('projects/')).map(f => JSON.parse(this.files[f]))]; }   // split boards keep one file per project
  project(id = 'pr_one') { return this.projects().find(p => p.id === id) || null; }
}

let base;
const shot = async (page, name) => { if (SHOTS) { fs.mkdirSync(SHOTS, { recursive: true }); await page.waitForTimeout(250); await page.screenshot({ path: path.join(SHOTS, name + '.png') }); } };
// the page never scrolls sideways, the drawer body neither, and every header control sits inside the drawer on one row
async function assertFits(page, dlg, where) {
  const m = await page.evaluate(id => {
    const d = document.getElementById(id), r = d.getBoundingClientRect(), head = d.querySelector('.dhead'), body = d.querySelector('.dbody');
    const kids = [...head.children].filter(x => x.offsetParent !== null).map(x => { const b = x.getBoundingClientRect(); return { id: x.id || x.className, left: b.left, right: b.right, top: b.top, bottom: b.bottom }; });
    const hr = head.getBoundingClientRect();
    const wide = [...body.querySelectorAll('*')].filter(x => x.offsetParent !== null && x.getBoundingClientRect().right > r.right + 0.5).map(x => x.id || x.className).slice(0, 5);
    return { vw: window.innerWidth, docW: document.documentElement.scrollWidth, bodyScroll: body.scrollWidth - body.clientWidth, dRight: r.right, headH: hr.height, headTop: hr.top, kids, wide };
  }, dlg);
  assert(m.docW <= m.vw, `${where}: the page scrolls sideways (${m.docW} > ${m.vw})`);
  assert(m.bodyScroll <= 0, `${where}: the drawer body scrolls sideways by ${m.bodyScroll}px`);
  assert.deepEqual(m.wide, [], `${where}: these stick out of the drawer`);
  for (const k of m.kids) { assert(k.left >= 0 && k.right <= m.dRight + 0.5, `${where}: header item ${k.id} sticks out (${k.left}-${k.right})`); assert(k.top >= m.headTop - 0.5 && k.bottom <= m.headTop + m.headH + 0.5, `${where}: header item ${k.id} wraps to another line`); }
  assert(m.headH <= 64, `${where}: the header is one row (got ${m.headH}px)`);
}
const INIT = () => { localStorage.setItem('kb_repo', 'acme/board'); localStorage.setItem('kb_branch', 'main'); localStorage.setItem('kb_path', 'board/tasks.json'); localStorage.setItem('kb_token', 'test'); localStorage.setItem('kb_me', 'alex'); localStorage.setItem('kb_api', 'https://api.test'); localStorage.setItem('kb_layout', 'classic'); localStorage.setItem('kb_tour', 'done'); localStorage.setItem('kb_tour_seen', '1'); sessionStorage.setItem('kb_view', 'people'); };

(async () => {
  await new Promise(ok => server.listen(0, '127.0.0.1', ok)); base = `http://127.0.0.1:${server.address().port}`;
  const browser = await chromium.launch({ headless: true });
  try {
    // A real CLI write must be visible in the actual card drawer, and a plural-only web link in the person drawer.
    {
      const os = require('node:os'), cp = require('node:child_process');
      const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'keeptrack-contact-'));
      const local = path.join(dir, 'tasks.json'), linkedApi = new Github();
      try {
        fs.writeFileSync(local, text({ ...root, version: 3, tasks: [card], contacts: [person], projects: [project] }));
        cp.execFileSync('python3', [path.join(ROOT, 'board/kit/keeptrack.py'), '--file', local, 'task-set', '#1', '--contact', 'p_one'],
          { env: { ...process.env, BOARD_USER: 'alex', BOARD_AGENT: 'codex', BOARD_SESSION: 'test-contact' } });
        const linked = JSON.parse(fs.readFileSync(local)).tasks[0];
        linked.history.push({ at: stamp, by: 'codex', text: 'contact: p_one' });
        delete linked.contact; // prove the person drawer reads the web list without the legacy field
        linkedApi.files['cards/t_one.json'] = text(linked);
        linkedApi.files['people/p_one.json'] = text({ ...person, phones: [{ id: 'ph1', label: 'Work', value: '+440000000000' }] });
        const ctx = await browser.newContext({ viewport: { width: 390, height: 844 } });
        try {
          const pg = await ctx.newPage(); await pg.addInitScript(INIT); await pg.route('https://api.test/**', r => linkedApi.route(r));
          await pg.goto(base + '/board/index.html'); await pg.locator('.prow', { hasText: 'Casey Example' }).click();
          await pg.locator('#pTasks .dtask', { hasText: 'Kick-off' }).waitFor();
          await pg.locator('#pTasksSec .ui-addrow__ghost').click(); await pg.locator('#pTaskNew').fill('Plural contact snapshot');
          const saving = pg.waitForResponse(r => ['PUT', 'PATCH'].includes(r.request().method()) && r.url().includes('/repos/acme/board/'));
          await pg.locator('#pTaskNew').press('Enter'); await saving;
          const added = Object.entries(linkedApi.files).filter(([f]) => f.startsWith('cards/')).map(([,v]) => JSON.parse(v)).find(t => t.title === 'Plural contact snapshot');
          assert.equal(added.contacts[0].email, 'casey@acme.test');
          assert.equal(added.contacts[0].phone, '+440000000000');

          // kit v110: with settings.card_contact_details false the person drawer's Add task keeps email and phone off the card
          const rootNow = JSON.parse(linkedApi.files['tasks.json']);
          linkedApi.files['tasks.json'] = text({ ...rootNow, settings: { ...rootNow.settings, card_contact_details: false, min_kit: 110 } });
          linkedApi.head = 'head-' + ++linkedApi.n;
          await pg.reload(); await pg.locator('.prow', { hasText: 'Casey Example' }).waitFor(); if (!await pg.locator('#dlgContact[open]').count()) await pg.locator('.prow', { hasText: 'Casey Example' }).click();
          await pg.locator('#pTasks .dtask', { hasText: 'Kick-off' }).waitFor();
          await pg.locator('#pTasksSec .ui-addrow__ghost').click(); await pg.locator('#pTaskNew').fill('No contact details');
          const savingOff = pg.waitForResponse(r => ['PUT', 'PATCH'].includes(r.request().method()) && r.url().includes('/repos/acme/board/'));
          await pg.locator('#pTaskNew').press('Enter'); await savingOff;
          const bare = Object.entries(linkedApi.files).filter(([f]) => f.startsWith('cards/')).map(([,v]) => JSON.parse(v)).find(t => t.title === 'No contact details');
          assert.deepEqual(bare.contacts, [{ person_id: 'p_one', name: 'Casey Example', role: bare.contacts[0].role }], 'id, name and role only');
          linkedApi.files['tasks.json'] = text(rootNow); linkedApi.head = 'head-' + ++linkedApi.n;
          await pg.reload(); await pg.locator('.prow', { hasText: 'Casey Example' }).waitFor(); if (!await pg.locator('#dlgContact[open]').count()) await pg.locator('.prow', { hasText: 'Casey Example' }).click();

          await pg.locator('#pTasks .dtask', { hasText: 'Kick-off' }).click(); await pg.locator('#dlgCard[open]').waitFor();
          assert.match(await pg.locator('#cContactList').textContent(), /Casey Example/);
          const toggle = pg.locator('#cmHistBtn');
          if (await toggle.getAttribute('aria-pressed') !== 'true') await toggle.click();
          await pg.locator('.cmhist', { hasText: 'contact: Casey Example' }).waitFor();
          assert.doesNotMatch(await pg.locator('#cmStream').textContent(), /contact: p_one/);
        } finally { await ctx.close(); }
      } finally { fs.rmSync(dir, { recursive: true, force: true }); }
    }
    // Same display details must not let removing the second linked person remove the first.
    {
      const api = new Github(), a = { ...person, email: 'team@acme.test', phone: '', emails: [{ value: 'team@acme.test', label: 'Shared' }], phones: [] };
      const b = { ...a, id: 'p_two' }, snapshot = p => ({ person_id: p.id, name: p.name, role: p.role, email: 'team@acme.test', phone: '' });
      api.files['people/p_one.json'] = text(a); api.files['people/p_two.json'] = text(b);
      api.files['cards/t_one.json'] = text({ ...card, contact: b.id, contacts: [snapshot(a), snapshot(b)] });
      const ctx = await browser.newContext({ viewport: { width: 390, height: 844 } });
      try {
        const pg = await ctx.newPage(); await pg.addInitScript(INIT); await pg.route('https://api.test/**', r => api.route(r));
        await pg.goto(base + '/board/index.html?repo=acme%2Fboard&card=t_one#1'); await pg.locator('#dlgCard[open]').waitFor();
        const remove = pg.locator('#cContactList button[aria-label="Remove contact Casey Example"]');
        assert.equal(await remove.count(), 2);
        await remove.nth(1).click();
        const saving = pg.waitForResponse(r => r.request().method() === 'PUT' && r.url().includes('/contents/board/'));
        await pg.locator('dialog.ui-sheet--alert[open] button', { hasText: 'Remove' }).click(); await saving;
        const saved = JSON.parse(api.files['cards/t_one.json']);
        assert.deepEqual(saved.contacts.map(k => k.person_id), ['p_one']);
        assert.equal(saved.contact, undefined);
        assert.equal(await pg.locator('#cContactList button[aria-label="Remove contact Casey Example"]').count(), 1);
        await pg.locator('#cContactSec .ui-addrow__ghost').click(); await pg.locator('#cContactNew').fill('Casey');
        const suggestion = pg.locator('#cContactSuggestions [role="option"]');
        await suggestion.waitFor(); assert.equal(await suggestion.count(), 1, 'the other shared-mailbox person remains available');
        const adding = pg.waitForResponse(r => r.request().method() === 'PUT' && r.url().includes('/contents/board/'));
        await suggestion.click(); await adding;
        assert.deepEqual(JSON.parse(api.files['cards/t_one.json']).contacts.map(k => k.person_id), ['p_one', 'p_two']);

      } finally { await ctx.close(); }
    }
    const api = new Github();
    const page = await browser.newPage({ viewport: { width: 390, height: 844 } }); const errors = [], native = [];
    page.on('pageerror', e => errors.push(e.message)); page.on('dialog', d => { native.push(d.type() + ': ' + d.message()); d.dismiss().catch(() => {}); });
    await page.addInitScript(INIT); await page.route('https://api.test/**', r => api.route(r)); await page.goto(base + '/board/index.html'); await page.waitForSelector('.prow');
    await page.evaluate(() => { window.__copied = ''; Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText: async t => { window.__copied = t; } } }); });
    const saved = () => page.waitForResponse(r => ['PUT', 'PATCH', 'DELETE'].includes(r.request().method()) && r.url().startsWith('https://api.test/repos/acme/board/'));
    const confirmSheet = page.locator('dialog.ui-sheet--alert[open]'), menu = page.locator('.ui-menu');
    const tomorrow = await page.evaluate(() => { const d = new Date(); d.setDate(d.getDate() + 1); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`; });

    // ---- person drawer: header, properties, sections ----
    await page.locator('.prow', { hasText: 'Casey Example' }).click(); await page.locator('#dlgContact[open]').waitFor();
    assert.equal(await page.locator('#pName').inputValue(), 'Casey Example');
    assert.equal(await page.locator('#pAvatar').textContent(), 'CE');
    assert.deepEqual(await page.locator('#pHead button').evaluateAll(xs => xs.map(x => x.getAttribute('aria-label'))), ['Undo last board change', 'Copy for AI', 'More actions', 'Close']);
    assert.deepEqual(await page.locator('#pProps .ui-props__label').allTextContents(), ['Stage', 'Next step', 'Next date', 'Client', 'Role', 'Value', 'Source', 'GitHub']);
    assert.deepEqual(await page.locator('#pBody .ui-section__text:visible').allTextContents(), ['Emails', 'Phones', 'Contact log', 'Notes', 'Tasks', 'Links', 'Client north star', 'Projects', 'Files and folders for Acme', 'History']);
    for (const sec of ['#pPhoneSec', '#pLinkSec', '#pFilesSec', '#pTasksSec']) { assert.equal(await page.locator(`${sec} .ui-addrow__ghost`).isVisible(), true, `${sec}: an empty section is one ghost add row`); assert.equal(await page.locator(`${sec} .ui-addrow__form`).isVisible(), false); }
    assert.equal(await page.locator('#pHist').isVisible(), false, 'History starts closed');
    await assertFits(page, 'dlgContact', 'person opened'); await shot(page, 'person-phone-light-writable');

    // stage, next step and its date
    let w = saved(); await page.locator('#pStage').selectOption('Contacted'); await w; assert.equal(api.person().stage, 'Contacted');
    await page.locator('#pNext').fill('Call Casey'); w = saved(); await page.locator('#pNext').press('Tab'); await w; assert.equal(api.person().next, 'Call Casey');
    w = saved(); await page.locator('#dlgContact .dquick', { hasText: 'Tomorrow' }).click(); await w; assert.equal(api.person().next_due, tomorrow);
    assert.equal(await page.locator('#pNextDue').inputValue(), tomorrow); assert.equal(await page.locator('#pNextDueClear').isVisible(), true);
    assert.equal(await page.locator('#pNextDueBtn').innerText(), 'Tomorrow', 'the date pill reads like the rest of the board');
    w = saved(); await page.locator('#pNextDueClear').click(); await w; assert.equal(api.person().next_due, '');
    assert.equal(await page.locator('#pNextDueBtn').innerText(), 'No date');
    await page.locator('#pRole').fill('Head buyer'); w = saved(); await page.locator('#pRole').press('Tab'); await w; assert.equal(api.person().role, 'Head buyer');

    // emails: add with label and address, then remove (asks first; Cancel keeps it)
    await page.locator('#pEmailSec .ui-addrow__ghost').click(); await page.locator('#pEmailLabel').fill('Home'); await page.locator('#pEmailNew').fill('casey@home.test');
    w = saved(); await page.locator('#pEmailAdd').click(); await w;
    assert.deepEqual(api.person().emails.map(x => [x.label, x.value]), [['Work', 'casey@acme.test'], ['Home', 'casey@home.test']]);
    await page.locator('#pEmails .methodvalue >> nth=1').waitFor(); assert.equal(await page.locator('#pEmailCount').textContent(), '2');
    await page.locator('#pEmails [aria-label="Remove email"]').nth(1).click(); await confirmSheet.waitFor(); assert.match(await confirmSheet.textContent(), /Remove the Home email “casey@home\.test”\?/);
    await confirmSheet.locator('button', { hasText: 'Cancel' }).click(); await confirmSheet.waitFor({ state: 'detached' }); assert.equal(api.person().emails.length, 2);
    await page.locator('#pEmails [aria-label="Remove email"]').nth(1).click(); w = saved(); await confirmSheet.locator('button', { hasText: 'Remove' }).click(); await w;
    assert.deepEqual(api.person().emails.map(x => x.value), ['casey@acme.test']);
    await page.locator('#pEmailNew').fill('not an email'); await page.locator('#pEmailAdd').click(); await page.waitForTimeout(200);
    assert.equal(await page.locator('#pEmailNew').inputValue(), 'not an email', 'an invalid address stays in the box'); assert.equal(api.person().emails.length, 1);
    await page.locator('#pEmailNew').press('Escape'); assert.equal(await page.locator('#dlgContact').getAttribute('open'), '', 'Escape in an add row only closes the row');
    assert.equal(await page.locator('#pEmailSec .ui-addrow__ghost').isVisible(), true);

    // links: add (label + address), then remove
    await page.locator('#pLinkSec .ui-addrow__ghost').click(); await page.locator('#pLinkTitle').fill('Blog'); await page.locator('#pLinkNew').fill('https://casey.example/blog');
    w = saved(); await page.locator('#pLinkNew').press('Enter'); await w; assert.deepEqual(api.person().links, [{ title: 'Blog', url: 'https://casey.example/blog' }]);
    assert.equal(await page.locator('#pLinks a.ui-listrow__main').getAttribute('href'), 'https://casey.example/blog');
    await page.locator('#pLinks [aria-label="Remove link Blog"]').click(); w = saved(); await confirmSheet.locator('button', { hasText: 'Remove' }).click(); await w; assert.deepEqual(api.person().links, []);

    // contact log: an email touch
    await page.locator('#pTouchText').fill('Sent the intro deck'); await page.locator('#pChan').selectOption('email');
    w = saved(); await page.locator('#pTouchPost').click(); await w;
    const touch = api.person().comments.at(-1); assert.deepEqual([touch.channel, touch.text, touch.draft], ['email', 'Sent the intro deck', false]);
    await page.locator('#pTouches .cmcard').waitFor(); assert.equal(await page.locator('#pTouchCount').textContent(), '1');
    // a draft shows Mark sent and Copy
    await page.locator('#pTouchText').fill('Draft follow-up'); await page.locator('#pDraft').check(); w = saved(); await page.locator('#pTouchPost').click(); await w;
    assert.equal(api.person().comments.at(-1).draft, true); await page.locator('#pTouches .cmcard.draft').waitFor();
    await page.locator('#pTouches .cmcard.draft button', { hasText: 'Copy' }).click(); await page.waitForFunction(() => window.__copied === 'Draft follow-up');

    // notes and a task for this person
    await page.locator('#pNotes').fill('Prefers email.'); w = saved(); await page.locator('#pNotes').blur(); await w; assert.equal(api.person().notes, 'Prefers email.');
    await page.locator('#pTasksSec .ui-addrow__ghost').click(); await page.locator('#pTaskNew').fill('Send pricing'); w = saved(); await page.locator('#pTaskNew').press('Enter'); await w;
    await page.locator('#pTasks .dtask').waitFor();
    const newCard = Object.keys(api.files).filter(f => f.startsWith('cards/')).map(f => JSON.parse(api.files[f])).find(t => t.title === 'Send pricing');
    assert.ok(newCard && newCard.contact === 'p_one' && newCard.client === 'Acme', 'the task is linked to the person and their client');
    assert.equal(newCard.contacts[0].person_id, 'p_one', 'a task added from a person is also linked in the card Contacts section');
    assert.equal(newCard.contacts[0].email, api.person().emails[0].value, 'plural CRM emails survive into the card snapshot');
    assert.equal(newCard.contacts[0].phone, (api.person().phones[0] || {}).value || '', 'plural CRM phones survive into the card snapshot');

    // History opens; the drawer still fits after all that
    await page.locator('#pHistSec .ui-section__toggle').click(); assert.equal(await page.locator('#pHist').isVisible(), true);
    assert.ok((await page.locator('#pHist li').count()) > 1);
    await assertFits(page, 'dlgContact', 'person after edits');
    await page.locator('#pBody').evaluate(b => { b.scrollTop = 0; }); await shot(page, 'person-phone-light-writable-filled');
    if (SHOTS) {
      await page.emulateMedia({ colorScheme: 'dark' }); await shot(page, 'person-phone-dark-writable');
      await page.locator('#pBody').evaluate(b => { b.scrollTop = b.scrollHeight / 2; }); await shot(page, 'person-phone-dark-writable-middle');
      await page.setViewportSize({ width: 1280, height: 860 }); await page.locator('#pBody').evaluate(b => { b.scrollTop = 0; }); await shot(page, 'person-desktop-dark-writable');
      await page.emulateMedia({ colorScheme: 'light' }); await shot(page, 'person-desktop-light-writable');
      await page.setViewportSize({ width: 390, height: 844 });
    }

    // the ⋯ menu: copy for AI, open the client
    await page.locator('#pMore').click();
    assert.deepEqual(await menu.locator('[role=menuitem]').allTextContents(), ['Copy for AI', 'Copy link', 'Open client Acme', 'Delete person']);
    await shot(page, 'person-phone-light-menu');
    await menu.locator('[role=menuitem]', { hasText: 'Copy for AI' }).click(); await page.waitForFunction(() => /Help me with my contact Casey Example/.test(window.__copied));
    await page.locator('#pMore').click(); await menu.locator('[role=menuitem]', { hasText: 'Open client Acme' }).click();

    // ---- client drawer ----
    await page.locator('#dlgClient[open]').waitFor(); assert.equal(await page.locator('#dlgContact').getAttribute('open'), null);
    assert.equal(await page.locator('#clName').textContent(), 'Acme');
    assert.deepEqual(await page.locator('#clHead button').evaluateAll(xs => xs.map(x => x.getAttribute('aria-label'))), ['More actions', 'Close']);
    assert.deepEqual(await page.locator('#clBody .ui-props__label').allTextContents(), ['Stage', 'Owner', 'Domain', 'Value']);
    assert.deepEqual(await page.locator('#clPeople .ui-listrow__text').allTextContents(), ['Casey Example']);
    assert.deepEqual(await page.locator('#clBody .ui-section__text').allTextContents(), ['Notes', 'People', 'Activity', 'Open tasks', 'North star', 'Projects', 'Files and folders']);
    assert.equal(await page.locator('#clHead .didentity__kind').textContent(), 'Company');
    await page.locator('#clNorth').fill('Win the Acme rollout'); w = saved(); await page.locator('#clNorth').blur(); await w; assert.equal(api.root().client_info.Acme.north_star, 'Win the Acme rollout');
    await page.locator('#clFilesSec .ui-addrow__ghost').click(); await page.locator('#clFileTitle').fill('Client Drive'); await page.locator('#clFileNew').fill('https://drive.google.com/drive/folders/acme');
    w = saved(); await page.locator('#clFileAdd').click(); await w; assert.deepEqual(api.root().client_info.Acme.links, [{ title: 'Client Drive', url: 'https://drive.google.com/drive/folders/acme' }]);
    await page.locator('#clFiles .ui-listrow').waitFor(); assert.match(await page.locator('#clFiles').textContent(), /Client Drive.*drive\.google\.com/);
    await page.locator('#clFileTitle').fill('Local folder'); await page.locator('#clFileNew').fill('/srv/clients/acme'); w = saved(); await page.locator('#clFileAdd').click(); await w;
    await page.locator('#clFiles [aria-label="Copy local path"]').click(); await page.waitForFunction(() => window.__copied === '/srv/clients/acme');
    await page.locator('#clFiles [aria-label="Remove link Local folder"]').click(); w = saved(); await confirmSheet.locator('button', { hasText: 'Remove' }).click(); await w;
    assert.deepEqual(api.root().client_info.Acme.links.map(l => l.title), ['Client Drive']);
    await assertFits(page, 'dlgClient', 'client'); await shot(page, 'client-phone-light-writable');
    if (SHOTS) { await page.emulateMedia({ colorScheme: 'dark' }); await shot(page, 'client-phone-dark-writable'); await page.setViewportSize({ width: 1280, height: 860 }); await shot(page, 'client-desktop-dark-writable'); await page.emulateMedia({ colorScheme: 'light' }); await shot(page, 'client-desktop-light-writable'); await page.setViewportSize({ width: 390, height: 844 }); }
    await page.locator('#clMore').click(); assert.deepEqual(await menu.locator('[role=menuitem]').allTextContents(), ['Show only this company', 'Copy company name', 'Copy link']); await page.keyboard.press('Escape');
    // a new project opens in its own drawer
    await page.locator('#clProjSec .ui-addrow__ghost').click(); await page.locator('#clProjName').fill('Phase two'); w = saved(); await page.locator('#clProjAdd').click(); await w;
    await page.locator('#dlgProject[open]').waitFor(); assert.equal(await page.locator('#prName').inputValue(), 'Phase two');
    assert.ok(api.projects().some(p => p.name === 'Phase two' && p.client === 'Acme'));
    await page.locator('#prClose').click(); await page.locator('#dlgProject').waitFor({ state: 'hidden' });
    await page.locator('#clProjects .dnav', { hasText: 'Launch' }).click();

    // ---- project drawer ----
    await page.locator('#dlgProject[open]').waitFor(); assert.equal(await page.locator('#prName').inputValue(), 'Launch'); assert.equal(await page.locator('#dlgClient').getAttribute('open'), null);
    assert.deepEqual(await page.locator('#prHead button').evaluateAll(xs => xs.map(x => x.getAttribute('aria-label'))), ['More actions', 'Close']);
    assert.deepEqual(await page.locator('#prBody .ui-props__label').allTextContents(), ['Status', 'Client', 'Tasks']);
    assert.equal(await page.locator('#prTaskSum').textContent(), '1 open · 0 done');
    assert.deepEqual(await page.locator('#prTasks .ui-task__title').allTextContents(), ['Kick-off']);
    w = saved(); await page.locator('#prStatus').selectOption('paused'); await w; assert.equal(api.project().status, 'paused');
    assert.match(await page.locator('#prStatus').evaluate(x => x.parentElement.className), /ui-select--warn/);
    await page.locator('#prName').fill('Launch v2'); w = saved(); await page.locator('#prName').press('Enter'); await w; assert.equal(api.project().name, 'Launch v2');
    await page.locator('#prNorth').fill('Ship by spring'); w = saved(); await page.locator('#prNorth').blur(); await w; assert.equal(api.project().north_star, 'Ship by spring');
    // people: a suggestion from the client's people, then remove it (asks first)
    w = saved(); await page.locator('#prSuggest .ui-pill', { hasText: 'Casey Example' }).click(); await w; assert.deepEqual(api.project().people, ['casey@acme.test']);
    await page.locator('#prPeople .ui-listrow').waitFor(); assert.match(await page.locator('#prPeople').textContent(), /Casey Example.*casey@acme\.test/);
    await page.locator('#prPeople [aria-label="Remove Casey Example from the project"]').click(); w = saved(); await confirmSheet.locator('button', { hasText: 'Remove' }).click(); await w; assert.deepEqual(api.project().people, []);
    await page.locator('#prPeopleSec .ui-addrow__ghost').click(); await page.locator('#prPersonEmail').fill('sam@acme.test'); w = saved(); await page.locator('#prPersonAdd').click(); await w; assert.deepEqual(api.project().people, ['sam@acme.test']);
    await page.locator('#prLinkSec .ui-addrow__ghost').click(); await page.locator('#prLinkTitle').fill('Plan'); await page.locator('#prLinkNew').fill('https://example.com/plan'); w = saved(); await page.locator('#prLinkNew').press('Enter'); await w;
    assert.deepEqual(api.project().links, [{ title: 'Plan', url: 'https://example.com/plan' }]);
    // tick the task done from the drawer: it moves to Completed
    w = saved(); await page.locator('#prTasks .dtask .ui-iconbtn').click(); await w; assert.equal(JSON.parse(api.files['cards/t_one.json']).column, 'done');
    await page.locator('#prDoneSec .ui-section__toggle').click(); await page.locator('#prDoneTasks .dtask.is-done').waitFor();
    await assertFits(page, 'dlgProject', 'project'); await page.locator('#prBody').evaluate(b => { b.scrollTop = 0; }); await shot(page, 'project-phone-light-writable');
    if (SHOTS) { await page.emulateMedia({ colorScheme: 'dark' }); await shot(page, 'project-phone-dark-writable'); await page.setViewportSize({ width: 1280, height: 860 }); await shot(page, 'project-desktop-dark-writable'); await page.emulateMedia({ colorScheme: 'light' }); await shot(page, 'project-desktop-light-writable'); await page.setViewportSize({ width: 390, height: 844 }); }
    // delete via ⋯: Cancel keeps it, Remove deletes it and clears it from its task
    assert.equal(await page.locator('#prViewTasks').isVisible(), false, 'View on board hides when every linked task is done');
    // reopen the task so View on board can filter to it
    w = saved(); await page.locator('#prDoneTasks .dtask .ui-iconbtn').click(); await w;
    assert.equal(await page.locator('#prViewTasks').isVisible(), true);
    await page.locator('#prMore').click(); assert.deepEqual(await menu.locator('[role=menuitem]').allTextContents(), ['Show only this project', 'Open client Acme', 'Copy project name', 'Copy link', 'Delete project']);
    await page.keyboard.press('Escape');
    await page.locator('#prViewTasks').click();
    await page.locator('#dlgProject').waitFor({ state: 'hidden' });
    assert.equal(await page.evaluate(() => document.getElementById('fProject').value), 'pr_one');
    assert.deepEqual(await page.locator('#fClient').evaluate(s => [...s.selectedOptions].map(o => o.value)), ['Acme']);
    assert.equal(await page.locator('#fStatus').inputValue(), '__open');
    assert.equal(await page.locator('#projectBar').count(), 0, 'projects stay in the company control');
    assert.match(await page.locator('.cpill.projtok').textContent(), /Launch v2/);
    // back to People without fighting the board history entry View on board pushed
    await page.evaluate(() => { document.getElementById('fClear').click(); });
    await page.locator('#viewSw [role=tab]', { hasText: 'People' }).click();
    await page.waitForFunction(() => document.body.dataset.view === 'people');
    await page.evaluate(() => { location.hash = 'project=pr_one'; });
    await page.locator('#dlgProject[open]').waitFor();
    // delete via ⋯: Cancel keeps it, Remove deletes it and clears it from its task
    await page.locator('#prMore').click(); await menu.locator('[role=menuitem]', { hasText: 'Delete project' }).click(); await confirmSheet.waitFor(); assert.match(await confirmSheet.textContent(), /Remove project "Launch v2" and clear it from 1 task/);
    await confirmSheet.locator('button', { hasText: 'Cancel' }).click(); await confirmSheet.waitFor({ state: 'detached' }); assert.ok(api.project(), 'Cancel keeps the project');
    await page.locator('#prMore').click(); await menu.locator('[role=menuitem]', { hasText: 'Delete project' }).click(); await confirmSheet.waitFor();
    w = saved(); await confirmSheet.locator('button.ui-btn--danger').click(); await w; await page.locator('#dlgProject').waitFor({ state: 'hidden' });
    for (let i = 0; i < 50 && api.project(); i++) await page.waitForTimeout(100);
    assert.equal(api.project(), null, 'the project is gone'); assert.equal(JSON.parse(api.files['cards/t_one.json']).project, '', 'its task no longer points at it');

    // ---- delete the person via ⋯ ----
    await page.locator('.prow', { hasText: 'Casey Example' }).click(); await page.locator('#dlgContact[open]').waitFor();
    assert.equal(await page.locator('#pEmailSec .ui-addrow__form').isVisible(), false, 'add rows start closed on every open');
    await page.locator('#pMore').click(); await menu.locator('[role=menuitem]', { hasText: 'Delete person' }).click(); await confirmSheet.waitFor();
    assert.match(await confirmSheet.textContent(), /Delete person\?.*Delete the person “Casey Example”\?/s);
    await confirmSheet.locator('button', { hasText: 'Cancel' }).click(); await confirmSheet.waitFor({ state: 'detached' }); assert.ok(api.person(), 'Cancel keeps the person');
    await page.locator('#pMore').click(); await menu.locator('[role=menuitem]', { hasText: 'Delete person' }).click(); await confirmSheet.waitFor();
    w = saved(); await confirmSheet.locator('button.ui-btn--danger').click(); await w; await page.locator('#dlgContact').waitFor({ state: 'hidden' });
    for (let i = 0; i < 50 && api.person(); i++) await page.waitForTimeout(100);
    assert.equal(api.person(), null, 'the person file is gone');

    // ---- the add-person form ----
    await page.locator('.padd button').click(); await page.locator('#dlgAddPerson[open]').waitFor();
    assert.deepEqual(await page.locator('#dlgAddPerson .ui-props__label').allTextContents(), ['Client', 'Role', 'Email', 'Phone', 'LinkedIn', 'GitHub']);
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    await shot(page, 'addperson-phone-light');
    await page.locator('#apName').fill('Robin Doe'); await page.locator('#apCompany').fill('Acme'); await page.locator('#apEmail').fill('robin@acme.test');
    w = page.waitForResponse(r => r.request().method() === 'PUT' && /\/contents\/board\/people\//.test(r.url())); await page.locator('#apSave').click(); await w;
    await page.locator('#dlgContact[open]').waitFor(); assert.equal(await page.locator('#pName').inputValue(), 'Robin Doe');
    assert.deepEqual(await page.locator('#pEmails .methodvalue').evaluateAll(xs => xs.map(x => x.value)), ['robin@acme.test']);
    await page.keyboard.press('Escape'); await page.locator('#dlgContact').waitFor({ state: 'hidden' });

    assert.deepEqual(native, [], 'no native dialogs');
    assert.deepEqual(errors, [], 'no page errors');
    await page.close();

    // ---- a board member's own person record (v33): "You", never a follow-up, not in the pipeline, no contact help ----
    {
      const api2 = new Github(); api2.files['people/p_me.json'] = text({ ...person, id: 'p_me', name: 'Alex Member', company: 'Rain', role: '', github: 'ALEX', emails: [], next_due: '2020-01-01' });
      const pg = await browser.newPage({ viewport: { width: 1280, height: 860 } }); const errs = []; pg.on('pageerror', e => errs.push(e.message));
      await pg.addInitScript(INIT); await pg.route('https://api.test/**', r => api2.route(r)); await pg.goto(base + '/board/index.html'); await pg.waitForSelector('.prow');
      assert.deepEqual(await pg.locator('.prow b').allTextContents(), ['Alex Member', 'Casey Example'], 'you come first in People');
      assert.equal(await pg.locator('.prow', { hasText: 'Alex Member' }).locator('.memberpill').textContent(), 'You');
      await pg.evaluate(() => { window.__copied = ''; Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText: async t => { window.__copied = t; } } }); });
      await pg.locator('.prow', { hasText: 'Alex Member' }).click(); await pg.locator('#dlgContact[open]').waitFor();
      assert.match(await pg.locator('#pMember').textContent(), /This is you \(@alex\)/);
      await pg.locator('#pAgent').click(); await pg.waitForFunction(() => window.__copied);
      const prompt = await pg.evaluate(() => window.__copied); assert.match(prompt, /is me .*not a contact/); assert.doesNotMatch(prompt, /Help me with my contact/);
      await pg.keyboard.press('Escape'); await pg.locator('#dlgContact').waitFor({ state: 'hidden' });
      for (const v of ['today', 'pipeline']) { await pg.locator(`#viewSw button[data-view="${v}"]`).click(); await pg.waitForTimeout(300);
        assert.equal(await pg.locator('#board', { hasText: 'Casey Example' }).count(), 1, `${v} shows contacts`);
        assert.equal(await pg.locator('#board', { hasText: 'Alex Member' }).count(), 0, `a member is not in ${v}`); }
      assert.deepEqual(errs, []); await pg.close();
      // v34: a second person with the member's login hides neither: both stay contacts, no "You" pill
      const api3 = new Github(); api3.files['people/p_me.json'] = text({ ...person, id: 'p_me', name: 'Alex Member', github: 'alex' }); api3.files['people/p_one.json'] = text({ ...person, github: 'alex' });
      const p3 = await browser.newPage({ viewport: { width: 1280, height: 860 } }), errs3 = []; p3.on('pageerror', e => errs3.push(e.message)); await p3.addInitScript(INIT); await p3.route('https://api.test/**', r => api3.route(r));
      await p3.goto(base + '/board/index.html'); await p3.waitForSelector('.prow');
      assert.equal(await p3.locator('.memberpill').count(), 0, 'a duplicated member login marks nobody as the member');
      const peopleFiles = () => Object.keys(api3.files).filter(f => f.startsWith('people/')).length; const before = peopleFiles();
      assert.equal(await p3.locator('#memberBar').isVisible().catch(() => false) && /no person record/.test(await p3.locator('#memberBar').textContent()), false, 'no "add yourself" offer when your login is on people already');
      for (const v of ['today', 'pipeline']) { await p3.locator(`#viewSw button[data-view="${v}"]`).click(); await p3.waitForTimeout(300);
        for (const who of ['Casey Example', 'Alex Member']) assert.equal(await p3.locator('#board', { hasText: who }).count(), 1, `${who} stays a contact in ${v}`); }
      assert.equal(peopleFiles(), before, 'loading never adds another copy of your record'); assert.deepEqual(errs3, []); await p3.close();
    }

    // ---- kit v84: the Companies tab, the company record, links to it, and the pipeline's People | Companies toggle ----
    {
      const api4 = new Github(), day = n => { const d = new Date(Date.now() - n * 864e5); return d.toISOString(); };
      const touches = Array.from({ length: 12 }, (_, i) => ({ id: 'c' + i, at: day(20 - i), by: 'alex', channel: i % 2 ? 'email' : 'call', text: 'Touch ' + i, draft: false }));
      api4.files['people/p_one.json'] = text({ ...person, value: '1000', next: 'Send the deck', next_due: '2030-01-09', comments: [{ id: 'cx', at: day(1), by: 'alex', channel: 'linkedin', text: 'Newest note to Casey', draft: false }] });
      api4.files['people/p_two.json'] = text({ ...person, id: 'p_two', name: 'Robin Talker', role: 'CFO', stage: 'Talking', value: '5,000', next: 'Book a call', next_due: '2030-01-05', emails: [], comments: touches });
      api4.files['people/p_three.json'] = text({ ...person, id: 'p_three', name: 'Jo Beta', company: 'Beta Ltd', stage: 'New', emails: [], next: '', next_due: '' });
      api4.files['cards/t_two.json'] = text({ ...card, id: 't_two', num: 2, title: 'Old work', column: 'done', rank: 'a2' });
      // a client with only a task and no record is a task bucket: hidden from Companies, still a client; one with a record shows
      { const r = JSON.parse(api4.files['tasks.json']); r.clients = ['Acme', 'Empty Co', 'Recorded Co', 'Consult Co']; r.client_info['Recorded Co'] = { notes: 'Met at a fair', links: [] };
        r.client_info['Beta Ltd'] = { stage: 'Gone', links: [] }; api4.files['tasks.json'] = text(r); }   // a stage the board no longer has
      api4.files['projects/pr_consult.json'] = text({ ...project, id: 'pr_consult', client: 'Consult Co', name: 'Discovery' });   // a client with only a project is a real client
      api4.files['cards/t_three.json'] = text({ ...card, id: 't_three', num: 3, title: 'Bucket task', client: 'Empty Co', project: '', rank: 'a3' });
      const pg = await browser.newPage({ viewport: { width: 1280, height: 860 } }), errs = [], nat = []; pg.on('pageerror', e => errs.push(e.message)); pg.on('dialog', d => { nat.push(d.message()); d.dismiss().catch(() => {}); });
      await pg.addInitScript(INIT); await pg.route('https://api.test/**', r => api4.route(r)); await pg.goto(base + '/board/index.html'); await pg.waitForSelector('.prow');
      const save = () => pg.waitForResponse(r => ['PUT', 'PATCH', 'DELETE'].includes(r.request().method()) && r.url().startsWith('https://api.test/repos/acme/board/'));
      const info = () => (api4.root().client_info || {}).Acme || {};
      // the tab sits between People and Pipeline
      assert.deepEqual(await pg.locator('#viewSw .viewgroup[data-grp="crm"] [role="tab"]').evaluateAll(xs => xs.map(x => x.dataset.view)), ['people', 'companies', 'pipeline']);
      await pg.locator('#viewSw [data-view="companies"]').click(); await pg.waitForSelector('.crow');
      // every client name and every person's company, deduplicated; sorted by stage order (New before Talking)
      assert.deepEqual(await pg.locator('.crow .pwho b').allTextContents(), ['Beta Ltd', 'Acme', 'Consult Co', 'Recorded Co'], 'Empty Co (no people, no record, no files, no projects) is left out');
      assert.equal(await pg.locator('#fClient option[value="Empty Co"]').count(), 1, 'it stays a client for tasks and the top chips');
      assert.equal(await pg.locator('.crow[data-company="Recorded Co"] .pnext').textContent(), 'No people yet');
      assert.equal(await pg.locator('.crow[data-company="Beta Ltd"] .stagepill.derived').textContent(), 'New', 'a stored stage the board no longer has counts as unset');
      const acme = pg.locator('.crow[data-company="Acme"]');
      assert.equal(await acme.locator('.pwho .muted').textContent(), '2 people · 1 open task');
      assert.equal(await acme.locator('.stagepill').textContent(), 'Talking', 'until set, the most advanced stage among its people');
      assert.match(await acme.locator('.stagepill').getAttribute('class'), /\bderived\b/);
      assert.match(await acme.locator('.pnext').textContent(), /Book a call.*Robin Talker/, 'the earliest next step among its people, with whose it is');
      assert.match(await acme.locator('.plast').textContent(), /last contact 1d ago/);
      assert.equal(await pg.locator('.crow[data-company="Beta Ltd"] .pnext').textContent(), 'No next step');
      await pg.locator('.psearch').fill('robin'); await pg.waitForFunction(() => document.querySelectorAll('.crow').length === 1);
      assert.deepEqual(await pg.locator('.crow .pwho b').allTextContents(), ['Acme'], 'search reaches its people');
      await pg.locator('.psearch').fill(''); await pg.locator('.companiesv .pillsel[aria-label="Filter by stage"]').selectOption('New'); await pg.waitForFunction(() => document.querySelectorAll('.crow').length === 1);
      assert.deepEqual(await pg.locator('.crow .pwho b').allTextContents(), ['Beta Ltd'], 'the stage filter');
      await pg.locator('.companiesv .pillsel[aria-label="Filter by stage"]').selectOption(''); await pg.waitForFunction(() => document.querySelectorAll('.crow').length === 4);
      await shot(pg, 'companies-desktop-light');
      // ---- the company record ----
      await acme.locator('.pwho b').click(); await pg.locator('#dlgClient[open]').waitFor();
      assert.equal(await pg.locator('#clStage').inputValue(), '', 'no stage of its own yet');
      assert.equal(await pg.locator('#clStage option:checked').textContent(), 'Talking (from its people)');
      assert.equal(await pg.locator('#clValue').textContent(), '6,000', 'value: the sum of its people\'s values');
      assert.deepEqual(await pg.locator('#clPeople .dperson .ui-listrow__text').allTextContents(), ['Robin Talker', 'Casey Example'], 'most advanced first');
      assert.match(await pg.locator('#clPeople .dperson').first().textContent(), /CFO · last contact \d+d ago.*Talking/);
      assert.equal(await pg.locator('#clActCount').textContent(), '13');
      assert.equal(await pg.locator('#clActivity .cmcard').count(), 10, 'activity is capped');
      assert.match(await pg.locator('#clActivity .cmcard').first().textContent(), /LinkedIn.*Casey Example.*Newest note to Casey/, 'newest first, labelled with the person');
      await pg.locator('#clActMore').click(); await pg.waitForFunction(() => document.querySelectorAll('#clActivity .cmcard').length === 13);
      assert.equal(await pg.locator('#clActMore').isVisible(), false);
      assert.deepEqual(await pg.locator('#clTasks .ui-task__title').allTextContents(), ['Kick-off'], 'open tasks only');
      await assertFits(pg, 'dlgClient', 'company record 1280px'); await shot(pg, 'company-desktop-light');
      // stage, owner, domain and notes save to client_info
      let w = save(); await pg.locator('#clStage').selectOption('Proposal'); await w; assert.equal(info().stage, 'Proposal');
      assert.match(await pg.locator('#clStage').evaluate(x => x.parentElement.className), /ui-select--info/);
      w = save(); await pg.locator('#clOwner').selectOption('alex'); await w; assert.equal(info().owner, 'alex');
      await pg.locator('#clDomain').fill('https://www.Acme.test/about'); w = save(); await pg.locator('#clDomain').press('Tab'); await w; assert.equal(info().domain, 'www.acme.test');
      await pg.locator('#clDomain').fill('not a domain'); await pg.locator('#clDomain').press('Tab'); await pg.waitForTimeout(200);
      assert.equal(await pg.locator('#clDomain').inputValue(), 'www.acme.test', 'a value that is not a domain is refused, as keeptrack.py does'); assert.equal(info().domain, 'www.acme.test');
      await pg.locator('#clNotes').fill('Key account.'); w = save(); await pg.locator('#clNotes').blur(); await w; assert.equal(info().notes, 'Key account.');
      assert.equal(info().north_star, '', 'other client_info fields stay');
      await pg.locator('#clMore').click(); assert.deepEqual(await pg.locator('.ui-menu [role=menuitem]').allTextContents(), ['Show only this company', 'Copy company name', 'Copy link', "Use people's stage"]);
      w = save(); await pg.locator('.ui-menu [role=menuitem]', { hasText: "Use people's stage" }).click(); await w; assert.equal('stage' in info(), false, 'the stage is cleared, not blanked');
      await pg.locator('#clStage option:checked', { hasText: 'Talking (from its people)' }).waitFor({ state: 'attached' });
      w = save(); await pg.locator('#clOwner').selectOption(''); await w; assert.equal('owner' in info(), false);
      // names that are Object.prototype keys are refused and never reach the prototype
      await pg.locator('#clPeople .dperson', { hasText: 'Casey Example' }).click(); await pg.locator('#dlgContact[open]').waitFor();
      await pg.locator('#pCompany').fill('__proto__'); await pg.locator('#pCompany').press('Tab'); await pg.locator('.ui-toast', { hasText: 'cannot be a client or company name' }).waitFor();
      assert.equal(await pg.locator('#pCompany').inputValue(), 'Acme'); assert.equal(JSON.parse(api4.files['people/p_one.json']).company, 'Acme');
      assert.deepEqual(await pg.evaluate(() => [Object.keys(Object.prototype), ({}).stage, ({}).links]), [[], undefined, undefined], 'Object.prototype is untouched');
      await pg.keyboard.press('Escape'); await pg.locator('#dlgContact').waitFor({ state: 'hidden' });
      await pg.locator('#viewSw [data-view="companies"]').click(); await pg.locator('.crow[data-company="Acme"] .pwho b').click(); await pg.locator('#dlgClient[open]').waitFor();
      // a person row opens the person
      await pg.locator('#clPeople .dperson', { hasText: 'Robin Talker' }).click(); await pg.locator('#dlgContact[open]').waitFor(); assert.equal(await pg.locator('#pName').inputValue(), 'Robin Talker');
      // the person drawer's Client field opens the company
      assert.equal(await pg.locator('#pCompanyOpen').getAttribute('aria-label'), 'Open company Acme');
      await pg.locator('#pCompanyOpen').click(); await pg.locator('#dlgClient[open]').waitFor(); assert.equal(await pg.locator('#dlgContact').getAttribute('open'), null);
      await pg.keyboard.press('Escape'); await pg.locator('#dlgClient').waitFor({ state: 'hidden' });
      // People rows: the company is a link to its record, the rest of the row opens the person
      await pg.locator('#viewSw [data-view="people"]').click(); await pg.waitForSelector('.prow .colink');
      await pg.locator('.prow', { hasText: 'Jo Beta' }).locator('.colink').click(); await pg.locator('#dlgClient[open]').waitFor();
      assert.equal(await pg.locator('#clName').textContent(), 'Beta Ltd'); assert.equal(await pg.locator('#dlgContact').getAttribute('open'), null);
      await pg.keyboard.press('Escape'); await pg.locator('#dlgClient').waitFor({ state: 'hidden' });
      await pg.locator('.prow', { hasText: 'Jo Beta' }).locator('.colink').press('Enter'); await pg.locator('#dlgClient[open]').waitFor();
      assert.equal(await pg.locator('#dlgContact').getAttribute('open'), null, 'Enter on the link opens only the company');
      await pg.keyboard.press('Escape'); await pg.locator('#dlgClient').waitFor({ state: 'hidden' });
      // ---- pipeline: People | Companies ----
      await pg.locator('#viewSw [data-view="pipeline"]').click(); await pg.waitForSelector('#pipeMode');
      assert.equal(await pg.locator('#pipeMode [aria-selected="true"]').textContent(), 'People');
      await pg.locator('.pcard', { hasText: 'Robin Talker' }).locator('.colink').click(); await pg.locator('#dlgClient[open]').waitFor();
      assert.equal(await pg.locator('#clName').textContent(), 'Acme', 'a person card links to the company'); await pg.keyboard.press('Escape'); await pg.locator('#dlgClient').waitFor({ state: 'hidden' });
      await pg.locator('#pipeMode [data-value="companies"]').click(); await pg.waitForSelector('.ccard');
      assert.equal(await pg.evaluate(() => Object.keys(localStorage).filter(k => k.startsWith('kb_pipe_mode:')).map(k => localStorage.getItem(k)).join()), 'companies', 'the toggle is remembered in this browser');
      const ccol = st => pg.locator(`.col[data-stage="${st}"] .ccard`);
      assert.deepEqual(await ccol('Talking').locator('.ctitle').allTextContents(), ['Acme']);
      assert.match(await ccol('Talking').textContent(), /2 people.*Book a call.*6,000/);
      assert.match(await ccol('Talking').getAttribute('class'), /\bderived\b/);
      assert.deepEqual(await ccol('New').locator('.ctitle').allTextContents(), ['Beta Ltd']);
      assert.equal(await pg.locator('.col[data-stage="Talking"] h2 .psum').textContent(), '6,000');
      await shot(pg, 'pipeline-companies-desktop-light');
      // drag and drop as the page's own handlers see it: the card's dragstart fills the DataTransfer, the column's drop reads it
      const dragDrop = (card, stage) => pg.evaluate(([card, stage]) => { const k = document.querySelector(`.ccard[data-company="${card}"]`), to = document.querySelector(`.col[data-stage="${stage}"] .cards`), dt = new DataTransfer();
        k.dispatchEvent(new DragEvent('dragstart', { bubbles: true, dataTransfer: dt })); to.dispatchEvent(new DragEvent('dragover', { bubbles: true, cancelable: true, dataTransfer: dt }));
        to.dispatchEvent(new DragEvent('drop', { bubbles: true, cancelable: true, dataTransfer: dt })); k.dispatchEvent(new DragEvent('dragend', { bubbles: true, dataTransfer: dt })); }, [card, stage]);
      w = save(); await dragDrop('Acme', 'Won'); await w;
      assert.equal(info().stage, 'Won', 'dragging a company card sets the company stage');
      await pg.waitForFunction(() => !!document.querySelector('.col[data-stage="Won"] .ccard'));
      assert.equal((JSON.parse(api4.files['people/p_two.json'])).stage, 'Talking', 'its people keep their own stages');
      await ccol('Won').click(); await pg.locator('#dlgClient[open]').waitFor(); assert.equal(await pg.locator('#clStage').inputValue(), 'Won');
      await pg.keyboard.press('Escape'); await pg.locator('#dlgClient').waitFor({ state: 'hidden' });
      // Closing a routed drawer schedules history.back(). Wait for that navigation before reloading.
      await pg.waitForFunction(() => !(history.state || {}).kbDlg && !new URLSearchParams(location.hash.slice(1)).has('company'));
      await pg.reload(); await pg.waitForSelector('.ccard'); assert.equal(await pg.locator('#pipeMode [aria-selected="true"]').textContent(), 'Companies', 'still Companies after a reload');
      await pg.setViewportSize({ width: 390, height: 844 }); await pg.waitForTimeout(150);
      assert.equal(await pg.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true, 'company pipeline fits a phone');
      await shot(pg, 'pipeline-companies-phone-light');
      await pg.locator('#viewSw [data-view="companies"]').click().catch(() => pg.evaluate(() => { location.hash = 'view=companies'; })); await pg.waitForSelector('.crow');
      assert.equal(await pg.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true, 'Companies fits a phone'); await shot(pg, 'companies-phone-light');
      await pg.locator('.crow[data-company="Acme"] .pwho b').click(); await pg.locator('#dlgClient[open]').waitFor();
      await assertFits(pg, 'dlgClient', 'company record 390px'); await shot(pg, 'company-phone-light');
      assert.deepEqual(nat, []); assert.deepEqual(errs, []); await pg.close();
    }

    // ---- read-only demo board: fields disabled, add and remove controls hidden, copy and navigation still work, no Delete ----
    for (const vp of [{ width: 390, height: 844 }, { width: 1280, height: 860 }]) {
      for (const scheme of SHOTS ? ['light', 'dark'] : ['light']) {
        const demo = await browser.newPage({ viewport: vp, colorScheme: scheme }); const demoErrors = []; demo.on('pageerror', e => demoErrors.push(e.message));
        await demo.addInitScript(() => { try { localStorage.setItem('kb_tour_seen', '1'); localStorage.setItem('kb_tour', 'done'); } catch {} });
        await demo.goto(base + '/board/index.html?demo=crm'); await demo.locator('#roBar').waitFor();
        await demo.locator('.prow b').first().click(); await demo.locator('#dlgContact[open]').waitFor(); await demo.waitForTimeout(100);
        for (const id of ['pName', 'pStage', 'pNext', 'pNextDue', 'pRole', 'pNotes', 'pTouchText']) assert.equal(await demo.locator('#' + id).isDisabled(), true, id + ' is locked');
        assert.equal(await demo.locator('#dlgContact .ui-addrow:visible').count(), 0, 'no add rows'); assert.equal(await demo.locator('#dlgContact .ui-listrow button[aria-label^="Remove"]:visible').count(), 0, 'no remove buttons');
        for (const id of ['pAgent', 'pMore', 'pClose']) assert.equal(await demo.locator('#' + id).isEnabled(), true, id + ' stays usable');
        await demo.locator('#pMore').click(); const items = await demo.locator('.ui-menu [role=menuitem]').allTextContents(); assert.ok(!items.includes('Delete person')); assert.ok(items.includes('Copy for AI'));
        await demo.keyboard.press('Escape'); await assertFits(demo, 'dlgContact', `read-only person ${vp.width}px`); await shot(demo, `person-${vp.width}-${scheme}-readonly`);
        const client = items.find(x => x.startsWith('Open client'));
        if (client) {
          await demo.locator('#pMore').click(); await demo.locator('.ui-menu [role=menuitem]', { hasText: client }).click(); await demo.locator('#dlgClient[open]').waitFor(); await demo.waitForTimeout(100);
          assert.equal(await demo.locator('#clNorth').isDisabled(), true); assert.equal(await demo.locator('#dlgClient .ui-addrow:visible').count(), 0);
          for (const id of ['clStage', 'clOwner', 'clDomain', 'clNotes']) assert.equal(await demo.locator('#' + id).isDisabled(), true, id + ' is locked');
          assert.equal(await demo.locator('#clPeople .dperson').first().isEnabled(), true, 'people rows still open the person');
          await demo.locator('#clMore').click(); assert.ok(!(await demo.locator('.ui-menu [role=menuitem]').allTextContents()).includes("Use people's stage")); await demo.keyboard.press('Escape');
          await assertFits(demo, 'dlgClient', `read-only client ${vp.width}px`); await shot(demo, `client-${vp.width}-${scheme}-readonly`);
          const proj = demo.locator('#clProjects .dnav').first();
          if (await proj.count()) {
            await proj.click(); await demo.locator('#dlgProject[open]').waitFor(); await demo.waitForTimeout(100);
            for (const id of ['prName', 'prStatus', 'prNorth']) assert.equal(await demo.locator('#' + id).isDisabled(), true, id + ' is locked');
            await demo.locator('#prMore').click(); assert.ok(!(await demo.locator('.ui-menu [role=menuitem]').allTextContents()).includes('Delete project')); await demo.keyboard.press('Escape');
            await assertFits(demo, 'dlgProject', `read-only project ${vp.width}px`); await shot(demo, `project-${vp.width}-${scheme}-readonly`);
          }
        }
        await demo.evaluate(() => document.querySelectorAll('dialog[open]').forEach(d => d.close()));
        const goView = async v => { for (let i = 0; i < 10; i++) {   // a closing drawer takes its own history step back: go once that has landed
          await demo.waitForTimeout(150); await demo.evaluate(x => { location.hash = 'view=' + x; }, v);
          if (await demo.waitForFunction(x => document.body.dataset.view === x, v, { timeout: 1000 }).then(() => true, () => false)) return; } throw new Error('could not open ' + v); };
        await goView('pipeline'); await demo.waitForSelector('#pipeMode');
        await demo.locator('#pipeMode [data-value="companies"]').click(); await demo.waitForSelector('.ccard');
        assert.deepEqual(await demo.locator('.pcard').evaluateAll(xs => [...new Set(xs.map(x => x.draggable))]), [false], 'read-only cards cannot be dragged');
        await demo.locator('#pipeMode [data-value="people"]').click(); await demo.waitForSelector('.pcard:not(.ccard)');
        await goView('companies'); await demo.waitForSelector('.crow');
        assert.equal(await demo.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true, `read-only Companies at ${vp.width}px fits`);
        assert.deepEqual(demoErrors, [], 'no page errors on the demo');
        await demo.close();
      }
    }
    // A selected company stays a normal pill, and a second company can still pick its own project.
    {
      const apiP = new Github();
      apiP.files['tasks.json'] = text({ ...root, clients: ['Rain Ventures', 'Beta'], next_num: 4 });
      apiP.files['projects/pr_one.json'] = text({ ...project, client: 'Rain Ventures', name: 'Launch' });
      apiP.files['projects/pr_two.json'] = text({ ...project, id: 'pr_two', client: 'Beta', name: 'Beta site' });
      apiP.files['cards/t_one.json'] = text({ ...card, client: 'Rain Ventures', title: 'Rain task' });
      apiP.files['cards/t_two.json'] = text({ ...card, id: 't_two', num: 2, client: 'Beta', project: 'pr_two', title: 'Beta task', rank: 'a2' });
      apiP.files['cards/t_three.json'] = text({ ...card, id: 't_three', num: 3, client: 'Rain Ventures', project: '', title: 'Rain other', rank: 'a3' });
      const pg = await browser.newPage({ viewport: { width: 740, height: 800 } }); const errs = []; pg.on('pageerror', e => errs.push(e.message));
      await pg.addInitScript(() => { localStorage.setItem('kb_repo', 'acme/board'); localStorage.setItem('kb_branch', 'main'); localStorage.setItem('kb_path', 'board/tasks.json'); localStorage.setItem('kb_token', 'test'); localStorage.setItem('kb_me', 'alex'); localStorage.setItem('kb_api', 'https://api.test'); localStorage.setItem('kb_layout', 'classic'); localStorage.setItem('kb_tour', 'done'); sessionStorage.setItem('kb_view', 'board'); });
      await pg.route('https://api.test/**', r => apiP.route(r)); await pg.goto(base + '/board/index.html'); await pg.locator('.card .t', { hasText: 'Rain task' }).waitFor();
      const company = name => pg.locator('#clientBar .cpill').filter({ has: pg.locator('.cdotc') }).filter({ hasText: name });
      const openCompanyOverflow = async () => {
        // Selecting an overflow company deliberately leaves its menu open. Toggle only when
        // closed: clicking More unconditionally would hide the Projects button we need next.
        if (!(await pg.locator('#clientPop').isVisible())) await pg.locator('.cpill.more').click();
        await pg.locator('#clientPop').waitFor({ state: 'visible' });
      };
      const pickCompany = async name => {
        const pill = company(name);
        if (await pill.count()) { await pill.click({ position: { x: 24, y: 16 } }); return; }
        await openCompanyOverflow(); await pg.locator(`#clientPop .cmenu[data-client="${name}"]`).click();
      };
      const pickProject = async (name, label) => {
        const pill = company(name);
        if (await pill.count() && await pill.locator('.cpillproj').count()) await pill.locator('.cpillproj').click();
        else {
          // Selecting an overflow company can leave this popover open while the bar reflows.
          // Toggle only when closed; otherwise the test hides the very project button it needs.
          if (!(await pg.locator('#clientPop').isVisible())) await pg.locator('.cpill.more').click();
          await pg.locator(`#clientPop [aria-label="Projects for ${name}"]`).click();
        }
        await pg.locator('.ui-menu [role=menuitem]', { hasText: label }).click();
      };
      const rain = company('Rain Ventures');
      await pickCompany('Rain Ventures');
      await rain.locator('.cpillproj').waitFor();
      const tall = await rain.boundingBox();
      assert.ok(tall && tall.height < 48, `selected company pill is ${tall && Math.round(tall.height)}px tall`);
      await rain.locator('.cpillproj').click();
      assert.equal(await rain.getAttribute('aria-pressed'), 'true', 'opening projects leaves the company selected');
      await pg.locator('.ui-menu [role=menuitem]', { hasText: 'Launch' }).click();
      await pg.locator('.card .t', { hasText: 'Rain other' }).waitFor({ state: 'hidden' });
      await pickCompany('Beta');
      await pg.locator('.card .t', { hasText: 'Beta task' }).waitFor();
      assert.equal(await pg.locator('.card .t', { hasText: 'Rain other' }).count(), 0, 'the first company stays narrowed to its project');
      // Force the overflow branch on every machine, independent of available fonts and pill widths.
      await pg.setViewportSize({ width: 390, height: 800 });
      await pg.locator('.cpill.more').waitFor();
      await openCompanyOverflow();
      await pg.locator('#clientPop [aria-label="Projects for Beta"]').waitFor();
      await openCompanyOverflow();
      assert.equal(await pg.locator('#clientPop').isVisible(), true, 'opening an already open company menu keeps its project controls visible');
      await pickProject('Beta', 'Beta site');
      assert.equal(await pg.locator('.card .t', { hasText: 'Beta task' }).count(), 1);
      assert.equal(await pg.locator('.card .t', { hasText: 'Rain other' }).count(), 1, 'the other selected company stays whole');
      assert.deepEqual(errs, []); await pg.close();
    }
    console.log('crm-drawers: all checks passed');
  } finally { await browser.close(); server.close(); }
})().catch(e => { console.error(e); process.exit(1); });

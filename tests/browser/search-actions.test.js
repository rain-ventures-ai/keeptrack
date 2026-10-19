'use strict';
const assert = require('node:assert/strict');
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');
const ROOT = path.resolve(__dirname, '../..');
const server = http.createServer((req, res) => {
  const file = path.resolve(ROOT, '.' + new URL(req.url, 'http://local').pathname);
  if (!file.startsWith(ROOT + path.sep)) return res.writeHead(403).end();
  fs.readFile(file, (error, data) => { if (error) return res.writeHead(404).end();
    res.setHeader('Content-Type', ({ '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json' })[path.extname(file)] || 'application/octet-stream'); res.end(data); });
});
(async () => {
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage(); const errors = []; let writes = 0;
    page.on('pageerror', error => errors.push(error.message));
    await page.addInitScript(() => { localStorage.setItem('kb_tour_seen', '1'); localStorage.setItem('kb_theme', 'sand');
      localStorage.setItem('kb_repo', 'acme/search'); localStorage.setItem('kb_branch', 'main'); localStorage.setItem('kb_token', 'test'); localStorage.setItem('kb_api', 'https://api.test'); sessionStorage.setItem('kb_view', 'board'); });
    const HOUR = 60 * 60 * 1000, DAY = 24 * HOUR;
    const before = ms => new Date(Date.now() - ms).toISOString();
    const makeTask = (id, num, title, created, updated, extra = {}) => ({ id, num, title, column: 'todo', priority: 'medium', assignees: [], labels: [], comments: [], todos: [], history: [], links: [], created, updated, ...extra });
    const board = { version: 3, columns: [{ id: 'todo', name: 'To do' }, { id: 'done', name: 'Done' }], people: [], clients: ['Acme School'], agents: [], labels: [], settings: {},
      contacts: [{ id: 'c_pat', name: 'Pat Lee', company: 'Acme School', stage: 'lead', notes: '', next: '', comments: [], history: [], links: [] },
        { id: 'c_kim', name: 'Kim Roe', company: 'Globex Ltd', stage: 'lead', notes: '', next: '', comments: [], history: [], links: [] }],
      projects: [{ id: 'pr_wifi', name: 'Campus wifi rollout', client: 'Acme School', status: 'active', people: [] }, { id: 'pr_26', name: 'Phase 26', client: 'Acme School', status: 'active', people: [] }],
      tasks: [makeTask('t_search', 1, 'Search example card', before(800 * DAY), before(90 * DAY), { client: 'Acme School' }),
        makeTask('t_new_1', 2, 'Research: personal AI benchmark for testing new models', before(22 * DAY), before(3 * HOUR)),
        makeTask('t_new_2', 3, 'Review new follow-ups from the latest Keeptrack release and record reads', before(20 * DAY), before(8 * DAY), { comments: [{ by: 'ollie', at: before(2 * HOUR), text: 'Latest note' }] }),
        makeTask('t_new_3', 4, 'Prepare a new proposal with the full heartbeat and feature plan', before(90 * DAY), before(15 * DAY)),
        makeTask('t_new_4', 5, 'Upgrade the new board tools after checking every shared workspace', before(3 * DAY), before(2 * DAY)),
        makeTask('t_new_5', 6, 'Plan the next new family bike trip with train and weather options', before(5 * HOUR), before(2 * HOUR)),
        makeTask('t_num_96', 96, 'Order 26 chairs', before(5 * DAY), before(DAY), { column: 'done', details: '26 chairs, 26 legs' }),
        makeTask('t_num_260', 260, 'Number prefix card', before(5 * DAY), before(DAY), { column: 'done' }),
        makeTask('t_num_26', 26, 'Number target card', before(5 * DAY), before(DAY), { column: 'done' })] };
    await page.route('https://api.test/**', route => { if (route.request().method() !== 'GET') writes++;
      const url = route.request().url();
      if (url.includes('/contents/board/tasks.json')) return route.fulfill({ contentType: 'application/json', body: JSON.stringify({ sha: 'one', encoding: 'base64', content: Buffer.from(JSON.stringify(board)).toString('base64') }) });
      if (url.includes('/contents/board/KIT_VERSION')) return route.fulfill({ body: '999' });
      return route.fulfill({ status: 404, body: '{}' }); });
    await page.goto(`http://127.0.0.1:${server.address().port}/board/index.html?repo=acme/search&branch=main&path=board/tasks.json`);
    await page.waitForSelector('.card');
    assert.deepEqual(await page.locator('.card').nth(0).locator('.cardage span').allTextContents(), ['Created 2y ago', 'Active 3mo ago']);
    assert.deepEqual(await page.locator('.card').nth(1).locator('.cardage span').allTextContents(), ['Created 3w ago', 'Active 3h ago']);
    assert.deepEqual(await page.locator('.card').nth(2).locator('.cardage span').allTextContents(), ['Created 2w ago', 'Active 2h ago'], 'a newer comment is the latest activity');
    assert.equal(await page.locator('.card').nth(0).locator('.cardage time').first().getAttribute('datetime'), board.tasks[0].created);
    assert.match(await page.locator('.card').nth(0).locator('.cardage time').first().getAttribute('title'), /\d{4}/, 'the exact date is available on hover');
    const search = async query => { await page.evaluate(() => document.getElementById('btnSearch').click()); await page.locator('#qQ').fill(query); await page.waitForTimeout(150); };
    await search('HELP'); await page.getByRole('button', { name: 'Open Help', exact: true }).click();
    assert.equal(await page.locator('#dlgHelp').evaluate(dialog => dialog.open), true);
    await page.locator('#hClose').click();
    await search('setup agents'); await page.getByRole('button', { name: 'Set up agents and integrations', exact: true }).click();
    assert.equal(await page.locator('#panelAgents').isVisible(), true);
    await page.locator('#dlgSettings').evaluate(dialog => dialog.close());
    await search('connection'); await page.getByRole('button', { name: 'Connection and boards', exact: true }).click();
    assert.equal(await page.locator('#panelConn').isVisible(), true);
    await page.locator('#dlgSettings').evaluate(dialog => dialog.close());
    await search('theme'); await page.getByRole('button', { name: 'Appearance and themes', exact: true }).click();
    assert.equal(await page.locator('#sTheme').isVisible(), true);
    await page.locator('#dlgSettings').evaluate(dialog => dialog.close());
    await search('widgets'); await page.getByRole('button', { name: 'Board customisations', exact: true }).click();
    assert.equal(await page.locator('#sWidgets').isVisible(), true);
    await page.waitForFunction(() => { const section = document.getElementById('secWidgets').getBoundingClientRect(), dialog = document.getElementById('dlgSettings').getBoundingClientRect(); return section.top >= dialog.top && section.top < dialog.bottom - 80; });
    await page.locator('#dlgSettings').evaluate(dialog => dialog.close());
    await search('MIDNIGHT'); await page.locator('#qQ').press('Enter');
    assert.equal(await page.locator('html').getAttribute('data-theme'), 'midnight');
    assert.equal(await page.evaluate(() => localStorage.getItem('kb_theme')), 'midnight');
    await page.evaluate(() => { window.kbTheme.useBoard({ repo: 'acme/search', branch: 'main', path: 'board/tasks.json' }); window.kbTheme.enableBoard(true); });
    await search('forest'); await page.getByRole('button', { name: /Use Forest.*theme/i }).click();
    assert.equal(await page.locator('html').getAttribute('data-theme'), 'forest');
    assert.equal(await page.evaluate(() => localStorage.getItem('kb_theme')), 'midnight', 'board choice preserves browser default');
    await page.evaluate(() => window.kbTheme.useBoard({ repo: 'acme/other', branch: 'main', path: 'board/tasks.json' }));
    assert.equal(await page.locator('html').getAttribute('data-theme'), 'midnight');
    // Existing navigation/data results and keyboard navigation stay present.
    await search(''); assert.equal(await page.locator('.qgo').count() > 0, true);
    await page.locator('#qQ').press('ArrowDown'); assert.equal(await page.locator('.qhit:focus').count(), 1);
    await page.locator('#qClose').click();
    // A phone keyboard leaves little vertical space. Results must retain their content height and scroll, rather than
    // flex-shrinking until wrapped titles and metadata paint over the next result.
    await page.setViewportSize({ width: 390, height: 460 }); await search('new');
    const mobileLayout = await page.locator('#qRes').evaluate(res => {
      const rows = [...res.querySelectorAll('.qhit')].map(row => { const r = row.getBoundingClientRect(), title = row.querySelector('.qt')?.getBoundingClientRect(), sub = row.querySelector('.qsub')?.getBoundingClientRect(); return { top: r.top, bottom: r.bottom, height: r.height, contentBottom: Math.max(title?.bottom || 0, sub?.bottom || 0) }; });
      return { rows, clientHeight: res.clientHeight, scrollHeight: res.scrollHeight };
    });
    assert.equal(mobileLayout.rows.length >= 6, true); assert.equal(mobileLayout.scrollHeight > mobileLayout.clientHeight, true, 'phone results scroll when they exceed the available height');
    mobileLayout.rows.forEach((row, i) => assert.equal(row.contentBottom <= row.bottom, true, `search result ${i + 1} contains its wrapped title and metadata`));
    mobileLayout.rows.slice(1).forEach((row, i) => assert.equal(row.top >= mobileLayout.rows[i].bottom, true, `search result ${i + 2} does not overlap the previous result`));
    await page.locator('#qClose').click(); await page.setViewportSize({ width: 1280, height: 720 });
    // A number puts the card with that number first, then cards whose number starts with it, then other matches
    for (const query of ['26', '#26']) { await search(query);
      assert.deepEqual((await page.locator('#qRes .qhit:not(.qgo):not(.qaction) .qt').allTextContents()).slice(0, 3), ['Number target card', 'Number prefix card', 'Order 26 chairs'], query); }
    await page.locator('#qQ').press('Enter'); assert.equal(await page.locator('#dlgCard').evaluate(dialog => dialog.open), true, 'Enter opens the numbered card');
    await page.locator('#dlgCard').evaluate(dialog => dialog.close());
    // A client or project name finds the client or project itself, above its cards and people
    await search('acme sch');
    assert.deepEqual(await page.locator('#qRes .qhead').allTextContents(), ['Clients and projects', 'People and tasks']);
    assert.deepEqual(await page.locator('#qRes .qplace .qt').allTextContents(), ['Acme School']);
    assert.match(await page.locator('#qRes .qplace .qsub').first().textContent(), /Client · 1 open task · 1 person · 2 projects/);
    await page.locator('#qQ').press('Enter'); assert.equal(await page.locator('#dlgClient').evaluate(dialog => dialog.open), true, 'Enter opens the client');
    await page.locator('#dlgClient').evaluate(dialog => dialog.close());
    await search('chool'); assert.deepEqual(await page.locator('#qRes .qplace .qt').allTextContents(), ['Acme School'], 'three letters match inside a name');
    await search('globex'); assert.match(await page.locator('#qRes .qplace .qsub').first().textContent(), /^Company · 0 open tasks · 1 person$/, 'a CRM-only company is not called a client');
    await search('wifi'); await page.getByRole('button', { name: /Campus wifi rollout/ }).click();
    assert.equal(await page.locator('#dlgProject').evaluate(dialog => dialog.open), true, 'a project result opens the project');
    await page.locator('#dlgProject').evaluate(dialog => dialog.close());
    await search('example card'); await page.getByRole('button', { name: /Search example card/ }).click();
    assert.equal(await page.locator('#dlgCard').evaluate(dialog => dialog.open), true);
    assert.equal(writes, 0); assert.deepEqual(errors, []);
    console.log('search-actions: all checks passed');
  } finally { await browser.close(); await new Promise(resolve => server.close(resolve)); }
})().catch(error => { console.error(error); process.exitCode = 1; });

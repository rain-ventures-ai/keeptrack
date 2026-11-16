'use strict';
const assert = require('node:assert/strict'), fs = require('node:fs'), vm = require('node:vm'), path = require('node:path');
const { webcrypto } = require('node:crypto');
const source = fs.readFileSync(path.join(__dirname, '../../board/board.js'), 'utf8');
const clone = x => JSON.parse(JSON.stringify(x));
const canonical = x => JSON.stringify((function sorted(v) { if (Array.isArray(v)) return v.map(sorted); if (v && typeof v === 'object') return Object.fromEntries(Object.keys(v).sort().map(k => [k, sorted(v[k])])); return v; })(x));
const board = () => ({ settings: { kit_owner: 'owner', rook_research: { v: 1, enabled: true, board: 'owner/board', owner: 'owner',
  projects: ['pr_one'], profile: 'public-research', policy_digest: 'sha256:' + 'b'.repeat(64), approval_ttl: 300 } }, people: [{ github: 'owner' }], projects: [{ id: 'pr_one' }],
  tasks: [{ id: 't_research', title: 'Compare public documentation', project: 'pr_one', column: 'backlog', details: 'Summarise the two sources.',
    todos: [], after: [], links: [{ url: 'https://example.org/guide', title: 'Public guide' }], comments: [], history: [] }] });

module.exports = async function run() {
  let data = board(), user = 'owner', saves = 0, saved, race = () => {}, toast = '', ownerAvailable = true;
  const cfg = () => ({ repo: 'owner/board', me: user });
  const context = vm.createContext({ Map, Set, URL, Error, TextEncoder, Uint8Array, AbortController, setTimeout, clearTimeout,
    rookApprovalConfig: () => ({ endpoint: 'https://owner.example.org/owner-action', token: 'o'.repeat(64) }),
    fetch: async (url, options) => { assert.equal(url, 'https://owner.example.org/owner-action'); assert.equal(options.credentials, 'omit');
      assert.equal(options.headers.Authorization, 'Bearer ' + 'o'.repeat(64)); const p = JSON.parse(options.body);
      return { ok: ownerAvailable, json: async () => ({ v: 1, task_id: p.task_id, approval_id: p.approval_id, answer_id: p.answer_id, content_hash: p.content_hash }) }; },
    Date: class extends Date { static now() { return Date.parse('2026-11-15T12:00:00Z'); } }, crypto: webcrypto, clone, jcanon: canonical, cfg,
    state: data, ro: false, HOSTED: false, kitOwner: () => 'owner', toast: t => { toast = t; },
    boardId: () => 'r_abcdef1234', rid6: () => '123456', nowIso: () => '2026-11-15T12:00:00Z', waitingOf: t => t.waiting,
    proposalIn: () => null, proposalPath: id => `proposals/${id}.json`, jsonText: JSON.stringify, stamp: () => {},
    mutate: async (fn, message, ids, base, opts) => { assert.equal(opts.recheck, true); assert.equal(opts.remember, false); race(data);
      const latest = clone(data), result = opts.extra(data, {}, latest); if (result.abort) { toast = result.abort; return false; }
      saves++; saved = result; data = latest; context.state = data; return true; } });
  vm.runInContext(source.slice(source.indexOf('  function rookResearchScope('), source.indexOf('  function renderRookResearch(')) +
    '\nthis.api = { rookResearchScope, revokeResearchOnEdit, handResearchToRook };', context);
  const reset = () => { data = board(); context.state = data; user = 'owner'; saves = 0; race = () => {}; ownerAvailable = true; };
  assert.equal(await context.api.handResearchToRook('t_research'), true);
  assert.equal(saves, 1);
  const p = JSON.parse(saved.files['proposals/r_abcdef1234.json']);
  assert.equal(p.decision.by, 'owner'); assert.equal(p.decision.answer.approved, true);
  assert.equal(p.change.content_hash, 'sha256:' + Buffer.from(await webcrypto.subtle.digest('SHA-256', new TextEncoder().encode(canonical(context.api.rookResearchScope(board(), board().tasks[0], 'owner/board'))))).toString('hex'));
  assert.equal(data.tasks[0].column, 'backlog', 'only the private host may admit/start');
  assert.equal(data.tasks[0].coordination.executor, 'relay-research', 'the button cannot opt a research card into the repository runner');
  assert.equal(data.tasks[0].coordination.research.request.answer_id, p.decision.id);
  assert.equal(await context.api.handResearchToRook('t_research'), false, 'duplicate click does not create another approval');
  reset(); user = 'other'; assert.equal(await context.api.handResearchToRook('t_research'), false); assert.equal(saves, 0);
  reset(); ownerAvailable = false; assert.equal(await context.api.handResearchToRook('t_research'), false); assert.equal(saves, 0, 'no public approval is saved when the private owner endpoint refuses');
  reset(); race = d => { d.tasks[0].details = 'Edited during save'; };
  assert.equal(await context.api.handResearchToRook('t_research'), false); assert.match(toast, /changed/); assert.equal(saves, 0);
  reset(); data.settings.rook_research.enabled = false;
  assert.equal(await context.api.handResearchToRook('t_research'), false); assert.equal(saves, 0);
  for (const change of [d => { d.settings.rook_research.extra = true; },
    d => { d.settings.rook_research.projects = Array(17).fill('pr_one'); },
    d => { d.tasks[0].links[0].url = 'https://example.org/bad\x01path'; }]) {
    reset(); change(data); assert.equal(await context.api.handResearchToRook('t_research'), false); assert.equal(saves, 0);
  }
  reset(); delete data.settings.kit_owner; data.people.unshift({ name: 'No GitHub account' }); context.kitOwner = () => '';
  assert.equal(await context.api.handResearchToRook('t_research'), true, 'use the first person with a GitHub login, like native scope');
  context.kitOwner = () => 'owner';
  reset(); data.tasks[0].links[0].url = 'https://user:secret@example.org';
  assert.equal(await context.api.handResearchToRook('t_research'), false); assert.equal(saves, 0);
  reset(); data.tasks[0].details = 'é'.repeat(1999);
  assert.equal(await context.api.handResearchToRook('t_research'), false); assert.equal(saves, 0); assert.match(toast, /4000/);
  reset(); data.tasks[0].todos = [{ text: 'a'.repeat(301), done: false }];
  assert.equal(await context.api.handResearchToRook('t_research'), false); assert.equal(saves, 0);
  const before = board(); before.tasks[0].column = 'in-progress'; before.tasks[0].claim = { unattended_approved: true };
  before.tasks[0].coordination = { research: { admission: { id: 'ra_exact', active: true } } };
  const after = clone(before); after.tasks[0].column = 'backlog';
  context.api.revokeResearchOnEdit(before, after); assert.equal(after.tasks[0].coordination.research.admission.active, false);
  assert.equal(after.tasks[0].claim.unattended_approved, undefined);
  const undone = clone(before); context.api.revokeResearchOnEdit(after, undone);
  assert.equal(undone.tasks[0].coordination.research.admission.active, false, 'undo cannot restore a consumed grant');
  for (const edit of [t => { t.details = 'Different approved scope'; }, t => { t.links[0].url = 'https://example.org/other'; },
    t => { t.todos.push({ text: 'Additional work', done: false }); }]) {
    const changed = clone(before); edit(changed.tasks[0]);
    context.api.revokeResearchOnEdit(before, changed);
    assert.equal(changed.tasks[0].coordination.research.admission.active, false, 'editing approved input withdraws authority');
    const restored = clone(before); context.api.revokeResearchOnEdit(changed, restored);
    assert.equal(restored.tasks[0].coordination.research.admission.active, false, 'undoing an input edit cannot restore the old grant');
  }
  assert.match(source, /revokeResearchOnEdit\(pre, latest\)/, 'every browser save checks revocation');
  console.log('Rook research button, scope race and revocation checks passed');
};
if (require.main === module) module.exports().catch(e => { console.error(e); process.exitCode = 1; });

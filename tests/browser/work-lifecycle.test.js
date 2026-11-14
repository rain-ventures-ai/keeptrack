'use strict';
// Real web lifecycle helpers, temporary in-memory boards; no browser/network needed.
const assert = require('node:assert/strict'), fs = require('node:fs'), vm = require('node:vm'), path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../../board/board.js'), 'utf8');
const clone = x => JSON.parse(JSON.stringify(x));
const task = id => ({ id, num: 1, title: id, column: 'done', updated: '2020-01-01', details: 'Source details',
  todos: [], links: [], labels: [], assignees: [], contacts: [], comments: [], history: [],
  project: 'pr_one', coordination: { runs: [{ id: 'wr_example', terminal: { kind: 'finished' }, needs_reconciliation: true }] } });
const board = () => ({ columns: [{ id: 'todo' }, { id: 'done' }], tasks: [task('source')], contacts: [] });
module.exports = async function run() {
  let current = board(), closed;
  const context = vm.createContext({ Set, Error, clone, todayIso: () => '2026-11-14', dayIso: () => '2026-01-01',
    memberOf: () => false, relationOf: () => null, similarNorm: x => String(x || '').toLowerCase(), setRelation: () => {},
    jcanon: JSON.stringify, waitingOf: () => null, editing: 'source', titleOf: () => 'source', editingDesc: false, backPending: null,
    KINDS: ['tasks', 'contacts'], sameJson: (a, b) => JSON.stringify(a) === JSON.stringify(b),
    byId: (d, k) => new Map((d[k] || []).map(t => [t.id, t])), writeBlocked: () => false, ask: async () => true,
    claimState: () => 'running', agentLimitFull: () => '', nowIso: () => '2026-11-14T12:00:00Z', toast: () => {},
    isSplit: () => false,
    edit: async (id, fn) => { fn(current.tasks.find(t => t.id === id), current); return true; },
    el: () => ({ append() {} }), ui: { button: () => ({}), confirm: async () => true },
    $: () => ({ addEventListener: (event, fn) => { closed = fn; }, close: () => closed() }),
    mutate: (fn, message, ids, base, options) => { assert.equal(options?.recheck, true, 'destructive operation rechecks each save'); return fn(current); } });
  const helperStart = source.indexOf('  function unresolvedWork(');
  const helper = helperStart < 0 ? '' : source.slice(helperStart, source.indexOf('  function archivePlan(', helperStart));
  vm.runInContext(helper + source.slice(source.indexOf('  function archivePlan('), source.indexOf('  function archiveMerge(')) +
    source.slice(source.indexOf('  function mergeCardInto('), source.indexOf('  async function mergeCards(')) +
    source.slice(source.indexOf('  async function mergeCards('), source.indexOf('  async function finishMerge(')) +
    source.slice(source.indexOf('  function applyInverse('), source.indexOf('  async function undoLast(')) +
    source.slice(source.indexOf('  async function clearWait('), source.indexOf('  function openPeopleMenu(')) +
    source.slice(source.indexOf('  async function deleteTask('), source.indexOf('  // Settings → Connection → Advanced → Move settings:')) +
    '\nthis.api = { archivePlan, mergeCardInto, mergeCards, deleteTask, applyInverse, unresolvedRemoval, clearWait };', context);
  const failures = [];
  const check = async (name, fn) => { try { await fn(); } catch (e) { failures.push(name + ': ' + e.message); } };
  await check('explicit archive retains unresolved attempt', () => {
    const d = board(), before = clone(d);
    assert.throws(() => context.api.archivePlan(d, { taskId: 'source' }), /unresolved/i); assert.deepEqual(d, before);
  });
  await check('batch archive skips only held work', () => {
    const d = board(), resolved = task('resolved'); resolved.coordination.runs[0].resolution = { disposition: 'retry-safe' }; d.tasks.push(resolved);
    const result = context.api.archivePlan(d, { taskIds: ['source', 'resolved'], onlyDone: true });
    assert.deepEqual(d.tasks.map(t => t.id), ['source']); assert.equal(Object.values(result)[0].tasks[0].id, 'resolved');
  });
  await check('bulk archive retains unresolved attempt', () => {
    const d = board(); context.api.archivePlan(d, { done_days: 90, lost_days: 180, keep_history: 20 });
    assert.equal(d.tasks.length, 1);
  });
  await check('merge refuses before copying', () => {
    const d = board(), target = task('target'); target.coordination = null; d.tasks.push(target); const before = clone(d);
    assert.throws(() => context.api.mergeCardInto(d, 'source', 'target'), /unresolved/i); assert.deepEqual(d, before);
  });
  await check('delete rechecks latest task after confirmation', async () => {
    current = board(); const before = clone(current);
    await assert.rejects(context.api.deleteTask(), /unresolved/i); assert.deepEqual(current, before);
  });
  await check('merge rechecks latest task after confirmation', async () => {
    current = board(); const target = task('target'); target.coordination = null; current.tasks.push(target);
    context.state = clone(current); context.state.tasks[0].coordination = null; const before = clone(current);
    await assert.rejects(context.api.mergeCards('source', 'target'), /unresolved/i); assert.deepEqual(current, before);
  });
  await check('undo of card creation cannot erase a later run', () => {
    const d = board(), before = clone(d), saved = clone(d); saved.tasks[0].coordination = null;
    assert.throws(() => context.api.applyInverse(d, { before: { tasks: [], contacts: [] }, after: saved }), /unresolved/i);
    assert.deepEqual(d, before);
  });
  await check('unwait does not revive another claim through a project hold', async () => {
    current = board(); const legacy = task('target'); legacy.coordination = null;
    legacy.waiting = { on: 'pause' }; legacy.claim = { status: 'blocked', blocked_by_wait: true };
    current.tasks.push(legacy); context.state = clone(current);
    await context.api.clearWait('target');
    assert.equal(current.tasks[1].claim.status, 'blocked');
  });
  await check('stale attended wait clearing does not approve unattended execution', async () => {
    current = board(); current.tasks[0].coordination = null; current.tasks[0].column = 'in-progress';
    current.tasks[0].claim = { status: 'blocked', blocked_by_wait: true, attended: true };
    context.state = clone(current); context.claimState = () => 'stale';
    await context.api.clearWait('source');
    assert.equal(current.tasks[0].column, 'in-progress'); assert.equal(current.tasks[0].claim, null);
  });
  await check('stale approved unattended wait can requeue', async () => {
    current = board(); current.tasks[0].coordination = null; current.tasks[0].column = 'in-progress';
    current.tasks[0].claim = { status: 'blocked', blocked_by_wait: true, unattended_approved: true };
    context.state = clone(current); context.claimState = () => 'stale';
    await context.api.clearWait('source');
    assert.equal(current.tasks[0].column, 'todo'); assert.equal(current.tasks[0].claim, null);
  });
  await check('legacy project name cannot bypass a canonical hold on web unwait', async () => {
    current = board(); current.projects = [{ id: 'pr_one', name: 'One', client: 'Example' }];
    const legacy = task('target'); legacy.coordination = null; legacy.project = 'One';
    legacy.claim = { status: 'blocked', blocked_by_wait: true }; legacy.waiting = { on: 'pause' };
    current.tasks.push(legacy); context.state = clone(current); context.claimState = () => 'running';
    await context.api.clearWait('target');
    assert.equal(current.tasks[1].claim.status, 'blocked');
  });
  await check('renamed historical run cannot lose its hold on web revival', async () => {
    current = board(); current.projects = [{ id: 'pr_one', name: 'Renamed', client: 'Example' }];
    current.tasks[0].project = 'One'; current.tasks[0].coordination.owner = 'rook:One';
    current.tasks[0].coordination.runs[0].project_id = 'One';
    const legacy = task('target'); legacy.coordination = null;
    legacy.claim = { status: 'blocked', blocked_by_wait: true }; legacy.waiting = { on: 'pause' };
    current.tasks.push(legacy); context.state = clone(current); context.claimState = () => 'running';
    await context.api.clearWait('target');
    assert.equal(current.tasks[1].claim.status, 'blocked');
  });
  assert.deepEqual(failures, [], failures.join('\n'));
  assert.equal(context.api.unresolvedRemoval(board(), { tasks: [] }).id, 'source', 'fresh-save guard protects removal after a conflict choice');
  const resolved = board(); resolved.tasks[0].coordination.runs[0].resolution = { disposition: 'recorded-result' };
  assert.equal(context.api.unresolvedRemoval(resolved, { tasks: [] }), undefined);
  assert.equal(Object.values(context.api.archivePlan(resolved, { taskId: 'source' }))[0].tasks.length, 1);
  assert.equal(resolved.tasks.length, 0);
  console.log('web coordinated lifecycle tests passed');
};
if (require.main === module) module.exports().catch(e => { console.error(e); process.exitCode = 1; });

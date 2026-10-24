'use strict';
// Exercise production archive-demand/cache/sharding helpers with immutable snapshot SHAs.
const assert = require('node:assert/strict'), fs = require('node:fs'), vm = require('node:vm'), path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../../board/board.js'), 'utf8');
const clone = x => JSON.parse(JSON.stringify(x));
const env = (extra = {}) => ({ version: 3, archive: true, year: '2020', tasks: [], contacts: [], proposals: [], history: {}, ...extra });
(async () => {
  let config = { repo: 'synthetic/board', branch: 'main', path: 'board/tasks.json' }, deleted = [], calls = [], serializations = 0;
  const values = new Map(), context = vm.createContext({ Map, Set, Uint8Array, TextEncoder, Error,
    isObj: x => x && typeof x === 'object' && !Array.isArray(x),
    cfg: () => config, archGen: 0, ARCH_MAX: 1000, archBytes: s => Buffer.byteLength(s), clone,
    jsonText: x => { serializations++; return JSON.stringify(x, null, 2) + '\n'; }, sameJson: (a,b) => JSON.stringify(a) === JSON.stringify(b),
    safeCardId: x => typeof x === 'string' && /^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$/.test(x),
    idb: { get: async key => values.get(key), set: async (key,value) => values.set(key,value), keys: async () => [...values.keys()], del: async key => { deleted.push(key); values.delete(key); } },
    ghApi: async (...args) => { calls.push(args); return { ok: true, json: async () => ({ encoding: 'base64', content: Buffer.from(JSON.stringify(env())).toString('base64') }) }; }, b64d: x => Buffer.from(x,'base64').toString()
  });
  vm.runInContext(source.slice(source.indexOf('  const wantedRel ='), source.indexOf('  let graphqlBlobsDenied =')) +
    source.slice(source.indexOf('  const archivePartKey ='), source.indexOf('  function archivePlan(')) +
    source.slice(source.indexOf('  class ArchiveUnpackable extends'), source.indexOf('  async function archiveSplitNow(')) +
    '\nthis.api = { archiveEntry, pruneBlobCache, shardArchiveFamily };', context);
  const live = 'a'.repeat(40), stale = 'b'.repeat(40), foreign = `kb_blob:another/board:${stale}`;
  values.set(`kb_blob:${config.repo}:${live}`, 'live'); values.set(`kb_blob:${config.repo}:${stale}`, 'stale'); values.set(foreign, 'foreign'); values.set(`kb_blob:${config.repo}:settings`, 'keep');
  await context.api.pruneBlobCache(new Set([live]), config, 0);
  assert.deepEqual(deleted, [`kb_blob:${config.repo}:${stale}`]); assert.equal(values.get(foreign), 'foreign');
  const meta = { files: new Map([['archive/2020.json', { sha: 'c'.repeat(40), size: 700000 }]]) };
  assert.equal(calls.length, 0);
  const entry = await context.api.archiveEntry(meta, '2020');
  assert.equal(entry.obj.year, '2020'); assert.equal(calls.length, 1); assert.equal(calls[0][1], '/git/blobs/' + 'c'.repeat(40));
  await context.api.archiveEntry(meta, '2020'); assert.equal(calls.length, 1, 'same snapshot body hydrates once');
  let release;
  context.idb.get = () => new Promise(resolve => { release = resolve; });
  const pending = context.api.archiveEntry({ files: new Map([['archive/2021.json', { sha: 'd'.repeat(40) }]]) }, '2021');
  config = { ...config, repo: 'another/board' }; context.archGen++; release(undefined);
  await assert.rejects(pending, /board changed/); assert.equal(calls.length, 1, 'switched board never fetches or caches an old snapshot blob');
  config = { repo: 'synthetic/board', branch: 'main', path: 'board/tasks.json' }; context.archGen = 0; context.idb.get = async key => values.get(key);
  const cur = env({ custom: ['preserved'], tasks: Array.from({ length: 6 }, (_, n) => ({ id: 't_' + n, details: 'x'.repeat(350) })), history: { t_2: [{ text: 'older' }], t_live: [{ text: 'older live history' }] } });
  const before = clone(cur), parts = await context.api.shardArchiveFamily('2020', cur, {}, { archive: { files: {} } }, { files: new Map() }, config, 0);
  assert.ok(parts.size > 1); assert.deepEqual(cur, before); assert.deepEqual(parts.get('2020').custom, ['preserved']);
  const records = [], history = {};
  for (const value of parts.values()) { assert.ok(Buffer.byteLength(JSON.stringify(value,null,2)+'\n') <= 1000); records.push(...value.tasks); Object.assign(history,value.history);
    if (value.tasks.some(x => x.id === 't_2')) assert.deepEqual(clone(value.history.t_2), [{ text: 'older' }]); }
  assert.deepEqual(records.map(x => x.id).sort(), cur.tasks.map(x => x.id).sort()); assert.deepEqual(clone(history),cur.history);
  await assert.rejects(context.api.shardArchiveFamily('2020', env({ tasks:[{ id:'t_big', details:'x'.repeat(2000) }] }), {}, { archive:{files:{}} }, { files:new Map() }, config,0), /single logical/);
  await assert.rejects(context.api.shardArchiveFamily('2020',env({tasks:[null]}),{}, {archive:{files:{}}},{files:new Map()},config,0), /Invalid archive records/);
  serializations = 0;
  const large = env({ tasks:Array.from({length:1000},(_,n)=>({id:'t_'+n,title:'small record'})) });
  const packed = await context.api.shardArchiveFamily('2020',large,{}, {archive:{files:{}}},{files:new Map()},config,0);
  assert.ok(serializations < 1000 * 2 + packed.size * 4, 'packing serializes each logical record once, not growing whole-year prefixes');
  console.log('archive lazy/shard helper tests passed');
})().catch(e=>{console.error(e);process.exitCode=1;});

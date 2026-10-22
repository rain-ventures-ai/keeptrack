'use strict';
// Run real image helpers with deterministic ownership, time and API responses.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { File } = require('node:buffer');
const source = fs.readFileSync(path.join(__dirname, '../../board/board.js'), 'utf8');
module.exports = async function imageReview() {
  let now = 0, status = 500, requests = 0, revoked = [], nextUrl = 0, observer, ownerChecks = 0, watching = false;
  const makeOwner = (connected = false) => ({ nodeType: 1, connected, setAttribute() {}, querySelectorAll: () => [],
    get isConnected() { ownerChecks++; return this.connected; }, set isConnected(value) { this.connected = value; } });
  const context = vm.createContext({ Uint8Array, DataView, Blob, File, TextDecoder, Map, Set, WeakMap, queueMicrotask, Date: { now: () => now },
    IMG_MAX: 2 * 1024 * 1024, IMG_TYPES: { png: 'image/png' },
    MutationObserver: class { constructor(cb) { observer = cb; } observe() { watching = true; } disconnect() { watching = false; } },
    document: { documentElement: {}, querySelectorAll: () => { throw new Error('cache should not query the DOM per entry'); } },
    URL: { createObjectURL: () => `blob:${++nextUrl}`, revokeObjectURL: u => revoked.push(u) },
    remotePath: x => x, imgKind: () => 'image/png',
    gh: async () => { requests++; return { ok: status === 200, status, headers: new Headers(status === 403 ? { 'x-ratelimit-remaining': '0' } : {}), text: async () => '', arrayBuffer: async () => new ArrayBuffer(8) }; }
  });
  const flush = async () => { await Promise.resolve(); await Promise.resolve(); };
  vm.runInContext(source.slice(source.indexOf('  const imgCache ='), source.indexOf('  function imgKind(')) + '\nthis.api = { assetBlobUrl, cacheImage, cacheUploadedImage, imageOwnerReady, disposeImageEntry, imgCache, imgOwned, imgFailures };', context);
  const { api } = context;
  const load = async rel => { const owner = makeOwner(true); const url = await api.assetBlobUrl(rel, owner); owner.isConnected = false; api.imageOwnerReady(owner); await flush(); return url; };
  for (const code of [500, 429, 403, 404]) {
    status = code; requests = 0; now = 0; api.imgCache.clear(); api.imgOwned.clear(); api.imgFailures.clear();
    await load('x.png'); assert.equal(requests, 1);
    now = 30001; await load('x.png'); assert.equal(requests, 2, `${code} is retried`);
    now = 60002; await load('x.png'); assert.equal(requests, 2, `${code} backs off`);
    now = 90002; status = 200; assert.match(await load('x.png'), /^blob:/);
  }
  context.gh = async () => { requests++; return { ok: false, status: 403, headers: new Headers(), text: async () => 'Forbidden' }; };
  api.imgCache.clear(); api.imgOwned.clear(); api.imgFailures.clear(); requests = 0; now = 0;
  await load('x.png'); now = 9999999; await load('x.png'); assert.equal(requests, 1, 'ordinary permission denial stays final');

  const beforeMissingOwner = requests;
  assert.throws(() => api.assetBlobUrl('orphan.png'), /DOM owner/); assert.equal(requests, beforeMissingOwner);
  // Retry history survives reusable-cache eviction without retaining any blob/DOM owners.
  api.imgCache.clear(); api.imgOwned.clear(); api.imgFailures.clear(); now = 0; requests = 0;
  context.gh = async () => { requests++; return { ok: false, status: 500, headers: new Headers() }; };
  await load('retry.png');
  for (let i = 0; i < 121; i++) api.cacheImage(`filler${i}.png`, { settled: true, p: Promise.resolve(''), owners: new Map() });
  assert.equal(api.imgCache.has('retry.png'), false);
  now = 10000; await load('retry.png'); assert.equal(requests, 1, 'eviction does not reset the retry cooldown');
  now = 30001; await load('retry.png'); assert.equal(requests, 2); assert.equal(api.imgFailures.get('retry.png').retryMs, 60000);
  // Pending requests may exceed the reusable cache, but leases prevent revocation before assignment.
  const pending = [], owners = Array.from({ length: 300 }, () => makeOwner());
  context.gh = () => new Promise(resolve => pending.push(resolve));
  api.imgCache.clear(); api.imgOwned.clear(); api.imgFailures.clear(); revoked = [];
  ownerChecks = 0;
  const reads = owners.map((owner, i) => api.assetBlobUrl(`burst${i}.png`, owner));
  assert.equal(api.imgCache.size, 120);
  assert.equal(api.imgOwned.size, 180);
  pending.forEach(resolve => resolve({ ok: true, arrayBuffer: async () => new ArrayBuffer(8) }));
  const urls = await Promise.all(reads); await flush();
  assert.equal(ownerChecks, 0, 'settlement bookkeeping is constant per entry and never scans other owners');
  assert.equal(new Set(urls).size, 300); assert.deepEqual(revoked, [], 'settlement cannot revoke URLs awaiting their DOM assignment');
  owners.forEach(owner => { owner.isConnected = true; api.imageOwnerReady(owner); }); await flush();
  assert.deepEqual(revoked, [], 'displayed leases survive LRU eviction');
  ownerChecks = 0;
  for (let i = 0; i < 1000; i++) observer([{ removedNodes: [makeOwner()] }]);
  assert.equal(ownerChecks, 0, 'unrelated removed subtrees do not inspect existing image owners');
  owners.forEach(owner => { owner.isConnected = false; }); observer(owners.map(owner => ({ removedNodes: [owner] }))); await flush();
  assert.ok(ownerChecks <= owners.length, 'removal checks each affected owner once');
  assert.equal(watching, false, 'observer disconnects when the last lease is released');
  assert.equal(api.imgOwned.size, 0, 'removing displayed owners releases overflow without another cache access');
  assert.equal(api.imgCache.size, 120); assert.equal(revoked.length, 180);
  assert.ok([...api.imgCache.values()].every(e => e.owners.size === 0));

  // A render discarded while requests are pending is reclaimed after the promise's consumer finishes.
  pending.length = 0; api.imgCache.clear(); api.imgOwned.clear(); api.imgFailures.clear(); revoked = [];
  const abandoned = Array.from({ length: 150 }, () => makeOwner());
  const discarded = abandoned.map((owner, i) => api.assetBlobUrl(`gone${i}.png`, owner).then(u => { api.imageOwnerReady(owner); return u; }));
  pending.forEach(resolve => resolve({ ok: true, arrayBuffer: async () => new ArrayBuffer(8) }));
  await Promise.all(discarded); await flush();
  assert.equal(api.imgCache.size, 120); assert.equal(api.imgOwned.size, 0); assert.equal(revoked.length, 30);

  api.imgCache.clear(); api.imgOwned.clear(); api.imgFailures.clear(); revoked = []; pending.length = 0;
  const racingOwner = makeOwner(true), racing = api.assetBlobUrl('recreated.png', racingOwner);
  assert.equal(pending.length, 1);
  api.cacheUploadedImage('recreated.png', new Uint8Array([1,2,3]), 'image/png');
  const uploadedUrl = api.imgCache.get('recreated.png').url;
  for (let i = 0; i < 121; i++) api.cacheImage(`later${i}.png`, { settled: true, p: Promise.resolve(''), owners: new Map() });
  assert.ok(!revoked.includes(uploadedUrl), 'supersession transfers pending leases before LRU eviction');
  pending[0]({ ok: false, status: 404, headers: new Headers() });
  assert.equal(await racing, uploadedUrl, 'older GET hands out uploaded bytes instead of a stale 404');
  assert.equal(api.imgFailures.has('recreated.png'), false, 'superseded settlement cannot recreate failure history');
  racingOwner.connected = false; api.imageOwnerReady(racingOwner);
  assert.ok(revoked.includes(uploadedUrl), 'transferred lease releases normally after use');
  vm.runInContext(source.slice(source.indexOf('  async function redrawImage('), source.indexOf('  const b64 =')) + '\nthis.strip = strippedImage; this.redraw = redrawImage;', context);
  const ch = (kind, body, little = false) => { const b = Buffer.alloc(8 + body.length + (little ? body.length % 2 : 4)); b.write(kind, little ? 0 : 4); if (little) b.writeUInt32LE(body.length, 4); else b.writeUInt32BE(body.length, 0); body.copy(b, 8); return b; };
  const strip = async (b, type) => { const result = await context.strip(new File([b], 'image', { type })); assert.ok(result, `${type} parses`); return { ...result, bytes: Buffer.from(await result.blob.arrayBuffer()) }; };
  const pngHead = Buffer.from([137,80,78,71,13,10,26,10]);
  const ihdr = Buffer.alloc(13); ihdr.writeUInt32BE(1, 0); ihdr.writeUInt32BE(1, 4); ihdr[8] = 8; ihdr[9] = 2;
  const control = sequence => { const b = Buffer.alloc(26); b.writeUInt32BE(sequence); b.writeUInt32BE(1, 4); b.writeUInt32BE(1, 8); return b; };
  const frames = Buffer.concat([ch('IHDR', ihdr), ch('acTL', Buffer.from([0,0,0,2,0,0,0,0])), ch('fcTL', control(0)), ch('IDAT', require('node:zlib').deflateSync(Buffer.from([0,17,34,51]))), ch('fcTL', control(1)), ch('fdAT', Buffer.concat([Buffer.from([0,0,0,2]), require('node:zlib').deflateSync(Buffer.from([0,51,34,17]))])), ch('IEND', Buffer.alloc(0))]);
  const apng = await strip(Buffer.concat([pngHead, ch('tEXt', Buffer.from('GPS')), ch('vpAg', Buffer.from('AUTHOR')), ch('iCCP', Buffer.from('PROFILE-AUTHOR')), frames]), 'image/png');
  assert.equal(apng.bytes.includes(Buffer.from('acTL')), false); assert.equal(apng.bytes.includes(Buffer.from('fdAT')), false); assert.equal(apng.animated, false); assert.equal(apng.stillOnly, true); assert.equal(apng.profiled, true);
  const still = await strip(Buffer.concat([pngHead, ch('IDAT', Buffer.from('pixels-acTL-still')), ch('IEND', Buffer.alloc(0))]), 'image/png');
  assert.equal(still.animated, false, 'acTL in compressed pixel bytes does not mean animation');
  const stillChunks = [ch('IHDR', ihdr), ch('IDAT', Buffer.from('pixels'))];
  assert.equal(await context.strip(new File([Buffer.concat([pngHead, ch('IHDR', ihdr), ...Array(4097).fill(ch('IDAT', Buffer.alloc(0))), ch('IEND', Buffer.alloc(0))])], 'many.png', { type: 'image/png' })), null, 'PNG chunk budget is checked before retaining views');
  const orphaned = await strip(Buffer.concat([pngHead, ...stillChunks, ch('fdAT', Buffer.from('HIDDEN-AUTHOR')), ch('IEND', Buffer.alloc(0))]), 'image/png');
  assert.equal(orphaned.animated, false); assert.equal(orphaned.bytes.includes('HIDDEN-AUTHOR'), false, 'ignored still-image fdAT data is dropped');
  for (const [kind, size] of [['cICP',4], ['mDCV',24], ['cLLI',8]]) {
    const coloured = await strip(Buffer.concat([pngHead, ch('IHDR', ihdr), ch(kind, Buffer.alloc(size)), ch('IDAT', Buffer.from('pixels')), ch('IEND', Buffer.alloc(0))]), 'image/png');
    assert.equal(coloured.profiled, true, `${kind} removal requires canvas colour conversion`);
  }
  const ignoredFrame = await strip(Buffer.concat([pngHead, ch('IHDR', ihdr), ch('acTL', Buffer.from([0,0,0,2,0,0,0,0])), ch('fcTL', control(0)),
    ch('IDAT', require('node:zlib').deflateSync(Buffer.from([0,17,34,51]))), ch('fcTL', control(1)), ch('fdAT', Buffer.concat([Buffer.from([0,0,0,2]), Buffer.from('PRIVATE-NON-ZLIB-FRAME')])), ch('IEND', Buffer.alloc(0))]), 'image/png');
  assert.equal(ignoredFrame.stillOnly, true); assert.equal(ignoredFrame.bytes.includes('PRIVATE'), false);
  assert.equal(Buffer.from(await ignoredFrame.poster.arrayBuffer()).includes('PRIVATE'), false, 'canvas source also excludes every animation stream');
  const frame = Buffer.concat([Buffer.alloc(16), ch('VP8 ', Buffer.from('frame pixels'), true), ch('AUTH', Buffer.from('FRAME-AUTHOR'), true)]);
  const chunks = Buffer.concat([ch('VP8X', Buffer.from([46,0,0,0,0,0,0,0,0,0]), true), ch('ANIM', Buffer.alloc(6), true), ch('ANMF', frame, true), ch('ANMF', frame, true), ch('ICCP', Buffer.from('PROFILE-AUTHOR'), true), ch('AUTH', Buffer.from('AUTHOR'), true)]);
  const riff = chunks => { const h = Buffer.from('RIFF0000WEBP'); h.writeUInt32LE(chunks.length + 4, 4); return Buffer.concat([h, chunks]); };
  const webp = await strip(Buffer.concat([riff(chunks), ch('EXIF', Buffer.from('GPS!'), true)]), 'image/webp');
  assert.equal(webp.bytes.includes(Buffer.from('AUTHOR')), false); assert.equal(webp.bytes[20], 2, 'only animation flag survives');
  assert.equal(webp.bytes.toString().split('ANMF').length, 3); assert.equal(webp.animated, true); assert.equal(webp.profiled, true);
  for (const kind of ['VP8L', 'VP8 ']) {
    const simple = await strip(riff(ch(kind, Buffer.from([0x2f,1,2,3]), true)), 'image/webp');
    assert.equal(simple.animated, false, `${kind} payload bits are not VP8X flags`);
  }
  for (const malformed of [
    riff(ch('VP8X', Buffer.from([2,0,0,0,0,0,0,0,0,0]), true)),
    riff(Buffer.concat([ch('VP8X', Buffer.from([2,0,0,0,0,0,0,0,0,0]), true), ch('ANIM', Buffer.alloc(6), true)])),
    riff(Buffer.concat([ch('VP8X', Buffer.from([2,0,0,0,0,0,0,0,0,0]), true), ch('ANIM', Buffer.alloc(6), true), ch('ANMF', Buffer.alloc(16), true)]))
  ]) assert.equal(await context.strip(new File([malformed], 'bad.webp', { type: 'image/webp' })), null, 'animation bit without control/pixel frames is refused');
  for (const body of [ch('VP8 ', Buffer.alloc(0), true), Buffer.concat([ch('VP8 ', Buffer.from('x'), true), ch('VP8L', Buffer.from('x'), true)]), Buffer.concat(Array(4097).fill(ch('JUNK', Buffer.alloc(0), true)))]) {
    assert.equal(await context.strip(new File([riff(body)], 'bad.webp', { type: 'image/webp' })), null, 'empty, duplicate and excessive WebP chunks are rejected');
  }
  const animatedHead = Buffer.concat([ch('VP8X', Buffer.from([2,0,0,0,0,0,0,0,0,0]), true), ch('ANIM', Buffer.alloc(6), true)]);
  assert.equal(await context.strip(new File([riff(Buffer.concat([animatedHead, ...Array(513).fill(ch('ANMF', frame, true))]))], 'bad.webp', { type: 'image/webp' })), null, 'WebP frame budget is bounded independently of chunks');
  const gifHead = Buffer.from('47494638396101000100800000000000ffffff', 'hex'), gifFrame = Buffer.from('2c0000000001000100000202440100', 'hex');
  const gce = Buffer.from('21f9040107000000', 'hex'), text = Buffer.concat([Buffer.from([0x21,1,12]), Buffer.alloc(12), Buffer.from([1,65,0])]);
  for (const extension of [text, Buffer.from([0x21,0xfe,1,65,0])]) {
    const result = await strip(Buffer.concat([gifHead, gce, extension, gifFrame, Buffer.from([0x3b])]), 'image/gif');
    assert.equal(result.bytes.includes(gce), extension !== text, 'plaintext consumes its graphics control, comments do not');
  }
  const seg = (m, body) => Buffer.concat([Buffer.from([255,m,0,body.length + 2]), body]);
  const scans = Buffer.concat([seg(218, Buffer.alloc(0)), Buffer.from('scan'), ...[225,226,227,235,236,237,239].map(m => seg(m, Buffer.from('AUTHOR'))), seg(196, Buffer.from([255,217,1])), seg(218, Buffer.alloc(0)), Buffer.from([2,255,217])]);
  const jpeg = await strip(Buffer.concat([Buffer.from([255,216]), scans]), 'image/jpeg');
  assert.equal(jpeg.bytes.includes(Buffer.from('AUTHOR')), false); assert.equal(jpeg.bytes.at(-3), 2, 'table bytes cannot truncate the final scan');
  const jfif = Buffer.concat([Buffer.from('JFIF\0'), Buffer.from([1,2,0,0,1,0,1,1,1]), Buffer.from('AUTHOR-THUMBNAIL')]);
  const tagged = await strip(Buffer.concat([Buffer.from([255,216]), seg(224, jfif), seg(226, Buffer.from('ICC_PROFILE\0PROFILE-AUTHOR')), scans]), 'image/jpeg');
  assert.equal(tagged.bytes.includes(Buffer.from('AUTHOR')), false); assert.equal(tagged.profiled, true);

  // Export failures still close the decoded bitmap, including exceptions from canvas.toBlob.
  let closed = 0;
  context.createImageBitmap = async () => ({ width: 10, height: 10, close: () => { closed++; } });
  context.document.createElement = () => ({ getContext: () => ({ drawImage() {} }), toBlob: () => { throw new Error('export failed'); } });
  assert.equal(await context.redraw(new File([], 'x.png', { type: 'image/png' })), null); assert.equal(closed, 1);
  context.document.createElement = () => ({ getContext: () => ({ drawImage() {} }), toBlob: callback => callback(new Blob([Buffer.alloc(32)])) });
  const small = new Blob([Buffer.alloc(1)]), file = new File([], 'x.png', { type: 'image/png' });
  assert.equal((await context.redraw(file, small, false)).size, 32, 'all stills export decoded pixels even when the original is smaller');
  assert.equal((await context.redraw(file, small, true)).size, 32, 'profiled stills must use converted canvas pixels');
  context.document.createElement = () => ({ getContext: () => ({ drawImage() {} }), toBlob: callback => callback(null) });
  assert.equal(await context.redraw(file, small, false), null, 'null exports fail closed instead of returning compressed source bytes');
  assert.equal(await context.redraw(file, small, true), null, 'required conversion still fails closed on null export');
  context.document.createElement = () => ({ getContext: () => ({ drawImage() {} }), toBlob: callback => callback(new Blob([Buffer.alloc(32)])) });
  context.createImageBitmap = async () => ({ width: 4000, height: 2, close() {} });
  assert.equal((await context.redraw(file, small, false)).size, 32, 'small compressed originals cannot bypass required dimension scaling');

};
if (require.main === module) module.exports().then(() => console.log('image-review: all checks passed')).catch(e => { console.error(e); process.exitCode = 1; });

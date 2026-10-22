'use strict';
// Run real image helpers with deterministic ownership, time and API responses.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { File } = require('node:buffer');
const source = fs.readFileSync(path.join(__dirname, '../../board/board.js'), 'utf8');
module.exports = async function imageReview() {
  let now = 0, status = 500, requests = 0, revoked = [], nextUrl = 0, observer;
  const context = vm.createContext({ Uint8Array, DataView, Blob, File, TextDecoder, Map, Set, WeakMap, queueMicrotask, Date: { now: () => now },
    IMG_MAX: 2 * 1024 * 1024, IMG_TYPES: { png: 'image/png' },
    MutationObserver: class { constructor(cb) { observer = cb; } observe() {} },
    document: { documentElement: {}, querySelectorAll: () => { throw new Error('cache should not query the DOM per entry'); } },
    URL: { createObjectURL: () => `blob:${++nextUrl}`, revokeObjectURL: u => revoked.push(u) },
    remotePath: x => x, imgKind: () => 'image/png',
    gh: async () => { requests++; return { ok: status === 200, status, headers: new Headers(status === 403 ? { 'x-ratelimit-remaining': '0' } : {}), text: async () => '', arrayBuffer: async () => new ArrayBuffer(8) }; }
  });
  const flush = async () => { await Promise.resolve(); await Promise.resolve(); };
  vm.runInContext(source.slice(source.indexOf('  const imgCache ='), source.indexOf('  function imgKind(')) + '\nthis.api = { assetBlobUrl, cacheImage, imageOwnerReady, pruneImageCache, imgCache, imgOwned };', context);
  const { api } = context;
  const load = async rel => { const owner = { isConnected: true }; const url = await api.assetBlobUrl(rel, owner); api.imageOwnerReady(owner); owner.isConnected = false; await flush(); return url; };
  for (const code of [500, 429, 403, 404]) {
    status = code; requests = 0; now = 0; api.imgCache.clear(); api.imgOwned.clear();
    await load('x.png'); assert.equal(requests, 1);
    now = 30001; await load('x.png'); assert.equal(requests, 2, `${code} is retried`);
    now = 60002; await load('x.png'); assert.equal(requests, 2, `${code} backs off`);
    now = 90002; status = 200; assert.match(await load('x.png'), /^blob:/);
  }
  context.gh = async () => { requests++; return { ok: false, status: 403, headers: new Headers(), text: async () => 'Forbidden' }; };
  api.imgCache.clear(); api.imgOwned.clear(); requests = 0; now = 0;
  await load('x.png'); now = 9999999; await load('x.png'); assert.equal(requests, 1, 'ordinary permission denial stays final');

  // Pending requests may exceed the reusable cache, but leases prevent revocation before assignment.
  const pending = [], owners = Array.from({ length: 300 }, () => ({ isConnected: false }));
  context.gh = () => new Promise(resolve => pending.push(resolve));
  api.imgCache.clear(); api.imgOwned.clear(); revoked = [];
  const reads = owners.map((owner, i) => api.assetBlobUrl(`burst${i}.png`, owner));
  assert.equal(api.imgCache.size, 120);
  assert.equal(api.imgOwned.size, 180);
  pending.forEach(resolve => resolve({ ok: true, arrayBuffer: async () => new ArrayBuffer(8) }));
  const urls = await Promise.all(reads); await flush();
  assert.equal(new Set(urls).size, 300); assert.deepEqual(revoked, [], 'settlement cannot revoke URLs awaiting their DOM assignment');
  owners.forEach(owner => { owner.isConnected = true; api.imageOwnerReady(owner); }); await flush();
  assert.deepEqual(revoked, [], 'displayed leases survive LRU eviction');
  owners.forEach(owner => { owner.isConnected = false; }); observer(); await flush();
  assert.equal(api.imgOwned.size, 0, 'removing displayed owners releases overflow without another cache access');
  assert.equal(api.imgCache.size, 120); assert.equal(revoked.length, 180);
  assert.ok([...api.imgCache.values()].every(e => e.owners.size === 0));

  // A render discarded while requests are pending is reclaimed after the promise's consumer finishes.
  pending.length = 0; api.imgCache.clear(); api.imgOwned.clear(); revoked = [];
  const abandoned = Array.from({ length: 150 }, () => ({ isConnected: false }));
  const discarded = abandoned.map((owner, i) => api.assetBlobUrl(`gone${i}.png`, owner).then(u => { api.imageOwnerReady(owner); return u; }));
  pending.forEach(resolve => resolve({ ok: true, arrayBuffer: async () => new ArrayBuffer(8) }));
  await Promise.all(discarded); await flush();
  assert.equal(api.imgCache.size, 120); assert.equal(api.imgOwned.size, 0); assert.equal(revoked.length, 30);

  vm.runInContext(source.slice(source.indexOf('  async function redrawImage('), source.indexOf('  const b64 =')) + '\nthis.strip = strippedImage; this.redraw = redrawImage;', context);
  const ch = (kind, body, little = false) => { const b = Buffer.alloc(8 + body.length + (little ? body.length % 2 : 4)); b.write(kind, little ? 0 : 4); if (little) b.writeUInt32LE(body.length, 4); else b.writeUInt32BE(body.length, 0); body.copy(b, 8); return b; };
  const strip = async (b, type) => { const result = await context.strip(new File([b], 'image', { type })); assert.ok(result, `${type} parses`); return { ...result, bytes: Buffer.from(await result.blob.arrayBuffer()) }; };
  const pngHead = Buffer.from([137,80,78,71,13,10,26,10]);
  const frames = Buffer.concat([ch('acTL', Buffer.alloc(8)), ch('fcTL', Buffer.alloc(26)), ch('IDAT', Buffer.from('pixels')), ch('fdAT', Buffer.from('frame2')), ch('IEND', Buffer.alloc(0))]);
  const apng = await strip(Buffer.concat([pngHead, ch('tEXt', Buffer.from('GPS')), ch('vpAg', Buffer.from('AUTHOR')), ch('iCCP', Buffer.from('PROFILE-AUTHOR')), frames]), 'image/png');
  assert.deepEqual(apng.bytes, Buffer.concat([pngHead, frames])); assert.equal(apng.animated, true); assert.equal(apng.profiled, true);
  const still = await strip(Buffer.concat([pngHead, ch('IDAT', Buffer.from('pixels-acTL-still')), ch('IEND', Buffer.alloc(0))]), 'image/png');
  assert.equal(still.animated, false, 'acTL in compressed pixel bytes does not mean animation');
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
  assert.equal((await context.redraw(file, small, false)).size, 1, 'unscaled safe originals may win the size comparison');
  assert.equal((await context.redraw(file, small, true)).size, 32, 'profiled stills must use converted canvas pixels');
  context.createImageBitmap = async () => ({ width: 4000, height: 2, close() {} });
  assert.equal((await context.redraw(file, small, false)).size, 32, 'small compressed originals cannot bypass required dimension scaling');

};
if (require.main === module) module.exports().then(() => console.log('image-review: all checks passed')).catch(e => { console.error(e); process.exitCode = 1; });

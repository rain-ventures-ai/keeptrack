'use strict';
// Exercise the real helpers, with deterministic time and API responses for cache policy.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { File } = require('node:buffer');
const source = fs.readFileSync(path.join(__dirname, '../../board/board.js'), 'utf8');
module.exports = async function imageReview() {
  let now = 0, status = 500, requests = 0, displayed = [], revoked = [];
  const context = vm.createContext({ Uint8Array, DataView, Blob, File, TextDecoder, Date: { now: () => now },
    IMG_KEEP: 120, IMG_MAX: 2 * 1024 * 1024, IMG_TYPES: { png: 'image/png' },
    document: { querySelectorAll: () => displayed }, URL: { createObjectURL: () => 'blob:ok', revokeObjectURL: u => revoked.push(u) },
    remotePath: x => x, imgKind: () => 'image/png',
    gh: async () => { requests++; return { ok: status === 200, status, headers: new Headers(status === 403 ? { 'x-ratelimit-remaining': '0' } : {}), text: async () => '', arrayBuffer: async () => new ArrayBuffer(8) }; }
  });
  vm.runInContext(source.slice(source.indexOf('  const imgCache ='), source.indexOf('  function imgKind(')) + '\nthis.api = { assetBlobUrl, cacheImage, imgCache };', context);
  const { api } = context;
  for (const code of [500, 429, 403, 404]) {
    status = code; requests = 0; now = 0; api.imgCache.clear();
    await api.assetBlobUrl('x.png'); assert.equal(requests, 1);
    now = 30001; await api.assetBlobUrl('x.png'); assert.equal(requests, 2, `${code} is retried`);
    now = 60002; await api.assetBlobUrl('x.png'); assert.equal(requests, 2, `${code} backs off`);
    now = 90002; status = 200; assert.equal(await api.assetBlobUrl('x.png'), 'blob:ok');
  }
  status = 403; // plain permission denial stays final
  context.gh = async () => { requests++; return { ok: false, status: 403, headers: new Headers(), text: async () => 'Forbidden' }; };
  api.imgCache.clear(); requests = 0; now = 0; await api.assetBlobUrl('x.png'); now = 9999999; await api.assetBlobUrl('x.png'); assert.equal(requests, 1);
  api.imgCache.clear(); displayed = [{ src: 'blob:visible' }]; revoked = [];
  api.cacheImage('visible', { settled: true, url: 'blob:visible' });
  for (let i = 0; i < 120; i++) api.cacheImage(String(i), { settled: true, url: `blob:${i}` });
  assert.equal(api.imgCache.has('visible'), true); assert.deepEqual(revoked, ['blob:0']);
  displayed = []; api.cacheImage('next', { settled: true, url: 'blob:next' });
  assert.equal(api.imgCache.has('visible'), false); assert.ok(revoked.includes('blob:visible'), 'off-screen URL is eventually revoked');

  vm.runInContext(source.slice(source.indexOf('  async function strippedImage('), source.indexOf('  const b64 =')) + '\nthis.strip = strippedImage;', context);
  const ch = (kind, body, little = false) => { const b = Buffer.alloc(8 + body.length + (little ? body.length % 2 : 4)); b.write(kind, little ? 0 : 4); if (little) b.writeUInt32LE(body.length, 4); else b.writeUInt32BE(body.length, 0); body.copy(b, 8); return b; };
  const strip = async (b, type) => Buffer.from(await (await context.strip(new File([b], 'image', { type }))).arrayBuffer());
  const pngHead = Buffer.from([137,80,78,71,13,10,26,10]);
  const frames = Buffer.concat([ch('acTL', Buffer.alloc(8)), ch('fcTL', Buffer.alloc(26)), ch('IDAT', Buffer.from('pixels')), ch('fdAT', Buffer.from('frame2')), ch('IEND', Buffer.alloc(0))]);
  assert.deepEqual(await strip(Buffer.concat([pngHead, ch('tEXt', Buffer.from('GPS')), frames]), 'image/png'), Buffer.concat([pngHead, frames]), 'APNG frames survive stripping');
  const chunks = Buffer.concat([ch('VP8X', Buffer.from([14,0,0,0,0,0,0,0,0,0]), true), ch('ANIM', Buffer.alloc(6), true), ch('ANMF', Buffer.from('frame1'), true), ch('ANMF', Buffer.from('frame2'), true)]);
  const h = Buffer.from('RIFF0000WEBP'); h.writeUInt32LE(chunks.length + 4, 4);
  const webp = Buffer.concat([h, chunks]); const clean = await strip(Buffer.concat([webp, ch('EXIF', Buffer.from('GPS!'), true)]), 'image/webp');
  assert.equal(clean.includes(Buffer.from('GPS!')), false); assert.equal(clean[20], 2, 'animation flag kept, EXIF and XMP cleared'); assert.equal(clean.toString().split('ANMF').length, 3);
  const seg = (m, body) => Buffer.concat([Buffer.from([255,m,0,body.length + 2]), body]);
  const scans = Buffer.concat([seg(218, Buffer.alloc(0)), Buffer.from('scan'), seg(225, Buffer.from('GPS!')), seg(196, Buffer.from([255,217,1])), seg(218, Buffer.alloc(0)), Buffer.from([2,255,217])]);
  const jpeg = await strip(Buffer.concat([Buffer.from([255,216]), scans]), 'image/jpeg'); assert.equal(jpeg.includes(Buffer.from('GPS!')), false); assert.equal(jpeg.at(-3), 2, 'progressive table cannot truncate the final scan');
};
if (require.main === module) module.exports().then(() => console.log('image-review: all checks passed')).catch(e => { console.error(e); process.exitCode = 1; });

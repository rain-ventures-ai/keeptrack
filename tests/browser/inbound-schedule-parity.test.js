'use strict';
// kit v122: the web board's inbound schedule rules (board.js) give the same answers as keeptrack.py's (inbound_expected_run,
// inbound_stopped, inbound_attention), across time zones, summer time changes, weekends and grace times.
// No browser: the functions are cut out of board.js and run here.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { execFileSync } = require('node:child_process');

const ROOT = path.resolve(__dirname, '../..');
const src = fs.readFileSync(path.join(ROOT, 'board/board.js'), 'utf8');
const from = src.indexOf("  const INBOUND_DAYS = ["), to = src.indexOf('  function inboundBar() {');
assert.ok(from > 0 && to > from, 'the inbound schedule functions are in board.js');
const lib = new Function(src.slice(from, to) + '\nreturn { inboundSchedule, inboundExpectedRun, inboundAlert };')();

const schedules = [
  { days: ['mon', 'tue', 'wed', 'thu', 'fri'], times: ['09:07', '11:07', '14:07', '16:07'], tz: 'Europe/London', grace_minutes: 30 },
  { days: ['mon', 'wed', 'sat'], times: ['23:50', '00:10'], tz: 'America/New_York', grace_minutes: 5 },
  { days: ['sun'], times: ['03:00'], tz: 'Australia/Sydney', grace_minutes: 720 },
  { days: ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'], times: ['06:30'], grace_minutes: 1 },
  { days: ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'], times: ['01:30', '02:30'], tz: 'Europe/London', grace_minutes: 30 },   // the repeated and the missing hour
  { days: ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'], times: ['02:30'], tz: 'America/New_York', grace_minutes: 30 },
  { days: ['sun'], times: ['09:00'], tz: 'Asia/Kolkata', grace_minutes: 10 },
];
const instants = [];   // a spread of instants, and ones next to the 2026 clock changes (London 25 Oct and 29 Mar, New York 1 Nov, Sydney 4 Oct)
for (let t = Date.UTC(2026, 2, 27); t < Date.UTC(2026, 10, 6); t += 7 * 3600000 + 11 * 60000) instants.push(t);
for (const d of [[2026, 9, 25], [2026, 2, 29], [2026, 10, 1], [2026, 9, 4], [2026, 2, 8], [2026, 9, 24], [2026, 9, 26]]) for (let h = -6; h <= 30; h += 1.5) instants.push(Date.UTC(d[0], d[1], d[2]) + h * 3600000);
const iso = ms => new Date(ms).toISOString().replace('.000Z', 'Z');

const py = `
import json, sys, datetime as dt
sys.path.insert(0, ${JSON.stringify(path.join(ROOT, 'board/kit'))})
import keeptrack
cases = json.load(sys.stdin)
out = []
for sched, instants in cases:
    s = keeptrack.inbound_schedule({"settings": {"inbound_schedule": sched}})
    row = []
    for i in instants:
        at = dt.datetime.fromisoformat(i.replace("Z", "+00:00"))
        r = keeptrack.inbound_expected_run(s, at); f = keeptrack.inbound_expected_run(s, at, True)
        row.append([r and r.strftime("%Y-%m-%dT%H:%M:%SZ"), f and f.strftime("%Y-%m-%dT%H:%M:%SZ")])
    out.append(row)
print(json.dumps(out))
`;
const expected = JSON.parse(execFileSync('python3', ['-I', '-c', py], { input: JSON.stringify(schedules.map(s => [s, instants.map(iso)])), encoding: 'utf8' }));
let checked = 0;
schedules.forEach((raw, i) => {
  const s = lib.inboundSchedule({ inbound_schedule: raw });
  assert.ok(s, 'a valid schedule');
  instants.forEach((at, j) => {
    const r = lib.inboundExpectedRun(s, at), f = lib.inboundExpectedRun(s, at, true);
    assert.deepEqual([r === null ? null : iso(r), f === null ? null : iso(f)], expected[i][j], `${JSON.stringify(raw)} at ${iso(at)}`);
    checked++;
  });
});
for (const bad of [{ days: ['funday'], times: ['09:00'] }, { days: ['mon'], times: ['25:00'] }, { days: ['mon'], times: [] }, { days: ['mon'], times: ['09:00'], tz: 'Not/AZone' },
  { days: ['mon'], times: ['09:00'], tz: '' }, { days: ['mon'], times: ['09:00'], tz: '+05:30' }, { days: ['mon'], times: ['09:00'], tz: '+01:00' }, { days: ['mon'], times: ['09:00'], grace_minutes: 0 }, { days: ['mon'], times: ['09:00'], grace_minutes: true }, 'mon 09:00', null]) {
  assert.equal(lib.inboundSchedule({ inbound_schedule: bad }), null, JSON.stringify(bad));
}
// alerts: the same cases as tests/test_kit_v122.py
const sch = { inbound_schedule: schedules[0] }, NAME = '20261030T170000Z-rainshift-contact-a.json', at = t => Date.parse(t + 'Z');
for (const now of ['2026-10-30T20:00:00', '2026-10-31T03:00:00', '2026-11-01T12:00:00', '2026-11-02T09:20:00']) assert.equal(lib.inboundAlert([NAME], {}, sch, at(now)).waiting, 0, now);
let a = lib.inboundAlert([NAME], {}, sch, at('2026-11-02T09:40:00'));
assert.equal(a.waiting, 1); assert.equal(a.missed, 'Mon 09:07');
a = lib.inboundAlert(['20261030T140000Z-rainshift-contact-b.json'], {}, sch, at('2026-10-30T14:40:00'));
assert.equal(a.waiting, 1); assert.equal(a.missed, 'Fri 14:07');
assert.equal(lib.inboundAlert(['20261030T140000Z-rainshift-contact-b.json'], {}, sch, at('2026-10-30T14:20:00')).waiting, 0);
assert.equal(lib.inboundAlert(['odd.json'], {}, sch, at('2026-10-30T14:20:00')).waiting, 1);
assert.equal(lib.inboundAlert([NAME], {}, {}, at('2026-10-30T18:00:00')).waiting, 0);   // no schedule: 1 hour
assert.equal(lib.inboundAlert([NAME], {}, {}, at('2026-10-30T19:30:00')).waiting, 1);   // 2.5 hours
const last = v => ({ last_run: { at: v, handled: 0, failed: 0 } });
const st = lib.inboundAlert([], last('2026-10-30T09:08:01.000Z'), sch, at('2026-11-02T09:40:00')).stopped;
assert.deepEqual([st.since, st.expected, st.future], ['Fri 09:08', 'Mon 09:07', false]);
assert.equal(lib.inboundAlert([], last('2026-11-02T09:08:01.000Z'), sch, at('2026-11-02T09:40:00')).stopped, null);
assert.equal(lib.inboundAlert([], last('2026-10-30T09:08:01.000Z'), sch, at('2026-11-02T09:20:00')).stopped, null);
assert.equal(lib.inboundAlert([], last('2026-10-30T09:08:01.000Z'), sch, at('2026-11-01T12:00:00')).stopped, null);
assert.equal(lib.inboundAlert([], {}, sch, at('2026-11-02T09:40:00')).stopped, null);
assert.equal(lib.inboundAlert([], last('2026-10-30T09:08:01'), sch, at('2026-11-02T09:40:00')).stopped, null);
assert.equal(lib.inboundAlert([], last('2026-11-12T09:08:00.000Z'), sch, at('2026-11-11T09:40:00')).stopped.future, true);   // a last run in the future does not hide a dead drain
assert.equal(lib.inboundSchedule({ inbound_schedule: { days: ['mon'], times: ['09:00'] } }).tz, 'UTC');   // no zone: UTC for every reader   // a time without a zone is ignored, as in Python
console.log(`inbound schedule parity: ok (${checked} instants)`);

"""Kit v71 Review Inbox read-time rules: the shared cases in tests/fixtures/inbox-rules-cases.json give the same result in
keeptrack.py (inbox_lapse_days, recommended_option, ask_lapsed) and board.js (inboxLapseDays, recommendedOption, askLapsed)."""
import json, os, shutil, subprocess, sys, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "board", "kit"))
import keeptrack  # noqa: E402

CASES = json.load(open(os.path.join(HERE, "fixtures", "inbox-rules-cases.json"), encoding="utf-8"))
# board.js keeps these inside the page closure: cut the block between its markers.
NODE = r"""
const src = require('fs').readFileSync(process.argv[1], 'utf8');
const a = src.indexOf('  // >>> inbox-rules'), b = src.indexOf('  // <<< inbox-rules');
if (a < 0 || b < a) { console.error('inbox-rules block not found in board.js'); process.exit(2); }
const f = new Function(src.slice(a, b) + '\nreturn { inboxLapseDays, recommendedOption, askLapsed };')();
let raw = ''; process.stdin.setEncoding('utf8'); process.stdin.on('data', x => raw += x);
process.stdin.on('end', () => { const c = JSON.parse(raw); process.stdout.write(JSON.stringify({
  lapse_days: c.lapse_days.map(x => f.inboxLapseDays(x.settings)),
  recommended: c.recommended.map(x => { const o = f.recommendedOption(x.change); return o ? o.key : null; }),
  lapsed: c.lapsed.map(x => f.askLapsed(x.p, x.today, x.days, x.zone)) })); });
"""


def python_results():
    rec = [keeptrack.recommended_option(c["change"]) for c in CASES["recommended"]]
    return {"lapse_days": [keeptrack.inbox_lapse_days({"settings": c["settings"]}) for c in CASES["lapse_days"]],
            "recommended": [o["key"] if o else None for o in rec],
            "lapsed": [keeptrack.ask_lapsed(c["p"], c["today"], c["days"], c.get("zone")) for c in CASES["lapsed"]]}


class InboxRulesParity(unittest.TestCase):
    def check(self, got):
        for group in ("lapse_days", "recommended", "lapsed"):
            for case, value in zip(CASES[group], got[group], strict=True):
                with self.subTest(group=group, case=case["name"]):
                    self.assertEqual(case["want"], value)

    def test_python_follows_the_shared_cases(self):
        self.check(python_results())

    @unittest.skipUnless(shutil.which("node"), "node is not installed")
    def test_board_js_follows_the_shared_cases(self):
        proc = subprocess.run(["node", "-e", NODE, os.path.join(ROOT, "board", "board.js")],
                              input=json.dumps(CASES), text=True, capture_output=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.check(json.loads(proc.stdout))


if __name__ == "__main__":
    unittest.main()

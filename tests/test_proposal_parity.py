"""Proposal accept parity: the shared cases in tests/fixtures/proposal-change-cases.json are refused alike by keeptrack.py
(check_stored_change) and board.js (proposalRefusal)."""
import contextlib, io, json, os, shutil, subprocess, sys, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "board", "kit"))
import keeptrack  # noqa: E402

CASES = json.load(open(os.path.join(HERE, "fixtures", "proposal-change-cases.json"), encoding="utf-8"))["cases"]
# board.js keeps proposalRefusal inside the page closure: cut the block from CHANGE_FIELDS to the end of proposalRefusal.
NODE = r"""
const src = require('fs').readFileSync(process.argv[1], 'utf8');
const a = src.indexOf('  const CHANGE_FIELDS = {'), b = src.indexOf('  let inboxF = ');
if (a < 0 || b < a) { console.error('proposalRefusal block not found in board.js'); process.exit(2); }
const refusal = new Function('validRank', 'const isObj = v => !!v && typeof v === "object" && !Array.isArray(v);\n' + src.slice(a, b) + '\nreturn proposalRefusal;')(require(process.argv[1]).validRank);
let raw = ''; process.stdin.setEncoding('utf8'); process.stdin.on('data', x => raw += x);
process.stdin.on('end', () => process.stdout.write(JSON.stringify(JSON.parse(raw).map(c => refusal({ kind: c.kind }, c.change)))));
"""


def python_ok(case):
    try:
        with contextlib.redirect_stderr(io.StringIO()):
            keeptrack.check_stored_change({"id": "r_case", "kind": case["kind"], "change": case["change"]})
        return True
    except SystemExit:
        return False


class ProposalParity(unittest.TestCase):
    def test_python_refuses_the_shared_cases(self):
        for c in CASES:
            with self.subTest(c["name"]):
                self.assertEqual(python_ok(c), c["ok"])

    @unittest.skipUnless(shutil.which("node"), "node is not installed")
    def test_board_js_refuses_the_shared_cases(self):
        proc = subprocess.run(["node", "-e", NODE, os.path.join(ROOT, "board", "board.js")],
                              input=json.dumps(CASES), text=True, capture_output=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        for c, why in zip(CASES, json.loads(proc.stdout), strict=True):
            with self.subTest(c["name"]):
                self.assertEqual(why == "", c["ok"], why)


if __name__ == "__main__":
    unittest.main()

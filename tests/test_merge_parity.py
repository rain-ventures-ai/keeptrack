"""merge3 parity: the shared cases in tests/fixtures/merge3-cases.json run through keeptrack.py and board.js alike."""
import json, os, shutil, subprocess, sys, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "board", "kit"))
import keeptrack  # noqa: E402

CASES = json.load(open(os.path.join(HERE, "fixtures", "merge3-cases.json"), encoding="utf-8"))["cases"]
# board.js keeps merge3 inside the page closure: cut the block from VOLATILE to the end of merge3list and run it in node.
# A missing side is undefined in JS and None in Python: the replacer writes it as null so both read the same.
NODE = r"""
const src = require('fs').readFileSync(process.argv[1], 'utf8');
const a = src.indexOf('  const VOLATILE = {'), b = src.indexOf('  // Put a chosen value at a clash path');
if (a < 0 || b < a) { console.error('merge3 block not found in board.js'); process.exit(2); }
const merge3 = new Function(src.slice(a, b) + '\nreturn merge3;')();
let raw = ''; process.stdin.setEncoding('utf8'); process.stdin.on('data', x => raw += x);
process.stdin.on('end', () => process.stdout.write(JSON.stringify(JSON.parse(raw).map(c => merge3(c.base, c.mine, c.theirs)), (k, v) => v === undefined ? null : v)));
"""


def text(v):   # key order counts too: both sides write the merged board in this order
    return json.dumps(v, ensure_ascii=False)


class Merge3Parity(unittest.TestCase):
    def test_cases_cover_the_merge_rules(self):
        names = " ".join(c["name"] for c in CASES)
        for rule in ("clean merge", "clash", "list by id", "without ids", "volatile"):
            self.assertIn(rule, names)

    def test_python_merge3_matches_the_shared_cases(self):
        for c in CASES:
            with self.subTest(c["name"]):
                r = keeptrack.merge3(c["base"], c["mine"], c["theirs"])
                self.assertEqual(text(r["merged"]), text(c["merged"]))
                self.assertEqual(r["clashes"], c["clashes"])

    @unittest.skipUnless(shutil.which("node"), "node is not installed")
    def test_board_js_merge3_matches_the_shared_cases(self):
        proc = subprocess.run(["node", "-e", NODE, os.path.join(ROOT, "board", "board.js")],
                              input=json.dumps(CASES), text=True, capture_output=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        for c, r in zip(CASES, json.loads(proc.stdout), strict=True):
            with self.subTest(c["name"]):
                self.assertEqual(text(r["merged"]), text(c["merged"]))
                self.assertEqual(r["clashes"], c["clashes"])


if __name__ == "__main__":
    unittest.main()

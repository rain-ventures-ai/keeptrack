"""Similar-card parity (kit v52): keeptrack.py and board.js score titles and pick a kind alike, for the shared cases in
tests/fixtures/similar-cases.json, so a card added on the web board and one added by an agent are matched the same way."""
import json, os, shutil, subprocess, sys, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "board", "kit"))
import keeptrack  # noqa: E402

CASES = json.load(open(os.path.join(HERE, "fixtures", "similar-cases.json"), encoding="utf-8"))["cases"]
NODE = r"""
const m = require(process.argv[1]);
let raw = ''; process.stdin.setEncoding('utf8'); process.stdin.on('data', x => raw += x);
process.stdin.on('end', () => process.stdout.write(JSON.stringify(JSON.parse(raw).map(c => {
  const s = m.similarScore(c.a, c.b); return [s, m.similarKind(s, c.same, c.a, c.b)]; }))));
"""


class SimilarParity(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "node is not installed")
    def test_board_js_scores_like_keeptrack_py(self):
        proc = subprocess.run(["node", "-e", NODE, os.path.join(ROOT, "board", "board.js")],
                              input=json.dumps(CASES), text=True, capture_output=True)
        self.assertEqual(0, proc.returncode, proc.stderr)
        for c, (score, kind) in zip(CASES, json.loads(proc.stdout)):
            with self.subTest(a=c["a"], b=c["b"], same=c["same"]):
                py = keeptrack.similar_score(c["a"], c["b"])
                self.assertAlmostEqual(py, score, places=9)
                self.assertEqual(keeptrack.similar_kind(py, c["same"], c["a"], c["b"]), kind)


if __name__ == "__main__":
    unittest.main()

import json
import os
import random
import shutil
import subprocess
import sys
import unittest


HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "board", "kit"))
import keeptrack  # noqa: E402


class WebRankParity(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "node is not installed")
    def test_key_between_matches_python_for_500_random_cases(self):
        rng = random.Random(481516)
        keys = []
        for _ in range(180):
            at = rng.randrange(len(keys) + 1)
            keys.insert(at, keeptrack.key_between(keys[at - 1] if at else None, keys[at] if at < len(keys) else None))
        bounds = [None] + keys
        cases = []
        for _ in range(500):
            i = rng.randrange(len(keys) + 1)
            j = rng.randrange(i, len(keys) + 1)
            a = keys[i - 1] if i else None
            b = keys[j] if j < len(keys) else None
            if a is not None and b is not None and a >= b:
                b = None
            cases.append([a, b])
        script = """
const { keyBetween } = require(process.argv[1]);
let raw = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', x => raw += x);
process.stdin.on('end', () => process.stdout.write(JSON.stringify(JSON.parse(raw).map(([a,b]) => keyBetween(a,b)))));
"""
        proc = subprocess.run(
            ["node", "-e", script, os.path.join(ROOT, "board", "board.js")],
            input=json.dumps(cases), text=True, capture_output=True, check=True,
        )
        self.assertEqual(json.loads(proc.stdout), [keeptrack.key_between(a, b) for a, b in cases])

    @unittest.skipUnless(shutil.which("node"), "node is not installed")
    def test_json_text_matches_python_utf8_format(self):
        value = {"title": "Acme café £ \u2028 \"quoted\" \\ tab\t", "emoji": "\U0001F600", "done": False, "items": [1, -2, 0, "two", [], {}], "empty": None, "nested": {"a": {"b": []}}}
        proc = subprocess.run(
            ["node", "-e", "const { jsonText } = require(process.argv[1]); let s='';process.stdin.on('data',x=>s+=x);process.stdin.on('end',()=>process.stdout.write(jsonText(JSON.parse(s))))", os.path.join(ROOT, "board", "board.js")],
            input=json.dumps(value, ensure_ascii=False), text=True, capture_output=True, check=True,
        )
        self.assertEqual(proc.stdout, json.dumps(value, indent=2, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    unittest.main()

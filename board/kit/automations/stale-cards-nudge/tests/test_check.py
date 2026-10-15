import contextlib, importlib.util, io, json, os, pathlib, tempfile, unittest
from unittest.mock import patch

class PackTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        spec = importlib.util.spec_from_file_location("sample_check", pathlib.Path(__file__).resolve().parents[1] / "check.py")
        self.mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(self.mod)
        self.saved = os.getcwd(); os.chdir(self.root); self.addCleanup(os.chdir, self.saved)
        self.state = self.root / "seen.json"; self.config = self.root / "config.json"
        self.state.write_text(json.dumps({"keys": {}, "cursor": None})); self.config.write_text("{}")
        self.env = patch.dict(os.environ, KEEPTRACK_STATE=str(self.state), KEEPTRACK_CONFIG=str(self.config))
        self.env.start(); self.addCleanup(self.env.stop)

    def run_check(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out): code = self.mod.main()
        value = json.loads(out.getvalue())
        self.assertEqual(value["schema"], "keeptrack-check/1")
        return code, value

    def test_weekly_attention_filter(self):
        # The production CLI's in-process attention logic is already covered by
        # board tests; this fixture checks the pack's protocol and weekly dedup.
        board = self.root / "board"; board.mkdir()
        (board / "keeptrack.py").write_text('''import json
def cmd_list(args):
    assert args.attention and args.json
    print(json.dumps([{"id": "t_stale"}]))
''')
        code, value = self.run_check(); self.assertEqual(code, 0)
        self.assertEqual(value["items"][0]["ref"], "t_stale")
        item = value["items"][0]
        self.state.write_text(json.dumps({"keys": {item["key"]: item["rev"]}, "cursor": None}))
        self.assertEqual(self.run_check()[1]["items"], [])

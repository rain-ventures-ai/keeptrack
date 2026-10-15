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

    def test_new_revised_seen_and_fifty_item_batch(self):
        folder = self.root / "notes"; folder.mkdir()
        self.config.write_text(json.dumps({"notes_dir": str(folder)}))
        note = folder / "private.md"; note.write_text("Private contents")
        code, value = self.run_check(); self.assertEqual(code, 0); self.assertEqual(len(value["items"]), 1)
        self.assertNotIn("private", json.dumps(value).lower())
        item = value["items"][0]
        self.state.write_text(json.dumps({"keys": {item["key"]: item["rev"]}, "cursor": None}))
        self.assertEqual(self.run_check()[1]["items"], [])
        note.write_text("Changed contents"); self.assertEqual(len(self.run_check()[1]["items"]), 1)
        for n in range(51): (folder / (str(n) + ".txt")).write_text("Notes")
        value = self.run_check()[1]; self.assertEqual(len(value["items"]), 50); self.assertTrue(value["more"])
        self.assertIsNotNone(value["cursor"])

    def test_missing_folder_blocked(self):
        self.config.write_text(json.dumps({"notes_dir": str(self.root / "missing")}))
        code, value = self.run_check(); self.assertEqual(code, 2); self.assertEqual(value["note"], "source-missing")

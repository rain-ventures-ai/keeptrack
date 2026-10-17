"""The step-3 resolver: prints each named note's text itself, so the agent never types a file name into a shell."""
import sys, contextlib, hashlib, importlib.util, io, os, pathlib, tempfile, time, unittest

PACK = pathlib.Path(__file__).resolve().parents[1]
HOSTILE_NAME = "$(touch PWNED)`id`'q.md"


def load():
    saved, sys.dont_write_bytecode = sys.dont_write_bytecode, True
    try:
        spec = importlib.util.spec_from_file_location("notes_resolve", PACK / "resolve.py")
        mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); return mod
    finally:
        sys.dont_write_bytecode = saved


def key(rel):
    return "sha256:" + hashlib.sha256(rel.encode()).hexdigest()


class ResolveTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name); self.folder = self.root / "notes"; self.folder.mkdir()
        self.saved = os.getcwd(); os.chdir(self.root); self.addCleanup(os.chdir, self.saved)

    def resolve(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out): code = load().main([str(self.folder), *args])
        return code, out.getvalue()

    def test_prints_the_text_of_each_named_note_and_quotes_its_name(self):
        (self.folder / HOSTILE_NAME).write_text("ACTION: Alex to send the plan.\n")
        (self.folder / "sub").mkdir(); (self.folder / "sub/b.md").write_text("Second note")
        old = time.mktime((2026, 10, 14, 12, 0, 0, 0, 0, -1)); os.utime(self.folder / "sub/b.md", (old, old))
        code, out = self.resolve(key(HOSTILE_NAME), key("sub/b.md"), key("gone.md"))
        self.assertEqual(code, 0)
        self.assertIn("ACTION: Alex to send the plan.", out); self.assertIn("Second note", out)
        self.assertIn('"$(touch PWNED)`id`\'q.md"', out, "the name is shown as a JSON string, for reading only")
        self.assertIn("date: 2026-10-14", out)
        self.assertIn("=== " + key("gone.md") + " not-found ===", out)
        self.assertFalse((self.root / "PWNED").exists())

    def test_long_note_is_cut_with_a_marker_and_bad_keys_refused(self):
        (self.folder / "long.md").write_text("x" * 300000)
        code, out = self.resolve(key("long.md"))
        self.assertIn("cut off", out); self.assertLess(len(out), 210000)
        self.assertEqual(self.resolve("not-a-key")[0], 2)


class SkillTest(unittest.TestCase):
    def test_skill_never_has_the_agent_type_a_path_or_note_text_into_a_shell(self):
        text = (PACK / "SKILL.md").read_text()
        self.assertIn("resolve.py", text)
        self.assertNotIn("rglob", text, "the resolver is a pack file, not a listing of names to cat")
        self.assertNotIn("separate\n   `python3 -c` that reads the text on stdin", text)
        self.assertIn("<<'KT_TEXT'", text)


if __name__ == "__main__":
    unittest.main()

"""Tests for board/kit/keeptrack.py against a local --file board. Run: python3 -m unittest discover tests"""
import contextlib, importlib.util, io, json, os, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("keeptrack", os.path.join(HERE, "..", "board", "kit", "keeptrack.py"))
kt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(kt)


class Args:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def write(path, d):
    with open(path, "w") as f:
        json.dump(d, f)


def board():
    return {"version": 3, "settings": {}, "people": [{"github": "osouthgate", "name": "O"}],
            "columns": [{"id": "todo", "name": "To do"}, {"id": "done", "name": "Done"}],
            "tasks": [{"id": "t_old", "title": "Old", "column": "done", "updated": "2025-01-01T00:00:00Z", "history": [], "todos": []},
                      {"id": "t_live", "title": "Live", "column": "todo", "updated": "2026-10-01T00:00:00Z", "history": [],
                       "todos": [{"id": "d_a", "text": "A", "done": False}, {"text": "B", "done": False}]}],
            "contacts": []}


class LocalBoard(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        os.makedirs(os.path.join(self.dir.name, "board"))
        self.file = os.path.join(self.dir.name, "board", "tasks.json")
        write(self.file, board())
        self.old = kt.FILE, kt.save
        kt.FILE = self.file
        os.environ.setdefault("BOARD_USER", "osouthgate")

    def tearDown(self):
        kt.FILE, kt.save = self.old
        self.dir.cleanup()

    def read(self):
        with open(self.file) as f:
            return json.load(f)

    def quiet(self, f, *a):
        with contextlib.redirect_stdout(io.StringIO()):
            return f(*a)

    def test_archive_year_must_be_four_digits(self):
        self.assertEqual(kt.archive_path("2025"), "board/archive/2025.json")
        for bad in ("../../x", "2025/../../a", "20251", ""):
            with self.assertRaises(SystemExit):
                kt.archive_path(bad)

    def test_todo_retry_ticks_the_same_item(self):
        real, calls = kt.save, []
        def racing(data, sha, msg):   # like a 409 from GitHub: someone added a to-do at the top before our write
            if not calls:
                calls.append(1); d = self.read()
                d["tasks"][1]["todos"].insert(0, {"id": "d_z", "text": "Z", "done": False}); write(self.file, d)
                return False
            return real(data, sha, msg)
        kt.save = racing
        self.quiet(kt.cmd_todo_set, Args(id="t_live", n="2"), True)   # "2" was B when we read it
        todos = {x["text"]: x["done"] for x in self.read()["tasks"][1]["todos"]}
        self.assertEqual(todos, {"Z": False, "A": False, "B": True})

    def test_archive_then_unarchive_updates_both_files(self):
        self.quiet(kt.cmd_archive, Args(done_days=None, lost_days=None, keep_history=None, dry_run=False))
        arch = os.path.join(self.dir.name, "board", "archive", "2025.json")
        self.assertEqual([t["id"] for t in json.load(open(arch))["tasks"]], ["t_old"])
        self.quiet(kt.cmd_unarchive, Args(ref="t_old"))
        self.assertEqual(json.load(open(arch))["tasks"], [])
        d = self.read()
        self.assertIn("t_old", [t["id"] for t in d["tasks"]])
        self.assertEqual(d["archive"]["files"]["2025"], {"tasks": 0, "contacts": 0})


if __name__ == "__main__":
    unittest.main()


class WebBoardCopies(unittest.TestCase):
    def test_routine_loader_matches_kit(self):
        # Settings → Agents shows the routine instructions from board.js; they must match board/kit/routine-loader.txt
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        loader = open(os.path.join(root, 'board', 'kit', 'routine-loader.txt'), encoding='utf-8').read().rstrip('\n')
        js = open(os.path.join(root, 'board', 'board.js'), encoding='utf-8').read()
        self.assertIn('const LOADER = ' + json.dumps(loader, ensure_ascii=False) + ';', js)

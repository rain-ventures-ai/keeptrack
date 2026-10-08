"""Tests for `keeptrack.py import` (onboarding staging files) against a local --file board. Run: python3 -m unittest discover tests"""
import contextlib, importlib.util, io, json, os, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("keeptrack_imp", os.path.join(HERE, "..", "board", "kit", "keeptrack.py"))
kt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(kt)


class Args:
    def __init__(self, **kw):
        self.__dict__.update(kw)


BOARD = {"version": 3, "settings": {"stages": ["New", "Contacted", "Talking", "Won", "Lost"]},
         "columns": [{"id": "todo", "name": "To do"}, {"id": "done", "name": "Done"}],
         "people": [{"github": "osouthgate", "name": "O"}], "clients": ["General"], "tasks": [], "client_info": {},
         "contacts": [{"id": "p_amira", "name": "Amira Patel", "company": "Harbour Foods", "email": "amira@harbour.example",
                       "role": "Head of Ops", "phone": "", "stage": "Talking", "history": [], "comments": []}]}

STAGING = {"source": "Test run",
           "people": [{"name": "Priya Shah", "company": "Northwind", "email": "priya@northwind.example", "stage": "talking",
                       "next": "Send the proposal", "due": "2026-10-15", "evidence": "Named by the owner"},
                      {"name": "A. Patel", "email": "AMIRA@harbour.example", "role": "CEO", "phone": "+44 1"}],
           "companies": ["Acme Ltd"],
           "folders": [{"company": "Northwind", "title": "Drive", "url": "https://drive.google.com/drive/folders/abc"},
                       {"company": "Acme Ltd", "url": "/Users/chris/Clients/Acme"}],
           "tasks": [{"title": "Write the proposal", "client": "Northwind", "contact": "priya@northwind.example",
                      "todos": ["Draft"], "links": [{"title": "Trello card", "url": "https://trello.com/c/x"}]}]}


class Import(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        os.makedirs(os.path.join(self.dir.name, "board"))
        self.file = os.path.join(self.dir.name, "board", "tasks.json")
        json.dump(BOARD, open(self.file, "w"))
        self.staging = os.path.join(self.dir.name, "staging.json")
        json.dump(STAGING, open(self.staging, "w"))
        self.old = kt.FILE
        kt.FILE = self.file
        os.environ.setdefault("BOARD_USER", "osouthgate")

    def tearDown(self):
        kt.FILE = self.old
        self.dir.cleanup()

    def run_import(self, path=None, dry=False):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            kt.cmd_import(Args(path=path or self.staging, dry_run=dry, source=None))
        return out.getvalue()

    def read(self):
        return json.load(open(self.file))

    def test_dry_run_saves_nothing(self):
        before = open(self.file).read()
        out = self.run_import(dry=True)
        self.assertIn("DRY RUN", out)
        self.assertEqual(open(self.file).read(), before)

    def test_import_adds_fills_and_never_overwrites(self):
        self.run_import()
        d = self.read()
        priya = next(p for p in d["contacts"] if p["name"] == "Priya Shah")
        self.assertEqual((priya["stage"], priya["next_due"]), ("Talking", "2026-10-15"))
        self.assertIn("Named by the owner", priya["history"][0]["text"])
        amira = next(p for p in d["contacts"] if p["id"] == "p_amira")
        self.assertEqual(amira["role"], "Head of Ops")    # had a value: not changed
        self.assertEqual(amira["phone"], "+44 1")         # was empty: filled
        self.assertEqual(amira["name"], "Amira Patel")
        self.assertEqual(len(d["contacts"]), 2)
        self.assertEqual(d["client_info"]["Acme Ltd"]["links"][0]["url"], "file:///Users/chris/Clients/Acme")
        task = d["tasks"][0]
        self.assertEqual((task["contact"], task["todos"][0]["text"]), (priya["id"], "Draft"))
        self.assertTrue({"Northwind", "Acme Ltd"} <= set(d["clients"]))

    def test_second_run_adds_nothing(self):
        self.run_import()
        first = self.read()
        out = self.run_import()
        self.assertIn("added 0, filled in 0", out)
        second = self.read()
        self.assertEqual((len(second["contacts"]), len(second["tasks"])), (len(first["contacts"]), len(first["tasks"])))

    def test_bad_file_is_refused_whole(self):
        bad = dict(STAGING, people=STAGING["people"] + [{"name": "X", "stage": "Nope"}, {"name": "Y", "due": "2026-01-01"}],
                   folders=[{"company": "Z", "url": "~/x"}])
        json.dump(bad, open(self.staging, "w"))
        before = open(self.file).read()
        with self.assertRaises(SystemExit) as e, contextlib.redirect_stdout(io.StringIO()):
            kt.cmd_import(Args(path=self.staging, dry_run=False, source=None))
        msg = str(e.exception)
        for part in ("unknown stage 'Nope'", "needs a next step", "absolute folder path"):
            self.assertIn(part, msg)
        self.assertEqual(open(self.file).read(), before)

    def test_csv_people(self):
        csv = os.path.join(self.dir.name, "people.csv")
        open(csv, "w").write("Name,Company,Email,Stage\nSam Lee,Acme Ltd,sam@acme.example,New\n,,,\n")
        self.run_import(csv)
        self.assertIn("Sam Lee", [p["name"] for p in self.read()["contacts"]])
        open(csv, "w").write("name,emial\nA,b\n")
        with self.assertRaises(SystemExit):
            kt.cmd_import(Args(path=csv, dry_run=True, source=None))


if __name__ == "__main__":
    unittest.main()

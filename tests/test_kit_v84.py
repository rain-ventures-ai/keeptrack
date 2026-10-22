"""Kit v84: companies on the board (private-tasks card #281). client_info[<company>] gains stage, owner, domain and
notes; `client-set` sets and clears them with checks, `clients` shows them, a company's stage is worked out from its
people until one is set, and older kits keep the new fields."""
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
KIT = os.path.join(REPO, "board", "kit")
sys.path.insert(0, KIT)
import keeptrack  # noqa: E402
from board_fixtures import copy_board_fixture  # noqa: E402

KT = os.path.join(KIT, "keeptrack.py")
V83_REF = "a479e72:board/kit/keeptrack.py"   # kit v83 on main, before company records


class Board(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = os.path.join(self.tmp.name, "board")
        copy_board_fixture("v4_kit72", self.dir)
        self.file = os.path.join(self.dir, "tasks.json")
        self.env = dict(os.environ, BOARD_USER="alex", BOARD_AGENT="claude", BOARD_SESSION="feedc0de11",
                        BOARD_WRITE="local", BOARD_PROJECT="")
        for k in ("BOARD_REPO", "BOARD_TOKEN", "BOARD_HOSTED_API", "BOARD_API"):
            self.env.pop(k, None)

    def tearDown(self):
        self.tmp.cleanup()

    def kt(self, *args, ok=True, script=KT, stdin=None):
        r = subprocess.run([sys.executable, script, "--file", self.file, *args], env=self.env, cwd=self.tmp.name,
                           capture_output=True, text=True, input=stdin)
        if ok:
            self.assertEqual(0, r.returncode, r.stdout + r.stderr)
        return r

    def root(self):
        with open(self.file, encoding="utf-8") as f:
            return json.load(f)

    def write_root(self, root):
        with open(self.file, "w", encoding="utf-8") as f:
            json.dump(root, f)

    def info(self, company="Acme"):
        return self.root()["client_info"][company]

    def clients_line(self, company="Acme"):
        return next(x for x in self.kt("clients").stdout.splitlines() if x.startswith(company + "  "))

    def test_set_show_and_clear_each_field(self):
        out = self.kt("client-set", "Acme", "--stage", "contacted", "--owner", "@ALEX", "--domain", "https://www.Acme.test/about",
                      "--notes", "Key account").stdout
        self.assertIn("stage for Acme: Contacted", out)
        info = self.info()
        self.assertEqual(("Contacted", "alex", "www.acme.test", "Key account"), (info["stage"], info["owner"], info["domain"], info["notes"]))
        self.assertEqual("One trusted view of every order", info["north_star"], "the north star stays")
        line = self.clients_line()
        for words in ("stage: Contacted", "owner: @alex", "domain: www.acme.test", "notes: Key account"):
            self.assertIn(words, line)
        self.assertNotIn("from its people", line)
        out = self.kt("client-set", "Acme", "--stage", "", "--owner", "", "--domain", "", "--notes", "").stdout
        self.assertIn("stage for Acme cleared", out)
        info = self.info()
        for k in ("stage", "owner", "domain", "notes"):
            self.assertNotIn(k, info, "a cleared field is removed, not left empty")
        self.assertEqual("One trusted view of every order", info["north_star"])

    def test_reserved_names_are_refused(self):
        before = self.root()
        for args in (("client-set", "__proto__", "--stage", "New"), ("client-set", " constructor "), ("client-rename", "Acme", "prototype"),
                     ("person-add", "Robin", "--company", "__proto__"), ("add", "Task", "--client", "constructor")):
            self.assertIn("cannot be a client or company name", self.kt(*args, ok=False).stderr, args)
        self.assertEqual(before, self.root())

    def test_an_existing_reserved_name_can_be_cleaned_up(self):
        root = self.root(); root["clients"] += ["__proto__", "prototype"]; self.write_root(root)
        self.assertIn("removed client __proto__", self.kt("client-rm", "__proto__").stdout)
        self.assertIn("renamed client prototype -> Proto Ltd", self.kt("client-rename", "prototype", "Proto Ltd").stdout)
        self.assertNotIn("__proto__", self.root()["clients"]); self.assertIn("Proto Ltd", self.root()["clients"])
        self.kt("list", "--all", "--client", "constructor")   # a filter is not a write

    def test_import_skips_reserved_names(self):
        staging = os.path.join(self.tmp.name, "staging.json")
        with open(staging, "w", encoding="utf-8") as f:
            json.dump({"companies": ["__proto__", "Good Co"], "people": [{"name": "Robin Proto", "company": "constructor"}],
                       "folders": [{"company": "prototype", "url": "https://drive.google.com/x"}],
                       "tasks": [{"title": "Proto task", "client": "__proto__"}]}, f)
        out = self.kt("import", staging).stdout
        self.assertEqual(4, out.count("! skipped"), out)
        root = self.root()
        self.assertIn("Good Co", root["clients"])
        self.assertFalse(set(root["clients"]) & set(keeptrack.RESERVED_NAMES))
        self.assertFalse(set(root["client_info"]) & set(keeptrack.RESERVED_NAMES))
        self.assertNotIn("Robin Proto", self.kt("people").stdout)
        self.assertNotIn("Proto task", self.kt("list", "--all").stdout)

    def test_proposal_naming_a_reserved_client_cannot_be_accepted(self):
        props = os.path.join(self.tmp.name, "props.json")
        with open(props, "w", encoding="utf-8") as f:
            json.dump([{"kind": "task.create", "title": "Proto task", "action_key": "ak-proto", "work_key": "wk-proto", "reason": "test",
                        "source": {"kind": "meeting", "id": "doc-1", "revision": "1", "title": "M", "date": "2026-10-08", "url": "https://example.invalid/m"},
                        "change": {"title": "Proto task", "client": "__proto__"}}], f)
        env = dict(self.env); env.pop("BOARD_AGENT", None); env["HOME"] = self.tmp.name
        run = lambda *args: subprocess.run([sys.executable, KT, "--file", self.file, *args], env=env, cwd=self.tmp.name, capture_output=True, text=True)
        added = run("proposal-add", props)
        self.assertEqual(0, added.returncode, added.stderr)
        listed = run("proposals", "--json"); self.assertEqual(0, listed.returncode, listed.stderr)
        data = json.loads(listed.stdout); items = data if isinstance(data, list) else data.get("proposals", [])
        pid = next(x["id"] for x in items if x.get("title") == "Proto task")
        r = run("proposal-accept", pid)
        self.assertNotEqual(0, r.returncode); self.assertIn("cannot be a client or company name", r.stderr)
        self.assertNotIn("Proto task", self.kt("list", "--all").stdout)
        self.assertNotIn("__proto__", self.root()["clients"])

    def run_as_person(self, *args):
        env = dict(self.env); env.pop("BOARD_AGENT", None); env["HOME"] = self.tmp.name
        return subprocess.run([sys.executable, KT, "--file", self.file, *args], env=env, cwd=self.tmp.name, capture_output=True, text=True)

    def add_proposals(self, items):
        props = os.path.join(self.tmp.name, "merge-props.json")
        src = {"kind": "meeting", "id": "doc-2", "revision": "1", "title": "M", "date": "2026-10-08", "url": "https://example.invalid/m"}
        with open(props, "w", encoding="utf-8") as f:
            json.dump([dict(x, source=src, reason="test") for x in items], f)
        r = self.run_as_person("proposal-add", props); self.assertEqual(0, r.returncode, r.stderr)
        data = json.loads(self.run_as_person("proposals", "--json").stdout)
        items = data if isinstance(data, list) else data.get("proposals", [])
        return {x["title"]: x["id"] for x in items}

    def test_every_create_path_is_refused_at_write(self):
        before = self.root()
        r = self.kt("client-link", "__proto__", "https://x.example/folder", ok=False)
        self.assertIn("cannot be a client or company name", r.stderr)
        self.assertEqual(before, self.root())
        n = self.kt("person-add", "Robin Doe", "--company", "Acme").stdout.split()[1]
        for cmd in (("touch", n, "Called", "--company", "__proto__"), ("person-set", n, "--company", "prototype")):
            r = self.kt(*cmd, ok=False)
            self.assertIn("cannot be a client or company name", r.stderr, cmd)
        self.assertNotIn("__proto__", json.dumps(self.root()))
        ids = self.add_proposals([
            {"kind": "task.create", "title": "Merge client", "action_key": "ak-m1", "work_key": "wk-m1", "change": {"title": "Merge client", "client": "__proto__"}},
            {"kind": "person.upsert", "title": "Merge company", "action_key": "ak-m2", "work_key": "wk-m2", "change": {"name": "Robin Doe", "company": "constructor"}}])
        num = self.kt("list", "--all").stdout.splitlines()[0][1:].split()[0]
        for pid, into, field in ((ids["Merge client"], "#" + num, "client"), (ids["Merge company"], n, "company")):
            r = self.run_as_person("proposal-merge", pid, "--into", into, "--fields", field)
            self.assertNotEqual(0, r.returncode, r.stdout)
            self.assertIn("cannot be a client or company name", r.stderr, field)
        every = "".join(open(os.path.join(d, f), encoding="utf-8").read() for d, _, fs in os.walk(self.dir) for f in fs if f.endswith(".json") and "proposals" not in d)
        self.assertNotIn('"__proto__"', every); self.assertNotIn('"constructor"', every); self.assertNotIn('"prototype"', every)

    def test_init_refuses_a_reserved_client(self):
        board = os.path.join(self.tmp.name, "fresh", "board", "tasks.json")
        r = subprocess.run([sys.executable, KT, "--file", board, "init", "--person", "alex:Alex", "--client", "__proto__"],
                           env=self.env, cwd=self.tmp.name, capture_output=True, text=True)
        self.assertNotEqual(0, r.returncode); self.assertIn("cannot be a client or company name", r.stderr)

    def test_import_summary_counts_reserved_skips(self):
        staging = os.path.join(self.tmp.name, "staging2.json")
        with open(staging, "w", encoding="utf-8") as f:
            json.dump({"companies": ["__proto__", "Fine\u202eCo"], "tasks": [{"title": "T\u0007x", "client": "constructor"}]}, f)
        dry = self.kt("import", staging, "--dry-run").stdout
        self.assertIn("and 2 with a reserved name", dry)
        out = self.kt("import", staging).stdout
        self.assertIn("and 2 with a reserved name", out)
        self.assertNotIn("\u202e", out); self.assertNotIn("\u0007", out)

    def test_client_info_entry_that_is_text_never_crashes(self):
        root = self.root(); root["client_info"]["Acme"] = "oops"; root["clients"].append(7); self.write_root(root)
        self.assertIn("Acme  (", self.kt("clients").stdout)
        self.assertEqual(("", True), keeptrack.company_stage(self.root(), "Acme"))

    def test_clients_skips_records_that_are_not_text(self):
        self.kt("person-add", "Robin Doe", "--company", "Acme")
        path = next(os.path.join(self.dir, "people", f) for f in os.listdir(os.path.join(self.dir, "people")))
        with open(path, encoding="utf-8") as f:
            person = json.load(f)
        person["company"] = {"a": 1}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(person, f)
        self.assertIn("Acme  (", self.kt("clients").stdout)

    def test_whitespace_notes_clear_and_stale_stage_is_unset(self):
        self.kt("client-set", "Acme", "--notes", "Keep")
        self.assertIn("notes for Acme cleared", self.kt("client-set", "Acme", "--notes", "   ").stdout)
        self.assertNotIn("notes", self.info())
        self.kt("person-add", "Sam Lee", "--company", "Acme", "--stage", "Contacted")
        root = self.root(); root["client_info"]["Acme"]["stage"] = "Gone"; self.write_root(root)
        self.assertIn("stage: Contacted (from its people)", self.clients_line(), "a stage the board no longer has counts as unset")

    def test_refusals_write_nothing(self):
        before = self.root()
        self.assertIn("unknown stage", self.kt("client-set", "Acme", "--stage", "Maybe", ok=False).stderr)
        self.assertIn("not a board member", self.kt("client-set", "Acme", "--owner", "nobody", ok=False).stderr)
        self.assertIn("not a domain", self.kt("client-set", "Acme", "--domain", "not a domain", ok=False).stderr)
        self.assertEqual(before, self.root())

    def test_derived_stage_from_people(self):
        self.kt("person-add", "Robin Doe", "--company", "Acme", "--stage", "Lost")
        self.assertIn("stage: Lost (from its people)", self.clients_line())
        self.kt("person-add", "Sam Lee", "--company", "Acme", "--stage", "Contacted")
        self.assertIn("stage: Contacted (from its people)", self.clients_line(), "a lost person never outranks a live one")
        self.kt("person-add", "Jo Won", "--company", "Acme", "--stage", "Won")
        self.assertIn("stage: Won (from its people)", self.clients_line())
        data = self.root()
        data["contacts"] = [{"company": "Acme", "stage": "Won", "github": "alex", "id": "p_x", "name": "Me"}]
        self.assertEqual(("", True), keeptrack.company_stage(data, "Acme"), "a member's own record does not count")
        self.kt("client-set", "Acme", "--stage", "New")
        self.assertIn("stage: New  ", self.clients_line(), "a stage that is set wins")

    def test_notes_from_stdin_and_new_client(self):
        self.kt("client-set", "Beta Ltd", "--notes", "-", stdin="Line one\nLine two\n")
        self.assertEqual("Line one\nLine two", self.info("Beta Ltd")["notes"])
        self.assertIn("Beta Ltd", self.root()["clients"])
        self.assertIn("notes: Line one Line two", self.clients_line("Beta Ltd"))
        self.kt("client-set", "Gamma")   # with no flag it still only adds the client
        self.assertIn("Gamma", self.root()["clients"])

    def test_stage_rename_follows_and_drop_is_refused(self):
        self.kt("client-set", "Acme", "--stage", "Won")
        self.kt("settings-set", "--rename-stage", "Won=Closed")
        self.assertEqual("Closed", self.info()["stage"])
        r = self.kt("settings-set", "--stages", "New,Contacted,Lost", ok=False)
        self.assertIn("companies are still in a stage", r.stderr)
        self.assertEqual("Closed", self.info()["stage"])

    def test_member_rm_clears_owner(self):
        self.kt("member-add", "sam", "--name", "Sam")
        self.kt("client-set", "Acme", "--owner", "sam")
        self.assertIn("no longer owner of Acme", self.kt("member-rm", "sam").stdout)
        self.assertNotIn("owner", self.info())

    def test_doctor_warns_but_never_stops(self):
        root = self.root(); root["client_info"]["Acme"].update({"stage": "Zzz", "owner": "ghost"}); self.write_root(root)
        r = self.kt("doctor", "--json", ok=False)
        report = json.loads(r.stdout)
        warned = [x for x in report["warnings"] if x["code"] == "CLIENT_RECORD"]
        self.assertEqual(2, len(warned))
        hard = [x for x in report["issues"] if x not in report["warnings"]]
        self.assertEqual([], [x for x in hard if x["code"] == "CLIENT_RECORD"], "a company record is never a hard issue")
        self.assertTrue(report["healthy"], "the fixture board is otherwise clean, so the board stays healthy")
        self.assertEqual(0, r.returncode)
        self.assertIn("CLIENT_RECORD", keeptrack.DOCTOR_WARNINGS)
        self.assertNotIn("CLIENT", keeptrack.DOCTOR_WARNINGS, "a project's unknown client stays a problem")

    def test_merge_keeps_both_sides_fields(self):
        base = {"client_info": {"Acme": {"north_star": "x", "links": []}}}
        mine = json.loads(json.dumps(base)); mine["client_info"]["Acme"]["stage"] = "Talking"
        theirs = json.loads(json.dumps(base)); theirs["client_info"]["Acme"]["owner"] = "alex"; theirs["client_info"]["Acme"]["domain"] = "acme.test"
        r = keeptrack.merge3(base, mine, theirs)
        self.assertEqual([], r["clashes"])
        self.assertEqual({"north_star": "x", "links": [], "stage": "Talking", "owner": "alex", "domain": "acme.test"}, r["merged"]["client_info"]["Acme"])
        clash = json.loads(json.dumps(base)); clash["client_info"]["Acme"]["stage"] = "Won"
        self.assertEqual([["client_info", "Acme", "stage"]], [c["path"] for c in keeptrack.merge3(base, mine, clash)["clashes"]])

    def test_v83_keeptrack_keeps_company_records(self):
        try:
            src = subprocess.check_output(["git", "show", V83_REF], cwd=REPO, text=True, stderr=subprocess.DEVNULL)
        except (subprocess.CalledProcessError, OSError):
            if os.environ.get("CI"):   # CI checks out with fetch-depth 0: a missing ref there is a failure, not a skip
                self.fail("kit v83 (" + V83_REF + ") is not in this clone")
            self.skipTest("kit v83 is not in this clone (git fetch --depth=1500 origin main)")
        old = os.path.join(self.tmp.name, "keeptrack_v83.py")
        with open(old, "w", encoding="utf-8") as f:
            f.write(src)
        self.kt("client-set", "Acme", "--stage", "Contacted", "--owner", "alex", "--domain", "acme.test", "--notes", "n")
        self.kt("client-set", "Acme", "--north-star", "from kit v83", script=old)
        self.kt("client-rename", "Acme", "Acme Ltd", script=old)
        self.kt("label-add", "v83", script=old)
        info = self.info("Acme Ltd")
        self.assertEqual(("Contacted", "alex", "acme.test", "n", "from kit v83"), (info["stage"], info["owner"], info["domain"], info["notes"], info["north_star"]))


class Page(unittest.TestCase):
    def read(self, rel):
        with open(os.path.join(REPO, rel), encoding="utf-8") as f:
            return f.read()

    def test_page_has_companies(self):
        js = self.read("board/board.js")
        for words in ("function renderCompaniesView()", "function companyFacts(name)", "{ value: 'companies', icon: 'building-2'",
                      "const pipeKey = () => 'kb_pipe_mode:'", "function setCompanyStage(", "drawerSelect('clStage'", "drawerSelect('clOwner'"):
            self.assertIn(words, js)
        for page in ("board/index.html", "board/hosted.html"):
            self.assertIn("People or companies by stage", self.read(page), page)
        self.assertIn('"building-2"', self.read("board/icons.js"))


class Docs(unittest.TestCase):
    def test_kit_v84_upgrade_notes_and_changelog(self):   # the version itself: test_kit_v96.py
        with open(os.path.join(KIT, "UPGRADING.md"), encoding="utf-8") as f:
            v84 = f.read().split("### v84 (schema 4)", 1)[1].split("### v83", 1)[0]
        for words in ("kit-update", "client-set NAME --stage", "CLIENT_RECORD", "No migration", "Older kits"):
            self.assertIn(words, v84)
        with open(os.path.join(KIT, "README.md"), encoding="utf-8") as f:
            readme = f.read()
        for words in ('"stage": "Proposal", "owner": "alex", "domain": "acme.com", "notes"', "--owner LOGIN", "CLIENT_RECORD"):
            self.assertIn(words, readme)
        with open(os.path.join(REPO, "CHANGELOG.md"), encoding="utf-8") as f:
            self.assertIn("Kit v84", f.read())
        with open(os.path.join(REPO, "docs", "help", "companies.md"), encoding="utf-8") as f:
            self.assertIn("Use people's stage", f.read())


if __name__ == "__main__":
    unittest.main()

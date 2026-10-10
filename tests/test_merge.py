"""Three-way merge (merge3) and what keeptrack.py does when another writer saves first. Run: python3 -m unittest discover tests"""
import contextlib, copy, importlib.util, io, json, os, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("keeptrack", os.path.join(HERE, "..", "board", "kit", "keeptrack.py"))
kt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(kt)

M = kt.merge3


def card(**kw):
    c = {"id": "t_a", "title": "A", "column": "todo", "details": "", "labels": [], "links": [], "todos": [], "comments": [],
         "history": [], "claim": None, "updated": "2026-10-01T00:00:00Z"}
    c.update(kw)
    return c


class Merge3(unittest.TestCase):
    def test_different_fields_both_survive(self):
        r = M({"a": 1, "b": 1}, {"a": 2, "b": 1}, {"a": 1, "b": 2})
        self.assertEqual(r, {"merged": {"a": 2, "b": 2}, "clashes": []})

    def test_same_change_on_both_sides_is_not_a_clash(self):
        self.assertEqual(M({"a": 1}, {"a": 2}, {"a": 2}), {"merged": {"a": 2}, "clashes": []})

    def test_same_field_different_values_clashes_and_keeps_theirs(self):
        r = M({"title": "x"}, {"title": "mine"}, {"title": "theirs"})
        self.assertEqual(r["merged"], {"title": "theirs"})
        self.assertEqual(r["clashes"], [{"path": ["title"], "base": "x", "mine": "mine", "theirs": "theirs"}])

    def test_nested_objects_merge_field_by_field(self):
        b = {"claim": {"agent": "a", "status": "running", "note": ""}}
        r = M(b, {"claim": {"agent": "a", "status": "running", "note": "mine"}}, {"claim": {"agent": "a", "status": "done", "note": ""}})
        self.assertEqual(r["merged"], {"claim": {"agent": "a", "status": "done", "note": "mine"}})
        self.assertEqual(r["clashes"], [])

    def test_entries_added_on_both_sides_are_kept(self):
        b = {"comments": [{"id": "c1", "text": "one"}]}
        mine = {"comments": [{"id": "c1", "text": "one"}, {"id": "c2", "text": "mine"}]}
        theirs = {"comments": [{"id": "c1", "text": "one"}, {"id": "c3", "text": "theirs"}]}
        r = M(b, mine, theirs)
        self.assertEqual([c["id"] for c in r["merged"]["comments"]], ["c1", "c3", "c2"])
        self.assertEqual(r["clashes"], [])

    def test_removed_on_one_side_and_untouched_on_the_other_is_removed(self):
        base = [{"id": "d1", "text": "a"}, {"id": "d2", "text": "b"}]
        self.assertEqual(M(base, [base[0]], copy.deepcopy(base))["merged"], [base[0]])
        self.assertEqual(M(base, copy.deepcopy(base), [base[1]])["merged"], [base[1]])
        self.assertEqual(M({"x": base}, {"x": [base[0]]}, {"x": [base[1]]})["merged"], {"x": []})

    def test_entries_edited_on_both_sides_merge_recursively(self):
        base = [{"id": "d1", "text": "a", "done": False}]
        r = M(base, [{"id": "d1", "text": "a", "done": True}], [{"id": "d1", "text": "a2", "done": False}])
        self.assertEqual(r, {"merged": [{"id": "d1", "text": "a2", "done": True}], "clashes": []})

    def test_entry_edited_on_both_sides_in_the_same_field_clashes(self):
        base = [{"id": "d1", "text": "a"}]
        r = M(base, [{"id": "d1", "text": "mine"}], [{"id": "d1", "text": "theirs"}])
        self.assertEqual(r["merged"], [{"id": "d1", "text": "theirs"}])
        self.assertEqual([c["path"] for c in r["clashes"]], [["d1", "text"]])

    def test_edit_against_delete_clashes_whichever_side_edits(self):
        base = [{"id": "d1", "text": "a"}]
        gone = M(base, [{"id": "d1", "text": "mine"}], [])          # they deleted it, I edited it
        self.assertEqual((gone["merged"], gone["clashes"][0]["path"], gone["clashes"][0]["theirs"]), ([], ["d1"], None))
        kept = M(base, [], [{"id": "d1", "text": "theirs"}])         # I deleted it, they edited it
        self.assertEqual((kept["merged"], kept["clashes"][0]["mine"]), ([{"id": "d1", "text": "theirs"}], None))

    def test_scalar_lists_merge_as_sets(self):
        r = M({"labels": ["a", "b"]}, {"labels": ["a", "b", "mine"]}, {"labels": ["b", "theirs"]})
        self.assertEqual(sorted(r["merged"]["labels"]), ["b", "mine", "theirs"])
        self.assertEqual(r["clashes"], [])

    def test_entries_without_an_id_merge_by_content(self):
        l1, l2, l3 = {"title": "1", "url": "u1"}, {"title": "2", "url": "u2"}, {"title": "3", "url": "u3"}
        r = M([l1, l2], [l1, l2, l3], [l1])
        self.assertEqual(r, {"merged": [l1, l3], "clashes": []})

    def test_a_reorder_survives_when_only_they_added(self):
        r = M(["a", "b"], ["b", "a"], ["a", "b", "c"])
        self.assertEqual(r["merged"], ["b", "a", "c"])

    def test_item_lists_merge_by_id(self):
        base = {"tasks": [card(id="t_a"), card(id="t_b", title="B")]}
        mine = copy.deepcopy(base); mine["tasks"][0]["title"] = "mine"
        theirs = copy.deepcopy(base); theirs["tasks"][0]["column"] = "done"; theirs["tasks"].append(card(id="t_c", title="C"))
        r = M(base, mine, theirs)
        self.assertEqual(r["clashes"], [])
        self.assertEqual([(t["id"], t["title"], t["column"]) for t in r["merged"]["tasks"]], [("t_a", "mine", "done"), ("t_b", "B", "todo"), ("t_c", "C", "todo")])

    def test_bookkeeping_fields_never_clash(self):
        base = {"updated": "1", "updatedBy": "x", "next_num": 3, "claim": {"heartbeat_at": "1", "status": "running"}}
        mine = {"updated": "3", "updatedBy": "me", "next_num": 4, "claim": {"heartbeat_at": "3", "status": "running"}}
        theirs = {"updated": "2", "updatedBy": "they", "next_num": 5, "claim": {"heartbeat_at": "2", "status": "running"}}
        r = M(base, mine, theirs)
        self.assertEqual(r["clashes"], [])
        self.assertEqual((r["merged"]["updated"], r["merged"]["next_num"]), ("3", 5))

    def test_true_and_one_are_different_values(self):
        self.assertEqual(len(M({"a": 0}, {"a": True}, {"a": 1})["clashes"]), 1)

    def test_inputs_are_not_changed(self):
        base = {"c": [{"id": "1", "t": "a"}]}; mine = {"c": [{"id": "1", "t": "b"}]}; theirs = {"c": [{"id": "1", "t": "a"}, {"id": "2"}]}
        before = copy.deepcopy((base, mine, theirs)); M(base, mine, theirs)
        self.assertEqual((base, mine, theirs), before)


def write(path, d):
    with open(path, "w") as f:
        json.dump(d, f)


def board():
    return {"version": 3, "settings": {}, "people": [], "columns": [{"id": "todo", "name": "To do"}, {"id": "done", "name": "Done"}],
            "tasks": [card(id="t_a", num=1, title="A", todos=[{"id": "d_1", "text": "one", "done": False}]), card(id="t_b", num=2, title="B")],
            "contacts": [{"id": "p_1", "name": "Casey", "stage": "New", "links": [], "comments": [], "history": [],
                          "log": [{"id": "l_1", "at": "2026-10-01", "text": "met"}]}], "next_num": 3}


class RaceCli(unittest.TestCase):
    """keeptrack.py on a --file board where another writer saves between our read and our write (save returns False, as a 409 does)."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        os.makedirs(os.path.join(self.dir.name, "board"))
        self.file = os.path.join(self.dir.name, "board", "tasks.json")
        write(self.file, board())
        self.old = kt.FILE, kt.save
        kt.FILE = self.file

    def tearDown(self):
        kt.FILE, kt.save = self.old
        self.dir.cleanup()

    def read(self):
        with open(self.file) as f:
            return json.load(f)

    def other_writer_then(self, change):
        """Make our first save lose a race: the other writer applies change(board) to the file first."""
        real, calls = kt.save, []
        def racing(data, sha, msg):
            if not calls:
                calls.append(1); d = self.read(); change(d); write(self.file, d)
                return False
            return real(data, sha, msg)
        kt.save = racing

    def run_mutate(self, fn):
        with contextlib.redirect_stdout(io.StringIO()):
            return kt.mutate(fn, "test")

    def test_different_fields_of_one_card_both_survive(self):
        self.other_writer_then(lambda d: d["tasks"][0].update(column="done"))
        self.run_mutate(lambda d: d["tasks"][0].update(title="Mine"))
        t = self.read()["tasks"][0]
        self.assertEqual((t["title"], t["column"]), ("Mine", "done"))

    def test_list_replaced_wholesale_still_keeps_their_added_entry(self):
        self.other_writer_then(lambda d: d["tasks"][0]["labels"].append("theirs"))
        self.run_mutate(lambda d: d["tasks"][0].update(labels=["mine"]))
        self.assertEqual(sorted(self.read()["tasks"][0]["labels"]), ["mine", "theirs"])

    def test_log_entries_added_by_both_are_kept(self):
        self.other_writer_then(lambda d: d["contacts"][0]["log"].append({"id": "l_theirs", "at": "2026-10-02", "text": "they called"}))
        self.run_mutate(lambda d: d["contacts"][0]["log"].append({"id": "l_mine", "at": "2026-10-03", "text": "I emailed"}))
        self.assertEqual([x["id"] for x in self.read()["contacts"][0]["log"]], ["l_1", "l_theirs", "l_mine"])

    def test_same_field_clash_stops_and_leaves_theirs_intact(self):
        self.other_writer_then(lambda d: d["tasks"][0].update(title="Theirs"))
        want = copy.deepcopy(board()); want["tasks"][0]["title"] = "Theirs"
        err = io.StringIO()
        with contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as cm:
            self.run_mutate(lambda d: d["tasks"][0].update(title="Mine", column="done"))
        self.assertEqual(cm.exception.code, 3)
        self.assertIn("tasks/t_a/title", err.getvalue()); self.assertIn("Theirs", err.getvalue()); self.assertIn("Mine", err.getvalue())
        self.assertEqual(self.read(), want)   # no part of our change was written, not even the field that did not clash

    def test_edit_against_delete_stops(self):
        self.other_writer_then(lambda d: d["tasks"].pop(1))
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as cm:
            self.run_mutate(lambda d: d["tasks"][1].update(title="Edited"))
        self.assertEqual(cm.exception.code, 3)
        self.assertEqual([t["id"] for t in self.read()["tasks"]], ["t_a"])

    def test_delete_against_edit_stops(self):
        self.other_writer_then(lambda d: d["tasks"][1].update(title="Edited"))
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as cm:
            self.run_mutate(lambda d: d["tasks"].pop(1))
        self.assertEqual(cm.exception.code, 3)
        self.assertEqual(self.read()["tasks"][1]["title"], "Edited")

    def test_deleting_a_card_nobody_else_touched_works(self):
        self.other_writer_then(lambda d: d["tasks"][0].update(title="Theirs"))
        self.run_mutate(lambda d: d["tasks"].pop(1))
        self.assertEqual([(t["id"], t["title"]) for t in self.read()["tasks"]], [("t_a", "Theirs")])

    def test_new_cards_from_both_sides_get_different_numbers(self):
        def theirs(d):
            d["tasks"].append(card(id="t_theirs", num=3, created="2026-10-02")); d["next_num"] = 4
        self.other_writer_then(theirs)
        self.run_mutate(lambda d: d["tasks"].append(card(id="t_mine", created="2026-10-03")))
        nums = {t["id"]: t["num"] for t in self.read()["tasks"]}
        self.assertEqual(nums["t_theirs"], 3)
        self.assertEqual(len(set(nums.values())), 4)

    def test_race_on_an_unrelated_file_change_just_saves(self):
        self.other_writer_then(lambda d: d.update(clients=["Acme"]))
        self.run_mutate(lambda d: d["tasks"][0].update(title="Mine"))
        d = self.read()
        self.assertEqual((d["tasks"][0]["title"], d["clients"]), ("Mine", ["Acme"]))


if __name__ == "__main__":
    unittest.main()

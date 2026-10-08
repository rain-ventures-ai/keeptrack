"""Tests for board/kit/keeptrack.py against a local --file board. Run: python3 -m unittest discover tests"""
import contextlib, copy, importlib.util, io, json, os, random, shutil, tempfile, unittest

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


def read_json(path):
    with open(path) as f:
        return json.load(f)


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
        self.assertEqual([t["id"] for t in read_json(arch)["tasks"]], ["t_old"])
        self.quiet(kt.cmd_unarchive, Args(ref="t_old"))
        self.assertEqual(read_json(arch)["tasks"], [])
        d = self.read()
        self.assertIn("t_old", [t["id"] for t in d["tasks"]])
        self.assertEqual(d["archive"]["files"]["2025"], {"tasks": 0, "contacts": 0})


if __name__ == "__main__":
    unittest.main()


class WebBoardCopies(unittest.TestCase):
    def test_routine_loader_matches_kit(self):
        # Settings → Agents shows the routine instructions from board.js; they must match board/kit/routine-loader.txt
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(root, 'board', 'kit', 'routine-loader.txt'), encoding='utf-8') as f:
            loader = f.read().rstrip('\n')
        with open(os.path.join(root, 'board', 'board.js'), encoding='utf-8') as f:
            js = f.read()
        self.assertIn('const LOADER = ' + json.dumps(loader, ensure_ascii=False) + ';', js)


FIXTURES = os.path.join(HERE, "fixtures")


def tree_bytes(path):
    out = {}
    for root, _, files in os.walk(path):
        for name in files:
            if name.endswith(".lock"):
                continue
            full = os.path.join(root, name)
            with open(full, "rb") as f:
                out[os.path.relpath(full, path)] = f.read()
    return out


def without_v4_fields(data):
    data = copy.deepcopy(data)
    data["version"] = 3
    data.pop("layout", None)
    for task in data["tasks"]:
        task.pop("rank", None)
    data["tasks"].sort(key=lambda x: x["id"])
    data["contacts"].sort(key=lambda x: x["id"])
    return data


class SplitStorage(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.board_dir = os.path.join(self.temp.name, "board")
        shutil.copytree(os.path.join(FIXTURES, "v4"), self.board_dir)
        self.old_file = kt.FILE
        kt.FILE = os.path.join(self.board_dir, "tasks.json")

    def tearDown(self):
        kt.FILE = self.old_file
        self.temp.cleanup()

    def quiet(self, fn, *args):
        with contextlib.redirect_stdout(io.StringIO()):
            return fn(*args)

    def changed(self, before):
        after = tree_bytes(self.board_dir)
        return {p for p in set(before) | set(after) if before.get(p) != after.get(p)}

    def test_load_v3_matches_v4_apart_from_rank(self):
        kt.FILE = os.path.join(FIXTURES, "v3", "tasks.json")
        v3 = kt.load_board()
        kt.FILE = os.path.join(FIXTURES, "v4", "tasks.json")
        v4 = kt.load_board()
        self.assertEqual(without_v4_fields(v3), without_v4_fields(v4))

    def test_add_changes_settings_and_one_new_card(self):
        before = tree_bytes(self.board_dir)
        self.quiet(kt.cmd_add, Args(title="New", column="todo", client=None, priority="medium", due=None,
                                    label=None, assign=None, details=None, todo=None))
        changed = self.changed(before)
        self.assertIn("tasks.json", changed)
        self.assertEqual(1, len([x for x in changed if x.startswith("cards/")]))
        self.assertEqual(2, len(changed))

    def test_comment_move_and_done_change_only_the_card(self):
        actions = [
            (kt.cmd_comment, Args(id="t_first", text="Update")),
            (kt.cmd_move, Args(id="t_first", column="done", column_pos=None, before=None, after=None,
                               top=True, priority=None, note=None)),
            (kt.cmd_done, Args(id="t_first", note="Complete")),
        ]
        for fn, args in actions:
            before = tree_bytes(self.board_dir)
            self.quiet(fn, args)
            self.assertEqual({"cards/t_first.json"}, self.changed(before))

    def test_archive_and_unarchive_update_split_files_together(self):
        card_path = os.path.join(self.board_dir, "cards", "t_first.json")
        card = read_json(card_path); card["column"] = "done"; write(card_path, card)
        before = tree_bytes(self.board_dir)
        self.quiet(kt.cmd_archive, Args(done_days=1, lost_days=None, keep_history=None, dry_run=False))
        self.assertEqual({"tasks.json", "cards/t_first.json", "archive/2026.json"}, self.changed(before))
        self.assertFalse(os.path.exists(card_path))
        before = tree_bytes(self.board_dir)
        self.quiet(kt.cmd_unarchive, Args(ref="t_first"))
        self.assertEqual({"tasks.json", "cards/t_first.json", "archive/2026.json"}, self.changed(before))
        self.assertTrue(os.path.exists(card_path))


class MigrationAndRanks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.board_dir = os.path.join(self.temp.name, "board")
        shutil.copytree(os.path.join(FIXTURES, "v3"), self.board_dir)
        self.old_file = kt.FILE
        kt.FILE = os.path.join(self.board_dir, "tasks.json")

    def tearDown(self):
        kt.FILE = self.old_file
        self.temp.cleanup()

    def test_migrate_dry_run_then_migrate_and_refuse_twice(self):
        before = tree_bytes(self.board_dir)
        with contextlib.redirect_stdout(io.StringIO()):
            kt.cmd_migrate(Args(to=4, dry_run=True))
        self.assertEqual(before, tree_bytes(self.board_dir))
        with contextlib.redirect_stdout(io.StringIO()):
            kt.cmd_migrate(Args(to=4, dry_run=False))
        self.assertNotIn("tasks", read_json(kt.FILE))
        self.assertTrue(os.path.isfile(os.path.join(self.board_dir, "cards", "t_first.json")))
        with self.assertRaises(SystemExit):
            kt.cmd_migrate(Args(to=4, dry_run=False))

    def test_count_check_aborts_on_a_planted_difference(self):
        before = tree_bytes(self.board_dir)
        real = kt.migration_files
        def damaged(data, state):
            files = real(data, state)
            card = json.loads(files["cards/t_first.json"])
            card["title"] = "Changed"
            files["cards/t_first.json"] = json.dumps(card)
            return files
        kt.migration_files = damaged
        try:
            with self.assertRaises(SystemExit):
                with contextlib.redirect_stdout(io.StringIO()):
                    kt.cmd_migrate(Args(to=4, dry_run=False))
        finally:
            kt.migration_files = real
        self.assertEqual(before, tree_bytes(self.board_dir))

    def test_key_between_properties(self):
        self.assertEqual("a0", kt.key_between(None, None))
        self.assertLess(kt.key_between(None, "a0"), "a0")
        self.assertGreater(kt.key_between("a0", None), "a0")
        rng, keys = random.Random(7), []
        for _ in range(1000):
            i = rng.randrange(len(keys) + 1)
            keys.insert(i, kt.key_between(keys[i - 1] if i else None, keys[i] if i < len(keys) else None))
        self.assertEqual(keys, sorted(keys))
        self.assertEqual(len(keys), len(set(keys)))
        self.assertLessEqual(max(map(len, keys)), 12)


class ApiSave(unittest.TestCase):
    def setUp(self):
        self.real_gh = kt.gh
        self.calls = []

    def tearDown(self):
        kt.gh = self.real_gh

    def fake_gh(self, *args, body=None):
        self.calls.append((args, body))
        endpoint = args[2] if len(args) > 2 and args[0] == "-X" else args[0]
        if endpoint.endswith("/git/blobs"):
            return 0, json.dumps({"sha": f"blob{len(self.calls)}"}), ""
        if endpoint.endswith("/git/trees"):
            return 0, json.dumps({"sha": "tree1"}), ""
        if endpoint.endswith("/git/commits"):
            return 0, json.dumps({"sha": "commit1"}), ""
        return 0, "{}", ""

    def test_one_file_uses_contents_api_with_sha(self):
        kt.gh = self.fake_gh
        state = {"head": "commit0", "base_tree": "tree0", "files": {"tasks.json": {"sha": "root-sha"}}}
        self.assertTrue(kt._api_save_changes({"tasks.json": "{}\n"}, set(), state, "Save"))
        args, body = self.calls[0]
        self.assertEqual("PUT", args[1])
        self.assertEqual("root-sha", body["sha"])

    def test_many_files_use_one_git_data_commit(self):
        kt.gh = self.fake_gh
        state = {"head": "commit0", "base_tree": "tree0", "files": {}}
        self.assertTrue(kt._api_save_changes({"tasks.json": "{}\n", "cards/t_x.json": "{}\n"}, set(), state, "Save"))
        tree_call = next(body for args, body in self.calls if args[2].endswith("/git/trees"))
        self.assertEqual("tree0", tree_call["base_tree"])
        self.assertEqual({"board/tasks.json", "board/cards/t_x.json"}, {x["path"] for x in tree_call["tree"]})
        patch_args, patch_body = self.calls[-1]
        self.assertEqual("PATCH", patch_args[1])
        self.assertFalse(patch_body["force"])


class Doctor(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.board_dir = os.path.join(self.temp.name, "board")
        shutil.copytree(os.path.join(FIXTURES, "v4"), self.board_dir)
        self.old_file = kt.FILE
        kt.FILE = os.path.join(self.board_dir, "tasks.json")

    def tearDown(self):
        kt.FILE = self.old_file
        self.temp.cleanup()

    def test_fix_is_safe_and_idempotent(self):
        card_path = os.path.join(self.board_dir, "cards", "t_first.json")
        card = read_json(card_path)
        card.pop("num"); card.pop("rank"); card["comments"][0].pop("id")
        wrong_path = os.path.join(self.board_dir, "cards", "wrong.json")
        write(wrong_path, card); os.remove(card_path)
        root = read_json(kt.FILE); root["next_num"] = 1; write(kt.FILE, root)
        issues, fixes, code = kt.doctor_board(True)
        self.assertEqual(1, code)
        self.assertTrue({"NUM_MISSING", "NEXT_NUM", "RANK", "COMMENT_FIELDS", "FILE_NAME"}.issubset({x["code"] for x in issues}))
        self.assertTrue(fixes)
        self.assertTrue(os.path.isfile(card_path)); self.assertFalse(os.path.exists(wrong_path))
        issues, fixes, code = kt.doctor_board(False)
        self.assertEqual(([], [], 0), (issues, fixes, code))
        before = tree_bytes(self.board_dir)
        kt.doctor_board(True)
        self.assertEqual(before, tree_bytes(self.board_dir))

    def test_invalid_json_is_reported_and_not_fixed(self):
        bad = os.path.join(self.board_dir, "cards", "bad.json")
        with open(bad, "w") as f:
            f.write("{not json\n")
        with open(bad, "rb") as f:
            original = f.read()
        issues, _, code = kt.doctor_board(True)
        self.assertEqual(1, code)
        self.assertIn("INVALID_JSON", {x["code"] for x in issues})
        with open(bad, "rb") as f:
            self.assertEqual(original, f.read())

    def test_report_finds_all_v4_problem_groups(self):
        first_path = os.path.join(self.board_dir, "cards", "t_first.json")
        second_path = os.path.join(self.board_dir, "cards", "t_second.json")
        first, second = read_json(first_path), read_json(second_path)
        first["column"] = "missing-column"
        first["labels"] = ["missing-label"]
        first["assignees"] = ["missing-user"]
        first["claim"] = {"status": "running", "claimed_at": "2020-01-01T00:00:00.000Z",
                          "heartbeat_at": "2020-01-01T00:00:00.000Z"}
        first["details"] = "x" * (5 * 1024 * 1024)
        second["id"] = first["id"]
        second["num"] = first["num"]
        second["column"] = first["column"]
        second["rank"] = first["rank"]
        second["comments"] = [{"id": "c_bad", "text": "Missing fields"}]
        write(first_path, first); write(second_path, second)
        person_path = os.path.join(self.board_dir, "people", "p_acme.json")
        person = read_json(person_path); person["stage"] = "Unknown"; write(person_path, person)
        os.makedirs(os.path.join(self.board_dir, "archive"))
        write(os.path.join(self.board_dir, "archive", "2026.json"),
              {"version": 3, "archive": True, "year": "2026", "tasks": [first], "contacts": [], "history": {}})
        with open(os.path.join(self.board_dir, "cards", "note.txt"), "w") as f:
            f.write("not a card")
        issues, _, code = kt.doctor_board(False)
        self.assertEqual(1, code)
        codes = {x["code"] for x in issues}
        self.assertTrue({"DUPLICATE_ID", "DUPLICATE_NUM", "FILE_NAME", "FILE_TYPE", "LIVE_AND_ARCHIVED",
                         "COLUMN", "LABEL", "ASSIGNEE", "STAGE", "CLAIM_FIELDS", "STALE_CLAIM",
                         "DUPLICATE_RANK", "COMMENT_FIELDS", "BOARD_SIZE", "FILE_SIZE"}.issubset(codes), codes)

    def test_v3_size_and_newer_schema_are_reported(self):
        shutil.rmtree(self.board_dir)
        shutil.copytree(os.path.join(FIXTURES, "v3"), self.board_dir)
        data = read_json(kt.FILE); data["padding"] = "x" * (601 * 1024); write(kt.FILE, data)
        issues, _, _ = kt.doctor_board(False)
        self.assertIn("BOARD_SIZE", {x["code"] for x in issues})
        data["version"] = kt.SCHEMA + 1; write(kt.FILE, data)
        issues, _, _ = kt.doctor_board(False)
        self.assertIn("NEW_SCHEMA", {x["code"] for x in issues})

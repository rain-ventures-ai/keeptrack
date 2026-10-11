"""Tests for board/kit/keeptrack.py against a local --file board. Run: python3 -m unittest discover tests"""
import contextlib, copy, importlib.util, io, json, os, random, re, shutil, subprocess, tempfile, unittest

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

    def test_list_searches_all_current_task_fields(self):
        data = self.read()
        data["tasks"][1]["details"] = "Merged but not published"
        data["tasks"][1]["labels"] = ["Release-Candidate"]
        write(self.file, data)
        for query in ("PUBLISHED", "release-candidate"):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                kt.cmd_list(Args(q=query, column=None, assignee=None, unclaimed=False, attention=False))
            self.assertIn("t_live", out.getvalue())
            self.assertNotIn("t_old", out.getvalue())

    def test_archive_then_unarchive_updates_both_files(self):
        self.quiet(kt.cmd_archive, Args(done_days=None, lost_days=None, keep_history=None, dry_run=False))
        arch = os.path.join(self.dir.name, "board", "archive", "2025.json")
        self.assertEqual([t["id"] for t in read_json(arch)["tasks"]], ["t_old"])
        self.quiet(kt.cmd_unarchive, Args(ref="t_old"))
        self.assertEqual(read_json(arch)["tasks"], [])
        d = self.read()
        self.assertIn("t_old", [t["id"] for t in d["tasks"]])
        self.assertEqual(d["archive"]["files"]["2025"], {"tasks": 0, "contacts": 0})

    def test_contact_methods_keep_legacy_first_values(self):
        p = {"id": "p_casey", "name": "Casey", "company": "Acme", "email": "work@example.test", "phone": "+44 20",
             "linkedin": "https://linkedin.com/in/casey", "links": [], "emails": [], "phones": []}
        kt.sync_person_methods(p)
        p["emails"].append({"id": "e_home", "label": "Personal", "value": "home@example.test"})
        p["phones"].append({"id": "ph_mobile", "label": "Mobile", "value": "+44 77"})
        args = Args(name=None, company=None, role=None, email="new-work@example.test", phone=None, linkedin=None,
                    value=None, source=None, notes=None, next=None, stage=None, due=None)
        kt.set_fields(board(), p, args)
        self.assertEqual([(x["label"], x["value"]) for x in p["emails"]],
                         [("Email", "new-work@example.test"), ("Personal", "home@example.test")])
        self.assertEqual(p["email"], "new-work@example.test")
        self.assertEqual([x["value"] for x in p["phones"]], ["+44 20", "+44 77"])
        self.assertEqual(p["linkedin"], "https://linkedin.com/in/casey")

    def test_person_output_distinguishes_references_and_resources(self):
        data = self.read(); data["clients"] = ["Acme"]; data["contacts"] = [{"id": "p_casey", "name": "Casey", "company": "Acme", "role": "",
            "email": "work@example.test", "phone": "+44 20", "linkedin": "https://linkedin.com/in/casey", "emails": [{"id": "e_work", "label": "Work", "value": "work@example.test"}, {"id": "e_home", "label": "Personal", "value": "home@example.test"}],
            "phones": [{"id": "ph_mobile", "label": "Mobile", "value": "+44 20"}], "links": [{"title": "LinkedIn", "url": "https://linkedin.com/in/casey"}, {"title": "Blog", "url": "https://casey.example"}],
            "stage": "New", "value": "", "source": "", "notes": "", "next": "", "next_due": "", "comments": [], "history": []}]; data["client_info"] = {"Acme": {"links": [{"title": "Drive", "url": "https://drive.google.com/x"}, {"title": "Local", "url": "/srv/acme"}]}}; write(self.file, data)
        out = io.StringIO()
        with contextlib.redirect_stdout(out): kt.cmd_person(Args(ref="Casey"))
        text = out.getvalue(); self.assertIn("email (Work): work@example.test", text); self.assertIn("email (Personal): home@example.test", text)
        self.assertIn("profile/reference link: Blog", text); self.assertIn("file/folder resource (Acme): Local  /srv/acme", text)
        self.assertIn("cloud resources need the matching connector/plugin/MCP", text)

    def test_client_link_accepts_local_resource_path(self):
        self.quiet(kt.cmd_client_link, Args(client="Acme", url="/srv/clients/acme", title="Local folder"))
        self.assertEqual(self.read()["client_info"]["Acme"]["links"], [{"title": "Local folder", "url": "/srv/clients/acme"}])

    def test_email_touch_keeps_source_time_and_is_idempotent(self):
        data = self.read(); data["contacts"] = [{"id": "p_casey", "name": "Casey", "company": "Acme", "stage": "New",
            "email": "casey@example.test", "emails": [{"id": "e_work", "label": "Work", "value": "casey@example.test"}],
            "phone": "", "phones": [], "linkedin": "", "links": [], "role": "", "value": "", "source": "",
            "notes": "", "next": "", "next_due": "", "comments": [], "history": []}]; write(self.file, data)
        source_id = "email:" + "a" * 64
        args = Args(ref="p_casey", text="Email received: confirmed Friday's call.", channel="email", draft=False,
                    at="2026-10-08T10:30:00+01:00", source_id=source_id, company=None, role=None, email=None,
                    phone=None, linkedin=None, value=None, source=None, notes=None, next=None, stage=None, due=None)
        self.quiet(kt.cmd_touch, args); self.quiet(kt.cmd_touch, args)
        person = self.read()["contacts"][0]
        self.assertEqual(1, len(person["comments"]))
        self.assertEqual("2026-10-08T09:30:00Z", person["comments"][0]["at"])
        self.assertEqual(source_id, person["comments"][0]["source_id"])
        self.assertEqual("Contacted", person["stage"])

    def test_task_link_accepts_local_resource_path(self):
        self.quiet(kt.cmd_link, Args(id="t_live", url="/srv/tasks/live", title="Working folder"))
        task = next(x for x in self.read()["tasks"] if x["id"] == "t_live")
        self.assertEqual(task["links"], [{"title": "Working folder", "url": "/srv/tasks/live"}])

    def test_list_filters_by_label(self):
        data = self.read(); data["tasks"][1]["labels"] = ["call"]; write(self.file, data)
        def listed(label):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                kt.cmd_list(Args(q=None, column=None, assignee=None, unclaimed=False, attention=False,
                                 project=None, client=None, label=label))
            return out.getvalue()
        text = listed("call")
        self.assertIn("t_live", text); self.assertNotIn("t_old", text)
        self.assertEqual("", listed("Call"))   # exact name, as the web board's label filter

    def test_todo_edit_changes_text_in_place(self):
        self.quiet(kt.cmd_todo_edit, Args(id="t_live", n="1", text="A, revised"))
        self.quiet(kt.cmd_todo_edit, Args(id="t_live", n="2", text="B2"))
        todos = self.read()["tasks"][1]["todos"]
        self.assertEqual(todos, [{"id": "d_a", "text": "A, revised", "done": False}, {"text": "B2", "done": False}])
        with self.assertRaises(SystemExit):
            self.quiet(kt.cmd_todo_edit, Args(id="t_live", n="3", text="nope"))
        self.assertEqual(self.read()["tasks"][1]["todos"], todos)


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


from board_fixtures import FIXTURES, copy_board_fixture


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
        copy_board_fixture("v4", self.board_dir)
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

    def test_an_id_that_is_a_path_never_becomes_a_file_outside_the_board(self):
        # Board data comes from anyone who can write the repo: a card whose id is a path must not make keeptrack write
        # outside the board folder on another member's machine.
        path = os.path.join(self.board_dir, "cards", "t_first.json")
        card = read_json(path); card["id"] = "../../escape"; write(path, card)
        before = tree_bytes(self.temp.name)
        with self.assertRaises(SystemExit) as e:
            self.quiet(kt.cmd_add, Args(title="New", column="todo", client=None, priority="medium", due=None,
                                        label=None, assign=None, details=None, todo=None))
        self.assertIn("can't be a file name", str(e.exception))
        self.assertEqual(before, tree_bytes(self.temp.name))
        self.assertFalse(os.path.exists(os.path.join(self.temp.name, "escape.json")))
        with self.assertRaises(SystemExit):
            kt._local_path("cards/../../../x.json")
        self.assertTrue(kt._local_path("cards/t_ok.json").endswith(os.path.join("board", "cards", "t_ok.json")))

    def test_a_symlinked_folder_is_never_followed(self):
        # A board repo can carry a committed symlink: cards -> a folder elsewhere on the member's machine.
        outside = os.path.join(self.temp.name, "outside"); os.makedirs(outside)
        shutil.move(os.path.join(self.board_dir, "cards"), os.path.join(outside, "cards"))
        os.symlink(os.path.join(outside, "cards"), os.path.join(self.board_dir, "cards"))
        before = tree_bytes(outside)
        with self.assertRaises(SystemExit) as e:
            kt.load_board()
        self.assertIn("outside the board folder", str(e.exception))
        self.assertEqual(before, tree_bytes(outside))

    def test_add_changes_settings_and_one_new_card(self):
        before = tree_bytes(self.board_dir)
        self.quiet(kt.cmd_add, Args(title="New", column="todo", client=None, priority="medium", due=None,
                                    label=None, assign=None, details=None, todo=None))
        changed = self.changed(before)
        self.assertIn("tasks.json", changed)
        self.assertEqual(1, len([x for x in changed if x.startswith("cards/")]))
        self.assertEqual(2, len(changed))

    def tick_first_todos(self):
        """done refuses open to-dos, so a test of done itself starts from a card whose to-dos are all ticked."""
        path = os.path.join(self.board_dir, "cards", "t_first.json")
        card = read_json(path)
        for d in card["todos"]:
            d["done"] = True
        write(path, card)

    def test_comment_move_and_done_change_only_the_card(self):
        self.tick_first_todos()
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

    def test_done_gives_a_card_a_unique_rank_in_its_new_column(self):
        second_path = os.path.join(self.board_dir, "cards", "t_second.json")
        second = read_json(second_path); second["column"] = "done"; second["rank"] = "a0"; write(second_path, second)
        self.tick_first_todos()
        self.quiet(kt.cmd_done, Args(id="t_first", note="Complete"))
        first = read_json(os.path.join(self.board_dir, "cards", "t_first.json"))
        self.assertEqual(first["column"], "done")
        self.assertGreater(first["rank"], second["rank"])

    def test_release_gives_a_card_a_unique_rank_in_its_new_column(self):
        second_path = os.path.join(self.board_dir, "cards", "t_second.json")
        second = read_json(second_path); second["column"] = "done"; second["rank"] = "a0"; write(second_path, second)
        self.quiet(kt.cmd_release, Args(id="t_first", column="done"))
        first = read_json(os.path.join(self.board_dir, "cards", "t_first.json"))
        self.assertEqual(first["column"], "done")
        self.assertGreater(first["rank"], second["rank"])

    def test_claim_gives_a_card_a_unique_rank_in_its_new_column(self):
        root = read_json(kt.FILE); root["columns"].append({"id": "in-progress", "name": "In progress"}); write(kt.FILE, root)
        second_path = os.path.join(self.board_dir, "cards", "t_second.json")
        second = read_json(second_path); second["column"] = "in-progress"; second["rank"] = "a0"; write(second_path, second)
        args = Args(id="t_first", for_user="alex", agent="codex", session="rank-test", force=False,
                    note="Test", session_url=None)
        self.quiet(kt.cmd_claim, args)
        first = read_json(os.path.join(self.board_dir, "cards", "t_first.json"))
        self.assertEqual(first["column"], "in-progress")
        self.assertGreater(first["rank"], second["rank"])

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
        copy_board_fixture("v3", self.board_dir)
        self.old_file = kt.FILE
        kt.FILE = os.path.join(self.board_dir, "tasks.json")

    def tearDown(self):
        kt.FILE = self.old_file
        self.temp.cleanup()

    def test_migrate_dry_run_lists_project_paths(self):
        data = read_json(kt.FILE)
        data["projects"] = [{"id": "pr_test01ab", "client": "Acme", "name": "Pilot", "north_star": "",
                              "status": "active", "links": [], "people": [], "created": "2026-01-01T00:00:00Z",
                              "updated": "2026-01-01T00:00:00Z"}]
        data["tasks"][0]["project"] = "pr_test01ab"
        write(kt.FILE, data)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            kt.cmd_migrate(Args(to=4, dry_run=True))
        text = out.getvalue()
        self.assertIn("projects/pr_test01ab.json", text)
        self.assertIn("dry run: wrote nothing", text)

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
        copy_board_fixture("v4", self.board_dir)
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
        copy_board_fixture("v3", self.board_dir)
        data = read_json(kt.FILE); data["padding"] = "x" * (601 * 1024); write(kt.FILE, data)
        issues, _, _ = kt.doctor_board(False)
        self.assertIn("BOARD_SIZE", {x["code"] for x in issues})
        data["version"] = kt.SCHEMA + 1; write(kt.FILE, data)
        issues, _, _ = kt.doctor_board(False)
        self.assertIn("NEW_SCHEMA", {x["code"] for x in issues})

    def run_cli(self, *flags):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = kt.cmd_doctor(Args(fix="--fix" in flags, json="--json" in flags))
        return code, out.getvalue()

    def test_exit_codes_and_json_output(self):
        code, out = self.run_cli()
        self.assertEqual((0, True), (code, "healthy" in out))
        root = read_json(kt.FILE); root["next_num"] = 1; write(kt.FILE, root)
        code, out = self.run_cli("--json")
        report = json.loads(out)
        self.assertEqual(1, code)
        self.assertFalse(report["healthy"])
        self.assertEqual(["NEXT_NUM"], [x["code"] for x in report["issues"]])
        with open(kt.FILE, "w") as f:
            f.write("{broken")
        code, _ = self.run_cli()
        self.assertEqual(2, code)

    def test_fix_does_nothing_when_ids_are_duplicated(self):
        second_path = os.path.join(self.board_dir, "cards", "t_second.json")
        second = read_json(second_path); second["id"] = "t_first"; second.pop("rank"); write(second_path, second)
        before = tree_bytes(self.board_dir)
        issues, fixes, code = kt.doctor_board(True)
        self.assertEqual((1, []), (code, fixes))
        self.assertIn("DUPLICATE_ID", {x["code"] for x in issues})
        self.assertEqual(before, tree_bytes(self.board_dir))

    def test_fix_does_not_rename_over_an_existing_file(self):
        first = read_json(os.path.join(self.board_dir, "cards", "t_first.json"))
        write(os.path.join(self.board_dir, "cards", "copy.json"), first)
        before = tree_bytes(self.board_dir)
        issues, fixes, _ = kt.doctor_board(True)
        self.assertIn("FILE_NAME", {x["code"] for x in issues})
        self.assertEqual([], fixes)
        self.assertEqual(before, tree_bytes(self.board_dir))

    def test_fix_does_nothing_on_a_newer_schema(self):
        root = read_json(kt.FILE); root["version"] = kt.SCHEMA + 1; root["next_num"] = 1; write(kt.FILE, root)
        before = tree_bytes(self.board_dir)
        _, fixes, _ = kt.doctor_board(True)
        self.assertEqual([], fixes)
        self.assertEqual(before, tree_bytes(self.board_dir))

    def test_fix_rebuilds_duplicate_ranks_and_keeps_order(self):
        first_path = os.path.join(self.board_dir, "cards", "t_first.json")
        second_path = os.path.join(self.board_dir, "cards", "t_second.json")
        first, second = read_json(first_path), read_json(second_path)
        order = [t["id"] for t in sorted([first, second], key=kt.task_order_key)]
        second["rank"] = first["rank"]; write(second_path, second)
        _, fixes, _ = kt.doctor_board(True)
        self.assertTrue(any("rebuilt ranks" in x for x in fixes))
        first, second = read_json(first_path), read_json(second_path)
        self.assertNotEqual(first["rank"], second["rank"])
        self.assertEqual(order, [t["id"] for t in sorted([first, second], key=kt.task_order_key)])
        self.assertEqual(([], [], 0), kt.doctor_board(False))

    def test_fix_on_a_v3_board_keeps_one_file(self):
        shutil.rmtree(self.board_dir)
        copy_board_fixture("v3", self.board_dir)
        data = read_json(kt.FILE); data["tasks"][1].pop("num"); data["next_num"] = 1; write(kt.FILE, data)
        _, fixes, _ = kt.doctor_board(True)
        self.assertTrue(fixes)
        self.assertEqual(["tasks.json"], sorted(os.listdir(self.board_dir)))
        self.assertEqual(([], [], 0), kt.doctor_board(False))


class PhaseOneSafety(unittest.TestCase):
    """Schema 4 must not reach real boards before the web board can read it (phase 2)."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.saved = {k: getattr(kt, k) for k in ("FILE", "ROOT", "REPO", "BRANCH", "WRITE", "gh", "need_repo_clone",
                                                  "cmd_kit_update", "kit_fetch", "remote_repo")}

    def tearDown(self):
        for k, v in self.saved.items():
            setattr(kt, k, v)
        self.temp.cleanup()

    def test_manifest_schema_is_one_the_web_board_reads(self):
        with open(os.path.join(HERE, "..", "board", "kit", "manifest.json")) as f:
            schema = json.load(f)["schema"]
        with open(os.path.join(HERE, "..", "board", "board.js")) as f:
            known = int(re.search(r"const KNOWN_SCHEMA = (\d+)", f.read()).group(1))
        self.assertLessEqual(schema, known)

    def test_kit_update_replaces_the_renamed_onboarding_skill(self):
        kt.ROOT = self.temp.name
        kt.need_repo_clone = lambda: None
        old = os.path.join(self.temp.name, ".claude", "skills", "keeptrack-onboard")
        os.makedirs(old)
        with open(os.path.join(old, "SKILL.md"), "w") as f:
            f.write("old skill")
        source = os.path.join(HERE, "..", "board", "kit")
        with contextlib.redirect_stdout(io.StringIO()) as out:
            kt.cmd_kit_update(Args(source=source, quiet=True))
        new = os.path.join(self.temp.name, ".claude", "skills", "onboard-keeptrack", "SKILL.md")
        self.assertFalse(os.path.exists(old))
        self.assertTrue(os.path.isfile(new))
        with open(new) as f:
            self.assertIn("name: onboard-keeptrack", f.read())
        email_skill = os.path.join(self.temp.name, ".claude", "skills", "keeptrack-email", "SKILL.md")
        email_routine = os.path.join(self.temp.name, ".claude", "skills", "keeptrack-email", "references", "routines.md")
        self.assertTrue(os.path.isfile(email_skill))
        self.assertTrue(os.path.isfile(email_routine))
        with open(email_skill) as f:
            self.assertIn("name: keeptrack-email", f.read())
        self.assertIn("removed: .claude/skills/keeptrack-onboard", out.getvalue())

    def test_bare_migrate_does_not_split(self):
        board_dir = os.path.join(self.temp.name, "board")
        copy_board_fixture("v3", board_dir)
        kt.FILE = os.path.join(board_dir, "tasks.json")
        old = read_json(kt.FILE); old["version"] = 2; write(kt.FILE, old)
        with contextlib.redirect_stdout(io.StringIO()):
            kt.cmd_migrate(Args(to=None, dry_run=False))
        data = read_json(kt.FILE)
        self.assertEqual(3, data["version"])
        self.assertNotIn("layout", data)
        self.assertEqual(2, len(data["tasks"]))
        self.assertFalse(os.path.exists(os.path.join(board_dir, "cards")))

    def test_init_writes_a_v4_split_board(self):
        kt.ROOT, kt.REPO = self.temp.name, "acme/board"
        kt.need_repo_clone = lambda: None
        kt.cmd_kit_update = lambda a: None
        template = os.path.join(HERE, "..", "board", "kit", "templates", "README.md")
        with open(template, "rb") as f:
            readme_template = f.read()
        kt.kit_fetch = lambda src, source=None: readme_template if src == "templates/README.md" else b""
        with contextlib.redirect_stdout(io.StringIO()):
            kt.cmd_init(Args(person=["alex:Alex"], client=None, source=None))
        data = read_json(os.path.join(self.temp.name, kt.PATH))
        self.assertEqual(4, data["version"])
        self.assertEqual("split", data["layout"])
        self.assertNotIn("tasks", data)
        self.assertNotIn("contacts", data)
        kt.FILE = os.path.join(self.temp.name, kt.PATH)
        loaded = kt.load_board()
        self.assertEqual([], loaded["tasks"])
        self.assertEqual([], loaded["contacts"])
        with open(os.path.join(self.temp.name, "README.md"), encoding="utf-8") as f:
            readme = f.read()
        self.assertIn("This board is powered by [Keeptrack]", readme)
        self.assertIn("repo=acme%2Fboard", readme)
        self.assertIn("path=board%2Ftasks.json", readme)

        # A project may already have its own README. init is safe to rerun and must never replace it.
        with open(os.path.join(self.temp.name, "README.md"), "w", encoding="utf-8") as f:
            f.write("Existing project README\n")
        with contextlib.redirect_stdout(io.StringIO()):
            kt.cmd_init(Args(person=["alex:Alex"], client=None, source=None))
        with open(os.path.join(self.temp.name, "README.md"), encoding="utf-8") as f:
            self.assertEqual("Existing project README\n", f.read())

    def test_git_load_reads_every_board_file_in_one_batch(self):
        remote, work = os.path.join(self.temp.name, "remote.git"), os.path.join(self.temp.name, "work")
        run = lambda *a, cwd=None: subprocess.run(a, cwd=cwd, check=True, capture_output=True)
        run("git", "init", "-q", "--bare", "-b", "main", remote)
        run("git", "clone", "-q", remote, work)
        copy_board_fixture("v4", os.path.join(work, "board"))
        with open(os.path.join(work, "README.md"), "w") as f:
            f.write("not a board file\n")
        run("git", "add", "-A", cwd=work)
        run("git", "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm", "board", cwd=work)
        run("git", "push", "-q", "origin", "main", cwd=work)
        kt.FILE, kt.ROOT, kt.REPO, kt.BRANCH, kt.WRITE = None, work, "acme/board", "main", "git"
        kt.remote_repo = lambda url: "acme/board"
        files, head = kt._git_snapshot()
        self.assertEqual({"tasks.json", "cards/t_first.json", "cards/t_second.json", "people/p_acme.json"}, set(files))
        for rel, entry in files.items():
            with open(os.path.join(FIXTURES, "v4", *rel.split("/")), encoding="utf-8") as f:
                self.assertEqual(f.read(), entry["text"])
        data = kt.load_board()
        self.assertEqual({"t_first", "t_second"}, {t["id"] for t in data["tasks"]})

    def test_api_load_reads_only_the_board_subtree(self):
        calls = []
        cache = os.path.join(self.temp.name, "cache")
        def fake_gh(*args, body=None):
            calls.append(args[0])
            ep = args[0]
            if "/git/ref/heads/" in ep:
                return 0, json.dumps({"object": {"sha": "c1"}}), ""
            if ep.endswith("/git/commits/c1"):
                return 0, json.dumps({"tree": {"sha": "root"}}), ""
            if ep.endswith("/git/trees/root"):
                return 0, json.dumps({"tree": [{"path": "clients", "type": "tree", "sha": "big"},
                                               {"path": "board", "type": "tree", "sha": "bt"}]}), ""
            if ep.endswith("/git/trees/bt?recursive=1"):
                return 0, json.dumps({"sha": "bt", "tree": [{"path": "tasks.json", "type": "blob", "sha": "s1"},
                                                            {"path": "cards", "type": "tree", "sha": "x"},
                                                            {"path": "cards/t_a.json", "type": "blob", "sha": "s2"}]}), ""
            if ep.endswith("/git/blobs/s1"):
                return 0, json.dumps({"encoding": "utf-8", "content": json.dumps({"version": 4, "layout": "split", "next_num": 2})}), ""
            if ep.endswith("/git/blobs/s2"):
                return 0, json.dumps({"encoding": "utf-8", "content": json.dumps({"id": "t_a", "num": 1, "column": "todo"})}), ""
            return 1, "", f"unexpected call {ep}"
        kt.gh, kt.FILE, kt.REPO, kt.BRANCH, kt.WRITE = fake_gh, None, "acme/board", "main", "api"
        old_cache = kt.CACHE_DIR; kt.CACHE_DIR = cache
        try:
            files, state = kt._api_snapshot()
        finally:
            kt.CACHE_DIR = old_cache
        self.assertEqual({"tasks.json", "cards/t_a.json"}, set(files))
        self.assertEqual("root", state["base_tree"])
        self.assertFalse(any("big" in c or c.endswith("/git/trees/c1?recursive=1") for c in calls))

    def test_doctor_fix_in_git_mode_makes_one_commit(self):
        remote, work = os.path.join(self.temp.name, "remote.git"), os.path.join(self.temp.name, "work")
        run = lambda *a, cwd=None: subprocess.run(a, cwd=cwd, check=True, capture_output=True, text=True)
        run("git", "init", "-q", "--bare", "-b", "main", remote)
        run("git", "clone", "-q", remote, work)
        copy_board_fixture("v4", os.path.join(work, "board"))
        card_path = os.path.join(work, "board", "cards", "t_first.json")
        card = read_json(card_path); card.pop("rank"); card["comments"][0].pop("id"); write(card_path, card)
        root = read_json(os.path.join(work, "board", "tasks.json")); root["next_num"] = 1
        write(os.path.join(work, "board", "tasks.json"), root)
        run("git", "add", "-A", cwd=work)
        run("git", "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm", "board", cwd=work)
        run("git", "push", "-q", "origin", "main", cwd=work)
        kt.FILE, kt.ROOT, kt.REPO, kt.BRANCH, kt.WRITE = None, work, "acme/board", "main", "git"
        kt.remote_repo = lambda url: "acme/board"
        env = {k: os.environ.get(k) for k in ("GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL", "GIT_COMMITTER_NAME", "GIT_COMMITTER_EMAIL")}
        os.environ.update(GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.com")
        try:
            _, fixes, _ = kt.doctor_board(True)
        finally:
            for k, v in env.items():
                os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
        self.assertGreaterEqual(len(fixes), 3)
        log = run("git", "--git-dir", remote, "log", "--oneline", "main").stdout.splitlines()
        self.assertEqual(2, len(log))
        self.assertIn("Repair board data", log[0])
        self.assertEqual(([], [], 0), kt.doctor_board(False))


class VisibilityAlarm(unittest.TestCase):
    """The optional visibility-alarm workflow: off by default, on with the flag, refreshed by kit-update once installed."""
    KIT = os.path.join(HERE, "..", "board", "kit")
    WORKFLOW = os.path.join(".github", "workflows", "visibility-alarm.yml")

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.saved = {k: getattr(kt, k) for k in ("ROOT", "REPO", "BRANCH", "need_repo_clone", "kit_fetch")}
        self.addCleanup(lambda: [setattr(kt, k, v) for k, v in self.saved.items()])
        kt.ROOT, kt.REPO, kt.BRANCH = self.temp.name, "acme/board", "main"
        kt.need_repo_clone = lambda: None

    def workflow(self):
        return os.path.join(self.temp.name, self.WORKFLOW)

    def template_bytes(self, kit=None):
        with open(os.path.join(kit or self.KIT, "templates", "visibility-alarm.yml"), "rb") as f:
            return f.read()

    def test_not_installed_by_default(self):
        with contextlib.redirect_stdout(io.StringIO()):
            kt.cmd_kit_update(Args(source=self.KIT, quiet=True))
        self.assertFalse(os.path.exists(self.workflow()))
        self.assertFalse(os.path.exists(os.path.join(self.temp.name, ".github")))

    def test_installed_with_the_flag(self):
        with contextlib.redirect_stdout(io.StringIO()):
            kt.cmd_kit_update(Args(source=self.KIT, quiet=True, visibility_alarm=True))
        with open(self.workflow(), "rb") as f:
            self.assertEqual(self.template_bytes(), f.read())

    def test_kit_update_refreshes_it_when_present(self):
        # Installed earlier, then the kit ships a new version of the workflow: a plain kit-update must carry it over.
        with contextlib.redirect_stdout(io.StringIO()):
            kt.cmd_kit_update(Args(source=self.KIT, quiet=True, visibility_alarm=True))
        newer = os.path.join(self.temp.name, "kit")
        shutil.copytree(self.KIT, newer)
        with open(os.path.join(newer, "templates", "visibility-alarm.yml"), "ab") as f:
            f.write(b"# newer kit\n")
        with contextlib.redirect_stdout(io.StringIO()) as out:
            kt.cmd_kit_update(Args(source=newer, quiet=True))
        with open(self.workflow(), "rb") as f:
            self.assertEqual(self.template_bytes(newer), f.read())
        self.assertIn(".github/workflows/visibility-alarm.yml", out.getvalue())

    def test_init_installs_it_only_with_the_flag(self):
        def fetch(name, source=None):
            with open(os.path.join(self.KIT, name), "rb") as f:
                return f.read()
        kt.kit_fetch = fetch
        with contextlib.redirect_stdout(io.StringIO()):
            kt.cmd_init(Args(person=["alex:Alex"], client=None, source=None))
        self.assertFalse(os.path.exists(self.workflow()))
        with contextlib.redirect_stdout(io.StringIO()):
            kt.cmd_init(Args(person=["alex:Alex"], client=None, source=None, visibility_alarm=True))
        with open(self.workflow(), "rb") as f:
            self.assertEqual(self.template_bytes(), f.read())

    def test_workflow_is_valid_yaml_with_the_expected_triggers_and_permissions(self):
        try:
            import yaml
        except ImportError:
            self.skipTest("pyyaml is not installed")
        with open(os.path.join(self.KIT, "templates", "visibility-alarm.yml"), encoding="utf-8") as f:
            wf = yaml.safe_load(f)
        triggers = wf[True] if True in wf else wf["on"]  # YAML 1.1 reads the key `on` as a boolean
        self.assertIn("public", triggers)
        self.assertIn("schedule", triggers)
        self.assertIn("workflow_dispatch", triggers)
        self.assertEqual({"contents": "read", "issues": "write"}, wf["permissions"])


class MoveInPlace(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.board_dir = os.path.join(self.temp.name, "board")
        copy_board_fixture("v4", self.board_dir)
        self.old_file = kt.FILE
        kt.FILE = os.path.join(self.board_dir, "tasks.json")

    def tearDown(self):
        kt.FILE = self.old_file
        self.temp.cleanup()

    def test_move_without_column_keeps_the_column(self):
        first = read_json(os.path.join(self.board_dir, "cards", "t_first.json"))
        second = read_json(os.path.join(self.board_dir, "cards", "t_second.json"))
        self.assertEqual(first["column"], second["column"])
        with contextlib.redirect_stdout(io.StringIO()):
            kt.cmd_move(Args(id="t_second", column=None, column_pos=None, before=None, after=None, top=True,
                             priority=None, note=None))
        moved = read_json(os.path.join(self.board_dir, "cards", "t_second.json"))
        self.assertEqual(second["column"], moved["column"])
        self.assertLess(moved["rank"], first["rank"])


class Verify(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.board_dir = os.path.join(self.temp.name, "board")
        copy_board_fixture("v3", self.board_dir)
        self.backup = os.path.join(self.temp.name, "backup-tasks.json")
        shutil.copy(os.path.join(self.board_dir, "tasks.json"), self.backup)
        self.old_file = kt.FILE
        kt.FILE = os.path.join(self.board_dir, "tasks.json")

    def tearDown(self):
        kt.FILE = self.old_file
        self.temp.cleanup()

    def run_verify(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = kt.cmd_verify(Args(against=self.backup))
        return code, out.getvalue()

    def test_migrated_board_matches_its_backup(self):
        with contextlib.redirect_stdout(io.StringIO()):
            kt.cmd_migrate(Args(to=4, dry_run=False))
        code, out = self.run_verify()
        self.assertEqual(0, code, out)
        self.assertIn("OK", out)

    def test_a_lost_card_and_a_changed_field_are_reported(self):
        with contextlib.redirect_stdout(io.StringIO()):
            kt.cmd_migrate(Args(to=4, dry_run=False))
        os.remove(os.path.join(self.board_dir, "cards", "t_second.json"))
        card_path = os.path.join(self.board_dir, "cards", "t_first.json")
        card = read_json(card_path); card["title"] = "Changed"; write(card_path, card)
        code, out = self.run_verify()
        self.assertEqual(1, code)
        self.assertIn("card t_second is missing", out)
        self.assertIn("card t_first differs: title", out)


class ImportOnSplitBoard(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.board_dir = os.path.join(self.temp.name, "board")
        copy_board_fixture("v4", self.board_dir)
        self.old_file = kt.FILE
        kt.FILE = os.path.join(self.board_dir, "tasks.json")
        self.staging = os.path.join(self.temp.name, "staging.json")
        write(self.staging, {"source": "test", "people": [{"name": "Bea Acme", "company": "Acme", "evidence": "test"}],
                             "tasks": [{"title": "Send the Acme notes", "client": "Acme", "evidence": "test"}]})

    def tearDown(self):
        kt.FILE = self.old_file
        self.temp.cleanup()

    def test_import_writes_new_files_with_rank_and_long_ids(self):
        before = set(tree_bytes(self.board_dir))
        with contextlib.redirect_stdout(io.StringIO()):
            kt.cmd_import(Args(path=self.staging, source=None, dry_run=False))
        new = set(tree_bytes(self.board_dir)) - before
        card = [p for p in new if p.startswith("cards")]
        person = [p for p in new if p.startswith("people")]
        self.assertEqual((1, 1), (len(card), len(person)), new)
        self.assertRegex(os.path.basename(card[0]), r"^t_[0-9a-z]{10}\.json$")
        self.assertTrue(kt.valid_rank(read_json(os.path.join(self.board_dir, card[0]))["rank"]))
        self.assertNotIn("tasks", read_json(kt.FILE))

    def test_dry_run_on_a_v3_board_does_not_split_in_memory(self):
        shutil.rmtree(self.board_dir)
        copy_board_fixture("v3", self.board_dir)
        before = tree_bytes(self.board_dir)
        with contextlib.redirect_stdout(io.StringIO()):
            kt.cmd_import(Args(path=self.staging, source=None, dry_run=True))
        self.assertEqual(before, tree_bytes(self.board_dir))
        data = kt.load_board(); kt.migrate_data(data)
        self.assertEqual(3, data["version"])
        self.assertNotIn("layout", data)


class DuplicateFiles(unittest.TestCase):
    def test_save_is_refused_when_two_files_share_an_id(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        board_dir = os.path.join(temp.name, "board")
        copy_board_fixture("v4", board_dir)
        old = kt.FILE; kt.FILE = os.path.join(board_dir, "tasks.json"); self.addCleanup(setattr, kt, "FILE", old)
        shutil.copy(os.path.join(board_dir, "cards", "t_first.json"), os.path.join(board_dir, "cards", "copy.json"))
        before = tree_bytes(board_dir)
        with self.assertRaises(SystemExit) as e:
            with contextlib.redirect_stdout(io.StringIO()):
                kt.cmd_comment(Args(id="t_second", text="hello", note=None))
        self.assertIn("same id", str(e.exception))
        self.assertEqual(before, tree_bytes(board_dir))


class CrmProjects(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        os.makedirs(os.path.join(self.dir.name, "board"))
        self.file = os.path.join(self.dir.name, "board", "tasks.json")
        d = board()
        d["clients"] = ["Acme"]
        d["client_info"] = {"Acme": {"links": []}}
        d["projects"] = []
        d["next_num"] = 3
        d["contacts"] = [{"id": "p_1", "name": "Bea", "company": "Acme", "email": "bea@example.com", "stage": "New",
                          "links": [], "comments": [], "history": []}]
        write(self.file, d)
        self.old = kt.FILE
        kt.FILE = self.file

    def tearDown(self):
        kt.FILE = self.old
        self.dir.cleanup()

    def test_member_person_is_listed_as_member_and_never_a_follow_up(self):
        """v33: a CRM person whose GitHub login is a board member's is that member's own record, not a contact."""
        d = read_json(self.file)
        d.setdefault("people", []).append({"github": "osouthgate", "name": "Oliver"})
        d["contacts"].append({"id": "p_me", "name": "Oliver", "company": "Rain Ventures", "github": "OSouthgate", "stage": "New",
                              "links": [], "comments": [], "history": []})
        write(self.file, d)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            kt.cmd_today(Args())
        self.assertIn("Bea", out.getvalue())
        self.assertNotIn("Oliver", out.getvalue(), "a member is never a follow-up")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            kt.cmd_people(Args(stage=None, q=None))
        self.assertIn("p_me  Oliver  [board member @osouthgate: own record, not a contact]", out.getvalue())
        self.assertIn("[New]", out.getvalue())   # Bea is still a contact

    def test_a_members_login_on_two_people_hides_neither(self):
        """v34: only the ONE person with a member's login is their own record; a duplicate can't hide a real contact."""
        d = read_json(self.file)
        d.setdefault("people", []).append({"github": "osouthgate", "name": "Oliver"})
        d["contacts"][0].update(github="osouthgate", next_due="2020-01-01")   # Bea, an overdue contact, given the member's login
        d["contacts"].append({"id": "p_me", "name": "Oliver", "github": "osouthgate", "stage": "New", "links": [], "comments": [], "history": []})
        write(self.file, d)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            kt.cmd_today(Args())
        self.assertIn("OVERDUE", out.getvalue()); self.assertIn("Bea", out.getvalue())
        self.assertIn("p_me  Oliver  [New]", out.getvalue(), "the member's own record is a contact again too")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            kt.cmd_people(Args(stage=None, q=None))
        self.assertNotIn("board member", out.getvalue())
        issues, _, _ = kt.doctor_board(False)
        self.assertIn("MEMBER_PERSON_DUP", {x["code"] for x in issues})
        # ids play no part: the member's record and other contacts saved with no id hide nothing (security review of #77)
        d = read_json(self.file); d["contacts"] = [{"name": "Me", "github": "osouthgate", "stage": "New"},
                                                  {"name": "Ghost", "stage": "New", "next_due": "2020-01-01"}]
        write(self.file, d)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            kt.cmd_today(Args())
        self.assertIn("Ghost", out.getvalue()); self.assertNotIn("Me ", out.getvalue())
        d["people"] = None; write(self.file, d)   # a null people[] never crashes today or doctor
        with contextlib.redirect_stdout(io.StringIO()):
            kt.cmd_today(Args())
        kt.doctor_board(False)

    def test_client_set_north_star_and_project_lifecycle(self):
        with contextlib.redirect_stdout(io.StringIO()):
            kt.cmd_client_set(Args(client="Acme", north_star="One view of orders"))
            kt.cmd_project_add(Args(name="Rollout", client="Acme", north_star="Go live in Q1", status="active"))
        data = read_json(self.file)
        self.assertEqual("One view of orders", data["client_info"]["Acme"]["north_star"])
        pr = data["projects"][0]
        self.assertTrue(pr["id"].startswith("pr_"))
        self.assertEqual("Rollout", pr["name"])
        with contextlib.redirect_stdout(io.StringIO()):
            kt.cmd_add(Args(title="Wire stock feed", column="todo", client="Acme", project=pr["id"],
                            priority="medium", due=None, assign=None, label=None, details=None, todo=None))
            kt.cmd_task_set(Args(id="t_live", client=None, project=pr["id"], contact=None))
        data = read_json(self.file)
        live = next(t for t in data["tasks"] if t["id"] == "t_live")
        self.assertEqual(pr["id"], live["project"])
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            kt.cmd_list(Args(column=None, assignee=None, client=None, project=pr["id"], unclaimed=False,
                             attention=False, q=None))
        self.assertIn("Wire stock feed", out.getvalue())
        with contextlib.redirect_stdout(io.StringIO()):
            kt.cmd_project_person(Args(ref=pr["id"], email="bea@example.com", remove=False))
        with contextlib.redirect_stdout(out):
            out.truncate(0); out.seek(0)
            kt.cmd_project(Args(ref=pr["id"]))
        text = out.getvalue()
        self.assertIn("bea@example.com", text)
        self.assertIn("Wire stock feed", text)

    def test_project_show_lists_only_open_tasks_and_resolves_name(self):
        with contextlib.redirect_stdout(io.StringIO()):
            kt.cmd_project_add(Args(name="Rollout", client="Acme", north_star="Go live in Q1", status="active"))
            pid = read_json(self.file)["projects"][0]["id"]
            kt.cmd_add(Args(title="Wire stock feed", column="todo", client="Acme", project=pid,
                            priority="medium", due=None, assign=None, label=None, details=None, todo=None))
            kt.cmd_add(Args(title="Shipped invoice", column="done", client="Acme", project=pid,
                            priority="medium", due=None, assign=None, label=None, details=None, todo=None))
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            kt.cmd_project(Args(ref="Rollout"))   # by name, not id
        text = out.getvalue()
        self.assertIn("north star: Go live in Q1", text)
        self.assertIn("open tasks:", text)
        self.assertIn("Wire stock feed", text)
        self.assertNotIn("Shipped invoice", text)

    def test_doctor_warns_board_member_without_person(self):
        data = read_json(self.file)
        data["people"] = [{"github": "ghostuser", "name": "Ghost"}]
        nums = [1, 2]
        for i, task in enumerate(data.get("tasks", [])):
            task["num"] = nums[i] if i < len(nums) else nums[-1] + i
        data["next_num"] = max(t["num"] for t in data["tasks"]) + 1
        write(self.file, data)
        issues, _, code = kt.doctor_board(False)
        self.assertEqual(0, code, "MEMBER_NO_PERSON is a warning only")
        self.assertIn("MEMBER_NO_PERSON", {x["code"] for x in issues})

    def test_project_remove_and_clear_task_reference(self):
        with contextlib.redirect_stdout(io.StringIO()):
            kt.cmd_project_add(Args(name="Rollout", client="Acme", north_star="", status="active"))
        pr = read_json(self.file)["projects"][0]
        with contextlib.redirect_stdout(io.StringIO()):
            kt.cmd_task_set(Args(id="t_live", client=None, project=pr["id"], contact=None))
        with self.assertRaises(SystemExit):
            with contextlib.redirect_stdout(io.StringIO()):
                kt.cmd_project_remove(Args(ref=pr["id"], clear_project=False))
        with contextlib.redirect_stdout(io.StringIO()):
            kt.cmd_project_remove(Args(ref=pr["id"], clear_project=True))
        data = read_json(self.file)
        self.assertEqual([], data["projects"])
        live = next(t for t in data["tasks"] if t["id"] == "t_live")
        self.assertEqual("", live.get("project"))

    def test_project_unlink_by_title_and_refuses_unknown_link(self):
        with contextlib.redirect_stdout(io.StringIO()):
            kt.cmd_project_add(Args(name="Rollout", client="Acme", north_star="", status="active"))
        pid = read_json(self.file)["projects"][0]["id"]
        with contextlib.redirect_stdout(io.StringIO()):
            kt.cmd_project_link(Args(ref=pid, url="https://drive.example/rollout", title="Plan"))
        with self.assertRaises(SystemExit):
            with contextlib.redirect_stdout(io.StringIO()):
                kt.cmd_project_unlink(Args(ref=pid, url="https://nope"))
        with contextlib.redirect_stdout(io.StringIO()):
            kt.cmd_project_unlink(Args(ref=pid, url="Plan"))
        self.assertEqual([], read_json(self.file)["projects"][0]["links"])

    def test_client_unlink_by_url_and_refuses_unknown_link(self):
        with contextlib.redirect_stdout(io.StringIO()):
            kt.cmd_client_link(Args(client="Acme", url="/srv/clients/acme", title="Local folder"))
        with self.assertRaises(SystemExit):
            with contextlib.redirect_stdout(io.StringIO()):
                kt.cmd_client_unlink(Args(client="Acme", url="/srv/nope"))
        with contextlib.redirect_stdout(io.StringIO()):
            kt.cmd_client_unlink(Args(client="Acme", url="/srv/clients/acme"))
        self.assertEqual([], read_json(self.file)["client_info"]["Acme"]["links"])

    def test_doctor_warns_orphan_project_reference(self):
        data = read_json(self.file)
        nums = [1, 2]
        for i, task in enumerate(data.get("tasks", [])):
            task["num"] = nums[i] if i < len(nums) else nums[-1] + i
        data["next_num"] = max(t["num"] for t in data["tasks"]) + 1
        data["tasks"][1]["project"] = "pr_missing99"
        data["people"] = [{"github": "osouthgate", "name": "O"}]
        data["contacts"][0]["github"] = "osouthgate"
        write(self.file, data)
        issues, _, code = kt.doctor_board(False)
        self.assertEqual(0, code, "PROJECT is a warning only")
        self.assertIn("PROJECT", {x["code"] for x in issues})


class SplitProjects(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.board_dir = os.path.join(self.temp.name, "board")
        copy_board_fixture("v4", self.board_dir)
        root = read_json(os.path.join(self.board_dir, "tasks.json"))
        root["clients"] = ["Acme"]
        root["client_info"] = {"Acme": {"links": []}}
        write(os.path.join(self.board_dir, "tasks.json"), root)
        self.old_file = kt.FILE
        kt.FILE = os.path.join(self.board_dir, "tasks.json")

    def tearDown(self):
        kt.FILE = self.old_file
        self.temp.cleanup()

    def test_split_v4_project_round_trip(self):
        before = tree_bytes(self.board_dir)
        with contextlib.redirect_stdout(io.StringIO()):
            kt.cmd_project_add(Args(name="Rollout", client="Acme", north_star="Go live", status="active"))
        changed = {p for p in set(before) | set(tree_bytes(self.board_dir)) if before.get(p) != tree_bytes(self.board_dir).get(p)}
        proj_files = [p for p in changed if p.startswith("projects/")]
        self.assertEqual(1, len(proj_files))
        pr_id = os.path.basename(proj_files[0]).replace(".json", "")
        on_disk = read_json(os.path.join(self.board_dir, proj_files[0]))
        self.assertEqual("Rollout", on_disk["name"])
        kt.FILE = os.path.join(self.board_dir, "tasks.json")
        loaded = kt.load_board()
        self.assertEqual(1, len(loaded["projects"]))
        self.assertEqual(pr_id, loaded["projects"][0]["id"])


def run_quiet(f, **kw):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        f(Args(**kw))
    return out.getvalue()


def refused(test, f, **kw):
    with test.assertRaises(SystemExit) as cm, contextlib.redirect_stdout(io.StringIO()):
        f(Args(**kw))
    return str(cm.exception.code)


class AdminRemoveAndAgents(unittest.TestCase):
    """task-rm, person-rm and the agents commands (issue #51), on a single-file and a split board."""
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old = kt.FILE
        # single-file board
        self.one = os.path.join(self.temp.name, "one", "board")
        os.makedirs(self.one)
        d = board()
        d["agents"] = ["claude", "codex"]
        d["contacts"] = [{"id": "p_1", "name": "Cat", "company": "", "stage": "New", "links": [], "comments": [], "history": []}]
        d["tasks"][1]["contact"] = "p_1"; d["tasks"][1]["assignees"] = ["codex"]
        write(os.path.join(self.one, "tasks.json"), d)
        # split board
        self.split = os.path.join(self.temp.name, "split", "board")
        copy_board_fixture("v4", self.split)
        card = os.path.join(self.split, "cards", "t_second.json")
        c = read_json(card); c["contact"] = "p_acme"; write(card, c)

    def tearDown(self):
        kt.FILE = self.old
        self.temp.cleanup()

    def use(self, d):
        kt.FILE = os.path.join(d, "tasks.json")

    def test_task_rm_single_file(self):
        self.use(self.one)
        before = read_json(kt.FILE)
        self.assertIn("--yes", refused(self, kt.cmd_task_rm, id="t_live", yes=False))
        self.assertEqual(before, read_json(kt.FILE))
        self.assertIn("deleted", run_quiet(kt.cmd_task_rm, id="t_live", yes=True))
        self.assertEqual(["t_old"], [t["id"] for t in read_json(kt.FILE)["tasks"]])

    def test_task_rm_refuses_an_active_claim(self):
        self.use(self.one)
        d = read_json(kt.FILE); d["tasks"][1]["claim"] = {"agent": "claude", "status": "running"}; write(kt.FILE, d)
        self.assertIn("active claim", refused(self, kt.cmd_task_rm, id="t_live", yes=True))
        self.assertEqual(2, len(read_json(kt.FILE)["tasks"]))

    def test_task_rm_split_deletes_the_card_file(self):
        self.use(self.split)
        before = tree_bytes(self.split)
        refused(self, kt.cmd_task_rm, id="t_first", yes=False)
        self.assertEqual(before, tree_bytes(self.split))
        run_quiet(kt.cmd_task_rm, id="#1", yes=True)
        after = tree_bytes(self.split)
        self.assertNotIn("cards/t_first.json", after)
        self.assertIn("cards/t_second.json", after)
        self.assertEqual({"cards/t_first.json"}, {p for p in set(before) | set(after) if before.get(p) != after.get(p)})
        issues, _, code = kt.doctor_board(False)
        self.assertEqual(0, code, issues)

    def test_person_rm_single_file_clears_task_contact(self):
        self.use(self.one)
        self.assertIn("--yes", refused(self, kt.cmd_person_rm, ref="Cat", yes=False))
        self.assertEqual(1, len(read_json(kt.FILE)["contacts"]))
        self.assertIn("cleared as contact on 1 tasks", run_quiet(kt.cmd_person_rm, ref="p_1", yes=True))
        d = read_json(kt.FILE)
        self.assertEqual([], d["contacts"])
        self.assertNotIn("contact", d["tasks"][1])
        self.assertIn("person deleted", d["tasks"][1]["history"][-1]["text"])

    def test_person_rm_split_deletes_the_person_file(self):
        self.use(self.split)
        refused(self, kt.cmd_person_rm, ref="p_acme", yes=False)
        self.assertTrue(os.path.exists(os.path.join(self.split, "people", "p_acme.json")))
        before = tree_bytes(self.split)
        run_quiet(kt.cmd_person_rm, ref="p_acme", yes=True)
        after = tree_bytes(self.split)
        self.assertNotIn("people/p_acme.json", after)
        self.assertEqual({"people/p_acme.json", "cards/t_second.json"}, {p for p in set(before) | set(after) if before.get(p) != after.get(p)})
        self.assertNotIn("contact", read_json(os.path.join(self.split, "cards", "t_second.json")))
        issues, _, code = kt.doctor_board(False)
        self.assertEqual(0, code, issues)

    def test_agents_add_list_remove(self):
        for d in (self.one, self.split):
            self.use(d)
            self.assertIn("added agent gemini", run_quiet(kt.cmd_agent_add, name="gemini"))
            self.assertIn("already an agent", refused(self, kt.cmd_agent_add, name="Gemini"))
            self.assertIn("not an agent name", refused(self, kt.cmd_agent_add, name="bad name"))
            self.assertIn("gemini", run_quiet(kt.cmd_agents))
            self.assertIn("is not an agent", refused(self, kt.cmd_agent_rm, name="nobody", unassign=False))
            run_quiet(kt.cmd_agent_rm, name="gemini", unassign=False)
            self.assertNotIn("gemini", read_json(kt.FILE)["agents"])

    def test_agent_rm_refuses_open_tasks_unless_unassign(self):
        self.use(self.one)
        self.assertIn("open task", refused(self, kt.cmd_agent_rm, name="codex", unassign=False))
        self.assertIn("codex", read_json(kt.FILE)["agents"])
        run_quiet(kt.cmd_agent_rm, name="codex", unassign=True)
        d = read_json(kt.FILE)
        self.assertEqual(["claude"], d["agents"])
        self.assertEqual([], d["tasks"][1]["assignees"])


class RenamesReachArchives(unittest.TestCase):
    """label-set --rename, client-rename and settings-set --rename-stage rewrite archive/<year>.json in the same save."""
    def archive(self):
        return {"version": 3, "archive": True, "year": "2025", "history": {}, "tasks": [
            {"id": "t_a", "num": 7, "title": "Old", "column": "done", "labels": ["call", "x"], "client": "Acme", "history": [], "updated": "2025-02-01T00:00:00Z"}],
            "contacts": [{"id": "p_a", "name": "Lo", "company": "Acme", "stage": "Contacted", "history": [], "updated": "2025-02-01T00:00:00Z"}]}

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old = kt.FILE
        index = {"files": {"2025": {"tasks": 1, "contacts": 1}}}
        self.one = os.path.join(self.temp.name, "one", "board")
        os.makedirs(os.path.join(self.one, "archive"))
        d = board()
        d.update(labels=[{"name": "call", "color": "#0c66e4"}], clients=["Acme"], client_info={},
                 settings={"stages": ["New", "Contacted", "Won", "Lost"]}, archive=index)
        write(os.path.join(self.one, "tasks.json"), d)
        write(os.path.join(self.one, "archive", "2025.json"), self.archive())
        self.split = os.path.join(self.temp.name, "split", "board")
        copy_board_fixture("v4", self.split)
        os.makedirs(os.path.join(self.split, "archive"))
        write(os.path.join(self.split, "archive", "2025.json"), self.archive())
        root = read_json(os.path.join(self.split, "tasks.json")); root["archive"] = index
        write(os.path.join(self.split, "tasks.json"), root)

    def tearDown(self):
        kt.FILE = self.old
        self.temp.cleanup()

    def check(self, d):
        kt.FILE = os.path.join(d, "tasks.json")
        arch = lambda: read_json(os.path.join(d, "archive", "2025.json"))
        out = run_quiet(kt.cmd_label_set, name="call", rename="phone", color=None)
        self.assertIn("and 1 archived", out); self.assertNotIn("note:", out)
        self.assertEqual(["phone", "x"], arch()["tasks"][0]["labels"])
        self.assertIn("label call renamed to phone", arch()["tasks"][0]["history"][-1]["text"])
        out = run_quiet(kt.cmd_client_rename, client="Acme", new="Acme Ltd")
        self.assertIn("2 archived items", out); self.assertNotIn("note:", out)
        self.assertEqual("Acme Ltd", arch()["tasks"][0]["client"])
        self.assertEqual("Acme Ltd", arch()["contacts"][0]["company"])
        out = run_quiet(kt.cmd_settings_set, title=None, stale_minutes=None, stages=None, rename_stage=["Contacted=Talking"])
        self.assertIn("and 1 archived", out); self.assertNotIn("note:", out)
        self.assertEqual("Talking", arch()["contacts"][0]["stage"])
        run_quiet(kt.cmd_unarchive, ref="p_a")
        back = next(c for c in kt.load_board()["contacts"] if c["id"] == "p_a")
        self.assertEqual(("Talking", "Acme Ltd"), (back["stage"], back["company"]))
        issues, _, code = kt.doctor_board(False)
        self.assertEqual(0, code, issues)

    def test_single_file_board(self):
        self.check(self.one)

    def test_rename_that_loses_a_save_race_still_rewrites_the_archive(self):
        # Another writer saves between our read and our write. A rename runs again on the latest board (it is not
        # merged), so the archive file is still rewritten and the other writer's change is kept.
        kt.FILE = os.path.join(self.one, "tasks.json")
        real, calls = kt.save_changes, []
        def racing(data, state=None, message="", extra=None):
            if not calls:
                calls.append(1); d = read_json(kt.FILE); d["settings"]["title"] = "Theirs"; write(kt.FILE, d)
                return False
            return real(data, state, message, extra=extra)
        kt.save_changes = racing
        try:
            out = run_quiet(kt.cmd_label_set, name="call", rename="phone", color=None)
        finally:
            kt.save_changes = real
        self.assertEqual(1, len(calls)); self.assertIn("and 1 archived", out)
        self.assertEqual(["phone", "x"], read_json(os.path.join(self.one, "archive", "2025.json"))["tasks"][0]["labels"])
        board = read_json(kt.FILE)
        self.assertEqual("Theirs", board["settings"]["title"])
        self.assertEqual(["phone"], [l["name"] for l in board["labels"]])

    def test_split_board(self):
        self.check(self.split)

    def test_an_archive_with_no_match_is_not_rewritten(self):
        kt.FILE = os.path.join(self.one, "tasks.json")
        path = os.path.join(self.one, "archive", "2025.json")
        os.utime(path, (1, 1))
        run_quiet(kt.cmd_label_add, name="other", color=None)
        run_quiet(kt.cmd_label_set, name="other", rename="other2", color=None)
        self.assertEqual(1, os.stat(path).st_mtime)


class VerifyLargeBackup(unittest.TestCase):
    """A tasks.json over 1 MB comes back from the contents API with no content; the raw re-read must use the backup ref."""
    NAMES = ("FILE", "WRITE", "gh", "http", "use_http", "REPO", "BRANCH", "PATH")

    def setUp(self):
        self.saved = {n: getattr(kt, n) for n in self.NAMES}
        self.urls = []
        kt.FILE, kt.WRITE, kt.REPO, kt.BRANCH, kt.PATH = None, "api", "o/r", "main", "board/tasks.json"
        kt.use_http = lambda: True
        backup = {"version": 3, "settings": {}, "tasks": [{"id": "t_backup"}], "contacts": []}
        live = {"version": 3, "settings": {}, "tasks": [{"id": "t_live"}], "contacts": []}

        def fake_http(method, path, body=None, accept=None):
            self.urls.append(path)
            return 0, json.dumps(backup if "ref=backup%2Fkit18" in path else live), ""

        kt.http = fake_http
        kt.gh = lambda *a, body=None: (0, json.dumps({"encoding": "none", "content": "", "sha": "s"}), "")

    def tearDown(self):
        for n, v in self.saved.items():
            setattr(kt, n, v)

    def test_raw_read_uses_the_backup_ref(self):
        data = kt._read_backup("backup/kit18")
        self.assertEqual("t_backup", data["tasks"][0]["id"])
        self.assertTrue(all("ref=backup%2Fkit18" in u for u in self.urls), self.urls)

    def test_without_a_ref_it_reads_the_board_branch(self):
        text = kt.content_text("board/tasks.json", {"encoding": "none", "content": ""})
        self.assertEqual("t_live", json.loads(text)["tasks"][0]["id"])
        self.assertIn("ref=main", self.urls[0])


class AttendedClaims(unittest.TestCase):
    """v26: a session a person drives sends no heartbeats and goes stale only after 12 hours."""

    def ago(self, minutes):
        import datetime as dt
        return (dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")

    def test_attended_claim_stays_running_far_longer(self):
        data = {"settings": {"stale_after_minutes": 30}}
        plain = {"status": "running", "claimed_at": self.ago(60), "heartbeat_at": self.ago(45)}
        self.assertEqual(kt.claim_state(data, plain), "stale")
        self.assertEqual(kt.claim_state(data, dict(plain, attended=True)), "running")
        self.assertEqual(kt.claim_state(data, dict(plain, attended=True, heartbeat_at=self.ago(13 * 60))), "stale")

    def test_attended_from_flag_or_environment(self):
        old = os.environ.pop("BOARD_ATTENDED", None)
        try:
            self.assertFalse(kt.attended(Args()))
            self.assertTrue(kt.attended(Args(attended=True)))
            os.environ["BOARD_ATTENDED"] = "1"
            self.assertTrue(kt.attended(Args()))
            os.environ["BOARD_ATTENDED"] = "0"
            self.assertFalse(kt.attended(Args()))
        finally:
            os.environ.pop("BOARD_ATTENDED", None)
            if old is not None:
                os.environ["BOARD_ATTENDED"] = old

    def test_auto_heartbeat_skips_attended_and_beats_otherwise(self):
        d = tempfile.TemporaryDirectory(); self.addCleanup(d.cleanup)
        claim_file = os.path.join(d.name, "claim.json")
        calls = []
        old = kt.CLAIM_FILE, kt.mutate
        kt.CLAIM_FILE, kt.mutate = claim_file, lambda fn, msg: calls.append(msg)
        try:
            for attended, expect in ((True, 0), (False, 1)):
                calls.clear()
                write(claim_file, {"id": "t_x", "session": "s", "attended": attended})
                os.utime(claim_file, (0, 0))   # long ago, so the throttle allows a beat
                kt.cmd_auto_heartbeat(Args())
                self.assertEqual(len(calls), expect, f"attended={attended}")
        finally:
            kt.CLAIM_FILE, kt.mutate = old

    def test_heartbeat_interval_is_15_minutes(self):
        self.assertEqual(kt.HEARTBEAT_EVERY, 900)


class ClaimLifecycle(unittest.TestCase):
    """v35: done, release and heartbeat belong to the claiming session; page placeholders are replaceable by the same
    agent and user; --force no longer bypasses the claim limit; done needs a result note and no open to-dos."""

    read = LocalBoard.read
    quiet = LocalBoard.quiet
    SESSION_ENV = ("BOARD_SESSION", "CLAUDE_SESSION_ID", "CODEX_SESSION_ID", "BOARD_ATTENDED")

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        os.makedirs(os.path.join(self.dir.name, "board"))
        self.file = os.path.join(self.dir.name, "board", "tasks.json")
        self.claim_file = os.path.join(self.dir.name, "claim.json")
        self.old = kt.FILE, kt.save, kt.CLAIM_FILE, kt.cloud_session_url
        kt.FILE, kt.CLAIM_FILE, kt.cloud_session_url = self.file, self.claim_file, lambda: ""   # not the real cloud session
        self.old_env = {k: os.environ.pop(k, None) for k in self.SESSION_ENV}
        self.old_user = os.environ.get("BOARD_USER")
        os.environ["BOARD_USER"] = "osouthgate"
        d = board()
        d["columns"] = [{"id": "todo", "name": "To do"}, {"id": "in-progress", "name": "In progress"},
                        {"id": "done", "name": "Done"}]
        card = lambda i, todos: {"id": f"t_c{i}", "num": i, "title": f"Card {i}", "column": "todo", "assignees": ["osouthgate"],
                                 "updated": "2026-10-01T00:00:00Z", "history": [], "todos": todos, "comments": []}
        d["tasks"] = [card(1, []), card(2, []),
                      card(3, [{"id": "d_1", "text": "Write", "done": False}, {"id": "d_2", "text": "Review", "done": False},
                               {"id": "d_3", "text": "Ship", "done": True}, {"id": "d_4", "text": "Tell Sam", "done": False},
                               {"id": "d_5", "text": "Archive", "done": False}]),
                      card(4, [{"id": "d_6", "text": "All ticked", "done": True}])]
        write(self.file, d)

    def tearDown(self):
        kt.FILE, kt.save, kt.CLAIM_FILE, kt.cloud_session_url = self.old
        for k, v in self.old_env.items():
            if v is not None:
                os.environ[k] = v
        if self.old_user is None:
            os.environ.pop("BOARD_USER", None)
        else:
            os.environ["BOARD_USER"] = self.old_user
        self.dir.cleanup()

    def card(self, n):
        return self.read()["tasks"][n - 1]

    def claim(self, n, session, **kw):
        args = Args(id=f"t_c{n}", for_user="osouthgate", agent="claude", session=session, force=False, note="x",
                    session_url=None, attended=False)
        args.__dict__.update(kw)
        self.quiet(kt.cmd_claim, args)

    def done(self, n, session=None, note="shipped it", **kw):
        args = Args(id=f"t_c{n}", note=note, session=session, force=False, cancel=False)
        args.__dict__.update(kw)
        return self.quiet(kt.cmd_done, args)

    def release(self, n, session=None, **kw):
        args = Args(id=f"t_c{n}", column=None, session=session, force=False)
        args.__dict__.update(kw)
        return self.quiet(kt.cmd_release, args)

    def beat(self, n, session=None, **kw):
        args = Args(id=f"t_c{n}", status=None, note=None, session=session, force=False)
        args.__dict__.update(kw)
        return self.quiet(kt.cmd_heartbeat, args)

    def set_claim(self, n, **changes):
        d = self.read(); d["tasks"][n - 1]["claim"].update(changes); write(self.file, d)

    def make_stale(self, n):
        self.set_claim(n, claimed_at="2026-01-01T00:00:00Z", heartbeat_at="2026-01-01T00:00:00Z")

    def placeholder(self, n, **kw):
        c = {"agent": "claude", "on_behalf_of": "osouthgate", "session_id": "pending-ab12", "session_url": "https://claude.ai/code/session_x",
             "status": "running", "claimed_at": kt.now(), "heartbeat_at": kt.now(), "note": "sent from the board"}
        c.update(kw)
        d = self.read(); d["tasks"][n - 1]["claim"] = c; d["tasks"][n - 1]["column"] = "in-progress"; write(self.file, d)

    def refusal(self, f, *a, **kw):
        with self.assertRaises(SystemExit) as e:
            f(*a, **kw)
        return str(e.exception)

    # --- ownership -------------------------------------------------------------------------------------------

    def test_another_session_cannot_finish_a_claimed_card(self):
        self.claim(1, "s1")
        msg = self.refusal(self.done, 1, session="s2")
        self.assertEqual(msg, "refused: t_c1 is claimed by claude, another session (running); it is not this session's "
                         "(use --force only if a person told you to; never pass --session with an id you did not generate)")
        self.assertEqual(self.card(1)["claim"]["session_id"], "s1")
        self.assertEqual(self.card(1)["column"], "in-progress")
        self.done(1, session="s2", force=True)
        self.assertEqual(self.card(1)["column"], "done")
        self.assertIsNone(self.card(1)["claim"])

    def test_the_claiming_session_can_finish_release_and_heartbeat(self):
        self.claim(1, "s1"); self.claim(2, "s2")
        self.beat(1, session="s1", note="going")
        self.release(2, session="s2")
        self.done(1, session="s1")
        self.assertEqual(self.card(1)["column"], "done")
        self.assertIsNone(self.card(2)["claim"])

    def test_session_from_the_environment_owns_its_claim(self):
        self.claim(1, "s1")
        os.environ["CLAUDE_SESSION_ID"] = "s1"
        try:
            self.beat(1)
            os.environ["CLAUDE_SESSION_ID"] = "s2"
            self.assertIn("refused", self.refusal(self.beat, 1))
            os.environ["BOARD_SESSION"] = "s1"               # BOARD_SESSION wins over CLAUDE_SESSION_ID
            self.beat(1)
        finally:
            os.environ.pop("CLAUDE_SESSION_ID", None); os.environ.pop("BOARD_SESSION", None)

    def test_another_session_cannot_heartbeat_but_force_works(self):
        self.claim(1, "s1")
        self.assertIn("not this session's", self.refusal(self.beat, 1, session="s2", note="hi"))
        self.assertNotEqual(self.card(1)["claim"].get("note"), "hi")
        self.beat(1, session="s2", note="hi", force=True)
        self.assertEqual(self.card(1)["claim"]["note"], "hi")

    def test_another_session_cannot_heartbeat_a_stale_claim_either(self):
        self.claim(1, "s1"); self.make_stale(1)
        self.assertIn("(stale)", self.refusal(self.beat, 1, session="s2"))

    def test_another_session_cannot_release_a_running_claim_but_force_works(self):
        self.claim(1, "s1")
        self.assertIn("(running)", self.refusal(self.release, 1, session="s2"))
        self.assertEqual(self.card(1)["claim"]["session_id"], "s1")
        self.release(1, session="s2", force=True)
        self.assertIsNone(self.card(1)["claim"])

    def test_any_session_can_release_a_stale_stuck_or_blocked_claim(self):
        self.claim(1, "s1"); self.make_stale(1)
        self.claim(2, "s2"); self.set_claim(2, status="stuck")
        self.claim(3, "s3"); self.set_claim(3, status="blocked")
        for n in (1, 2, 3):
            self.release(n, session="other")
            self.assertIsNone(self.card(n)["claim"], n)

    def test_done_on_another_sessions_stale_claim_still_needs_force(self):
        self.claim(1, "s1"); self.make_stale(1)
        self.claim(2, "s2"); self.set_claim(2, status="blocked")
        for n in (1, 2):
            self.assertIn("not this session's", self.refusal(self.done, n, session="other"))
            self.assertIsNotNone(self.card(n)["claim"])
            self.done(n, session="other", force=True)
            self.assertEqual(self.card(n)["column"], "done")

    def test_cancel_follows_the_same_ownership_rule(self):
        self.claim(1, "s1")
        self.assertIn("not this session's", self.refusal(self.done, 1, session="s2", cancel=True, note="dropped"))
        self.done(1, session="s2", cancel=True, note="dropped", force=True)
        self.assertEqual(self.card(1)["outcome"], "cancelled")

    def test_local_claim_record_makes_an_env_less_session_the_owner(self):
        self.claim(1, "attended-1"); self.claim(2, "s2")
        write(self.claim_file, {"id": "t_c1", "agent": "claude", "user": "osouthgate", "session": "attended-1", "attended": True})
        self.beat(1)                                          # no --session and no environment: the record says it is ours
        self.assertIn("not this session's", self.refusal(self.beat, 2))     # but the record is for card 1 only
        self.done(1)
        self.assertEqual(self.card(1)["column"], "done")
        self.assertFalse(os.path.exists(self.claim_file))     # done drops the record, so the next call owns nothing
        self.claim(3, "s3")
        self.assertIn("not this session's", self.refusal(self.release, 3))

    def test_the_local_record_for_another_card_grants_nothing(self):
        self.claim(1, "s1")
        write(self.claim_file, {"id": "t_c2", "session": "s1"})   # this clone's record is for a different card
        self.assertIn("not this session's", self.refusal(self.beat, 1, session="s2"))

    def test_outcome_never_disagrees_with_the_last_run_and_clears_on_reopen(self):
        self.claim(3, "s1"); self.done(3, session="s1", cancel=True, note="dropped")
        self.assertEqual((self.card(3)["outcome"], self.card(3)["last_run"]["outcome"]), ("cancelled", "cancelled"))
        self.quiet(kt.cmd_move, Args(id="t_c3", column="todo", note=None, priority=None, before=None, after=None, top=False))
        self.assertNotIn("outcome", self.card(3))
        d = self.read()
        for x in d["tasks"][2]["todos"]: x["done"] = True
        write(self.file, d)
        self.done(3, session="s1", note="finished after all")                # no claim this time
        self.assertEqual((self.card(3)["outcome"], self.card(3)["last_run"]["outcome"]), ("completed", "completed"))

    def test_session_for_order(self):
        os.environ["CODEX_SESSION_ID"] = "codex"
        try:
            self.assertEqual(kt.session_for(Args(session=None), "t_c1"), "codex")
            os.environ["CLAUDE_SESSION_ID"] = "claude"
            self.assertEqual(kt.session_for(Args(session=None), "t_c1"), "claude")
            os.environ["BOARD_SESSION"] = "board"
            self.assertEqual(kt.session_for(Args(session=None), "t_c1"), "board")
            self.assertEqual(kt.session_for(Args(session="flag"), "t_c1"), "flag")
        finally:
            for k in ("CODEX_SESSION_ID", "CLAUDE_SESSION_ID", "BOARD_SESSION"):
                os.environ.pop(k, None)
        write(self.claim_file, {"id": "t_c1", "session": "rec"})
        self.assertEqual(kt.session_for(Args(session=None), "t_c1"), "rec")
        self.assertNotEqual(kt.session_for(Args(session=None), "t_c2"), "rec")

    def test_a_page_placeholder_needs_force_for_done_release_and_heartbeat(self):
        self.placeholder(1)
        self.assertIn("not this session's", self.refusal(self.beat, 1, session="pending-ab12"))   # even by its own id
        self.assertIn("not this session's", self.refusal(self.release, 1, session="s1"))
        self.assertIn("not this session's", self.refusal(self.done, 1, session="s1"))
        self.beat(1, session="s1", force=True)
        self.release(1, session="s1", force=True)
        self.assertIsNone(self.card(1)["claim"])
        self.placeholder(2)
        self.done(2, session="s1", force=True)
        self.assertEqual(self.card(2)["column"], "done")

    def test_a_stale_placeholder_is_a_dead_run_any_session_can_release(self):
        self.placeholder(1); self.make_stale(1)                 # the routine never started
        self.release(1, session="s1")
        self.assertIsNone(self.card(1)["claim"])
        self.placeholder(2); self.make_stale(2)
        self.assertIn("not this session's", self.refusal(self.done, 2, session="s1"))   # done still asserts the work was finished

    def test_releasing_another_sessions_dead_run_keeps_this_clones_claim_record(self):
        self.placeholder(2, session_id="s2"); self.make_stale(2)   # another session's run died on card 2
        self.claim(1, "s1")                                        # this clone works on card 1
        write(self.claim_file, {"id": "t_c1", "agent": "claude", "user": "osouthgate", "session": "s1", "attended": False})   # (a --file board writes no record itself)
        self.release(2, session="s1")
        self.assertIsNone(self.card(2)["claim"])
        self.assertEqual(json.load(open(self.claim_file))["id"], "t_c1")   # still remembered
        self.done(1, session="s1")
        self.assertFalse(os.path.exists(self.claim_file))

    def test_a_refusal_never_prints_the_owning_session_id(self):
        self.claim(1, "secret-s1")
        msg = self.refusal(self.done, 1, session="s2")
        self.assertNotIn("secret-s1", msg); self.assertIn("another session", msg)

    def test_the_local_claim_record_owns_the_card_even_when_the_environment_names_another_session(self):
        self.claim(1, "abc")                                       # claim ID --session ABC, as the usage text shows
        write(self.claim_file, {"id": "t_c1", "agent": "claude", "user": "osouthgate", "session": "abc", "attended": True})
        os.environ["CLAUDE_SESSION_ID"] = "harness-id"             # later calls carry the harness's own id
        self.beat(1); self.done(1)
        self.assertEqual(self.card(1)["column"], "done")

    def test_an_old_finished_claim_blocks_nobody(self):
        self.placeholder(1, session_id="old-run", status="done")   # older cards kept a claim with status done
        self.release(1, session="s9"); self.assertIsNone(self.card(1)["claim"])

    def test_unclaimed_cards_need_no_ownership(self):
        self.release(1, session="s1")
        self.done(2, session="s1")
        self.assertEqual(self.card(2)["column"], "done")

    # --- placeholders and the claim limit --------------------------------------------------------------------

    def test_placeholder_of_the_same_agent_and_user_is_replaced_without_force(self):
        self.placeholder(1, on_behalf_of="OSouthgate")        # the page may not match the case of the login
        self.claim(1, "run-1")
        c = self.card(1)["claim"]
        self.assertEqual(c["session_id"], "run-1")
        self.assertEqual(c["session_url"], "https://claude.ai/code/session_x")   # the link the board found is kept
        self.assertEqual(self.card(1)["column"], "in-progress")

    def test_placeholder_of_another_user_or_agent_is_still_a_live_claim(self):
        self.placeholder(1, on_behalf_of="alice")
        self.assertIn("already claimed by claude session pending-ab12", self.refusal(self.claim, 1, "run-1"))
        self.placeholder(2)                                    # same user, but a different agent
        self.assertIn("already claimed by claude session pending-ab12", self.refusal(self.claim, 2, "run-2", agent="codex"))
        self.assertEqual(self.card(1)["claim"]["session_id"], "pending-ab12")
        self.claim(1, "run-1", force=True)                     # --force still takes a live claim over
        self.assertEqual(self.card(1)["claim"]["session_id"], "run-1")

    def test_a_users_own_run_replaces_their_placeholder_but_not_someone_elses(self):
        d = self.read(); d["tasks"][0]["assignees"].append("alice"); write(self.file, d)
        self.placeholder(1, on_behalf_of="alice")
        self.assertIn("already claimed", self.refusal(self.claim, 1, "run-1", for_user="osouthgate"))
        self.claim(1, "run-1", for_user="alice")               # alice's own run replaces her placeholder
        self.assertEqual(self.card(1)["claim"]["session_id"], "run-1")

    def test_a_running_claim_by_a_real_session_is_still_refused(self):
        self.claim(1, "s1")
        self.assertIn("already claimed by claude session s1", self.refusal(self.claim, 1, "s2"))

    def limited(self, n):
        d = self.read(); d["settings"] = {"max_agent_claims": n}; write(self.file, d)

    def test_force_no_longer_bypasses_the_agent_claim_limit(self):
        self.limited(2)
        self.claim(1, "s1"); self.claim(2, "s2")
        for force in (False, True):
            msg = self.refusal(self.claim, 3, "s3", force=force)
            self.assertIn("limit is 2", msg)
            self.assertTrue(msg.endswith("(raise settings.max_agent_claims, or use --attended for a session a person drives)"), msg)
            self.assertFalse(self.card(3).get("claim"))
        self.claim(3, "me", attended=True)                     # attended sessions and your own running card are exempt
        self.claim(2, "s2", force=True)

    def test_force_still_overrides_the_assignee_check_within_the_limit(self):
        self.limited(2)
        d = self.read(); d["tasks"][0]["assignees"] = ["someone"]; write(self.file, d)
        self.assertIn("is assigned to", self.refusal(self.claim, 1, "s1"))
        self.claim(1, "s1", force=True)
        self.assertEqual(self.card(1)["claim"]["session_id"], "s1")

    def test_placeholder_replacement_is_still_subject_to_the_limit(self):
        self.limited(1)
        self.claim(2, "s2")
        self.placeholder(1)
        self.assertIn("limit is 1", self.refusal(self.claim, 1, "run-1"))
        self.assertIn("limit is 1", self.refusal(self.claim, 1, "run-1", force=True))

    # --- done has rules --------------------------------------------------------------------------------------

    def test_done_needs_a_note(self):
        for note in (None, "", "   "):
            msg = self.refusal(self.done, 1, note=note)
            self.assertEqual(msg, "refused: done needs --note with the result (what was delivered, where it is)")
        self.assertEqual(self.card(1)["column"], "todo")

    def test_done_refuses_open_todos(self):
        msg = self.refusal(self.done, 3)
        self.assertEqual(msg, 'refused: t_c3 has 4 open to-dos (Write, Review, Tell Sam, ...); tick them with todo-done, remove them, '
                              'or close the card with --cancel --note "why"')
        self.assertEqual(self.card(3)["column"], "todo")
        self.assertNotIn("outcome", self.card(3))
        self.assertEqual(self.card(4)["todos"][0]["done"], True)
        self.done(4)                                           # every to-do ticked: fine
        self.assertEqual(self.card(4)["column"], "done")

    def test_done_records_a_completed_outcome(self):
        self.claim(1, "s1")
        self.done(1, session="s1", note="PR 12 merged")
        c = self.card(1)
        self.assertEqual(c["outcome"], "completed")
        self.assertEqual(c["last_run"]["outcome"], "completed")
        self.assertEqual(c["last_run"]["note"], "PR 12 merged")
        self.assertEqual(c["history"][-1]["text"], "done: PR 12 merged")
        self.done(2)                                           # no claim: the outcome is still on the card
        self.assertEqual(self.card(2)["outcome"], "completed")
        self.assertNotIn("last_run", self.card(2))

    def test_cancel_closes_the_card_with_open_todos_and_records_it(self):
        self.claim(3, "s1")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            kt.cmd_done(Args(id="t_c3", note="customer withdrew", session="s1", force=False, cancel=True))
        self.assertEqual(out.getvalue().strip(), "cancelled t_c3: Card 3")
        c = self.card(3)
        self.assertEqual(c["column"], "done")
        self.assertEqual(c["outcome"], "cancelled")
        self.assertEqual(c["last_run"]["outcome"], "cancelled")
        self.assertIsNone(c["claim"])
        self.assertEqual(c["history"][-1]["text"], "cancelled: customer withdrew")
        self.assertEqual(len(c["todos"]), 5)                   # the to-dos stay on the card as they were
        self.claim(1, "s1")
        self.done(1, session="s1", cancel=True, note="not needed")   # works without open to-dos too
        self.assertEqual(self.card(1)["outcome"], "cancelled")

    def test_cancel_needs_a_note(self):
        msg = self.refusal(self.done, 3, note=None, cancel=True)
        self.assertIn("refused", msg)
        self.assertIn("--note", msg)
        self.assertEqual(self.card(3)["column"], "todo")

    def test_show_prints_a_cancelled_outcome_only(self):
        self.done(3, cancel=True, note="customer withdrew")
        self.done(2)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            kt.cmd_show(Args(id="t_c3"))
        self.assertIn("outcome: cancelled (customer withdrew)", out.getvalue())
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            kt.cmd_show(Args(id="t_c2"))
        self.assertNotIn("outcome: ", out.getvalue().replace('"outcome": "completed"', ""))

    def test_move_to_done_is_allowed_but_warns_about_open_todos(self):
        def move(n):
            err = io.StringIO()
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
                kt.cmd_move(Args(id=f"t_c{n}", column="done", column_pos=None, before=None, after=None, top=False,
                                 priority=None, note=None))
            return err.getvalue()
        self.assertEqual(move(3), "note: t_c3 has 4 open to-dos; done --cancel records that they were dropped\n")
        self.assertEqual(self.card(3)["column"], "done")
        self.assertEqual(move(4), "")
        self.assertEqual(move(1), "")


class AgentClaimLimit(unittest.TestCase):
    """v27: a board setting max_agent_claims makes claim refuse past the limit, atomically with the claim."""

    read = LocalBoard.read
    quiet = LocalBoard.quiet

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        os.makedirs(os.path.join(self.dir.name, "board"))
        self.file = os.path.join(self.dir.name, "board", "tasks.json")
        write(self.file, board())
        self.old = kt.FILE, kt.save
        kt.FILE = self.file
        os.environ.setdefault("BOARD_USER", "osouthgate")
        d = self.read()
        d["columns"] = [{"id": "todo", "name": "To do"}, {"id": "in-progress", "name": "In progress"},
                        {"id": "done", "name": "Done"}]
        d["tasks"] = [{"id": f"t_c{i}", "num": i, "title": f"Card {i}", "column": "todo", "assignees": ["osouthgate"],
                       "updated": "2026-10-01T00:00:00Z", "history": [], "todos": [], "comments": []} for i in range(1, 6)]
        d["settings"] = {"max_agent_claims": 2}
        write(self.file, d)
        self.old_att = os.environ.pop("BOARD_ATTENDED", None)

    def tearDown(self):
        if self.old_att is not None:
            os.environ["BOARD_ATTENDED"] = self.old_att
        kt.FILE, kt.save = self.old
        self.dir.cleanup()

    def claim(self, tid, session, **kw):
        args = Args(id=tid, for_user="osouthgate", agent="claude", session=session, force=False, note="x",
                    session_url=None, attended=False)
        args.__dict__.update(kw)
        self.quiet(kt.cmd_claim, args)

    def test_third_agent_claim_is_refused(self):
        self.claim("t_c1", "s1"); self.claim("t_c2", "s2")
        with self.assertRaises(SystemExit) as e:
            self.claim("t_c3", "s3")
        self.assertIn("limit is 2", str(e.exception))
        self.assertFalse(self.read()["tasks"][2].get("claim"))

    def test_attended_stale_and_same_session_do_not_count_or_get_blocked(self):
        self.claim("t_c1", "s1"); self.claim("t_c2", "s2")
        self.claim("t_c3", "me", attended=True)                  # a person's session is not an agent slot
        d = self.read(); d["tasks"][0]["claim"]["heartbeat_at"] = d["tasks"][0]["claim"]["claimed_at"] = "2026-01-01T00:00:00Z"
        write(self.file, d)                                       # #1 is now a dead run: its slot is free
        self.claim("t_c4", "s4")
        with self.assertRaises(SystemExit):
            self.claim("t_c5", "s5")
        self.claim("t_c2", "s2")                                  # re-claiming your own card is never refused
        with self.assertRaises(SystemExit) as e:                  # --force overrides the assignee and live-claim checks only
            self.claim("t_c5", "s5", force=True)
        self.assertIn("raise settings.max_agent_claims", str(e.exception))

    def test_limit_is_rechecked_when_a_save_loses_a_race(self):
        # Two sessions read the board with one claim running and claim different cards. The second save loses the
        # race; a plain three-way merge would keep both claims (they touch different cards) and run 3 under a limit of 2.
        self.claim("t_c1", "s1")
        real, calls = kt.save, []
        def racing(data, sha, msg):
            if not calls:
                calls.append(1); d = self.read()
                d["tasks"][1]["claim"] = dict(d["tasks"][0]["claim"], session_id="s2"); write(self.file, d)
                return False
            return real(data, sha, msg)
        kt.save = racing
        with self.assertRaises(SystemExit) as e:
            self.claim("t_c3", "s3")
        self.assertIn("limit is 2", str(e.exception))
        self.assertFalse(self.read()["tasks"][2].get("claim"))

    def test_local_claim_record_is_written_only_after_the_save(self):
        """v32: a claim refused after a lost race leaves no local record behind."""
        written, old = [], kt.write_claim_record
        kt.write_claim_record = lambda: written.append(kt._PENDING_CLAIM.get("rec"))
        try:
            self.claim("t_c1", "s1")
            self.assertEqual("t_c1", written[0]["id"])
            real, calls = kt.save, []
            def racing(data, sha, msg):
                if not calls:
                    calls.append(1); d = self.read()
                    d["tasks"][1]["claim"] = dict(d["tasks"][0]["claim"], session_id="s2"); write(self.file, d)
                    return False
                return real(data, sha, msg)
            kt.save = racing
            with self.assertRaises(SystemExit):
                self.claim("t_c3", "s3")
            self.assertEqual(1, len(written))
        finally:
            kt.write_claim_record = old

    def test_heartbeat_reviving_a_stale_claim_respects_the_limit(self):
        """v32: a heartbeat that brings a stale claim back to running counts like a new claim."""
        self.claim("t_c1", "s1"); self.claim("t_c2", "s2")
        d = self.read(); d["tasks"][0]["claim"]["heartbeat_at"] = d["tasks"][0]["claim"]["claimed_at"] = "2026-01-01T00:00:00Z"
        write(self.file, d)
        self.claim("t_c3", "s3")                                  # #1 is stale, so its slot was free
        with self.assertRaises(SystemExit) as e:
            self.quiet(kt.cmd_heartbeat, Args(id="t_c1", status=None, note=None, session="s1"))
        self.assertIn("limit is 2", str(e.exception))
        self.assertEqual("2026-01-01T00:00:00Z", self.read()["tasks"][0]["claim"]["heartbeat_at"])
        with self.assertRaises(SystemExit):                       # nor can the same session re-claim it past the limit
            self.claim("t_c1", "s1")
        self.assertEqual("2026-01-01T00:00:00Z", self.read()["tasks"][0]["claim"]["heartbeat_at"])
        self.quiet(kt.cmd_heartbeat, Args(id="t_c2", status=None, note="still going", session="s2"))   # a running claim is never refused

    def test_api_claim_under_a_limit_saves_through_a_commit(self):
        # A one-file contents PUT only notices a change to that file; the claim limit reads every card, so its save
        # must go through the commit path, whose ref update fails if anyone else saved meanwhile.
        calls = []
        def gh(*args, body=None):
            calls.append(args[1:3])
            return 0, json.dumps({"sha": "abc"}), ""
        old_gh, old_rec = kt.gh, kt._MUT["recheck"]
        kt.gh = gh
        try:
            state = {"files": {"cards/t.json": {"sha": "s"}}, "head": "h", "base_tree": "bt"}
            kt._MUT["recheck"] = False
            kt._api_save_changes({"cards/t.json": "{}"}, set(), state, "m")
            self.assertIn("PUT", calls[0][0])
            calls.clear(); kt._MUT["recheck"] = True
            kt._api_save_changes({"cards/t.json": "{}"}, set(), state, "m")
            self.assertTrue(any("git/blobs" in str(c) for c in calls) and any("git/refs" in str(c) for c in calls))
        finally:
            kt.gh, kt._MUT["recheck"] = old_gh, old_rec

    def test_bad_limit_value_is_ignored_and_reported(self):
        d = self.read(); d["settings"]["max_agent_claims"] = "two"; write(self.file, d)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            kt.cmd_settings(Args())
        self.assertIn("max_agent_claims: no limit (ignored: 'two'", out.getvalue())
        for i in range(1, 4):
            self.claim(f"t_c{i}", f"s{i}")                        # not a crash, and no limit
        self.assertEqual(kt.claim_limit({"settings": {"max_agent_claims": -1}}), 0)
        self.assertEqual(kt.claim_limit({"settings": {"max_agent_claims": True}}), 0)
        self.assertEqual(kt.claim_limit({"settings": {"max_agent_claims": 2}}), 2)
        self.assertIn("SETTINGS", kt.DOCTOR_WARNINGS)

    def test_settings_set_max_agent_claims(self):
        self.quiet(kt.cmd_settings_set, Args(title=None, stale_minutes=None, stages=None, rename_stage=None,
                                             max_agent_claims=0))
        self.assertNotIn("max_agent_claims", self.read()["settings"])
        for i in range(1, 6):
            self.claim(f"t_c{i}", f"s{i}")                        # no limit


class TimeZoneDates(LocalBoard):
    """Date shortcuts (today, +N, OVERDUE/TODAY flags, the today view) run on the member's own clock, not the host's."""

    def set_tz(self, tz, owner_tz=None, owner=False):
        d = read_json(self.file)
        d["people"] = [{"github": "osouthgate", "name": "O"}]
        if tz:
            d["people"][0]["timezone"] = tz
        if owner:   # a second member is the kit owner; the acting user is osouthgate
            d["people"].append({"github": "bea", "name": "Bea", "timezone": owner_tz})
            d["settings"]["kit_owner"] = "bea"
        write(self.file, d)

    def zone_today(self, tz):
        import datetime as dt, zoneinfo
        return dt.datetime.now(zoneinfo.ZoneInfo(tz)).date()

    def add(self, due):
        with contextlib.redirect_stdout(io.StringIO()):
            kt.cmd_add(Args(title="Dated", column="todo", client="Acme", project=None, priority="medium",
                            due=due, assign=None, label=None, details=None, todo=None, all=True))
        return next(t for t in read_json(self.file)["tasks"] if t["title"] == "Dated")["due"]

    def test_board_today_uses_the_members_zone(self):
        for tz in ("Pacific/Kiritimati", "Pacific/Pago_Pago"):
            self.set_tz(tz)
            self.assertEqual(kt.board_today(read_json(self.file)), self.zone_today(tz))

    def test_add_due_today_and_plus_n_use_the_member_zone(self):
        import datetime as dt
        self.set_tz("Pacific/Kiritimati")
        today = self.zone_today("Pacific/Kiritimati")
        self.assertEqual(self.add("today"), today.isoformat())
        write(self.file, board()); self.set_tz("Pacific/Kiritimati")
        self.assertEqual(self.add("+1"), (today + dt.timedelta(days=1)).isoformat())

    def test_invalid_zone_falls_back_to_the_host_date(self):
        import datetime as dt
        self.set_tz("Not/AZone")
        data = read_json(self.file)
        self.assertIsNone(kt.board_timezone(data))
        self.assertEqual(kt.board_today(data), dt.date.today())

    def test_no_zone_on_record_uses_the_host_clock(self):
        import datetime as dt
        self.assertIsNone(kt.board_timezone(read_json(self.file)))
        self.assertEqual(kt.board_today(read_json(self.file)), dt.date.today())
        self.assertEqual(kt.board_today({}), dt.date.today())

    def test_kit_owners_zone_is_used_when_the_acting_user_has_none(self):
        self.set_tz(None, owner_tz="Pacific/Kiritimati", owner=True)
        data = read_json(self.file)
        self.assertEqual(str(kt.board_timezone(data)), "Pacific/Kiritimati")
        self.assertEqual(kt.board_today(data), self.zone_today("Pacific/Kiritimati"))

    def test_acting_users_zone_wins_over_the_owners(self):
        self.set_tz("Pacific/Pago_Pago", owner_tz="Pacific/Kiritimati", owner=True)
        self.assertEqual(str(kt.board_timezone(read_json(self.file))), "Pacific/Pago_Pago")

    def test_first_member_is_the_last_resort(self):
        d = read_json(self.file)
        d["people"] = [{"github": "zed", "name": "Z", "timezone": "Pacific/Pago_Pago"}, {"github": "amy", "name": "A"}]
        self.assertEqual(str(kt.board_timezone(d)), "Pacific/Pago_Pago")

    def test_overdue_and_today_flags_follow_the_board_clock(self):
        import datetime as dt
        self.set_tz("Pacific/Kiritimati")
        today = self.zone_today("Pacific/Kiritimati")
        d = read_json(self.file)
        p = {"id": "p_x", "name": "Pat", "stage": "New", "next": "Call", "next_due": today.isoformat()}
        self.assertTrue(kt.person_line(p, d).endswith(" TODAY"))
        p["next_due"] = (today - dt.timedelta(days=1)).isoformat()
        self.assertTrue(kt.person_line(p, d).endswith(" OVERDUE"))

    def test_today_prints_the_date_and_zone_first(self):
        self.set_tz("Pacific/Kiritimati")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            kt.cmd_today(Args())
        self.assertEqual(out.getvalue().splitlines()[0],
                         f"Today is {self.zone_today('Pacific/Kiritimati').isoformat()} (Pacific/Kiritimati)")
        self.set_tz(None)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            kt.cmd_today(Args())
        self.assertEqual(out.getvalue().splitlines()[0],
                         f"Today is {kt.board_today({}).isoformat()} (host clock; set a time zone with member-set --timezone Area/City)")

    def test_archive_plan_defaults_to_the_board_clock(self):
        import datetime as dt
        self.set_tz("Pacific/Kiritimati")
        d = read_json(self.file)
        rules = {"done_days": 0, "lost_days": 0, "keep_history": 0}
        today = self.zone_today("Pacific/Kiritimati")
        d["tasks"] = [{"id": "t_k", "title": "K", "column": "done", "history": [], "todos": [],
                       "updated": (today - dt.timedelta(days=1)).isoformat() + "T12:00:00Z"}]
        self.assertEqual(kt.archive_plan(copy.deepcopy(d), rules).keys(), kt.archive_plan(copy.deepcopy(d), rules, today).keys())

    def test_board_timezone_never_asks_gh_for_the_user(self):
        d = self.read(); d["people"] = [{"github": "osouthgate", "name": "O", "timezone": "Europe/London"}]; write(self.file, d)
        old = os.environ.pop("BOARD_USER", None); saved = kt.default_user
        kt.default_user = lambda: (_ for _ in ()).throw(AssertionError("gh was asked"))
        try:
            self.assertEqual(kt.board_timezone(d).key, "Europe/London")   # falls through to the first member
            self.assertIsNone(kt.board_timezone({"people": [{"github": "x"}]}))
        finally:
            kt.default_user = saved
            if old is not None: os.environ["BOARD_USER"] = old

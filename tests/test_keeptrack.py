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

    def test_done_gives_a_card_a_unique_rank_in_its_new_column(self):
        second_path = os.path.join(self.board_dir, "cards", "t_second.json")
        second = read_json(second_path); second["column"] = "done"; second["rank"] = "a0"; write(second_path, second)
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
        shutil.copytree(os.path.join(FIXTURES, "v3"), self.board_dir)
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
        shutil.copytree(os.path.join(FIXTURES, "v3"), board_dir)
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
        shutil.copytree(os.path.join(FIXTURES, "v4"), os.path.join(work, "board"))
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
        shutil.copytree(os.path.join(FIXTURES, "v4"), os.path.join(work, "board"))
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


class MoveInPlace(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.board_dir = os.path.join(self.temp.name, "board")
        shutil.copytree(os.path.join(FIXTURES, "v4"), self.board_dir)
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
        shutil.copytree(os.path.join(FIXTURES, "v3"), self.board_dir)
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
        shutil.copytree(os.path.join(FIXTURES, "v4"), self.board_dir)
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
        shutil.copytree(os.path.join(FIXTURES, "v3"), self.board_dir)
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
        shutil.copytree(os.path.join(FIXTURES, "v4"), board_dir)
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

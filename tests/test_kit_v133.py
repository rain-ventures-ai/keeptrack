"""Kit v133: `watch-poll --history` replays the board branch's commits, so a watcher never misses a change between polls.

The cursor is one commit. Each poll diffs the same watch projection at each consecutive board commit after it (at most 20 per
call), so a change made and undone between two polls gives two events. A cursor commit that is not an ancestor of the
branch head, or that is unknown, is refused loudly; a --file board has no history and is refused. Snapshot mode (no
--history) is unchanged. Both the git transport (a real clone) and the API transport (a fake GitHub API answered from the
same real repository) are covered."""
import base64
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock
import urllib.parse

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "board" / "kit" / "keeptrack.py"
spec = importlib.util.spec_from_file_location("kit133_keeptrack", SOURCE)
kt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(kt)

COLUMNS = [{"id": x, "name": x} for x in ("backlog", "todo", "in-progress", "pending-review", "done")]


def card(tid, num, title, project="pr_one", column="backlog"):
    return {"id": tid, "num": num, "title": title, "project": project, "column": column, "todos": [], "comments": [],
            "history": [], "labels": [], "assignees": []}


def board():
    return {"version": 3, "settings": {}, "people": [{"github": "owner"}], "agents": ["codex"],
            "projects": [{"id": "pr_one", "name": "One", "client": "Example"}, {"id": "pr_two", "name": "Two", "client": "Example"}],
            "clients": ["Example"], "columns": COLUMNS, "next_num": 3,
            "tasks": [card("t_alpha", 1, "Alpha"), card("t_beta", 2, "Beta", project="pr_two")]}


def decode(cursor):
    return json.loads(base64.urlsafe_b64decode(cursor))


class Release(unittest.TestCase):
    def test_release_133_is_consistent(self):
        read = lambda rel: (ROOT / rel).read_text(encoding="utf-8")
        version = json.loads(read("board/kit/manifest.json"))["version"]
        self.assertGreaterEqual(version, 133)
        self.assertEqual(str(version), re.search(r"^KIT_VERSION = (\d+)", read("board/kit/keeptrack.py"), re.M)[1])
        self.assertIn(f"const PAGE_KIT = {version};", read("board/board.js"))
        for plugin in (".claude-plugin", ".codex-plugin", ".cursor-plugin"):
            self.assertEqual(f"0.{version}.0", json.loads(read(f"board/kit/{plugin}/plugin.json"))["version"])
        self.assertIn("### v133 (schema 4)", read("board/kit/UPGRADING.md"))
        self.assertIn("Kit v133:", read("CHANGELOG.md"))
        self.assertIn("--history", read("board/kit/README.md"))
        self.assertIn("--history", read("board/kit/WORK.md"))


class GitBoard(unittest.TestCase):
    """A real bare remote, a writer clone that commits board changes, and the reader clone keeptrack.py runs in."""
    WRITE = "git"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.remote, self.writer, self.reader = str(base / "remote.git"), str(base / "writer"), str(base / "reader")
        self.run_git(None, "init", "-q", "--bare", "-b", "main", self.remote)
        self.run_git(None, "clone", "-q", self.remote, self.writer)
        (Path(self.writer) / "board").mkdir()
        (Path(self.writer) / "README.md").write_text("not a board file\n")
        self.save(board(), "board")
        self.push()
        self.run_git(None, "clone", "-q", self.remote, self.reader)
        env = mock.patch.dict(os.environ, {"BOARD_USER": "owner"}); env.start(); self.addCleanup(env.stop)
        patches = dict(FILE=None, ROOT=self.reader, REPO="acme/board", BRANCH="main", PATH="board/tasks.json",
                       WRITE=self.WRITE, BACKEND="github", CACHE_DIR=str(base / "cache"), remote_repo=lambda url: "acme/board")
        if self.WRITE != "git":
            patches["gh"] = self.fake_gh
        for name, value in patches.items():
            p = mock.patch.object(kt, name, value); p.start(); self.addCleanup(p.stop)

    def run_git(self, cwd, *args):
        where = ["-C", cwd] if cwd else []
        return subprocess.run(["git", *where, "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
                              check=True, capture_output=True, text=True).stdout.strip()

    def load_writer(self):
        return json.loads((Path(self.writer) / "board" / "tasks.json").read_text())

    def save(self, data, message):
        (Path(self.writer) / "board" / "tasks.json").write_text(json.dumps(data, indent=1))
        self.run_git(self.writer, "add", "-A")
        self.run_git(self.writer, "commit", "-qm", message)
        return self.run_git(self.writer, "rev-parse", "HEAD")

    def change(self, fn, message="change", push=True):
        data = self.load_writer(); fn(data)
        sha = self.save(data, message)
        if push:
            self.push()
        return sha

    def push(self):
        self.run_git(self.writer, "push", "-q", "origin", "main")

    def alpha(self, data):
        return next(t for t in data["tasks"] if t["id"] == "t_alpha")

    def poll(self, cursor=None, project="pr_one", history=True):
        out = io.StringIO()
        with mock.patch("sys.stdin", io.StringIO(json.dumps(cursor))), contextlib.redirect_stdout(out):
            kt.cmd_work(SimpleNamespace(work_action="watch-poll", project=project, history=history))
        return json.loads(out.getvalue())

    def head(self):
        return self.run_git(self.remote, "rev-parse", "main")

    # A git object store answering the few GitHub API calls the API transport makes.
    def fake_gh(self, *args, body=None):
        path = args[0][len("repos/acme/board/"):]
        g = lambda *a: subprocess.run(["git", "-C", self.remote, *a], capture_output=True, text=True)
        if path.startswith("git/ref/heads/"):
            return 0, json.dumps({"object": {"sha": g("rev-parse", "main").stdout.strip()}}), ""
        if path.startswith("git/commits/"):
            r = g("rev-parse", "--verify", "-q", path.rsplit("/", 1)[1] + "^{tree}")
            return (1, '{"message":"Not Found"}', "HTTP 404") if r.returncode else (0, json.dumps({"tree": {"sha": r.stdout.strip()}}), "")
        if path.startswith("git/trees/"):
            sha, _, query = path[len("git/trees/"):].partition("?")
            rows = []
            for line in g("ls-tree", "-l", *(["-r", "-t"] if query == "recursive=1" else []), sha).stdout.splitlines():
                meta, name = line.split("\t", 1); _mode, kind, oid, size = meta.split()
                rows.append({"path": name, "type": kind, "sha": oid, **({"size": int(size)} if size != "-" else {})})
            return 0, json.dumps({"sha": sha, "tree": rows, "truncated": False}), ""
        if path.startswith("git/blobs/"):
            raw = subprocess.run(["git", "-C", self.remote, "cat-file", "blob", path.rsplit("/", 1)[1]], capture_output=True).stdout
            return 0, json.dumps({"encoding": "base64", "content": base64.b64encode(raw).decode()}), ""
        if path.startswith("compare/"):
            spec, _, query = path[len("compare/"):].partition("?")
            base, head = spec.split("...")
            if g("cat-file", "-e", base + "^{commit}").returncode:
                return 1, '{"message":"No commit found for SHA"}', "gh: No commit found for SHA (HTTP 404)"
            q = urllib.parse.parse_qs(query); page, per = int(q["page"][0]), int(q["per_page"][0])
            if base == head:
                status = "identical"
            elif g("merge-base", "--is-ancestor", base, head).returncode == 0:
                status = "ahead"
            elif g("merge-base", "--is-ancestor", head, base).returncode == 0:
                status = "behind"
            else:
                status = "diverged"
            lines = g("rev-list", "--reverse", "--parents", f"{base}..{head}").stdout.splitlines()
            rows = [{"sha": x.split()[0], "parents": [{"sha": p} for p in x.split()[1:]]} for x in lines]
            return 0, json.dumps({"status": status, "total_commits": len(rows), "commits": rows[(page - 1) * per:page * per]}), ""
        return 1, "", f"unexpected call {args[0]}"


class HistoryGit(GitBoard):
    def test_baseline_is_quiet_and_the_cursor_is_one_commit(self):
        first = self.poll()
        self.assertEqual(([], True, False, "commit-replay"), (first["events"], first["baseline"], first["more"], first["semantics"]))
        self.assertEqual({"v": 2, "board": "acme/board", "project": "pr_one", "commit": self.head()}, decode(first["cursor"]))
        again = self.poll(first["cursor"])
        self.assertEqual(([], False, False), (again["events"], again["baseline"], again["more"]))
        self.assertEqual(first["cursor"], again["cursor"])

    def test_one_change_is_one_event_tagged_with_its_commit(self):
        cursor = self.poll()["cursor"]
        sha = self.change(lambda d: self.alpha(d).update(column="todo"))
        result = self.poll(cursor)
        self.assertEqual([("column", "t_alpha", sha)], [(e["kind"], e["card"]["id"], e["commit"]) for e in result["events"]])
        self.assertEqual("backlog -> todo", result["events"][0]["text"])
        self.assertRegex(result["events"][0]["id"], r"^[0-9a-f]{32}$")
        self.assertEqual(sha, decode(result["cursor"])["commit"]); self.assertFalse(result["more"])
        self.assertEqual([], self.poll(result["cursor"])["events"])
        # The same cursor replays the same events with the same ids: a consumer can de-duplicate a repeat.
        self.assertEqual([e["id"] for e in result["events"]], [e["id"] for e in self.poll(cursor)["events"]])

    def test_a_change_and_its_revert_between_polls_give_two_events(self):
        cursor = self.poll()["cursor"]
        snapshot = self.poll(history=False)["cursor"]
        there = self.change(lambda d: self.alpha(d).update(column="todo"), push=False)
        back = self.change(lambda d: self.alpha(d).update(column="backlog"))
        events = self.poll(cursor)["events"]
        self.assertEqual([("column", "backlog -> todo", there), ("column", "todo -> backlog", back)],
                         [(e["kind"], e["text"], e["commit"]) for e in events])
        self.assertEqual([], self.poll(snapshot, history=False)["events"])   # what snapshot mode misses

    def test_paging_over_more_than_twenty_commits_misses_none(self):
        cursor = self.poll()["cursor"]
        made = []
        for n in range(25):
            made.append(self.change(lambda d, n=n: self.alpha(d).update(title=f"Alpha {n}"), push=False))
            if n == 9:   # a commit outside the board folder is passed over, not replayed
                (Path(self.writer) / "README.md").write_text("changed\n")
                self.run_git(self.writer, "commit", "-qam", "readme")
        self.push()
        first = self.poll(cursor)
        self.assertTrue(first["more"]); self.assertEqual(made[:20], [e["commit"] for e in first["events"]])
        self.assertEqual(made[19], decode(first["cursor"])["commit"])
        second = self.poll(first["cursor"])
        self.assertFalse(second["more"]); self.assertEqual(made[20:], [e["commit"] for e in second["events"]])
        self.assertEqual({"fields"}, {e["kind"] for e in first["events"] + second["events"]})

    def test_other_projects_changes_are_not_events_but_the_cursor_moves(self):
        cursor = self.poll()["cursor"]
        self.change(lambda d: next(t for t in d["tasks"] if t["id"] == "t_beta").update(column="todo"))
        result = self.poll(cursor)
        self.assertEqual([], result["events"]); self.assertEqual(self.head(), decode(result["cursor"])["commit"])

    def test_a_rewritten_branch_is_refused_not_rebaselined(self):
        self.change(lambda d: self.alpha(d).update(title="kept"))
        cursor = self.poll()["cursor"]
        self.run_git(self.writer, "reset", "-q", "--hard", "HEAD~1")
        self.change(lambda d: self.alpha(d).update(title="rewritten"), push=False)
        self.run_git(self.writer, "push", "-q", "--force", "origin", "main")   # the test's own throwaway bare remote
        with self.assertRaisesRegex(SystemExit, "not an ancestor.*fresh baseline"):
            self.poll(cursor)

    def test_an_unknown_commit_is_refused(self):
        token = {"v": 2, "board": "acme/board", "project": "pr_one", "commit": "1" * 40}
        with self.assertRaisesRegex(SystemExit, "not a commit.*fresh baseline"):
            self.poll(base64.urlsafe_b64encode(json.dumps(token).encode()).decode())

    def test_wrong_scope_or_shape_cursors_are_refused(self):
        cursor = self.poll()["cursor"]; good = decode(cursor)
        enc = lambda v: base64.urlsafe_b64encode(json.dumps(v).encode()).decode()
        with self.assertRaisesRegex(SystemExit, "another board, project or version"):
            self.poll(cursor, project="pr_two")
        with mock.patch.object(kt, "_current_board", return_value="other/board"):
            with self.assertRaisesRegex(SystemExit, "another board"):
                self.poll(cursor)
        for bad in ({**good, "extra": 1}, {**good, "v": 1}, {**good, "v": True}, {**good, "v": 2.0},
                    {k: v for k, v in good.items() if k != "commit"}, {**good, "project": 7}):
            with self.assertRaisesRegex(SystemExit, "another board, project or version"):
                self.poll(enc(bad))
        for commit in ("A" * 40, "1" * 39, 7, None):
            with self.assertRaisesRegex(SystemExit, "invalid watch cursor commit"):
                self.poll(enc({**good, "commit": commit}))
        with self.assertRaisesRegex(SystemExit, "invalid watch cursor encoding"):
            self.poll("not base64!")
        with self.assertRaisesRegex(SystemExit, "oversized"):
            self.poll("a" * 200000)
        # A snapshot cursor is not a history cursor, and the other way round.
        with self.assertRaisesRegex(SystemExit, "another board, project or version"):
            self.poll(self.poll(history=False)["cursor"])
        with self.assertRaisesRegex(SystemExit, "another board, project or version"):
            self.poll(cursor, history=False)

    def test_a_commit_over_the_bounds_is_one_loud_event_and_the_replay_moves_on(self):
        cursor = self.poll()["cursor"]
        poison = self.change(lambda d: d["tasks"].extend(card(f"t_card{n:04d}", 10 + n, "Card") for n in range(257)), push=False)
        fixed = self.change(lambda d: d.update(tasks=d["tasks"][:2]), push=False)
        moved = self.change(lambda d: self.alpha(d).update(column="todo"))
        result = self.poll(cursor)
        self.assertEqual([("unreplayable", poison), ("unreplayable", fixed), ("column", moved)],
                         [(e["kind"], e["commit"]) for e in result["events"]])
        self.assertIn("bound", result["events"][0]["text"]); self.assertIsNone(result["events"][0]["card"])
        self.assertEqual((moved, False), (decode(result["cursor"])["commit"], result["more"]))

    def test_a_merge_never_invents_a_reverse_event(self):
        base = self.head()
        there = self.change(lambda d: self.alpha(d).update(column="todo"))   # H1: the card is in todo
        cursor = self.poll()["cursor"]
        self.run_git(self.writer, "checkout", "-q", "-b", "side", base)       # L: an older base, outside the board
        (Path(self.writer) / "README.md").write_text("side\n")
        self.run_git(self.writer, "commit", "-qam", "L")
        self.run_git(self.writer, "merge", "-q", "--no-ff", "-m", "M", "main")  # M = merge(L, H1), H1 the second parent
        merge = self.run_git(self.writer, "rev-parse", "HEAD")
        self.run_git(self.writer, "push", "-q", "origin", "side:main")
        events = self.poll(cursor)["events"]
        # M differs from its first parent L (backlog there): one real change on M, never "todo -> backlog".
        self.assertEqual([("backlog -> todo", merge)], [(e["text"], e["commit"]) for e in events])
        self.assertNotEqual(there, merge)

    def test_side_branch_changes_are_replayed_not_lost_in_a_merge(self):
        cursor = self.poll()["cursor"]
        self.run_git(self.writer, "checkout", "-q", "-b", "side")
        there = self.change(lambda d: self.alpha(d).update(column="todo"), push=False)
        back = self.change(lambda d: self.alpha(d).update(column="backlog"), push=False)
        self.run_git(self.writer, "checkout", "-q", "main")
        self.run_git(self.writer, "merge", "-q", "--no-ff", "-m", "merge side", "side")
        self.push()
        events = self.poll(cursor)["events"]
        self.assertEqual([("backlog -> todo", there), ("todo -> backlog", back)], [(e["text"], e["commit"]) for e in events])

    def test_two_comments_with_one_long_prefix_get_different_ids(self):
        cursor = self.poll()["cursor"]
        prefix = "x" * 130
        self.change(lambda d: self.alpha(d)["comments"].extend([{"id": "c_one", "by": "owner", "text": prefix + " one"},
                                                                {"id": "c_two", "by": "owner", "text": prefix + " two"}]))
        events = self.poll(cursor)["events"]
        self.assertEqual(["comment", "comment"], [e["kind"] for e in events])
        self.assertEqual(events[0]["text"], events[1]["text"])   # the shown text is cut to 120 characters
        self.assertNotEqual(events[0]["id"], events[1]["id"])

    def test_the_scan_limit_pages_without_skipping(self):
        cursor = self.poll()["cursor"]
        for _ in range(kt.WATCH_HISTORY_SCAN + 1):
            self.run_git(self.writer, "commit", "-q", "--allow-empty", "-m", "empty")
        moved = self.change(lambda d: self.alpha(d).update(column="todo"))
        first = self.poll(cursor)
        self.assertEqual(([], True), (first["events"], first["more"]))
        second = self.poll(first["cursor"])
        self.assertEqual([("column", moved)], [(e["kind"], e["commit"]) for e in second["events"]])
        self.assertFalse(second["more"])

    def test_a_past_commit_load_is_never_registered_for_a_save(self):
        before = dict(kt._BOARD_STATES)
        data = kt.load_board_at(self.head())
        self.assertEqual({"t_alpha", "t_beta"}, {t["id"] for t in data["tasks"]})
        self.assertNotIn(id(data), kt._BOARD_STATES); self.assertEqual(before, kt._BOARD_STATES)

    def test_snapshot_mode_is_unchanged(self):
        first = self.poll(history=False)
        self.assertEqual({"events", "cursor", "baseline", "semantics"}, set(first))
        self.assertEqual("snapshot-diff", first["semantics"]); self.assertTrue(first["baseline"])
        self.assertEqual({"v": 1, "board": "acme/board", "project": "pr_one"}, decode(first["cursor"])["scope"])
        self.change(lambda d: self.alpha(d).update(column="todo"))
        second = self.poll(first["cursor"], history=False)
        self.assertEqual(["column"], [e["kind"] for e in second["events"]])
        self.assertNotIn("commit", second["events"][0]); self.assertNotIn("id", second["events"][0])


class HistoryApi(GitBoard):
    WRITE = "api"

    def test_a_change_and_its_revert_between_polls_give_two_events(self):
        first = self.poll()
        self.assertEqual(self.head(), decode(first["cursor"])["commit"])
        there = self.change(lambda d: self.alpha(d).update(column="todo"), push=False)
        back = self.change(lambda d: self.alpha(d).update(column="backlog"))
        events = self.poll(first["cursor"])["events"]
        self.assertEqual([("backlog -> todo", there), ("todo -> backlog", back)], [(e["text"], e["commit"]) for e in events])

    def test_paging_matches_the_git_transport(self):
        cursor = self.poll()["cursor"]
        made = [self.change(lambda d, n=n: self.alpha(d).update(title=f"Alpha {n}"), push=False) for n in range(22)]
        self.push()
        first = self.poll(cursor); second = self.poll(first["cursor"])
        self.assertEqual((True, False), (first["more"], second["more"]))
        self.assertEqual(made, [e["commit"] for e in first["events"] + second["events"]])

    def test_a_rewritten_branch_and_an_unknown_commit_are_refused(self):
        self.change(lambda d: self.alpha(d).update(title="kept"))
        cursor = self.poll()["cursor"]
        self.run_git(self.writer, "reset", "-q", "--hard", "HEAD~1")
        self.change(lambda d: self.alpha(d).update(title="rewritten"), push=False)
        self.run_git(self.writer, "push", "-q", "--force", "origin", "main")   # the test's own throwaway bare remote
        with self.assertRaisesRegex(SystemExit, "not an ancestor.*fresh baseline"):
            self.poll(cursor)
        token = {**decode(cursor), "commit": "2" * 40}
        with self.assertRaisesRegex(SystemExit, "not a commit.*fresh baseline"):
            self.poll(base64.urlsafe_b64encode(json.dumps(token).encode()).decode())

    def test_side_branch_changes_are_replayed_in_topological_order(self):
        cursor = self.poll()["cursor"]
        self.run_git(self.writer, "checkout", "-q", "-b", "side")
        there = self.change(lambda d: self.alpha(d).update(column="todo"), push=False)
        back = self.change(lambda d: self.alpha(d).update(column="backlog"), push=False)
        self.run_git(self.writer, "checkout", "-q", "main")
        self.run_git(self.writer, "merge", "-q", "--no-ff", "-m", "merge side", "side")
        self.push()
        events = self.poll(cursor)["events"]
        self.assertEqual([("backlog -> todo", there), ("todo -> backlog", back)], [(e["text"], e["commit"]) for e in events])

    def test_a_commit_without_the_board_folder_is_one_loud_event(self):
        cursor = self.poll()["cursor"]
        self.run_git(self.writer, "rm", "-q", "-r", "board")
        self.run_git(self.writer, "commit", "-qm", "no board")
        gone = self.run_git(self.writer, "rev-parse", "HEAD")
        (Path(self.writer) / "board").mkdir()
        restored = self.save(board(), "board back")
        moved = self.change(lambda d: self.alpha(d).update(column="todo"))
        events = self.poll(cursor)["events"]
        self.assertEqual([("unreplayable", gone), ("unreplayable", restored), ("column", moved)],
                         [(e["kind"], e["commit"]) for e in events])

    def test_a_past_commit_never_prunes_the_blob_cache(self):
        old = self.head()
        self.change(lambda d: self.alpha(d).update(title="newer"))
        self.poll(history=False)
        cached = set(Path(kt.CACHE_DIR).rglob("*.json"))
        kt.load_board_at(old)
        self.assertLessEqual(cached, set(Path(kt.CACHE_DIR).rglob("*.json")))


class Probe:
    """Two side branches (3 board commits each), a main commit and two --no-ff merges, polled one call at a time under
    every page and scan cap: each run must end, deliver every board-changing commit (or name it in a gap event), and move
    the cursor strictly forward along head's first-parent line."""

    def split_card(self, tid, num, title):
        path = Path(self.writer) / "board" / "cards" / f"{tid}.json"
        path.write_text(json.dumps(card(tid, num, title), indent=1))
        self.run_git(self.writer, "add", "-A")
        self.run_git(self.writer, "commit", "-qm", f"{tid} {title}")
        return self.run_git(self.writer, "rev-parse", "HEAD")

    def build(self):
        root = {k: v for k, v in board().items() if k not in ("tasks", "projects")}
        root.update(version=4, layout="split")
        folder = Path(self.writer) / "board"
        (folder / "tasks.json").write_text(json.dumps(root, indent=1))
        (folder / "projects").mkdir(); (folder / "cards").mkdir()
        (folder / "projects" / "pr_one.json").write_text(json.dumps({"id": "pr_one", "name": "One", "client": "Example"}))
        self.split_card("t_alpha", 1, "Alpha"); self.split_card("t_gamma", 3, "Gamma")
        self.push()
        base = self.head()
        self.run_git(self.writer, "checkout", "-q", "-b", "s1", base)
        side1 = [self.split_card("t_alpha", 1, f"Alpha {n}") for n in range(3)]
        self.run_git(self.writer, "checkout", "-q", "-b", "s2", base)
        side2 = [self.split_card("t_gamma", 3, f"Gamma {n}") for n in range(3)]
        self.run_git(self.writer, "checkout", "-q", "main")
        main = self.split_card("t_delta", 4, "Delta")
        merges = []
        for branch in ("s1", "s2"):
            self.run_git(self.writer, "merge", "-q", "--no-ff", "-m", f"merge {branch}", branch)
            merges.append(self.run_git(self.writer, "rev-parse", "HEAD"))
        self.push()
        line = self.run_git(self.remote, "rev-list", "--first-parent", "--reverse", f"{base}..main").split()
        return base, side1, side2, main, merges, line

    def test_every_page_and_scan_cap_ends_without_missing_a_commit(self):
        base, side1, side2, main, merges, line = self.build()
        side_of = {**{c: merges[0] for c in side1}, **{c: merges[1] for c in side2}}
        token = base64.urlsafe_b64encode(json.dumps({"v": 2, "board": "acme/board", "project": "pr_one", "commit": base}).encode()).decode()
        for page in (1, 2, 3, 5):
            for scan in (2, 3, 4, 200):
                with self.subTest(page=page, scan=scan), mock.patch.object(kt, "WATCH_HISTORY_PAGE", page), \
                        mock.patch.object(kt, "WATCH_HISTORY_SCAN", scan):
                    cursor, events, at = token, [], -1
                    for _ in range(20):
                        result = self.poll(cursor)
                        events += result["events"]; cursor = result["cursor"]
                        now = line.index(decode(cursor)["commit"])
                        self.assertGreater(now, at); at = now   # strictly forward along the first-parent line
                        if not result["more"]:
                            break
                    self.assertFalse(result["more"]); self.assertEqual(line[-1], decode(cursor)["commit"])
                    delivered = {e["commit"] for e in events if e["kind"] != "unreplayable"}
                    gaps = {e["commit"] for e in events if e["kind"] == "unreplayable"}
                    missed = [c for c in side1 + side2 + [main] + merges
                              if c not in delivered and side_of.get(c) not in gaps]
                    self.assertEqual([], missed)
                    if scan >= 4:
                        self.assertEqual(set(), gaps)

    def test_a_side_branch_over_the_scan_cap_is_one_gap_event_and_progress(self):
        base, side1, side2, main, merges, line = self.build()
        token = base64.urlsafe_b64encode(json.dumps({"v": 2, "board": "acme/board", "project": "pr_one", "commit": main}).encode()).decode()
        with mock.patch.object(kt, "WATCH_HISTORY_SCAN", 3):
            result = self.poll(token)
        gap = [e for e in result["events"] if e["kind"] == "unreplayable"]
        self.assertEqual([merges[0]], [e["commit"] for e in gap]); self.assertIsNone(gap[0]["card"])
        self.assertIn("3 side-branch commits", gap[0]["text"])
        self.assertIn(merges[0], {e["commit"] for e in result["events"] if e["kind"] == "fields"})   # the merge itself
        self.assertEqual((merges[0], True), (decode(result["cursor"])["commit"], result["more"]))


class ProbeGit(Probe, GitBoard):
    pass


class ProbeApi(Probe, GitBoard):
    WRITE = "api"


class HistoryFile(unittest.TestCase):
    def test_a_file_board_has_no_history_and_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tasks.json"; path.write_text(json.dumps(board()))
            with mock.patch.object(kt, "FILE", str(path)), mock.patch.object(kt, "BACKEND", "github"):
                with mock.patch("sys.stdin", io.StringIO("null")), contextlib.redirect_stdout(io.StringIO()):
                    with self.assertRaisesRegex(SystemExit, "no commit history"):
                        kt.cmd_work(SimpleNamespace(work_action="watch-poll", project="pr_one", history=True))
                out = io.StringIO()
                with mock.patch("sys.stdin", io.StringIO("null")), contextlib.redirect_stdout(out):
                    kt.cmd_work(SimpleNamespace(work_action="watch-poll", project="pr_one", history=False))
                self.assertEqual("snapshot-diff", json.loads(out.getvalue())["semantics"])


if __name__ == "__main__":
    unittest.main()

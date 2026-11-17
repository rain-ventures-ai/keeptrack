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

    def test_a_replayed_commit_gives_the_same_events_whenever_it_is_replayed(self):
        cursor = self.poll()["cursor"]
        at = kt.now()
        claim = {"agent": "codex", "on_behalf_of": "owner", "session_id": "s", "generation": "g", "claimed_at": at,
                 "heartbeat_at": at, "status": "running"}
        self.change(lambda d: self.alpha(d).update(claim=claim, history=[{"at": at, "by": "codex@owner", "text": "claimed"}],
                                                   due="2000-01-01"))
        strip = lambda events: [{k: v for k, v in e.items() if k != "at"} for e in events]
        early = self.poll(cursor)["events"]
        with mock.patch.object(kt, "stale_limit", return_value=-1):   # long after the stale limit
            late = self.poll(cursor)["events"]
        self.assertEqual(strip(early), strip(late))
        claimed = [e for e in late if e["kind"] == "claim"]
        self.assertEqual([("claimed by codex", "codex@owner")], [(e["text"], e["by"]) for e in claimed])
        self.assertFalse({"stale", "overdue", "chase"} & {e["kind"] for e in late})

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


    def test_a_corrupt_past_commit_is_one_loud_event_but_a_corrupt_head_stops(self):
        self.build()
        cursor = self.poll()["cursor"]
        folder = Path(self.writer) / "board"
        good_card, good_root = (folder / "cards" / "t_alpha.json").read_text(), (folder / "tasks.json").read_text()

        def commit(path, text, message):
            path.write_text(text)
            self.run_git(self.writer, "commit", "-qam", message)
            return self.run_git(self.writer, "rev-parse", "HEAD")
        bad_card = commit(folder / "cards" / "t_alpha.json", "{not json", "corrupt card")
        self.push()
        with self.assertRaisesRegex(SystemExit, "invalid JSON"):   # at head: loud, as before
            self.poll(cursor)
        later = commit(Path(self.writer) / "README.md", "later\n", "readme")
        self.push()
        first = self.poll(cursor)
        self.assertEqual([("unreplayable", bad_card)], [(e["kind"], e["commit"]) for e in first["events"]])
        self.assertIn("not valid JSON", first["events"][0]["text"]); self.assertNotIn("{not json", first["events"][0]["text"])
        self.assertEqual((later, False), (decode(first["cursor"])["commit"], first["more"]))
        fixed = commit(folder / "cards" / "t_alpha.json", good_card, "fix card")
        bad_root = commit(folder / "tasks.json", "{not json", "corrupt root")
        fixed_root = commit(folder / "tasks.json", good_root, "fix root")
        moved = self.split_card("t_alpha", 1, "Alpha moved on")
        self.push()
        second = self.poll(first["cursor"])   # the cursor sits on a corrupt board and still moves past it
        self.assertEqual([("unreplayable", fixed), ("unreplayable", bad_root), ("unreplayable", fixed_root), ("fields", moved)],
                         [(e["kind"], e["commit"]) for e in second["events"]])
        self.assertEqual((moved, False), (decode(second["cursor"])["commit"], second["more"]))


    def no_board_then_back(self, *rm):
        cursor = self.poll()["cursor"]
        self.run_git(self.writer, "rm", "-q", "-r", *rm)
        self.run_git(self.writer, "commit", "-qm", "no board")
        gone = self.run_git(self.writer, "rev-parse", "HEAD")
        self.run_git(self.writer, "revert", "--no-edit", "HEAD")
        back = self.run_git(self.writer, "rev-parse", "HEAD")
        moved = self.split_card("t_alpha", 1, "Alpha again")
        self.push()
        with mock.patch.object(kt, "WATCH_HISTORY_PAGE", 1):   # the page ends on the commit without a board
            first = self.poll(cursor)
        self.assertEqual(([("unreplayable", gone)], gone, True),
                         ([(e["kind"], e["commit"]) for e in first["events"]], decode(first["cursor"])["commit"], first["more"]))
        second = self.poll(first["cursor"])   # the cursor has no board to read, and the poll still moves on
        self.assertEqual([("unreplayable", back), ("fields", moved)], [(e["kind"], e["commit"]) for e in second["events"]])
        self.assertEqual((moved, False), (decode(second["cursor"])["commit"], second["more"]))

    def test_a_cursor_on_a_commit_without_the_board_folder_moves_on(self):
        self.build()
        self.no_board_then_back("board")

    def test_a_cursor_on_a_commit_without_tasks_json_moves_on(self):
        self.build()
        self.no_board_then_back("board/tasks.json")


class ProbeGit(Probe, GitBoard):
    pass


class ProbeApi(Probe, GitBoard):
    WRITE = "api"


class ApiCost(GitBoard):
    """The API transport reads a catch-up's compare range once, not once per poll, and each replayed commit once."""
    WRITE = "api"

    def setUp(self):
        super().setUp()
        self.calls = []
        real = self.fake_gh
        p = mock.patch.object(kt, "gh", lambda *a, body=None: (self.calls.append(a[0]), real(*a, body=body))[1])
        p.start(); self.addCleanup(p.stop)
        p = mock.patch.object(kt, "_API_TREE_MEMO", {}); p.start(); self.addCleanup(p.stop)

    def empty_commits(self, n):
        """n commits that leave every file as it was, straight into the remote (one git process)."""
        head, stream = self.head(), []
        for i in range(n):
            message = f"empty {i}".encode()
            stream.append(b"commit refs/heads/main\ncommitter t <t@example.com> %d +0000\ndata %d\n%s\n"
                          % (1700000000 + i, len(message), message))
            if i == 0:
                stream.append(b"from %s\n" % head.encode())
        subprocess.run(["git", "-C", self.remote, "fast-import", "--quiet"], input=b"".join(stream), check=True, capture_output=True)

    def compares(self):
        return sum(1 for c in self.calls if "/compare/" in c)

    def test_a_long_catch_up_reads_the_compare_range_once(self):
        cursor = self.poll()["cursor"]
        self.empty_commits(1000)
        self.calls.clear()
        with mock.patch.object(kt, "WATCH_HISTORY_SCAN", 50):   # 20 polls
            polls = 0
            while True:
                result = self.poll(cursor); cursor = result["cursor"]; polls += 1
                if not result["more"]:
                    break
        self.assertEqual((20, self.head()), (polls, decode(cursor)["commit"]))
        # The range is read once (10 pages); every later poll adds one small count check.
        self.assertLessEqual(self.compares(), 10 + polls, f"{self.compares()} compare calls for a 1000-commit catch-up")
        self.empty_commits(5)   # a newer head: only its new commits are compared, plus the count check
        self.calls.clear()
        self.poll(cursor)
        self.assertEqual(2, self.compares())

    def cache(self, project="pr_one"):
        try:
            return json.loads(Path(kt._history_cache_file(project)).read_text())
        except FileNotFoundError:
            return None

    def test_two_watchers_keep_their_own_backlogs(self):
        ahead = self.poll()["cursor"]
        behind = self.poll(project="pr_two")["cursor"]
        self.empty_commits(1000)
        ahead = self.poll(ahead)["cursor"]   # watcher A catches up to head at once (no board change)
        self.calls.clear()
        with mock.patch.object(kt, "WATCH_HISTORY_SCAN", 50):
            for _ in range(20):   # A polls at head between each of B's catch-up polls
                ahead = self.poll(ahead)["cursor"]
                result = self.poll(behind, project="pr_two"); behind = result["cursor"]
        self.assertFalse(result["more"]); self.assertEqual(self.head(), decode(behind)["commit"])
        # A: one count check per poll. B: the range once (10 pages), then one count check per poll.
        self.assertLessEqual(self.compares(), 20 + 10 + 20, f"{self.compares()} compare calls for two watchers")

    def test_a_tampered_cache_costs_requests_never_commits(self):
        cursor = self.poll()["cursor"]
        made = [self.change(lambda d, n=n: self.alpha(d).update(title=f"Alpha {n}"), push=False) for n in range(6)]
        self.push()
        with mock.patch.object(kt, "WATCH_HISTORY_PAGE", 2):
            first = self.poll(cursor)
        path = Path(kt._history_cache_file("pr_one"))
        cache = json.loads(path.read_text())
        hidden = next(c for c in made[2:] if c in cache["parents"])
        cache["parents"].pop(hidden)   # a commit taken out of the local cache
        path.write_text(json.dumps(cache))
        events, cursor = list(first["events"]), first["cursor"]
        while True:
            result = self.poll(cursor); events += result["events"]; cursor = result["cursor"]
            if not result["more"]:
                break
        self.assertEqual(made, [e["commit"] for e in events])

    def test_old_and_surplus_cache_files_are_pruned(self):
        folder = Path(kt._history_cache_file("pr_one")).parent
        folder.mkdir(parents=True)
        for n in range(40):
            stale = folder / f"{n:016x}.json"; stale.write_text("{}")
            os.utime(stale, (1, 1) if n < 5 else None)
        (folder / "keep-me.txt").write_text("not a cache file")
        cursor = self.poll()["cursor"]
        self.change(lambda d: self.alpha(d).update(title="moved"))
        self.poll(cursor)
        names = {p.name for p in folder.iterdir()}
        self.assertIn("keep-me.txt", names); self.assertIn(Path(kt._history_cache_file("pr_one")).name, names)
        self.assertLessEqual(len([n for n in names if n.endswith(".json")]), kt.WATCH_HISTORY_CACHE_FILES)
        self.assertFalse({f"{n:016x}.json" for n in range(5)} & names)

    def test_the_cache_holds_the_backlog_not_the_history(self):
        cursor = self.poll()["cursor"]
        self.empty_commits(1000)
        sizes = []
        with mock.patch.object(kt, "WATCH_HISTORY_SCAN", 20):   # 50 polls
            for _ in range(50):
                result = self.poll(cursor); cursor = result["cursor"]
                sizes.append(len(self.cache()["parents"]))
        self.assertFalse(result["more"])
        self.assertEqual([1000 - 20 * k for k in range(1, 51)], sizes)
        self.assertEqual((decode(cursor)["commit"], self.head()), (self.cache()["base"], self.cache()["head"]))
        writes = []
        real = kt.atomic_write
        with mock.patch.object(kt, "atomic_write", lambda path, text, *a, **k: (writes.append(path), real(path, text, *a, **k))):
            self.poll(cursor); self.poll(cursor)
        self.assertEqual([], writes)   # nothing new: no write

    def test_over_the_limit_the_cache_is_rebuilt_never_left_stale(self):
        cursor = self.poll()["cursor"]
        self.empty_commits(100)
        with mock.patch.object(kt, "WATCH_HISTORY_CACHE_MAX", 30), mock.patch.object(kt, "WATCH_HISTORY_SCAN", 20):
            for extra in (0, 0, 0, 0, 0, 0, 45, 0, 0, 0):
                if extra:
                    self.empty_commits(extra)   # the head gains more than the cache may hold
                result = self.poll(cursor); cursor = result["cursor"]
                cache = self.cache()
                if cache is not None:
                    self.assertEqual((decode(cursor)["commit"], self.head()), (cache["base"], cache["head"]))
                    self.assertLessEqual(len(cache["parents"]), 30)
        self.assertEqual(self.head(), decode(cursor)["commit"])
        self.assertIsNotNone(self.cache())

    def test_a_replayed_commit_is_read_once(self):
        cursor = self.poll()["cursor"]
        sha = self.change(lambda d: self.alpha(d).update(title="Alpha read once " + os.urandom(4).hex()))
        self.calls.clear()
        self.assertEqual(["fields"], [e["kind"] for e in self.poll(cursor)["events"]])
        self.assertEqual(1, sum(1 for c in self.calls if c.endswith("/git/commits/" + sha)))


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

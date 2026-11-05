"""Kit v118: resolve never passes a partial answer off as a whole one. A board that can't be read is unknown, not
empty: the answer says complete false and which boards it could not read, and names no board it could not check. Each
board's projects are cached with the head commit they were read at, so an unchanged board is not read again, and a
failed read falls back to the last good one (said as stale). A board with a local clone is read with git."""
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from test_kit_v112 import Board, keeptrack, read  # noqa: E402

kt = keeptrack
GIT_ENV = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
P = [{"id": "pr_a", "name": "A", "status": "active", "repos": ["acme/web"]}]


def git_repo(path, origin=None):
    os.makedirs(path, exist_ok=True)
    subprocess.run(["git", "init", "-q", path], check=True, env=GIT_ENV)
    if origin:
        subprocess.run(["git", "-C", path, "remote", "add", "origin", origin], check=True, env=GIT_ENV)
    return os.path.realpath(path)


class Release(unittest.TestCase):
    def test_release_118_is_consistent(self):
        version = json.loads(read("board/kit/manifest.json"))["version"]
        self.assertGreaterEqual(version, 118)   # the exact version is asserted by the newest tests/test_kit_v*.py
        self.assertEqual(str(version), re.search(r"^KIT_VERSION = (\d+)", read("board/kit/keeptrack.py"), re.M)[1])
        self.assertIn(f"const PAGE_KIT = {version};", read("board/board.js"))
        for plugin in (".claude-plugin", ".codex-plugin", ".cursor-plugin"):
            self.assertEqual(f"0.{version}.0", json.loads(read(f"board/kit/{plugin}/plugin.json"))["version"])
        self.assertIn("### v118 (schema 4)", read("board/kit/UPGRADING.md"))
        self.assertIn("Kit v118:", read("CHANGELOG.md"))
        self.assertIn("complete", read("board/kit/README.md"))


class Cache(unittest.TestCase):
    """_board_projects: cache by head, stale on a failed read, unknown with no cache."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = mock.patch.dict(os.environ, {"XDG_CACHE_HOME": self.tmp.name})
        self.env.start()
        self.b = {"board": "acme/board", "branch": "main", "path": "board/tasks.json", "clone": "", "config": "", "current": False}

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def run_it(self, head, read_result):
        reads = []

        def reader(b):
            reads.append(b["board"])
            return read_result
        with mock.patch.object(kt, "_board_head_of", lambda b: head), mock.patch.object(kt, "_read_board_projects", reader):
            got = kt._board_projects(self.b)
        return got, reads

    def test_unchanged_head_reads_nothing(self):
        (projects, err, src), reads = self.run_it("a" * 40, (P, ""))
        self.assertEqual(("live", ["acme/board"]), (src, reads))
        self.assertEqual(0o600, os.stat(kt._projects_cache_file("acme/board")).st_mode & 0o777)
        (projects, err, src), reads = self.run_it("a" * 40, (None, "boom"))
        self.assertEqual(("cache", [], "acme/web"), (src, reads, projects[0]["repos"][0]))

    def test_moved_head_reads_again(self):
        self.run_it("a" * 40, (P, ""))
        newer = [dict(P[0], repos=["acme/api"])]
        (projects, _, src), reads = self.run_it("b" * 40, (newer, ""))
        self.assertEqual(("live", ["acme/api"]), (src, projects[0]["repos"]))
        self.assertEqual("b" * 40, kt._read_projects_cache("acme/board")["head"])

    def test_failed_read_uses_the_last_good_one_and_says_so(self):
        self.run_it("a" * 40, (P, ""))
        (projects, err, src), _ = self.run_it("b" * 40, (None, "TimeoutExpired"))
        self.assertEqual(("stale", "TimeoutExpired", "pr_a"), (src, err, projects[0]["id"]))
        (projects, err, src), _ = self.run_it(None, (None, "rate limited"))
        self.assertEqual("stale", src, "no head (GitHub down) and no read: still the last good one")

    def test_never_read_is_unknown_not_empty(self):
        (projects, err, src), _ = self.run_it(None, (None, "TimeoutExpired"))
        self.assertEqual((None, "TimeoutExpired", None), (projects, err, src))

    def test_no_head_means_no_cache_write(self):
        self.run_it(None, (P, ""))
        self.assertIsNone(kt._read_projects_cache("acme/board"))


class Incomplete(unittest.TestCase):
    """resolve with a board that could not be read."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = os.path.realpath(self.tmp.name)
        self.env = mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": os.path.join(self.root, "xdg")})
        self.env.start()
        self.boards = [{"board": "me/private"}, {"board": "team/consulting"}]
        self.data = {"me/private": [{"id": "pr_kt", "name": "Keeptrack", "status": "active", "repos": ["me/kt"]}],
                     "team/consulting": None}   # could not be read

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def resolve(self, folder):
        return kt.resolve_folder(folder, self.boards, lambda b: self.data.get(b, []))

    def test_an_unread_board_names_no_board(self):
        for origin in ("https://github.com/me/kt", "https://github.com/team/site"):
            r = self.resolve(git_repo(os.path.join(self.root, origin.split("/")[-1]), origin))
            self.assertEqual((None, False, "incomplete", ["team/consulting"]), (r["board"], r["complete"], r["why"], r["unread"]), origin)
        self.assertEqual([("me/private", "pr_kt")], [(m["board"], m["project"]) for m in
                                                     self.resolve(os.path.join(self.root, "kt"))["matches"]], "what was found")

    def test_all_read_is_complete(self):
        self.data["team/consulting"] = []
        r = self.resolve(git_repo(os.path.join(self.root, "kt2"), "https://github.com/me/kt"))
        self.assertEqual(("me/private", True, []), (r["board"], r["complete"], r["unread"]))

    def test_a_config_board_that_cannot_be_read_keeps_the_board_not_the_project(self):
        top = git_repo(os.path.join(self.root, "c"), "https://github.com/team/site")
        p = os.path.join(top, ".keeptrack", "config.json")
        os.makedirs(os.path.dirname(p))
        with open(p, "w") as f:
            json.dump({"repo": "team/consulting", "project": "pr_site"}, f)
        os.chmod(p, 0o600)
        kt.trust_config(p)
        r = self.resolve(top)
        self.assertEqual(("team/consulting", None, False, "config"), (r["board"], r["project"], r["complete"], r["why"]))

    def test_a_parent_with_an_unread_board_is_incomplete(self):
        parent = os.path.join(self.root, "p")
        git_repo(os.path.join(parent, "kt"), "https://github.com/me/kt")
        r = self.resolve(parent)
        self.assertEqual((None, False, "incomplete"), (r["board"], r["complete"], r["why"]))


class ReadThroughTheClone(unittest.TestCase):
    def test_a_board_with_a_clone_is_read_with_git(self):
        calls = []

        def fake_run(args, **kw):
            calls.append((args, kw.get("env", {}).get("BOARD_WRITE"), kw.get("cwd")))
            if args[0] == "git":
                return subprocess.CompletedProcess(args, 0, "c" * 40 + "\trefs/heads/master\n", "")
            return subprocess.CompletedProcess(args, 0, json.dumps(P), "")
        with tempfile.TemporaryDirectory() as clone:
            os.makedirs(os.path.join(clone, "board"))
            open(os.path.join(clone, "board", "keeptrack.py"), "w").close()
            b = {"board": "me/private", "branch": "master", "clone": clone, "config": "", "current": True}
            with mock.patch.object(kt.subprocess, "run", fake_run), \
                 mock.patch.dict(os.environ, {"XDG_CACHE_HOME": os.path.join(clone, "cache")}):
                self.assertEqual("c" * 40, kt._board_head_of(b))
                projects, err = kt._read_board_projects(b)
        self.assertEqual("pr_a", projects[0]["id"])
        self.assertEqual(["git", "-C", clone, "ls-remote", "origin", "refs/heads/master"], calls[0][0])
        self.assertEqual((os.path.join(clone, "board", "keeptrack.py"), "git", clone), (calls[1][0][1], calls[1][1], calls[1][2]),
                         "the clone's own keeptrack.py, with the git transport")


class Cli(Board):
    def test_board_head_refuses_a_file_board(self):
        p = self.kt("board-head", ok=False)
        self.assertNotEqual(0, p.returncode)
        self.assertIn("not known", p.stderr)

    def test_resolve_json_has_complete(self):
        self.kt("project-add", "Web", "--client", "Acme", "--repo", "acme/web")
        top = git_repo(os.path.join(self.repo, "w"), "https://github.com/acme/web")
        r = json.loads(self.kt("resolve", top, "--json", XDG_CONFIG_HOME=os.path.join(self.repo, "x"),
                               XDG_CACHE_HOME=os.path.join(self.repo, "c")).stdout)
        self.assertEqual((True, [], [], "Web"), (r["complete"], r["unread"], r["stale"], r["project_name"]))


if __name__ == "__main__":
    unittest.main()

"""Kit v112: keeptrack.py runs without git; the docs-home refusal trusts git's "not a repository"; more Windows
spellings; volume paths refused; release consistency."""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KIT = os.path.join(ROOT, "board", "kit")
if KIT not in sys.path:
    sys.path.insert(0, KIT)
import keeptrack  # noqa: E402


def read(path):
    with open(os.path.join(ROOT, path), encoding="utf8") as stream:
        return stream.read()


class Release(unittest.TestCase):
    def test_release_112_is_consistent(self):
        version = json.loads(read("board/kit/manifest.json"))["version"]
        self.assertEqual(version, 112)
        self.assertEqual(str(version), re.search(r"^KIT_VERSION = (\d+)", read("board/kit/keeptrack.py"), re.M)[1])
        self.assertIn(f"const PAGE_KIT = {version};", read("board/board.js"))
        for plugin in (".claude-plugin", ".codex-plugin", ".cursor-plugin"):
            self.assertEqual(f"0.{version}.0", json.loads(read(f"board/kit/{plugin}/plugin.json"))["version"])
        for version in (111, 112):
            self.assertIn(f"### v{version} (schema 4)", read("board/kit/UPGRADING.md"))
            self.assertIn(f"Kit v{version}:", read("CHANGELOG.md"))


def done(rc, err="", out=""):
    return subprocess.CompletedProcess(["git"], rc, out, err)


class GitAnswers(unittest.TestCase):
    def test_how_git_answered(self):
        for err, want in (("fatal: not a git repository (or any parent)", "none"),
                          ("fatal: detected dubious ownership in repository; add safe.directory", "refused"),
                          ("fatal: bad config line 3", "error"), ("fatal: unknown repository extension found", "error")):
            with mock.patch.object(keeptrack.subprocess, "run", lambda *a, err=err, **k: done(128, err)):
                self.assertEqual(("", want), keeptrack._git_toplevel("/x"), err)
        def missing(*a, **k):
            raise FileNotFoundError("git")
        with mock.patch.object(keeptrack.subprocess, "run", missing):
            self.assertEqual(("", "missing"), keeptrack._git_toplevel("/x"))
        seen = {}
        with mock.patch.object(keeptrack.subprocess, "run", lambda *a, **k: seen.update(k) or done(0, out="/top\n")):
            self.assertEqual(("/top", "ok"), keeptrack._git_toplevel("/x"))
        self.assertEqual("C", seen["env"]["LC_ALL"], "messages are matched in English")

    def test_a_folder_git_calls_not_a_repository_is_not_refused_for_a_git_entry_higher_up(self):
        with tempfile.TemporaryDirectory() as home:
            os.makedirs(os.path.join(home, ".git"))   # a stray or dotfiles .git git does not count for this folder
            boards = os.path.join(home, "boards")
            os.makedirs(boards)
            board = os.path.join(boards, "tasks.json")
            open(board, "w").close()
            with mock.patch.object(keeptrack, "ROOT", None), mock.patch.object(keeptrack, "FILE", board), \
                 mock.patch.object(keeptrack.subprocess, "run", lambda *a, **k: done(128, "fatal: not a git repository")):
                self.assertFalse(keeptrack._inside_board_checkout(os.path.join(home, "Documents")))
            for err in ("dubious ownership", "fatal: bad config line 3"):   # anything but "not a repository" fails closed
                with mock.patch.object(keeptrack, "ROOT", None), mock.patch.object(keeptrack, "FILE", board), \
                     mock.patch.object(keeptrack.subprocess, "run", lambda *a, err=err, **k: done(128, err)):
                    self.assertTrue(keeptrack._inside_board_checkout(os.path.join(home, "Documents")), err)


class TrustedClone(unittest.TestCase):
    """Finding the board clone (ROOT) trusts it: automations run from it. Only git's own answer, or with no git
    at all a .git this user owns, may name it; git's safe.directory refusal is final."""
    def test_git_refusal_and_foreign_trees_never_name_the_clone(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, ".git"))
            os.makedirs(os.path.join(tmp, "board"))
            open(os.path.join(tmp, "board", "tasks.json"), "w").close()
            for how, owned, want in (("refused", True, ""), ("error", True, ""), ("missing", False, ""), ("missing", True, tmp)):
                with mock.patch.object(keeptrack, "_git_toplevel", lambda f, how=how: ("", how)), \
                     mock.patch.object(keeptrack, "_own_tree", lambda t, owned=owned: owned):
                    top, h = keeptrack._git_toplevel(tmp)
                    if h == "missing":
                        top = keeptrack._dot_git_top(tmp)
                        top = top if top and keeptrack._own_tree(top) else ""
                    self.assertEqual(want, top, (how, owned))

    def test_own_tree_checks_owner_and_write_bits(self):
        if not hasattr(os, "getuid"):
            self.skipTest("no user ids here")
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, ".git"))
            os.chmod(tmp, 0o755); os.chmod(os.path.join(tmp, ".git"), 0o755)
            self.assertTrue(keeptrack._own_tree(tmp))
            os.chmod(os.path.join(tmp, ".git"), 0o777)
            self.assertFalse(keeptrack._own_tree(tmp), "a .git others can write is not trusted")
            os.chmod(os.path.join(tmp, ".git"), 0o755)
            me = os.getuid()
            with mock.patch.object(keeptrack.os, "getuid", lambda: me + 1):
                self.assertFalse(keeptrack._own_tree(tmp), "someone else's tree is not trusted")


class WithoutGitInstalled(unittest.TestCase):
    def run_without_git(self, script_dir, cwd, env_extra=()):
        with tempfile.TemporaryDirectory() as bin_dir:
            os.symlink(sys.executable, os.path.join(bin_dir, "python3"))
            env = {k: v for k, v in os.environ.items() if not k.startswith(("BOARD_", "GH_", "GITHUB_"))}
            env.update(PATH=bin_dir, HOME=cwd, **dict(env_extra))
            code = f"import sys; sys.argv=['keeptrack.py']; sys.path.insert(0, {script_dir!r}); import keeptrack as k; print('ROOT=' + str(k.ROOT))"
            return subprocess.run([os.path.join(bin_dir, "python3"), "-c", code], capture_output=True, text=True, cwd=cwd, env=env)

    def test_plugin_and_board_copies_start_without_git(self):
        with tempfile.TemporaryDirectory() as tmp:
            clone = os.path.join(tmp, "clone")
            os.makedirs(os.path.join(clone, ".git"))
            os.makedirs(os.path.join(clone, "board"))
            open(os.path.join(clone, "board", "tasks.json"), "w").close()
            shutil.copy(os.path.join(KIT, "keeptrack.py"), os.path.join(clone, "board", "keeptrack.py"))
            plugin = os.path.join(tmp, "plugin")
            os.makedirs(plugin)
            shutil.copy(os.path.join(KIT, "keeptrack.py"), os.path.join(plugin, "keeptrack.py"))
            p = self.run_without_git(plugin, clone)
            self.assertEqual(0, p.returncode, p.stderr)
            self.assertEqual("ROOT=" + clone, p.stdout.strip().splitlines()[-1], "a plugin copy finds the clone from its .git")
            p = self.run_without_git(os.path.join(clone, "board"), clone)
            self.assertEqual(0, p.returncode, p.stderr)
            self.assertEqual("ROOT=" + clone, p.stdout.strip().splitlines()[-1])
            outside = os.path.join(tmp, "elsewhere")
            os.makedirs(outside)
            p = self.run_without_git(plugin, outside, {"BOARD_REPO": "acme/board"})   # a plugin copy away from any clone
            self.assertEqual(0, p.returncode, p.stderr)
            self.assertEqual("ROOT=None", p.stdout.strip().splitlines()[-1])


class WindowsSpellings(unittest.TestCase):
    def test_this_machine_admin_shares_and_trailing_dots(self):
        f = lambda p: keeptrack._local_spelling(p, True)
        with mock.patch.object(keeptrack.socket, "gethostname", lambda: "MYPC"):   # Windows gives the short name
            for given, want in ((r"\\[::1]\C$\Users\o", r"C:\Users\o"), (r"\\127.1.2.3\d$\x", r"d:\x"),
                                (r"\\0--1.ipv6-literal.net\c$\z", r"c:\z"), (r"\\mypc\C$\repo", r"C:\repo"),
                                (r"\\MYPC.corp.example\C$\repo", r"C:\repo"), (r"\\otherpc\C$\repo", r"\\otherpc\C$\repo"),
                                (r"C:\repo.\docs ", r"C:\repo\docs"), (r"C:\a\..\b", r"C:\a\..\b"),
                                (r"\\?\C:\repo.\docs", r"C:\repo.\docs"), (r"\\127.1\C$\x", r"C:\x"),
                                (r"\\server\share\x.", r"\\server\share\x.")):
                self.assertEqual(want, f(given), given)

    def test_volume_and_device_paths_are_refused(self):
        for p in (r"\\?\GLOBALROOT\Device\HarddiskVolume3\x", r"\\?\Volume{1b2c}\x", r"\\.\Volume{1b2c}\x",
                  r"\\.\HarddiskVolume3\repo\docs", r"\\?\Harddisk0Partition1\x"):
            self.assertTrue(keeptrack._unverifiable_local(p, True), p)
        for p in (r"\\?\C:\x", r"\\?\UNC\host\share\x", r"\\.\UNC\host\share", r"C:\x", r"\\host\share\x"):
            self.assertFalse(keeptrack._unverifiable_local(p, True), p)
        self.assertFalse(keeptrack._unverifiable_local(r"\\?\GLOBALROOT\x", False), "only on Windows")
        a = SimpleNamespace(docs_provider="local", docs_root=r"C:\Docs", clear_docs_home=False)
        with mock.patch.object(keeptrack, "_unverifiable_local", lambda p, w=None: True), \
             mock.patch.object(keeptrack, "validate_docs_home", lambda v: v), \
             mock.patch.object(keeptrack, "load", side_effect=AssertionError("must refuse before loading")):
            with self.assertRaises(SystemExit) as stop:
                keeptrack.cmd_settings_set(a)
        self.assertIn("volume or device path", str(stop.exception))


if __name__ == "__main__":
    unittest.main()

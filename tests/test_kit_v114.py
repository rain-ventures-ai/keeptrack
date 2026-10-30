"""Kit v114: keeptrack.py runs without git; the docs-home refusal trusts git's "not a repository"; more Windows
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
    def test_release_114_is_consistent(self):
        version = json.loads(read("board/kit/manifest.json"))["version"]
        self.assertGreaterEqual(version, 114)   # the exact version is asserted by the newest tests/test_kit_v*.py
        self.assertEqual(str(version), re.search(r"^KIT_VERSION = (\d+)", read("board/kit/keeptrack.py"), re.M)[1])
        self.assertIn(f"const PAGE_KIT = {version};", read("board/board.js"))
        for plugin in (".claude-plugin", ".codex-plugin", ".cursor-plugin"):
            self.assertEqual(f"0.{version}.0", json.loads(read(f"board/kit/{plugin}/plugin.json"))["version"])
        for version in (113, 114):
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
        def hung(*a, **k):
            raise subprocess.TimeoutExpired("git", 3)
        with mock.patch.object(keeptrack.subprocess, "run", hung):
            self.assertEqual(("", "hung"), keeptrack._git_toplevel("/x"))
        seen = {}
        with mock.patch.object(keeptrack.subprocess, "run", lambda *a, **k: seen.update(k) or done(0, out="/top\n")):
            self.assertEqual(("/top", "ok"), keeptrack._git_toplevel("/x"))
        self.assertEqual("C", seen["env"]["LC_ALL"], "messages are matched in English")

    def test_git_is_asked_once_per_folder_while_loading_and_afresh_after(self):
        self.assertIsNone(keeptrack._TOPLEVEL, "loaded: no cache")
        calls = []
        with mock.patch.object(keeptrack.subprocess, "run", lambda *a, **k: calls.append(1) or done(0, out="/top\n")):
            with mock.patch.object(keeptrack, "_TOPLEVEL", {}):   # as while the module loads
                for _ in range(3):
                    self.assertEqual(("/top", "ok"), keeptrack._git_toplevel("/x"))
            self.assertEqual(1, len(calls), "the clone and the claim folder share one answer")
            keeptrack._git_toplevel("/x")
            self.assertEqual(2, len(calls))

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


class GitBudget(unittest.TestCase):
    def test_start_up_calls_share_five_seconds_and_never_get_ten(self):
        start = keeptrack._GIT_START
        for elapsed, startup, want in ((0, True, 5.0), (3, True, 2.0), (4.5, True, 1.0), (13, True, 1.0), (60, False, 10.0)):
            with mock.patch.object(keeptrack.time, "monotonic", lambda e=elapsed: start + e), \
                 mock.patch.object(keeptrack, "_GIT_STARTUP", startup):
                self.assertAlmostEqual(want, keeptrack._git_timeout(), places=3, msg=(elapsed, startup))
        # a call whose answer decides something keeps a floor once the budget is spent, never more than 10 s
        for elapsed, startup, want in ((0, True, 5.0), (3, True, 3.0), (9, True, 3.0), (10.5, True, 1.5), (13, True, 1.0), (60, False, 10.0)):
            with mock.patch.object(keeptrack.time, "monotonic", lambda e=elapsed: start + e), \
                 mock.patch.object(keeptrack, "_GIT_STARTUP", startup):
                self.assertAlmostEqual(want, keeptrack._git_timeout(keeptrack._GIT_DECIDES), places=3, msg=(elapsed, startup))

    def test_deciding_calls_use_the_floor(self):
        src = read("board/kit/keeptrack.py")
        for name in ("def _ask_toplevel", "def _default_branch", "def _tracked_by_git"):
            self.assertIn("timeout=_git_timeout(_GIT_DECIDES)", src.split(name)[1][:900], name)

    def test_a_slow_git_stops_rather_than_guess_the_branch(self):
        def hung(*a, **k):
            raise subprocess.TimeoutExpired("git", 3)
        with mock.patch.dict(os.environ, {"BOARD_BRANCH": ""}), mock.patch.object(keeptrack, "ROOT", "/clone"), \
             mock.patch.object(keeptrack.subprocess, "run", hung):
            with self.assertRaises(SystemExit) as stop:
                keeptrack._default_branch()
        self.assertIn("BOARD_BRANCH", str(stop.exception))
        def missing(*a, **k):
            raise FileNotFoundError("git")
        with mock.patch.dict(os.environ, {"BOARD_BRANCH": ""}), mock.patch.object(keeptrack, "ROOT", "/clone"), \
             mock.patch.object(keeptrack.subprocess, "run", missing):
            self.assertEqual("master", keeptrack._default_branch(), "no git at all: the older boards' default")

    def test_a_slow_git_never_moves_the_claim_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = os.path.join(tmp, "repo")
            os.makedirs(os.path.join(repo, ".git"))
            cwd = os.getcwd()
            try:
                os.chdir(repo)
                for owned in (False, True):   # a stray .git this user owns may not be the folder's repo either
                    with mock.patch.object(keeptrack, "_git_toplevel", lambda f: ("", "hung")), \
                         mock.patch.object(keeptrack, "_own_tree", lambda t, owned=owned: owned), \
                         mock.patch.object(keeptrack, "_CLAIM_UNSURE", ""):
                        with self.assertRaises(SystemExit) as stop:   # v115: the commands that use the record stop
                            keeptrack._local_dir(); keeptrack._claim_sure()
                    self.assertIn("in time", str(stop.exception.code))
                with mock.patch.object(keeptrack, "_git_toplevel", lambda f: ("", "hung")), \
                     mock.patch.object(keeptrack, "_GIT_STARTUP", True), mock.patch.object(keeptrack, "_CLAIM_UNSURE", ""):
                    with self.assertRaises(SystemExit) as stop:
                        keeptrack._local_dir(); keeptrack._claim_sure()
                self.assertEqual(0, stop.exception.code, "the heartbeat hook stops quietly")
                with mock.patch.object(keeptrack, "_git_toplevel", lambda f: ("", "missing")), \
                     mock.patch.object(keeptrack, "_own_tree", lambda t: False), \
                     mock.patch.object(keeptrack, "PROJECT_DIR", tmp):
                    self.assertEqual(os.path.join(tmp, keeptrack.CONFIG_DIR_NAME), keeptrack._local_dir(), "no git: the config's folder")
                os.chdir(tmp)
                with mock.patch.object(keeptrack, "_git_toplevel", lambda f: ("", "hung")), \
                     mock.patch.object(keeptrack, "PROJECT_DIR", tmp), \
                     mock.patch.object(keeptrack, "_dot_git_top", lambda f: ""):   # no repo here at all
                    self.assertEqual(os.path.join(tmp, keeptrack.CONFIG_DIR_NAME), keeptrack._local_dir())
            finally:
                os.chdir(cwd)

    def test_only_the_heartbeat_hook_keeps_the_start_up_budget(self):
        src = read("board/kit/keeptrack.py")
        self.assertIn('_GIT_STARTUP = a.cmd == "auto-heartbeat"', src)
        self.assertIn('_GIT_STARTUP = sys.argv[1:2] == ["auto-heartbeat"]', src, "from import on: other commands give git 10 s")
        self.assertFalse(keeptrack._GIT_STARTUP, "a module imported by tests is not the hook")
        self.assertNotIn("timeout=10, env=_git_c_env())   # the stderr text", src, "the hook's own git call uses the budget")


class TrustedClone(unittest.TestCase):
    """Finding the board clone (ROOT) trusts it: automations run from it. Only git's own answer, or with no git
    at all a .git this user owns, may name it; git's safe.directory refusal is final."""
    def test_git_refusal_and_foreign_trees_never_name_the_clone(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, ".git"))
            for how, owned, want in (("refused", True, ""), ("error", True, ""), ("none", True, ""),
                                     ("missing", False, ""), ("missing", True, tmp), ("hung", False, ""), ("hung", True, tmp)):
                with mock.patch.object(keeptrack, "_git_toplevel", lambda f, how=how: ("", how)), \
                     mock.patch.object(keeptrack, "_own_tree", lambda t, owned=owned: owned):
                    self.assertEqual(want, keeptrack._trusted_top(tmp), (how, owned))
        src = read("board/kit/keeptrack.py")
        self.assertIn("_top = _trusted_top(os.getcwd())", src, "the board clone is found through _trusted_top")
        self.assertIn("top = _trusted_top(os.getcwd())", src.split("def _local_dir")[1][:900], "so is the claim folder")

    def test_a_git_that_refuses_for_ownership_leaves_the_clone_unnamed_end_to_end(self):
        with tempfile.TemporaryDirectory() as tmp:
            clone, bin_dir = os.path.join(tmp, "clone"), os.path.join(tmp, "bin")
            for d in (os.path.join(clone, ".git"), os.path.join(clone, "board"), bin_dir):
                os.makedirs(d)
            open(os.path.join(clone, "board", "tasks.json"), "w").close()
            plugin = os.path.join(tmp, "plugin")
            os.makedirs(plugin)
            shutil.copy(os.path.join(KIT, "keeptrack.py"), os.path.join(plugin, "keeptrack.py"))
            git = os.path.join(bin_dir, "git")
            with open(git, "w") as f:
                f.write("#!/bin/sh\necho \"fatal: detected dubious ownership in repository at '$PWD'\" >&2\n"
                        "echo \"To add an exception for this directory, call: git config --global --add safe.directory\" >&2\nexit 128\n")
            os.chmod(git, 0o755)
            os.symlink(sys.executable, os.path.join(bin_dir, "python3"))
            env = {k: v for k, v in os.environ.items() if not k.startswith(("BOARD_", "GH_", "GITHUB_"))}
            env.update(PATH=bin_dir, HOME=tmp)
            code = f"import sys; sys.argv=['keeptrack.py']; sys.path.insert(0, {plugin!r}); import keeptrack as k; print('ROOT=' + str(k.ROOT))"
            p = subprocess.run([os.path.join(bin_dir, "python3"), "-c", code], capture_output=True, text=True, cwd=clone, env=env)
            self.assertEqual(0, p.returncode, p.stderr)
            self.assertEqual("ROOT=None", p.stdout.strip().splitlines()[-1], "git's ownership refusal is final")

    def test_own_tree_checks_owner_and_write_bits(self):
        if not hasattr(os, "getuid"):
            self.skipTest("no user ids here")
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, ".git"))
            os.chmod(tmp, 0o755); os.chmod(os.path.join(tmp, ".git"), 0o755)
            self.assertTrue(keeptrack._own_tree(tmp))
            os.chmod(os.path.join(tmp, ".git"), 0o775)
            self.assertTrue(keeptrack._own_tree(tmp), "group write is allowed, as git allows it (umask 002)")
            os.chmod(os.path.join(tmp, ".git"), 0o777)
            self.assertFalse(keeptrack._own_tree(tmp), "a .git everyone can write is not trusted")
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
            for d in (clone, os.path.join(clone, ".git")):
                os.chmod(d, 0o775)   # a umask 002 clone (Ubuntu, Fedora) is found too
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
    def test_trailing_dots_and_prefixes(self):
        f = lambda p: keeptrack._local_spelling(p, True)
        for given, want in ((r"C:\repo.\docs ", r"C:\repo\docs"), (r"C:\a\..\b", r"C:\a\..\b"),
                            (r"\\?\C:\repo.\docs", r"C:\repo\docs"), (r"\\?\UNC\host\share\x", r"\\host\share\x"),
                            (r"\\server\share\x.", r"\\server\share\x"),
                            (r"\\server\share.\repo. \docs", r"\\server\share.\repo\docs")):
            self.assertEqual(want, f(given), given)

    def test_spellings_text_cannot_compare_are_refused(self):
        for p in (r"\\127.1\C$\x", r"\\[::1]\c$", r"\\2130706433\C$\repo", r"\\0x7f000001\C$\repo",
                  r"\\0--0-0-0-0-0-0-1.ipv6-literal.net\C$\repo", r"\\otherpc\d$\x", r"\\?\UNC\host\C$\x",
                  r"C:\Users\o\BOARD-~1\docs", r"C:\PROGRA~2\x", r"C:\x\REPORT~1.DOC", r"C:\repo::$INDEX_ALLOCATION\docs", r"C:\repo\docs:alt",
                  r"\\host\share\x::$INDEX_ALLOCATION",
                  r"\\server\share\REPO~1 \docs"):
            self.assertTrue(keeptrack._unverifiable_local(p, True), p)
        for p in (r"C:\Users\o\Docs", r"\\host\share\x", r"\\host\docs$\x", r"C:\a~b\x", r"\\?\C:\x",
                  r"C:\docs\backup~2024", r"C:\docs\notes~1.backup"):
            self.assertFalse(keeptrack._unverifiable_local(p, True), p)

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

"""Kit v115: follow-ups from the v114 reviews. The session-start hook shares the git budget; in a hook no git call
runs past the deadline; a git too slow to place the claim record stops only the commands that use the record."""
import contextlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
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
    def test_release_115_is_consistent(self):
        version = json.loads(read("board/kit/manifest.json"))["version"]
        self.assertEqual(version, 115)
        self.assertEqual(str(version), re.search(r"^KIT_VERSION = (\d+)", read("board/kit/keeptrack.py"), re.M)[1])
        self.assertIn(f"const PAGE_KIT = {version};", read("board/board.js"))
        for plugin in (".claude-plugin", ".codex-plugin", ".cursor-plugin"):
            self.assertEqual(f"0.{version}.0", json.loads(read(f"board/kit/{plugin}/plugin.json"))["version"])
        for version in (114, 115):
            self.assertIn(f"### v{version} (schema 4)", read("board/kit/UPGRADING.md"))
            self.assertIn(f"Kit v{version}:", read("CHANGELOG.md"))
        self.assertNotIn("until 12 s in", read("CHANGELOG.md") + read("board/kit/UPGRADING.md"), "the docs give the real floor")


class HookDeadline(unittest.TestCase):
    def test_no_hook_git_call_runs_past_the_deadline(self):
        start = keeptrack._GIT_START
        for elapsed, floor, want in ((0, 1.0, 5.0), (9, 3.0, 3.0), (12, 1.0, 1.0), (13.5, 3.0, 0.5), (14, 1.0, 0.1),
                                     (30, 3.0, 0.1)):
            with mock.patch.object(keeptrack.time, "monotonic", lambda e=elapsed: start + e), \
                 mock.patch.object(keeptrack, "_GIT_STARTUP", True):
                self.assertAlmostEqual(want, keeptrack._git_timeout(floor), places=3, msg=(elapsed, floor))
        with mock.patch.object(keeptrack.time, "monotonic", lambda: start + 30), \
             mock.patch.object(keeptrack, "_GIT_STARTUP", False):
            self.assertEqual(10.0, keeptrack._git_timeout(keeptrack._GIT_DECIDES), "other commands keep 10 s")

    def test_the_session_start_hook_shares_the_budget(self):
        src = read("board/kit/keeptrack.py")
        self.assertIn('sys.argv[1:3] == ["here", "--hook"]', src)
        self.assertIn('(a.cmd == "here" and getattr(a, "hook", False))', src)
        self.assertIn("here --hook", read("board/kit/hooks/session-start.sh"), "the hook calls it so")
        body = src.split("def _here(a):")[1][:900]
        self.assertIn("_git_toplevel(os.getcwd())", body, "its own rev-parse is bounded")
        self.assertNotIn('subprocess.run(["git", "rev-parse"', body)


class ClaimPlaceUnknown(unittest.TestCase):
    """A slow git over a .git above: the claim record's place is unknown. Only the commands that use it stop."""

    def unsure(self, startup=False):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, ".git"))
            cwd = os.getcwd()
            try:
                os.chdir(tmp)
                with mock.patch.object(keeptrack, "_git_toplevel", lambda f: ("", "hung")), \
                     mock.patch.object(keeptrack, "_GIT_STARTUP", startup):
                    keeptrack._local_dir()   # no stop here: module load goes on
                    return keeptrack._CLAIM_UNSURE
            finally:
                os.chdir(cwd)

    def test_only_the_record_users_stop(self):
        with mock.patch.object(keeptrack, "_CLAIM_UNSURE", ""), mock.patch.object(keeptrack, "FILE", None):
            why = self.unsure()
            self.assertIn("in time", why)
            for use in (keeptrack.claim_record, lambda: keeptrack.record_lock().__enter__(),
                        lambda: keeptrack.ensure_local_dir(keeptrack.CLAIM_FILE)):
                with self.assertRaises(SystemExit) as stop:
                    use()
                self.assertIn("in time", str(stop.exception.code))
            with mock.patch.object(keeptrack, "_GIT_STARTUP", True):
                with self.assertRaises(SystemExit) as stop:
                    keeptrack.cmd_auto_heartbeat(SimpleNamespace())
                self.assertEqual(0, stop.exception.code, "the heartbeat hook stops quietly")
        self.assertEqual("", keeptrack._CLAIM_UNSURE)

    def test_claim_commands_stop_before_they_save(self):
        with mock.patch.object(keeptrack, "_CLAIM_UNSURE", "git did not answer in time"), \
             mock.patch.object(keeptrack, "FILE", None), \
             mock.patch.object(keeptrack, "mutate", side_effect=AssertionError("saved before stopping")), \
             mock.patch.object(keeptrack, "load", side_effect=AssertionError("read before stopping")):
            for cmd in (keeptrack.cmd_claim, keeptrack.cmd_next, keeptrack.cmd_done, keeptrack.cmd_review,
                        keeptrack.cmd_release, keeptrack.cmd_unwait):
                with self.assertRaises(SystemExit) as stop:
                    cmd(SimpleNamespace(id="t_x", note="n", on_behalf_of=None))
                self.assertIn("in time", str(stop.exception.code), cmd.__name__)

    def test_a_known_place_never_stops(self):
        with mock.patch.object(keeptrack, "_CLAIM_UNSURE", ""):
            keeptrack._claim_sure()

    def test_a_file_board_keeps_no_record_and_goes_on(self):
        with mock.patch.object(keeptrack, "_CLAIM_UNSURE", "git did not answer in time"), \
             mock.patch.object(keeptrack, "FILE", "/tmp/copy.json"), \
             mock.patch.object(keeptrack, "_tracked_by_git", side_effect=AssertionError("read a guessed record")):
            keeptrack._claim_sure()
            self.assertIsNone(keeptrack.claim_record(), "a record git did not place is never read")

    def test_hooks_keep_their_git_answers_and_count_the_script_time(self):
        self.assertIn("found=1 && break", read("board/kit/hooks/session-start.sh"), "one 3 s wait at most")
        src = read("board/kit/keeptrack.py")
        self.assertIn('_GIT_DEADLINE = 14.0 - (3.0 if sys.argv[1:3] == ["here", "--hook"] else 0.0)', src)
        self.assertIn("if not _GIT_STARTUP:\n    _TOPLEVEL = None", src, "a hook reuses the load-time answer in _here")
        self.assertIsNone(keeptrack._TOPLEVEL, "outside a hook later questions ask git afresh")

    def test_the_session_start_hook_never_shows_the_board_on_a_guess(self):
        with tempfile.TemporaryDirectory() as home:
            repo = os.path.join(home, "work", "repo")
            os.makedirs(os.path.join(repo, ".git"))
            cwd = os.getcwd()
            try:
                os.chdir(repo)
                for how in ("hung", "error", "missing"):
                    out = io.StringIO()
                    with mock.patch.object(keeptrack, "_git_toplevel", lambda f, how=how: ("", how)), \
                         mock.patch.object(keeptrack, "REPO", "acme/board"), mock.patch.object(keeptrack, "PROJECT_DIR", home), \
                         mock.patch.object(keeptrack, "DEFAULT_PROJECT", ""), \
                         mock.patch.object(keeptrack, "load", side_effect=AssertionError("board read for an unconnected repo")), \
                         contextlib.redirect_stdout(out):
                        keeptrack._here(SimpleNamespace(hook=True))
                    self.assertIn("not connected", out.getvalue(), how)
            finally:
                os.chdir(cwd)

    @unittest.skipIf(os.name == "nt", "a POSIX shell stub stands in for git")
    def test_the_session_start_script_gives_git_three_seconds(self):
        with tempfile.TemporaryDirectory() as tmp:
            bin_dir, proj, plugin = (os.path.join(tmp, d) for d in ("bin", "proj", "plugin"))
            for d in (bin_dir, os.path.join(proj, ".keeptrack"), plugin):
                os.makedirs(d)
            with open(os.path.join(proj, ".keeptrack", "config.json"), "w") as f:
                f.write('{"repo": "o/b"}')
            git = os.path.join(bin_dir, "git")
            with open(git, "w") as f:
                f.write("#!/bin/sh\nexec sleep 60\n")
            os.chmod(git, 0o755)
            with open(os.path.join(plugin, "keeptrack.py"), "w") as f:   # stands in for the real one: say it ran
                f.write("import sys; print('ran', *sys.argv[1:])\n")
            env = {"PATH": bin_dir + os.pathsep + "/usr/bin:/bin", "HOME": tmp, "CLAUDE_PLUGIN_ROOT": plugin}
            began = time.monotonic()
            p = subprocess.run(["sh", os.path.join(KIT, "hooks", "session-start.sh")], cwd=proj, env=env,
                               capture_output=True, text=True, timeout=30)
            took = time.monotonic() - began
            self.assertEqual((0, "ran here --hook"), (p.returncode, p.stdout.strip()), p.stderr)
            self.assertLess(took, 8, "the prefilter stops waiting for git after 3 s; keeptrack.py decides")

    def test_use_stops_on_a_hung_git_and_where_marks_an_unsure_path(self):
        with mock.patch.object(keeptrack, "_git_toplevel", lambda f: ("", "hung")):
            with self.assertRaises(SystemExit) as stop:
                keeptrack.cmd_use(SimpleNamespace(token_env=None, repo="acme/board"))
        self.assertIn("in time", str(stop.exception.code))
        src = read("board/kit/keeptrack.py")
        self.assertIn('(f"  (unsure: {_CLAIM_UNSURE})" if _CLAIM_UNSURE else "")', src)

    @unittest.skipIf(os.name == "nt", "a POSIX shell stub stands in for git")
    def test_a_hung_git_leaves_other_commands_and_the_hook_alone_end_to_end(self):
        with tempfile.TemporaryDirectory() as tmp:
            bin_dir, proj, plugin = (os.path.join(tmp, d) for d in ("bin", "proj", "plugin"))
            for d in (bin_dir, os.path.join(proj, ".git"), plugin):
                os.makedirs(d)
            git = os.path.join(bin_dir, "git")
            with open(git, "w") as f:
                f.write("#!/bin/sh\nexec sleep 60\n")
            os.chmod(git, 0o755)
            shutil.copy(os.path.join(KIT, "keeptrack.py"), os.path.join(plugin, "keeptrack.py"))
            env = {"PATH": bin_dir + os.pathsep + "/usr/bin:/bin", "HOME": tmp, "BOARD_REPO": "acme/board"}

            def run(*args):
                began = time.monotonic()
                p = subprocess.run([sys.executable, os.path.join(plugin, "keeptrack.py"), *args], cwd=proj, env=env,
                                   capture_output=True, text=True, timeout=60)
                return p, time.monotonic() - began

            p, took = run("auto-heartbeat")
            self.assertEqual(0, p.returncode, p.stderr)
            self.assertLess(took, 15, "the hook's git time ends at the deadline")
            p, _ = run("where")   # no claim record needed: it goes on
            self.assertEqual(0, p.returncode, p.stderr)
            self.assertIn("claims:", p.stdout)


if __name__ == "__main__":
    unittest.main()

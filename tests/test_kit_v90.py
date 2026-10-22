"""Kit v90: a folder's own token setting wins over a BOARD_TOKEN inherited from the shell (private-tasks card #286), with
a warning when it replaces a different value; `where` names the variable and the board that won; in a board clone, an
inherited BOARD_REPO that names another board than the clone's git remote is warned about."""
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
KIT = os.path.join(REPO, "board", "kit")
SCRIPT = os.path.join(KIT, "keeptrack.py")
sys.path.insert(0, KIT)
import keeptrack  # noqa: E402


class FolderTokenWins(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.xdg = os.path.join(self.tmp.name, "xdg")
        self._saved_xdg = os.environ.get("XDG_CONFIG_HOME")
        os.environ["XDG_CONFIG_HOME"] = self.xdg   # never touch the real ~/.config/keeptrack/trusted

    def tearDown(self):
        if self._saved_xdg is None:
            os.environ.pop("XDG_CONFIG_HOME", None)
        else:
            os.environ["XDG_CONFIG_HOME"] = self._saved_xdg
        self.tmp.cleanup()

    def folder(self, conf):
        """A project folder with a config `use` would write (trusted on this computer)."""
        d = os.path.join(self.tmp.name, "project")
        os.makedirs(os.path.join(d, ".keeptrack"))
        path = os.path.join(d, ".keeptrack", "config.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(conf, f)
        os.chmod(path, 0o600)
        keeptrack.trust_config(path)
        return d

    def clone(self, remote):
        d = os.path.join(self.tmp.name, "clone")
        subprocess.run(["git", "init", "-q", d], check=True)
        subprocess.run(["git", "-C", d, "remote", "add", "origin", f"https://github.com/{remote}.git"], check=True)
        os.makedirs(os.path.join(d, "board"))
        with open(os.path.join(d, "board", "tasks.json"), "w", encoding="utf-8") as f:
            json.dump({"tasks": []}, f)
        return d

    def env(self, **kw):
        env = {k: v for k, v in os.environ.items() if not k.startswith("BOARD_") and k not in ("KT_V90_TOKEN", "GH_TOKEN", "GITHUB_TOKEN")}
        env["XDG_CONFIG_HOME"] = self.xdg
        env.update(kw)
        return env

    def run_kt(self, cwd, env, *args):
        return subprocess.run([sys.executable, SCRIPT, *args], cwd=cwd, env=env, capture_output=True, text=True, timeout=60)

    def token_in(self, cwd, env):
        """The board token keeptrack ends up with in that folder (a fake value: tests only)."""
        code = f"import sys; sys.path.insert(0, {KIT!r}); import keeptrack; print(keeptrack.token())"
        return subprocess.run([sys.executable, "-c", code], cwd=cwd, env=env, capture_output=True, text=True,
                              timeout=60).stdout.strip()

    @staticmethod
    def line(out, start):
        return next((l for l in out.splitlines() if l.startswith(start)), "")

    def test_the_folder_token_wins_over_the_shell_and_says_so(self):
        d = self.folder({"repo": "o/board", "token_env": "KT_V90_TOKEN"})
        env = self.env(BOARD_TOKEN="shell-value", KT_V90_TOKEN="folder-value")
        self.assertEqual("folder-value", self.token_in(d, env))
        r = self.run_kt(d, env, "where")
        self.assertEqual(0, r.returncode, r.stderr)
        auth = self.line(r.stdout, "auth:")
        self.assertIn("$KT_V90_TOKEN", auth)
        self.assertIn("replaced a different BOARD_TOKEN", auth)
        self.assertIn("warning: $KT_V90_TOKEN", r.stderr)
        self.assertIn("this folder's own setting wins", r.stderr)
        self.assertNotIn("folder-value", r.stdout + r.stderr)   # never prints a token
        self.assertNotIn("shell-value", r.stdout + r.stderr)

    def test_the_same_value_needs_no_warning(self):
        d = self.folder({"repo": "o/board", "token_env": "KT_V90_TOKEN"})
        r = self.run_kt(d, self.env(BOARD_TOKEN="same", KT_V90_TOKEN="same"), "where")
        self.assertNotIn("warning", r.stderr)
        self.assertNotIn("replaced", self.line(r.stdout, "auth:"))
        self.assertIn("$KT_V90_TOKEN", self.line(r.stdout, "auth:"))

    def test_no_shell_token_needs_no_warning(self):
        d = self.folder({"repo": "o/board", "token_env": "KT_V90_TOKEN"})
        env = self.env(KT_V90_TOKEN="folder-value")
        self.assertEqual("folder-value", self.token_in(d, env))
        r = self.run_kt(d, env, "where")
        self.assertNotIn("warning", r.stderr)

    def test_an_unset_folder_variable_falls_back_to_the_shell_token(self):
        d = self.folder({"repo": "o/board", "token_env": "KT_V90_TOKEN"})
        env = self.env(BOARD_TOKEN="shell-value")
        self.assertEqual("shell-value", self.token_in(d, env))
        auth = self.line(self.run_kt(d, env, "where").stdout, "auth:")
        self.assertIn("$BOARD_TOKEN", auth)
        self.assertIn("$KT_V90_TOKEN", auth)
        self.assertIn("NOT set", auth)

    def test_without_a_config_the_shell_token_is_named(self):
        d = os.path.join(self.tmp.name, "plain"); os.makedirs(d)
        env = self.env(BOARD_TOKEN="shell-value", BOARD_REPO="o/board")
        self.assertEqual("shell-value", self.token_in(d, env))
        self.assertIn("$BOARD_TOKEN", self.line(self.run_kt(d, env, "where").stdout, "auth:"))

    def test_an_untrusted_config_never_takes_the_token(self):
        d = os.path.join(self.tmp.name, "download")
        os.makedirs(os.path.join(d, ".keeptrack"))
        with open(os.path.join(d, ".keeptrack", "config.json"), "w", encoding="utf-8") as f:
            json.dump({"repo": "evil/board", "token_env": "KT_V90_TOKEN"}, f)
        env = self.env(BOARD_TOKEN="shell-value", KT_V90_TOKEN="other-value")
        self.assertEqual("shell-value", self.token_in(d, env))

    def test_hooks_stay_silent(self):
        d = self.folder({"repo": "o/board", "token_env": "KT_V90_TOKEN"})
        env = self.env(BOARD_TOKEN="shell-value", KT_V90_TOKEN="folder-value", BOARD_API="http://127.0.0.1:9")
        r = self.run_kt(d, env, "here", "--hook")
        self.assertNotIn("warning:", r.stderr)

    def test_a_shell_board_repo_for_another_board_keeps_the_shell_token(self):
        # Review round 1 (blocking): the board and its token must come from the same place. A shell (a relay worker)
        # that sets BOARD_REPO for another board keeps its own BOARD_TOKEN; the folder's token_env is not used.
        d = self.folder({"repo": "o/board", "token_env": "KT_V90_TOKEN"})
        env = self.env(BOARD_REPO="o/other", BOARD_TOKEN="shell-value", KT_V90_TOKEN="folder-value")
        self.assertEqual("shell-value", self.token_in(d, env))
        r = self.run_kt(d, env, "where")
        self.assertEqual(0, r.returncode, r.stderr)
        self.assertNotIn("warning", r.stderr)
        self.assertIn("o/other", self.line(r.stdout, "board:"))
        auth = self.line(r.stdout, "auth:")
        self.assertIn("$BOARD_TOKEN", auth)
        self.assertIn("$KT_V90_TOKEN", auth)
        self.assertIn("not used", auth)
        self.assertNotIn("folder-value", r.stdout + r.stderr)
        self.assertNotIn("shell-value", r.stdout + r.stderr)

    def test_a_shell_board_repo_for_the_same_board_still_lets_the_folder_token_win(self):
        d = self.folder({"repo": "o/board", "token_env": "KT_V90_TOKEN"})
        env = self.env(BOARD_REPO="O/Board", BOARD_TOKEN="shell-value", KT_V90_TOKEN="folder-value")
        self.assertEqual("folder-value", self.token_in(d, env))

    def test_a_shell_board_repo_for_another_board_without_a_token_does_not_borrow_the_folder_token(self):
        d = self.folder({"repo": "o/board", "token_env": "KT_V90_TOKEN"})
        env = self.env(BOARD_REPO="o/other", KT_V90_TOKEN="folder-value")
        self.assertNotEqual("folder-value", self.token_in(d, env))
        r = self.run_kt(d, env, "where")
        self.assertIn("not used", self.line(r.stdout, "auth:"))

    def test_the_auto_heartbeat_hook_stays_silent(self):
        # Review round 1: auto-heartbeat runs after every tool call and has no --hook flag.
        d = self.folder({"repo": "o/board", "token_env": "KT_V90_TOKEN"})
        env = self.env(BOARD_TOKEN="shell-value", KT_V90_TOKEN="folder-value", BOARD_API="http://127.0.0.1:9")
        r = self.run_kt(d, env, "auto-heartbeat")
        self.assertEqual("", r.stderr)
        c = self.clone("o/board")
        r = self.run_kt(c, self.env(BOARD_REPO="o/other", BOARD_API="http://127.0.0.1:9"), "auto-heartbeat")
        self.assertEqual("", r.stderr)

    def test_where_with_a_local_file_does_not_warn_about_the_clone(self):
        c = self.clone("o/board")
        f = os.path.join(self.tmp.name, "copy.json")
        with open(f, "w", encoding="utf-8") as fh:
            json.dump({"tasks": []}, fh)
        r = self.run_kt(c, self.env(BOARD_REPO="o/other"), "--file", f, "where")
        self.assertEqual(0, r.returncode, r.stderr)
        self.assertNotIn("won over", r.stdout)
        self.assertNotIn("warning", r.stderr)

    def test_an_inherited_board_repo_that_differs_from_the_clone_is_warned_about(self):
        c = self.clone("o/board")
        r = self.run_kt(c, self.env(BOARD_REPO="o/other"), "where")
        self.assertEqual(0, r.returncode, r.stderr)
        self.assertIn("warning: BOARD_REPO=o/other from the shell, but this folder is a clone of o/board", r.stderr)
        self.assertIn("o/other", self.line(r.stdout, "board:"))   # it still decides
        self.assertIn("won over this clone of o/board", r.stdout)

    def test_a_matching_or_absent_board_repo_is_quiet(self):
        c = self.clone("o/board")
        for env in (self.env(BOARD_REPO="O/Board"), self.env()):
            r = self.run_kt(c, env, "where")
            self.assertNotIn("warning", r.stderr)
            self.assertNotIn("won over", r.stdout)
            self.assertIn("o/board", self.line(r.stdout, "board:").lower())

    def test_board_repo_outside_a_clone_is_quiet(self):
        d = os.path.join(self.tmp.name, "code"); os.makedirs(d)
        subprocess.run(["git", "init", "-q", d], check=True)
        r = self.run_kt(d, self.env(BOARD_REPO="o/other"), "where")
        self.assertNotIn("warning", r.stderr)


class Docs(unittest.TestCase):
    def test_kit_is_v90_with_upgrade_notes_and_changelog(self):
        self.assertGreaterEqual(keeptrack.KIT_VERSION, 90)   # the exact version is asserted by the newest tests/test_kit_v*.py
        with open(os.path.join(KIT, "UPGRADING.md"), encoding="utf-8") as f:
            v90 = f.read().split("### v90 (schema 4)", 1)[1].split("### v8", 1)[0]
        for words in ("kit-update", "token_env", "BOARD_REPO", "No migration", "where"):
            self.assertIn(words, v90)
        with open(os.path.join(REPO, "CHANGELOG.md"), encoding="utf-8") as f:
            self.assertIn("Kit v90", f.read())


if __name__ == "__main__":
    unittest.main()

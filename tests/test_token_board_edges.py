"""Regression coverage for token selection and clone mismatch diagnostics."""
import os
import pathlib
import shutil
import subprocess
import sys
from unittest import mock

import test_kit_v90 as v90

KIT = v90.KIT
keeptrack = v90.keeptrack


class TokenBoardEdges(v90.FolderTokenWins):
    def test_folder_token_never_goes_to_another_api_host(self):
        d = self.folder({"repo": "o/board", "token_env": "KT_V90_TOKEN"})
        for api in ("https://github.enterprise/api/v3", "http://127.0.0.1:9", "http://api.github.com", "https://api.github.com:8443"):
            for shell in ("shell-value", ""):
                with self.subTest(api=api, shell=bool(shell)):
                    env = self.env(BOARD_TOKEN=shell, BOARD_API=api, KT_V90_TOKEN="folder-value")
                    self.assertNotEqual("folder-value", self.token_in(d, env))
                    r = self.run_kt(d, env, "where")
                    self.assertIn("not used: BOARD_API", self.line(r.stdout, "auth:"))
                    self.assertNotIn("folder-value", r.stdout + r.stderr)

    def test_explicitly_empty_api_never_borrows_the_folder_token(self):
        d = self.folder({"repo": "o/board", "token_env": "KT_V90_TOKEN"})
        for shell in ("shell-value", ""):
            with self.subTest(shell=bool(shell)):
                env = self.env(BOARD_TOKEN=shell, BOARD_API="", KT_V90_TOKEN="folder-value")
                self.assertEqual(shell, self.token_in(d, env))
                r = self.run_kt(d, env, "where")
                self.assertEqual(0, r.returncode, r.stderr)
                self.assertIn("not used: BOARD_API", self.line(r.stdout, "auth:"))
                self.assertNotIn("folder-value", r.stdout + r.stderr)

    def test_without_a_resolved_board_the_folder_token_is_not_promoted(self):
        d = self.folder({"token_env": "KT_V90_TOKEN"})
        for shell in ("shell-value", ""):
            with self.subTest(shell=bool(shell)):
                env = self.env(BOARD_TOKEN=shell, KT_V90_TOKEN="folder-value")
                self.assertEqual(shell, self.token_in(d, env))
                r = self.run_kt(d, env, "where")
                self.assertIn("(none)", self.line(r.stdout, "board:"))
                self.assertIn("not used", self.line(r.stdout, "auth:"))

    def test_empty_shell_repo_uses_the_resolved_clone_before_selecting_token(self):
        c = self.clone("o/clone")
        cfg = os.path.join(c, ".keeptrack")
        os.makedirs(cfg)
        import json
        p = os.path.join(cfg, "config.json")
        with open(p, "w") as f:
            json.dump({"repo": "o/config", "token_env": "KT_V90_TOKEN"}, f)
        os.chmod(p, 0o600)
        keeptrack.trust_config(p)
        env = self.env(BOARD_REPO="", BOARD_TOKEN="shell-value", KT_V90_TOKEN="folder-value")
        self.assertEqual("shell-value", self.token_in(c, env))
        self.assertIn("o/clone", self.run_kt(c, env, "where").stdout)

    def test_unconnected_clone_is_not_recommended_as_a_target(self):
        c = self.clone("o/unknown")
        r = self.run_kt(c, self.env(BOARD_REPO="o/board"), "where")
        self.assertNotIn("unset board_repo", (r.stdout + r.stderr).lower())
        self.assertIn("connect this clone", r.stdout + r.stderr)

    def test_connected_clone_can_be_recommended(self):
        self.folder({"repo": "o/clone"})
        c = self.clone("o/clone")
        r = self.run_kt(c, self.env(BOARD_REPO="o/other"), "where")
        self.assertIn("unset BOARD_REPO", r.stdout + r.stderr)

    def test_nested_clone_diagnostic_uses_the_scripts_clone(self):
        outer = self.clone("o/outer")
        script = os.path.join(outer, "board", "keeptrack.py")
        shutil.copy(os.path.join(KIT, "keeptrack.py"), script)
        inner = os.path.join(outer, "inner")
        subprocess.run(["git", "init", "-q", inner], check=True)
        subprocess.run(["git", "-C", inner, "remote", "add", "origin", "https://github.com/o/inner.git"], check=True)
        os.makedirs(os.path.join(inner, "board"))
        pathlib.Path(inner, "board", "tasks.json").write_text('{"tasks": []}')
        r = subprocess.run([sys.executable, script, "where"], cwd=inner, env=self.env(BOARD_REPO="o/inner"),
                           capture_output=True, text=True, timeout=10)
        self.assertIn("clone of o/outer", r.stderr)
        self.assertIn("unset BOARD_REPO", r.stdout + r.stderr)
        self.assertNotIn("clone of o/inner", r.stderr)

    def test_hosted_diagnostics_start_no_git_processes(self):
        with mock.patch.object(keeptrack, "BACKEND", "hosted"), mock.patch.object(keeptrack, "SHELL_REPO", "o/board"), \
                mock.patch.object(keeptrack.subprocess, "run") as run:
            self.assertEqual(("", ""), keeptrack._repo_mismatch())
            run.assert_not_called()

    def test_diagnostic_git_budget_and_results_are_cached(self):
        with mock.patch.object(keeptrack, "BACKEND", "github"), mock.patch.object(keeptrack, "SHELL_REPO", "o/board"), \
                mock.patch.object(keeptrack, "ROOT", None), mock.patch.object(keeptrack, "_MISMATCH", None), \
                mock.patch.object(keeptrack.subprocess, "run", side_effect=subprocess.TimeoutExpired("git", 2)) as run:
            self.assertEqual(("", ""), keeptrack._repo_mismatch())
            self.assertEqual(("", ""), keeptrack._repo_mismatch())
            self.assertEqual(1, run.call_count)
            self.assertLessEqual(run.call_args.kwargs["timeout"], 2)

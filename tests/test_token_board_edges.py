"""Regression coverage for token selection and clone mismatch diagnostics."""
import json
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

    def alias_folder(self, alias):
        d = pathlib.Path(self.tmp.name, "alias-" + alias)
        (d / ".keeptrack").mkdir(parents=True)
        p = d / ".keeptrack" / "config.json"
        p.write_text(json.dumps({"repo": "o/board", "token_env": alias}))
        p.chmod(0o600)
        keeptrack.trust_config(str(p))
        return str(d)

    def test_malformed_api_does_not_break_where_or_local_file_commands(self):
        d = self.folder({"repo": "o/board", "token_env": "KT_V90_TOKEN"})
        copy = pathlib.Path(self.tmp.name, "copy.json")
        copy.write_text('{"tasks": []}')
        env = self.env(BOARD_API="https://[broken", KT_V90_TOKEN="folder-value")
        for args in (("where",), ("--file", str(copy), "where")):
            with self.subTest(args=args):
                r = self.run_kt(d, env, *args)
                self.assertEqual(0, r.returncode, r.stderr)
                self.assertIn("not used: BOARD_API", self.line(r.stdout, "auth:"))
                self.assertNotIn("folder-value", r.stdout + r.stderr)

    def test_skipped_global_aliases_do_not_reach_direct_http(self):
        aliases = ("BOARD_TOKEN", "GH_TOKEN", "GITHUB_TOKEN", "GH_ENTERPRISE_TOKEN", "GITHUB_ENTERPRISE_TOKEN")
        for alias in aliases:
            d = self.alias_folder(alias)
            for target in ({"BOARD_REPO": "o/other"}, {"BOARD_API": "https://ghe.example/api/v3"}):
                for shell in ("", "shell-value"):
                    if alias == "BOARD_TOKEN" and shell:
                        continue
                    env = self.env(BOARD_TOKEN=shell, **target)
                    env[alias] = "folder-value"
                    code = """import contextlib, io, sys
sys.path.insert(0, KIT_PATH)
import keeptrack as k
k.shutil.which = lambda command: None
seen = []
def send(req, **kw):
    seen.append(req.get_header('Authorization'))
    return contextlib.nullcontext(io.BytesIO(b'{}'))
k.urllib.request.urlopen = send
try:
    k.gh('repos/o/other')
except SystemExit:
    pass
assert k.token() != 'folder-value'
assert 'Bearer folder-value' not in seen
if k.token():
    assert seen == ['Bearer shell-value']
print('safe')
""".replace("KIT_PATH", repr(KIT))
                    with self.subTest(alias=alias, target=target, shell=bool(shell)):
                        r = subprocess.run([sys.executable, "-c", code], cwd=d, env=env, capture_output=True, text=True)
                        self.assertEqual(0, r.returncode, r.stderr)
                        self.assertEqual("safe", r.stdout.strip())
                        self.assertEqual("folder-value", env[alias], "the calling environment stays unchanged")

    def test_skipped_global_aliases_are_removed_before_gh_children(self):
        aliases = ("BOARD_TOKEN", "GH_TOKEN", "GITHUB_TOKEN", "GH_ENTERPRISE_TOKEN", "GITHUB_ENTERPRISE_TOKEN")
        bindir = pathlib.Path(self.tmp.name, "bin")
        bindir.mkdir()
        gh = bindir / "gh"
        gh.write_text("#!" + sys.executable + "\nimport os\nassert all(os.environ.get(k) != 'folder-value' for k in " + repr(aliases) + ")\nprint('safe-child')\n")
        gh.chmod(0o700)
        for alias in aliases:
            d = self.alias_folder(alias)
            for target in ({"BOARD_REPO": "o/other"}, {"BOARD_API": "https://ghe.example/api/v3"}):
                env = self.env(PATH=str(bindir) + os.pathsep + os.environ["PATH"], **target)
                env[alias] = "folder-value"
                code = f"import sys; sys.path.insert(0, {KIT!r}); import keeptrack as k; rc, out, err = k.gh('repos/o/other'); print(out.strip()); sys.exit(rc)"
                with self.subTest(alias=alias, target=target):
                    r = subprocess.run([sys.executable, "-c", code], cwd=d, env=env, capture_output=True, text=True)
                    self.assertEqual(0, r.returncode, r.stderr)
                    self.assertEqual("safe-child", r.stdout.strip())
                    where = self.run_kt(d, env, "where")
                    self.assertIn("not used", self.line(where.stdout, "auth:"))
                    self.assertNotIn("folder-value", where.stdout + where.stderr)

    def test_matching_legacy_global_aliases_remain_usable(self):
        for alias in ("BOARD_TOKEN", "GH_TOKEN", "GITHUB_TOKEN", "GH_ENTERPRISE_TOKEN", "GITHUB_ENTERPRISE_TOKEN"):
            d = self.alias_folder(alias)
            self.assertEqual("folder-value", self.token_in(d, self.env(**{alias: "folder-value"})))

    def test_use_refuses_automatic_auth_aliases_before_writing_config(self):
        d = pathlib.Path(self.tmp.name, "new-project")
        d.mkdir()
        for alias in ("BOARD_TOKEN", "GH_TOKEN", "GITHUB_TOKEN", "GH_ENTERPRISE_TOKEN", "GITHUB_ENTERPRISE_TOKEN"):
            with self.subTest(alias=alias):
                r = self.run_kt(str(d), self.env(), "use", "o/board", "--branch", "main", "--token-env", alias)
                self.assertNotEqual(0, r.returncode)
                self.assertIn("board-specific", r.stderr)
                self.assertFalse((d / ".keeptrack" / "config.json").exists())

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

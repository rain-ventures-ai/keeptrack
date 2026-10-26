"""Kit v110: docs-home checkout refusal, the card_contact_details setting, the JPEG scan copy, and release consistency."""
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
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
    def test_release_110_is_consistent(self):
        version = json.loads(read("board/kit/manifest.json"))["version"]
        self.assertEqual(version, 110)
        self.assertEqual(str(version), re.search(r"^KIT_VERSION = (\d+)", read("board/kit/keeptrack.py"), re.M)[1])
        self.assertIn(f"const PAGE_KIT = {version};", read("board/board.js"))
        for plugin in (".claude-plugin", ".codex-plugin", ".cursor-plugin"):
            self.assertEqual(f"0.{version}.0", json.loads(read(f"board/kit/{plugin}/plugin.json"))["version"])
        for version in (109, 110):
            self.assertIn(f"### v{version} (schema 4)", read("board/kit/UPGRADING.md"))
            self.assertIn(f"Kit v{version}:", read("CHANGELOG.md"))


class DocsHomeCheckout(unittest.TestCase):
    def test_paths_in_the_board_checkout_are_inside(self):
        with tempfile.TemporaryDirectory() as top, mock.patch.object(keeptrack, "ROOT", top), mock.patch.object(keeptrack, "FILE", None):
            for inside in (top, os.path.join(top, "docs"), os.path.join(top, "docs", "..", "research")):
                self.assertTrue(keeptrack._inside_board_checkout(inside), inside)
            for outside in (os.path.dirname(top), top + "-other", "/", os.path.join(top, "..", "elsewhere")):
                self.assertFalse(keeptrack._inside_board_checkout(outside), outside)
        with mock.patch.object(keeptrack, "ROOT", None), mock.patch.object(keeptrack, "FILE", None):
            self.assertFalse(keeptrack._inside_board_checkout("/anything"))

    def test_the_target_is_never_resolved(self):
        real = os.path.realpath
        seen = []
        with tempfile.TemporaryDirectory() as top, mock.patch.object(keeptrack, "ROOT", top), mock.patch.object(keeptrack, "FILE", None), \
             mock.patch.object(keeptrack.os.path, "realpath", lambda x, *a, **k: seen.append(x) or real(x)):
            keeptrack._inside_board_checkout(r"\\host.example\share\docs")
        self.assertEqual([top], seen, "only the checkout is resolved, never the docs-home path (a UNC host on Windows)")

    def test_a_copy_outside_a_board_repo_refuses_nothing_under_home(self):
        """The ~/.agents (Codex) and plugin layouts: keeptrack.py's parent is not board/, so ROOT is None outside a clone."""
        with tempfile.TemporaryDirectory() as home:
            agents = os.path.join(home, ".agents")
            os.makedirs(agents)
            with open(os.path.join(KIT, "keeptrack.py"), encoding="utf8") as src, open(os.path.join(agents, "keeptrack.py"), "w", encoding="utf8") as dst:
                dst.write(src.read())
            code = ("import sys; sys.argv=['keeptrack.py']; sys.path.insert(0, %r); import keeptrack as k; "
                    "print(k.ROOT, k._inside_board_checkout(%r))") % (agents, os.path.join(home, "Documents", "Keeptrack"))
            env = {kk: v for kk, v in os.environ.items() if not kk.startswith(("BOARD_", "GH_", "GITHUB_"))}
            out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=home, env=dict(env, HOME=home))
            self.assertEqual("None False", out.stdout.strip().splitlines()[-1] if out.stdout.strip() else out.stderr)

    def test_a_file_boards_own_checkout_is_inside(self):
        with tempfile.TemporaryDirectory() as clone:
            subprocess.run(["git", "init", "-q", clone], check=True)
            board = os.path.join(clone, "board", "tasks.json")
            os.makedirs(os.path.dirname(board))
            with mock.patch.object(keeptrack, "ROOT", None), mock.patch.object(keeptrack, "FILE", board):
                self.assertTrue(keeptrack._inside_board_checkout(os.path.join(clone, "notes")))
                self.assertFalse(keeptrack._inside_board_checkout(clone + "-docs"))

    def test_a_board_clone_the_command_runs_in_is_inside_whatever_board_repo_says(self):
        with tempfile.TemporaryDirectory() as clone:
            subprocess.run(["git", "init", "-q", clone], check=True)
            os.makedirs(os.path.join(clone, "board"))
            open(os.path.join(clone, "board", "tasks.json"), "w").close()
            here = os.getcwd()
            try:
                os.chdir(clone)
                with mock.patch.object(keeptrack, "ROOT", None), mock.patch.object(keeptrack, "FILE", None):
                    self.assertTrue(keeptrack._inside_board_checkout(os.path.join(clone, "docs")))
            finally:
                os.chdir(here)

    def test_settings_set_refuses_a_local_root_in_the_checkout_before_any_read(self):
        from types import SimpleNamespace
        a = SimpleNamespace(docs_provider="local", docs_root=os.path.join(keeptrack.ROOT or "/x", "docs"), clear_docs_home=False)
        with mock.patch.object(keeptrack, "ROOT", keeptrack.ROOT or "/x"), \
             mock.patch.object(keeptrack, "load", side_effect=AssertionError("must refuse before loading")):
            with self.assertRaises(SystemExit) as stop:
                keeptrack.cmd_settings_set(a)
        self.assertIn("inside this board repo's checkout", str(stop.exception))

    def test_the_skill_names_the_board_cli_and_the_refusal(self):
        skill = read("board/kit/skills/keeptrack-docs-home/SKILL.md")
        self.assertIn("python3 board/keeptrack.py", skill)
        self.assertIn("board repo's own checkout is always refused", skill)
        names = [c["name"] for c in json.loads(read("board/kit/skills/keeptrack-docs-home/evals/cases.json"))["cases"]]
        self.assertIn("docs-local-root-in-board-checkout", names)


class CardContactDetails(unittest.TestCase):
    PERSON = {"id": "p_1", "name": "Sam", "role": "CTO", "emails": [{"value": "sam@example.com"}], "phones": [{"value": "+1 555 0100"}]}

    def test_on_by_default_and_off_keeps_only_id_name_role(self):
        with mock.patch.object(keeptrack, "person_methods",
                               lambda p, kind: p.get(kind + "s", [])):
            on = keeptrack.contact_snapshot(self.PERSON, {"settings": {}})
            self.assertEqual("sam@example.com", on["email"])
            self.assertEqual("+1 555 0100", on["phone"])
            off = keeptrack.contact_snapshot(self.PERSON, {"settings": {"card_contact_details": False}})
            self.assertEqual({"person_id": "p_1", "name": "Sam", "role": "CTO"}, off)
        self.assertTrue(keeptrack.card_contact_details({}))
        self.assertTrue(keeptrack.card_contact_details({"settings": {"card_contact_details": "no"}}), "only exactly false turns it off")

    def test_the_cli_setting_round_trips_and_task_set_contact_honours_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            board = os.path.join(tmp, "tasks.json")
            person = {"id": "p_sam", "name": "Sam", "role": "CTO", "company": "", "emails": [{"value": "sam@example.com"}],
                      "phones": [{"value": "+1 555 0100"}]}
            task = lambda i, n: {"id": i, "num": n, "title": f"Card {n}", "column": "todo", "comments": [], "todos": [], "history": []}
            with open(board, "w", encoding="utf8") as f:
                json.dump({"version": 2, "columns": [{"id": "todo", "name": "To do"}], "tasks": [task("t_a", 1), task("t_b", 2)],
                           "people": [{"github": "alex", "name": "Alex"}], "contacts": [person], "settings": {}}, f)
            env = {k: v for k, v in os.environ.items() if not k.startswith(("BOARD_", "GH_", "GITHUB_"))}
            env.update(BOARD_USER="alex", HOME=tmp)
            run = lambda *args: subprocess.run([sys.executable, os.path.join(KIT, "keeptrack.py"), "--file", board, *args],
                                               capture_output=True, text=True, env=env)
            def card(i):
                with open(board, encoding="utf8") as f:
                    return next(t for t in json.load(f)["tasks"] if t["id"] == i)
            self.assertIn("card_contact_details: on", run("settings").stdout)
            p = run("task-set", "#1", "--contact", "Sam")
            self.assertEqual(0, p.returncode, p.stderr)
            self.assertEqual("sam@example.com", card("t_a")["contacts"][0]["email"])
            p = run("settings-set", "--card-contact-details", "off")
            self.assertEqual(0, p.returncode, p.stderr)
            self.assertIn("card_contact_details: off", run("settings").stdout)
            with open(board, encoding="utf8") as f:
                st = json.load(f)["settings"]
            self.assertIs(False, st["card_contact_details"])
            self.assertEqual(110, st["min_kit"], "older writers, which would still copy the details, stop writing")
            p = run("task-set", "#2", "--contact", "Sam")
            self.assertEqual(0, p.returncode, p.stderr)
            self.assertEqual({"person_id": "p_sam", "name": "Sam", "role": "CTO"}, card("t_b")["contacts"][0])
            self.assertEqual("sam@example.com", card("t_a")["contacts"][0]["email"], "existing cards are not rewritten")

    def test_min_kit_needed_counts_the_setting(self):
        self.assertEqual(110, keeptrack.min_kit_needed({"settings": {"card_contact_details": False}})[0])
        self.assertEqual(0, keeptrack.min_kit_needed({"settings": {"card_contact_details": True}})[0])

    def test_the_web_board_uses_the_same_rule(self):
        js = read("board/board.js")
        self.assertIn("card_contact_details !== false", js)
        self.assertEqual(2, js.count("contactSnapshot(") - 1, "both snapshot writers use the shared helper")


class JpegScanCopy(unittest.TestCase):
    def test_a_large_scan_copies_byte_for_byte_in_few_loop_steps(self):
        scan = bytes(range(256)) * 8000 + b"\xff\x00" + b"\x10" * 100000 + b"\xff\xd3" + b"\x20" * 1000   # ~2 MB, 8000 0xFF 0x00 stuffing pairs
        sos = b"\xff\xda\x00\x08\x01\x01\x00\x00\x3f\x00"
        blob = b"\xff\xd8" + sos + scan + b"\xff\xd9"
        steps = [0]
        code = keeptrack.strip_image_metadata.__code__
        def tracer(frame, event, arg):
            if frame.f_code is not code:
                return None
            def local(frame, event, arg):
                if event == "line":
                    steps[0] += 1
                return local
            return local
        sys.settrace(tracer)
        try:
            out = keeptrack.strip_image_metadata(blob, "jpg")
        finally:
            sys.settrace(None)
        self.assertIn(scan, out)
        self.assertTrue(out.endswith(b"\xff\xd9"))
        # about a dozen lines per 0xFF byte; a byte-at-a-time copy would run millions of lines on 2 MB
        self.assertLess(steps[0], 200_000, f"{steps[0]} lines: the scan copy must jump between 0xFF bytes with find")


if __name__ == "__main__":
    unittest.main()

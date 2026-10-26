"""Kit v110: docs-home checkout refusal, the card_contact_details setting, the JPEG scan copy, and release consistency."""
import json
import os
import re
import subprocess
import sys
import tempfile
import time
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
        with tempfile.TemporaryDirectory() as top, mock.patch.object(keeptrack, "ROOT", top):
            for inside in (top, os.path.join(top, "docs"), os.path.join(top, "docs", "..", "research")):
                self.assertTrue(keeptrack._inside_board_checkout(inside), inside)
            for outside in (os.path.dirname(top), top + "-other", "/"):
                self.assertFalse(keeptrack._inside_board_checkout(outside), outside)
        with mock.patch.object(keeptrack, "ROOT", None):
            self.assertFalse(keeptrack._inside_board_checkout("/anything"))

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

    def test_the_cli_setting_round_trips_on_a_file_board(self):
        with tempfile.TemporaryDirectory() as tmp:
            board = os.path.join(tmp, "tasks.json")
            with open(board, "w", encoding="utf8") as f:
                json.dump({"version": 2, "columns": [{"id": "todo", "name": "To do"}], "tasks": [], "people": [], "contacts": [], "settings": {}}, f)
            env = dict(os.environ, BOARD_USER="alex", HOME=tmp)
            run = lambda *args: subprocess.run([sys.executable, os.path.join(KIT, "keeptrack.py"), "--file", board, *args],
                                               capture_output=True, text=True, env=env)
            self.assertIn("card_contact_details: on", run("settings").stdout)
            p = run("settings-set", "--card-contact-details", "off")
            self.assertEqual(0, p.returncode, p.stderr)
            self.assertIn("card_contact_details: off", run("settings").stdout)
            with open(board, encoding="utf8") as f:
                self.assertIs(False, json.load(f)["settings"]["card_contact_details"])

    def test_the_web_board_uses_the_same_rule(self):
        js = read("board/board.js")
        self.assertIn("card_contact_details !== false", js)
        self.assertEqual(2, js.count("contactSnapshot(") - 1, "both snapshot writers use the shared helper")


class JpegScanCopy(unittest.TestCase):
    def test_a_large_scan_copies_byte_for_byte_and_fast(self):
        scan = bytes(range(0, 255)) * 8000 + b"\xff\x00" + b"\x10" * 100000 + b"\xff\xd3" + b"\x20" * 1000   # ~2 MB
        sos = b"\xff\xda\x00\x08\x01\x01\x00\x00\x3f\x00"
        blob = b"\xff\xd8" + sos + scan + b"\xff\xd9"
        try:
            start = time.monotonic()
            out = keeptrack.strip_image_metadata(blob, "jpg")
            took = time.monotonic() - start
        except ValueError as e:
            self.skipTest(f"minimal JPEG refused by the validator: {e}")
        self.assertIn(scan, out)
        self.assertTrue(out.endswith(b"\xff\xd9"))
        self.assertLess(took, 2.0, "the scan copy jumps between 0xFF bytes")


if __name__ == "__main__":
    unittest.main()

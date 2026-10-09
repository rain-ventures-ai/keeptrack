"""Older tools must not delete data written by newer schema or kit versions."""
import contextlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
from board_fixtures import FIXTURES, copy_board_fixture
KIT = os.path.join(REPO, "board", "kit")
LEGACY_KIT_REF = "400c9bc:board/kit/keeptrack.py"

spec = importlib.util.spec_from_file_location("keeptrack", os.path.join(KIT, "keeptrack.py"))
kt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(kt)


class Args:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def load_legacy_keeptrack():
    src = subprocess.check_output(["git", "show", LEGACY_KIT_REF], cwd=REPO, text=True)
    path = os.path.join(tempfile.gettempdir(), "keeptrack-v16-test.py")
    with open(path, "w", encoding="utf-8") as f:
        f.write(src)
    spec = importlib.util.spec_from_file_location("keeptrack_v16", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def project_files(board_dir):
    proj = os.path.join(board_dir, "projects")
    if not os.path.isdir(proj):
        return []
    return sorted(f for f in os.listdir(proj) if f.endswith(".json"))


class MixedVersions(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.board_dir = os.path.join(self.temp.name, "board")
        copy_board_fixture("v4_kit17", self.board_dir)
        self.saved = {k: getattr(kt, k) for k in ("FILE", "ROOT", "REPO", "BRANCH", "WRITE")}

    def tearDown(self):
        for k, v in self.saved.items():
            setattr(kt, k, v)
        self.temp.cleanup()

    def test_current_kit_reads_pre_projects_split_fixture(self):
        shutil.rmtree(self.board_dir)
        copy_board_fixture("v4", self.board_dir)
        kt.FILE = os.path.join(self.board_dir, "tasks.json")
        data = kt.load_board()
        self.assertEqual(2, len(data["tasks"]))
        self.assertEqual(1, len(data["contacts"]))
        self.assertEqual([], data.get("projects") or [])

    def test_v16_keeptrack_ignores_projects_but_preserves_files_on_save(self):
        legacy = load_legacy_keeptrack()
        legacy.FILE = os.path.join(self.board_dir, "tasks.json")
        before = project_files(self.board_dir)
        self.assertEqual(["pr_pilot01ab.json"], before)
        data = legacy.load_board()
        self.assertEqual(0, len(data.get("projects") or []))
        self.assertEqual(2, len(data["tasks"]))

        def touch(data):
            data["tasks"][0]["comments"].append(
                {"id": "c_legacy", "at": "2026-10-09T12:00:00.000Z", "by": "alex", "text": "legacy kit save"}
            )

        legacy.mutate(touch, "Comment from legacy kit")
        self.assertEqual(before, project_files(self.board_dir))
        proj = json.load(open(os.path.join(self.board_dir, "projects", "pr_pilot01ab.json"), encoding="utf-8"))
        self.assertEqual("Pilot rollout", proj["name"])

    def test_v17_kit_reads_projects_after_v16_noop_round_trip(self):
        legacy = load_legacy_keeptrack()
        legacy.FILE = os.path.join(self.board_dir, "tasks.json")

        def noop(data):
            data["settings"]["title"] = data["settings"].get("title") or "Fixture"

        with contextlib.redirect_stdout(io.StringIO()):
            legacy.mutate(noop, "Touch settings")
        kt.FILE = os.path.join(self.board_dir, "tasks.json")
        data = kt.load_board()
        self.assertEqual(1, len(data["projects"]))
        self.assertEqual("pr_pilot01ab", data["tasks"][0].get("project"))


if __name__ == "__main__":
    unittest.main()

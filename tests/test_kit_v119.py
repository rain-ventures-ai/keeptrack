"""Kit v119: release --watch frees the claim then polls the card (handoff without locking)."""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
KIT = os.path.join(ROOT, "board", "kit")
KT = os.path.join(KIT, "keeptrack.py")
sys.path.insert(0, KIT)
import keeptrack  # noqa: E402


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


class Release(unittest.TestCase):
    def test_release_119_is_consistent(self):
        version = json.loads(read("board", "kit", "manifest.json"))["version"]
        self.assertEqual(version, 119)
        self.assertEqual(str(version), re.search(r"^KIT_VERSION = (\d+)", read("board", "kit", "keeptrack.py"), re.M)[1])
        self.assertIn(f"const PAGE_KIT = {version};", read("board", "board.js"))
        for plugin in (".claude-plugin", ".codex-plugin", ".cursor-plugin"):
            self.assertEqual(f"0.{version}.0", json.loads(read("board", "kit", plugin, "plugin.json"))["version"], plugin)
        self.assertIn("### v119 (schema 4)", read("board", "kit", "UPGRADING.md"))
        self.assertIn("Kit v119:", read("CHANGELOG.md"))
        self.assertIn("release --watch", read("board", "kit", "repo-skills", "board", "SKILL.md"))
        self.assertIn("release <id> --column todo --watch", read("board", "kit", "templates", "AGENTS.md"))
        self.assertIn("--watch", read("board", "kit", "keeptrack.py"))


class ReleaseWatch(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.board = os.path.join(self.tmp.name, "board")
        shutil.copytree(os.path.join(HERE, "fixtures", "v4"), self.board)
        self.env = dict(os.environ, BOARD_USER="alex", HOME=self.tmp.name, BOARD_REPO="acme/board",
                        BOARD_BRANCH="main", BOARD_AGENT="claude", BOARD_SESSION="sess-a")
        for k in ("BOARD_TOKEN", "GH_TOKEN", "GITHUB_TOKEN"):
            self.env.pop(k, None)
        self.file = os.path.join(self.board, "tasks.json")

    def tearDown(self):
        self.tmp.cleanup()

    def kt(self, *args, ok=True, **env):
        p = subprocess.run([sys.executable, KT, "--file", self.file, *args],
                           capture_output=True, text=True, env=dict(self.env, **env))
        if ok and p.returncode:
            self.fail(f"{args} exited {p.returncode}: {p.stdout}{p.stderr}")
        return p

    def card(self, name="t_first.json"):
        with open(os.path.join(self.board, "cards", name), encoding="utf-8") as f:
            return json.load(f)

    def test_watch_flags_need_watch(self):
        self.kt("claim", "#1", "--note", "start")
        p = self.kt("release", "#1", "--timeout", "1", ok=False)
        self.assertNotEqual(0, p.returncode)
        self.assertIn("--watch", p.stderr)

    def test_release_watch_clears_claim_then_wakes_on_handoff_claim(self):
        self.kt("claim", "#1", "--note", "start")
        self.assertIsNotNone(self.card().get("claim"))
        proc = subprocess.Popen(
            [sys.executable, KT, "--file", self.file, "release", "#1", "--column", "todo",
             "--watch", "--every", "0.2", "--timeout", "5", "--json"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=self.env)
        err_chunks, out_chunks = [], []

        def drain(pipe, sink):
            sink.extend(pipe)

        threads = [threading.Thread(target=drain, args=(proc.stderr, err_chunks), daemon=True),
                   threading.Thread(target=drain, args=(proc.stdout, out_chunks), daemon=True)]
        for t in threads:
            t.start()
        end = time.time() + 8
        while time.time() < end:
            if "watching" in "".join(err_chunks):
                break
            if proc.poll() is not None:
                self.fail(f"release --watch exited early {proc.returncode}: {''.join(err_chunks)} {''.join(out_chunks)}")
            time.sleep(0.02)
        else:
            proc.kill()
            self.fail("release --watch never started watching: " + "".join(err_chunks))
        self.assertIsNone(self.card().get("claim"), "claim must be gone before/while watching")
        # another session can claim while we watch; that claim is a change that wakes the watcher
        self.kt("claim", "#1", "--note", "handoff", BOARD_SESSION="sess-b")
        self.assertEqual("sess-b", (self.card().get("claim") or {}).get("session_id"))
        code = proc.wait(timeout=5)
        for t in threads:
            t.join(timeout=1)
        proc.stdout.close()
        proc.stderr.close()
        out, err = "".join(out_chunks), "".join(err_chunks)
        self.assertEqual(0, code, err)
        self.assertIn("released", out)
        row = json.loads(out.strip().splitlines()[-1])
        self.assertEqual(1, row["num"])
        self.assertTrue(any("claim" in c for c in row["changes"]), row)


if __name__ == "__main__":
    unittest.main()

"""keeptrack.py watch: poll until a card changes, or until it reaches a column. A heartbeat alone does not count."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
KT = os.path.join(HERE, "..", "board", "kit", "keeptrack.py")


class WatchCli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.board = os.path.join(self.tmp.name, "board")
        shutil.copytree(os.path.join(HERE, "fixtures", "v4"), self.board)
        self.env = dict(os.environ, BOARD_USER="alex", HOME=self.tmp.name, BOARD_REPO="acme/board", BOARD_BRANCH="main")
        for k in ("BOARD_TOKEN", "GH_TOKEN", "GITHUB_TOKEN", "BOARD_AGENT"):
            self.env.pop(k, None)
        self.file = os.path.join(self.board, "tasks.json")

    def tearDown(self):
        self.tmp.cleanup()

    def kt(self, *args, ok=True):
        p = subprocess.run([sys.executable, KT, "--file", self.file, *args], capture_output=True, text=True, env=self.env)
        if ok and p.returncode:
            self.fail(f"{args} exited {p.returncode}: {p.stdout}{p.stderr}")
        return p

    def watch(self, *args):
        p = subprocess.Popen([sys.executable, KT, "--file", self.file, "watch", *args],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=self.env)
        p.out, p.err, p.threads = [], [], []
        for pipe, sink in ((p.stdout, p.out), (p.stderr, p.err)):
            t = threading.Thread(target=lambda pipe=pipe, sink=sink: sink.extend(pipe), daemon=True)
            t.start()
            p.threads.append(t)
        return p

    def wait_watching(self, p, timeout=8):
        end = time.time() + timeout
        while time.time() < end:
            if "watching" in "".join(p.err):
                return
            if p.poll() is not None:
                time.sleep(0.05)
                self.fail(f"watch exited {p.returncode} before it was watching: {''.join(p.err)} {''.join(p.out)}")
            time.sleep(0.02)
        self.fail("watch never started: " + "".join(p.err))

    def collect(self, p, timeout=4):
        code = p.wait(timeout=timeout)
        for t in p.threads:
            t.join(timeout=1)
        p.stdout.close()
        p.stderr.close()
        return code, "".join(p.out), "".join(p.err)

    def finish(self, p, timeout=4):
        code, out, err = self.collect(p, timeout)
        self.assertEqual(0, code, err)
        return out, err

    def card_path(self, name):
        return os.path.join(self.board, "cards", name)

    def test_a_comment_wakes_the_watch_and_a_timeout_does_not(self):
        p = self.watch("#1", "--every", "0.2", "--timeout", "3", "--json")
        self.wait_watching(p)
        self.kt("comment", "#1", "Shipped the notes")
        out, err = self.finish(p)
        row = json.loads(out)
        self.assertEqual(1, row["num"])
        self.assertTrue(any(c.startswith("comment:") for c in row["changes"]), row)
        self.assertIn("watching #1", err)

        quiet = self.watch("#2", "--every", "0.2", "--timeout", "0.5")
        code, out, err = self.collect(quiet, 3)
        self.assertEqual(2, code)
        self.assertEqual("", out.strip())
        self.assertIn("timed out", err)

    def test_a_heartbeat_alone_does_not_count(self):
        path = self.card_path("t_first.json")
        with open(path, encoding="utf-8") as f:
            card = json.loads(f.read())
        card["claim"] = {"agent": "codex", "status": "running", "note": "", "heartbeat_at": "2026-10-01T08:00:00.000Z"}
        card["updated"] = "2026-10-01T08:00:00.000Z"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(card, f)
        p = self.watch("#1", "--every", "0.2", "--timeout", "0.7")
        self.wait_watching(p)
        card["claim"]["heartbeat_at"] = "2026-10-23T12:00:00.000Z"
        card["updated"] = "2026-10-23T12:00:00.000Z"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(card, f)
        code, out, err = self.collect(p, 3)
        self.assertEqual(2, code, out)
        self.assertIn("timed out", err)

    def test_until_done_ignores_a_comment_and_reports_the_move(self):
        self.kt("move", "#2", "--column", "done")
        already = self.watch("#2", "--until", "done", "--every", "0.2", "--timeout", "2")
        out, err = self.finish(already, 3)
        self.assertIn("#2", out)
        self.assertIn("already done", out)
        self.assertNotIn("watching", err)

        p = self.watch("#1", "--until", "done", "--every", "0.2", "--timeout", "3")
        self.wait_watching(p)
        self.kt("comment", "#1", "still working")
        time.sleep(0.45)
        self.assertIsNone(p.poll(), "a comment is not Done")
        self.kt("move", "#1", "--column", "done")
        out, err = self.finish(p)
        self.assertIn("column todo -> done", out)

    def test_all_waits_until_every_card_is_done(self):
        p = self.watch("#1", "#2", "--until", "done", "--all", "--every", "0.2", "--timeout", "3", "--json")
        self.wait_watching(p)
        self.kt("move", "#1", "--column", "done")
        time.sleep(0.45)
        self.assertIsNone(p.poll(), "one Done card does not finish --all")
        self.kt("move", "#2", "--column", "done")
        out, err = self.finish(p)
        rows = json.loads(out)
        self.assertEqual([1, 2], sorted(r["num"] for r in rows))

    def test_a_card_that_leaves_the_board_is_reported(self):
        p = self.watch("#2", "--every", "0.2", "--timeout", "2")
        self.wait_watching(p)
        os.remove(self.card_path("t_second.json"))
        out, err = self.finish(p)
        self.assertIn("left the board", out)

    def test_bad_arguments_are_refused(self):
        for args in (["#1", "#1"], ["#1", "--until", "nowhere"], ["#1", "--all"], ["#99"]):
            p = self.kt("watch", *args, "--timeout", "1", ok=False)
            self.assertNotEqual(0, p.returncode, args)
            self.assertNotIn("watching", p.stderr)


if __name__ == "__main__":
    unittest.main()

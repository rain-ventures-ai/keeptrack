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


    def test_a_github_board_is_polled_at_most_every_ten_seconds(self):
        p = subprocess.run([sys.executable, KT, "watch", "#1", "--every", "1"], capture_output=True, text=True, env=self.env)
        self.assertNotEqual(0, p.returncode)
        self.assertIn("between 10 and 3600", p.stderr)

    def test_nan_and_infinite_values_are_refused(self):
        for args in (["--timeout", "nan"], ["--timeout", "inf"], ["--every", "nan"], ["--every", "inf"]):
            p = self.kt("watch", "#1", *args, ok=False)
            self.assertNotEqual(0, p.returncode, args)
            self.assertNotIn("watching", p.stderr, args)


KIT = os.path.join(HERE, "..", "board", "kit")
if KIT not in sys.path:
    sys.path.insert(0, KIT)
import keeptrack  # noqa: E402


class WatchApiBudget(unittest.TestCase):
    """In process: a fake clock, a fake board and a fake branch head. No network."""
    def setUp(self):
        self.k = keeptrack
        self.board = {"columns": [{"id": "todo"}, {"id": "done"}],
                      "tasks": [{"id": "t_a", "num": 1, "title": "A", "column": "todo", "comments": [], "todos": []}]}
        self.loads = 0

        class Clock:
            now = 0.0
            def monotonic(self): return Clock.now
            def sleep(self, s): Clock.now += s
        self.clock = Clock()

    def run_watch(self, polled, loaded="sha-1", timeout=None):
        """polled: what each cheap head read returns (the last value repeats); loaded: the head each load() reads."""
        k, polled = self.k, list(polled)
        def load():
            self.loads += 1
            return json.loads(json.dumps(self.board)), None
        def watch_head():
            return polled.pop(0) if len(polled) > 1 else polled[0]
        def loaded_head(_data):
            return loaded(self.loads) if callable(loaded) else loaded
        from types import SimpleNamespace
        from unittest import mock
        a = SimpleNamespace(ids=["#1"], every=15, timeout=timeout, until=None, all=False, json=False)
        with mock.patch.object(k, "FILE", None), mock.patch.object(k, "load", load), \
             mock.patch.object(k, "_watch_head", watch_head), mock.patch.object(k, "_loaded_head", loaded_head), \
             mock.patch.object(k, "time", self.clock), mock.patch("sys.stderr"):
            with self.assertRaises(SystemExit) as stop:
                k.cmd_watch(a)
        return stop.exception.code

    def test_an_unchanged_head_never_reloads_and_the_default_timeout_ends_the_watch(self):
        self.assertEqual(2, self.run_watch(["sha-1"]))
        self.assertEqual(1, self.loads, "only the first read loads the board")
        self.assertAlmostEqual(self.k.WATCH_TIMEOUT, self.clock.now, delta=15)

    def test_a_new_head_reloads_the_board_once(self):
        self.assertEqual(2, self.run_watch(["sha-1", "sha-2"], loaded=lambda n: "sha-1" if n == 1 else "sha-2", timeout=100))
        self.assertEqual(2, self.loads, "one reload after the head moved; the reload's own head is kept")

    def test_a_failed_head_read_skips_the_poll_instead_of_reloading(self):
        self.assertEqual(2, self.run_watch([None, None, "sha-1"], timeout=100))
        self.assertEqual(1, self.loads, "two failures, then the same head: no reload")

    def test_failed_head_reads_in_a_row_reload_the_board_so_a_lasting_error_shows(self):
        self.assertEqual(2, self.run_watch([None], timeout=100))
        self.assertEqual(1 + 2, self.loads, "seven polls in 100 s: a reload after the 3rd and the 6th failed read")
        self.loads = 0
        self.assertEqual(2, self.run_watch([None, None, "sha-1", None, None, "sha-1"], timeout=100))
        self.assertEqual(1, self.loads, "a good read resets the count")

    def test_a_board_without_a_cheap_head_reloads_every_poll(self):
        self.assertEqual(2, self.run_watch(["unused"], loaded=None, timeout=60))
        self.assertEqual(1 + 4, self.loads)


class WatchHead(unittest.TestCase):
    """_watch_head reads one ref, or gives None (never raises) so the watch skips or reloads."""
    def head(self, **patch):
        from unittest import mock
        base = {"FILE": None, "BACKEND": "github", "WRITE": "api", "REPO": "acme/board", "BRANCH": "main"}
        base.update(patch.pop("env", {}))
        base.update(patch)
        with mock.patch.multiple(keeptrack, **base):
            return keeptrack._watch_head()

    def run_cli(self, result, **env):
        """Patch subprocess.run: the git ls-remote (WRITE git) or gh api (no BOARD_TOKEN) head read."""
        from unittest import mock
        calls = []
        def run(cmd, **kw):
            calls.append((cmd, kw))
            if isinstance(result, BaseException):
                raise result
            return subprocess.CompletedProcess(cmd, result[0], result[1], "")
        with mock.patch.object(keeptrack.subprocess, "run", run), mock.patch.object(keeptrack, "use_http", lambda: False):
            got = self.head(env=env)
        return got, calls

    def run_git(self, result):
        return self.run_cli(result, WRITE="git", ROOT="/repo")

    def api(self, result):
        from unittest import mock
        with mock.patch.object(keeptrack, "use_http", lambda: True):
            return self.head(http=result if callable(result) else lambda *a, **k: result)

    def test_api_and_git_reads(self):
        self.assertEqual("abc", self.api((0, '{"object": {"sha": "abc"}}', "")))
        got, calls = self.run_cli((0, '{"object": {"sha": "cli"}}'))
        self.assertEqual("cli", got)
        cmd, kw = calls[0]
        self.assertEqual(["gh", "api", "repos/acme/board/git/ref/heads/main"], cmd)
        self.assertEqual(subprocess.DEVNULL, kw["stdin"])
        self.assertEqual(keeptrack.WATCH_HEAD_TIMEOUT, kw["timeout"])
        self.assertEqual(1, len(calls), "a failed probe is not retried")
        got, calls = self.run_git((0, "def\trefs/heads/main\n"))
        self.assertEqual("def", got)
        cmd, kw = calls[0]
        self.assertEqual(["git", "-C", "/repo", "ls-remote", "origin", "refs/heads/main"], cmd)
        self.assertEqual(subprocess.DEVNULL, kw["stdin"])
        self.assertEqual(keeptrack.WATCH_HEAD_TIMEOUT, kw["timeout"])
        self.assertEqual("0", kw["env"]["GIT_TERMINAL_PROMPT"])

    def test_a_hung_git_or_gh_head_read_gives_none(self):
        self.assertIsNone(self.run_git(subprocess.TimeoutExpired(["git"], 30))[0])
        self.assertIsNone(self.run_git((128, ""))[0])
        self.assertIsNone(self.run_cli(subprocess.TimeoutExpired(["gh"], 30))[0])
        got, calls = self.run_cli((1, ""))
        self.assertIsNone(got)
        self.assertEqual(1, len(calls))

    def test_the_loaded_head_frees_the_load_state(self):
        from unittest import mock
        board = {}
        keeptrack._BOARD_STATES[id(board)] = {"head": "sha-9", "files": {"cards/a.json": "{}"}}
        with mock.patch.multiple(keeptrack, FILE=None, BACKEND="github"):
            self.assertEqual("sha-9", keeptrack._loaded_head(board))
        self.assertNotIn(id(board), keeptrack._BOARD_STATES, "a long watch must not keep every reloaded board")

    def test_failures_and_boards_without_a_cheap_head_give_none(self):
        boom = lambda *a, **k: (_ for _ in ()).throw(SystemExit("rate limited"))
        self.assertIsNone(self.api((1, "", "HTTP 429")))
        self.assertIsNone(self.api((0, "not json", "")))
        self.assertIsNone(self.api(boom))
        self.assertIsNone(self.head(env={"FILE": "/tmp/board.json"}, http=boom))
        self.assertIsNone(self.head(env={"BACKEND": "hosted"}, http=boom))

if __name__ == "__main__":
    unittest.main()

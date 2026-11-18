"""Kit v137 (card #259): a routine register's last_run records run usage, or plainly that it is not known."""
import base64
import contextlib
import io
import json
import os
import re
import tempfile
import unittest
from unittest.mock import patch

from test_keeptrack import Args, kt

ROOT = os.path.dirname(os.path.dirname(__file__))


def read(path):
    with open(os.path.join(ROOT, path), encoding="utf8") as stream:
        return stream.read()


class Release(unittest.TestCase):
    def test_release_137_is_consistent(self):
        version = json.loads(read("board/kit/manifest.json"))["version"]
        self.assertGreaterEqual(version, 137)
        self.assertEqual(str(version), re.search(r"^KIT_VERSION = (\d+)", read("board/kit/keeptrack.py"), re.M)[1])
        self.assertIn(f"const PAGE_KIT = {version};", read("board/board.js"))
        for plugin in (".claude-plugin", ".codex-plugin", ".cursor-plugin"):
            self.assertEqual(f"0.{version}.0", json.loads(read(f"board/kit/{plugin}/plugin.json"))["version"])
        self.assertIn("### v137 (schema 4)", read("board/kit/UPGRADING.md"))
        self.assertIn("Kit v137", read("CHANGELOG.md"))
        self.assertIn("--usage engine=", read("board/kit/automation-loader.md"))
        self.assertIn("Run usage (kit v137)", read("board/kit/ROUTINES.md"))


class RoutineUsage(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.saved = {k: getattr(kt, k) for k in ("ROOT", "FILE", "default_user", "gh", "REPO", "BRANCH", "PATH")}
        kt.ROOT = self.tmp.name
        kt.FILE = os.path.join(self.tmp.name, "board", "tasks.json")
        kt.default_user = lambda: "osouthgate"
        self.path = os.path.join(kt.ROOT, "automation", "routines", "auto-x-osouthgate.json")
        os.makedirs(os.path.dirname(self.path))
        self.save({"version": 1, "id": "auto-x-osouthgate", "owner": "osouthgate", "last_successful_run_at": None, "runs": []})

    def tearDown(self):
        for k, v in self.saved.items():
            setattr(kt, k, v)
        self.tmp.cleanup()

    def save(self, doc):
        with open(self.path, "w", encoding="utf8") as f:
            json.dump(doc, f)

    def doc(self):
        with open(self.path, encoding="utf8") as f:
            return json.load(f)

    def args(self, kw):
        for k, v in (("id", "auto-x-osouthgate"), ("summary", None), ("count", []), ("usage", []), ("run_id", None),
                     ("status", None), ("since", None), ("push", False)):
            kw.setdefault(k, v)
        return kw

    def run_(self, **kw):
        kw = self.args(kw)
        with contextlib.redirect_stdout(io.StringIO()):
            kt.cmd_routine(Args(**kw))

    def refused(self, **kw):
        kw = self.args(kw)
        with self.assertRaises(SystemExit) as cm, contextlib.redirect_stdout(io.StringIO()):
            kt.cmd_routine(Args(**kw))
        return str(cm.exception.code)

    def one_run(self, run_id="r1", usage=None):
        self.run_(action="start", run_id=run_id)
        self.run_(action="finish", run_id=run_id, status="success", count=["proposals_added=1"], usage=usage or [])

    def test_finish_without_usage_says_unknown_plainly(self):
        self.one_run()
        doc = self.doc()
        self.assertEqual({"engine": "unknown", "known": False}, doc["last_run"]["usage"])
        self.assertEqual(doc["last_run"], doc["runs"][-1])

    def test_finish_records_given_usage_tokens_only(self):
        self.one_run(usage=["engine=claude", "in=10", "out=45", "cache_read=2000", "cache_write=300", "turns=7"])
        self.assertEqual({"engine": "claude", "known": True, "in": 10, "out": 45, "cache_read": 2000, "cache_write": 300,
                          "turns": 7}, self.doc()["last_run"]["usage"])
        self.run_(action="start", run_id="r2")
        for bad, why in ((["cost_usd=0.42"], "money"), (["in=-1"], "whole number"), (["engine=Claude Code"], "lower-case"),
                         (["tokens=5"], "unknown key"), (["in"], "KEY=VALUE"), (["in=1", "in=2"], "twice")):
            with self.subTest(bad=bad):
                self.assertIn(why, self.refused(action="finish", run_id="r2", status="success", count=[], usage=bad))

    def test_proposals_only_worker_names_its_engine_but_never_numbers(self):
        self.run_(action="start", run_id="r1")
        with patch.dict(os.environ, {"KEEPTRACK_PROPOSALS_ONLY": "1"}):
            self.assertIn("engine= only", self.refused(action="finish", run_id="r1", status="success", count=[], usage=["in=5"]))
            self.run_(action="finish", run_id="r1", status="success", count=[], usage=["engine=codex"])
            with self.assertRaises(SystemExit):
                kt._proposals_only(Args(cmd="routine", action="usage"))
        self.assertEqual({"engine": "codex", "known": False}, self.doc()["last_run"]["usage"])

    def test_usage_adds_measured_numbers_to_last_run_only(self):
        self.one_run(usage=["engine=claude"])
        before = self.doc()
        self.run_(action="usage", since=before["last_run"]["started_at"][:19] + "Z", usage=["engine=claude", "in=12", "out=3"])
        after = self.doc()
        self.assertEqual({"engine": "claude", "known": True, "in": 12, "out": 3}, after["last_run"]["usage"])
        self.assertEqual(before["runs"], after["runs"])   # the history keeps the report as finish wrote it (relay's guard)
        self.assertEqual({k: v for k, v in before.items() if k != "last_run"}, {k: v for k, v in after.items() if k != "last_run"})
        self.assertIn("already has its usage", self.refused(action="usage", run_id="r1", usage=["in=1"]))

    def test_usage_matches_only_the_run_it_names(self):
        self.one_run()
        self.assertIn("not r9", self.refused(action="usage", run_id="r9", usage=["in=1"]))
        self.assertIn("no run finished", self.refused(action="usage", since="2999-01-01T00:00:00Z", usage=["in=1"]))
        self.assertIn("exactly one", self.refused(action="usage", usage=["in=1"]))
        self.assertIn("at least one token count", self.refused(action="usage", run_id="r1", usage=["engine=claude"]))
        self.run_(action="usage", run_id="r1", usage=["in=1"])
        self.assertEqual({"engine": "unknown", "known": True, "in": 1}, self.doc()["last_run"]["usage"])

    def test_usage_with_no_finished_run_is_refused(self):
        self.assertIn("no finished run", self.refused(action="usage", run_id="r1", usage=["in=1"]))

    def test_usage_push_saves_through_the_api_and_rereads_on_conflict(self):
        self.one_run(usage=["engine=codex"])
        doc = self.doc()
        doc.update(board_repo="o/b", branch="main", board_path="board/tasks.json")
        kt.FILE, kt.REPO, kt.BRANCH, kt.PATH = None, "o/b", "main", "board/tasks.json"
        calls, puts = [], []

        def fake_gh(*args, body=None):
            calls.append(args)
            if args[0] != "-X":
                content = base64.b64encode(json.dumps(doc).encode()).decode()
                return 0, json.dumps({"sha": "s%d" % len(calls), "content": content, "encoding": "base64"}), ""
            puts.append(body)
            if len(puts) == 1:
                return 1, json.dumps({"message": "is at s9 but expected s1"}), "HTTP 409"
            return 0, "{}", ""
        kt.gh = fake_gh
        self.run_(action="usage", push=True, run_id="r1", usage=["engine=codex", "in=101", "out=10", "cache_read=50", "turns=2"])
        self.assertEqual(2, len(puts))
        saved = json.loads(base64.b64decode(puts[-1]["content"]))
        self.assertEqual({"engine": "codex", "known": True, "in": 101, "out": 10, "cache_read": 50, "turns": 2},
                         saved["last_run"]["usage"])
        self.assertEqual("main", puts[-1]["branch"])
        self.assertEqual(doc["runs"], saved["runs"])
        kt.default_user = lambda: "mallory"
        self.assertIn("registered owner", self.refused(action="usage", push=True, run_id="r1", usage=["in=1"]))


if __name__ == "__main__":
    unittest.main()

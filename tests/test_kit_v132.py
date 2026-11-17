"""Kit v132: every change to a card's label set leaves a "labels: a, b" history line with the full resulting list, so a
reader can prove from history alone who placed a label. Covers add --label, task-set, label-set --rename, label-rm --force
merge-card, proposal accept (create and update), proposal merge, inbound card creation, to-do split and kit-check.
`PATHS` below enumerates the label-mutating paths this file can reach; each must leave a labels: line."""
import json
import os
import re
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from test_kit_v112 import Board, read, item  # noqa: E402


class Release(unittest.TestCase):
    def test_release_132_is_consistent(self):
        version = json.loads(read("board/kit/manifest.json"))["version"]
        self.assertGreaterEqual(version, 132)
        self.assertEqual(str(version), re.search(r"^KIT_VERSION = (\d+)", read("board/kit/keeptrack.py"), re.M)[1])
        self.assertIn(f"const PAGE_KIT = {version};", read("board/board.js"))
        for plugin in (".claude-plugin", ".codex-plugin", ".cursor-plugin"):
            self.assertEqual(f"0.{version}.0", json.loads(read(f"board/kit/{plugin}/plugin.json"))["version"])
        self.assertIn("### v132 (schema 4)", read("board/kit/UPGRADING.md"))
        self.assertIn("Kit v132:", read("CHANGELOG.md"))

    def test_web_page_logs_a_new_card_with_labels_like_the_cli(self):
        src = read("board/board.js")
        self.assertIn("if (!p) { add('created'); if ((t.labels || []).length) add('labels: ' + t.labels.join(', ')); return; }", src)

    def test_rook_research_uses_the_full_list_helper(self):
        src = read("board/kit/research.py")
        self.assertNotIn('"labels: needs-human"', src)
        self.assertIn("kt.hist_labels(task)", src)


class LabelLines(Board):
    def add(self, title, *args):
        out = self.kt("add", title, *args).stdout
        self.ids = getattr(self, "ids", {})
        self.ids[title] = re.search(r"added #\d+ \(([^)]+)\)", out)[1]

    def cards(self):
        out = {}
        for name, c in self.folder("cards").items():
            out[c["title"]] = c
        return out

    def label_lines(self, title):
        return [h["text"] for h in self.cards()[title]["history"] if h["text"].startswith("labels:")]

    def test_add_with_labels_writes_the_full_list_and_without_writes_none(self):
        self.add("Has labels", "--label", "alpha", "--label", "beta")
        self.add("No labels")
        self.assertEqual(["labels: alpha, beta"], self.label_lines("Has labels"))
        self.assertEqual([], self.label_lines("No labels"))

    def test_task_set_still_writes_the_line(self):
        self.add("One", "--label", "alpha")
        self.kt("task-set", self.ids["One"], "--label", "beta")
        self.kt("task-set", self.ids["One"], "--unlabel", "alpha")
        self.assertEqual(["labels: alpha", "labels: alpha, beta", "labels: beta"], self.label_lines("One"))

    def test_board_wide_rename_and_delete_write_a_line_per_card(self):
        self.add("One", "--label", "alpha", "--label", "beta")
        self.add("Two", "--label", "beta")
        self.kt("label-set", "alpha", "--rename", "gamma")
        self.assertEqual(["labels: alpha, beta", "labels: gamma, beta"], self.label_lines("One"))
        self.assertEqual(["labels: beta"], self.label_lines("Two"))   # not on Two: nothing written
        self.kt("label-rm", "beta", "--force")
        self.assertEqual("labels: gamma", self.label_lines("One")[-1])
        self.assertEqual("labels: none", self.label_lines("Two")[-1])

    def test_merge_card_writes_a_line_only_when_the_target_gains_labels(self):
        self.add("Target", "--label", "alpha")
        self.add("Src", "--label", "alpha", "--label", "beta")
        self.add("Plain", "--label", "alpha")
        self.kt("merge-card", self.ids["Src"], self.ids["Target"])
        self.assertEqual(["labels: alpha", "labels: alpha, beta"], self.label_lines("Target"))
        self.kt("merge-card", self.ids["Plain"], self.ids["Target"])
        self.assertEqual(["labels: alpha", "labels: alpha, beta"], self.label_lines("Target"))


SRC = {"kind": "other", "id": "chat-1", "revision": "2026-11-17", "title": "chat", "date": "2026-11-17"}


class EveryPath(LabelLines):
    """Invariant: a label change is never saved without a labels: line, from any path."""

    def propose(self, key, kind, change, target=None):
        body = [{"kind": kind, "title": change.get("title") or key, "source": SRC, "action_key": key, "work_key": key,
                 "reason": "test", "target": target, "change": change}]
        p = subprocess.run([sys.executable, os.path.join(self.board, "keeptrack.py"), "--file", os.path.join(self.board, "tasks.json"),
                            "proposal-add", "-"], input=json.dumps(body), capture_output=True, text=True, env=self.env, cwd=self.repo)
        self.assertEqual(0, p.returncode, p.stderr)
        rows = json.loads(self.kt("proposals", "--status", "all", "--json").stdout)
        return next(r["id"] for r in rows if r["action_key"] == key)

    def test_every_reachable_path_leaves_a_labels_line(self):
        # add --label
        self.add("Added", "--label", "alpha")
        self.assertEqual(["labels: alpha"], self.label_lines("Added"))
        # task-set
        self.add("Set")
        self.kt("task-set", self.ids["Set"], "--label", "beta")
        self.assertEqual(["labels: beta"], self.label_lines("Set"))
        # proposal accept, create with labels
        pid = self.propose("create", "task.create", {"title": "From proposal", "column": "backlog", "labels": ["alpha", "beta"]})
        self.kt("proposal-accept", pid)
        self.assertEqual(["labels: alpha, beta"], self.label_lines("From proposal"))
        # proposal accept, create without labels: no line
        pid = self.propose("create2", "task.create", {"title": "From proposal plain", "column": "backlog"})
        self.kt("proposal-accept", pid)
        self.assertEqual([], self.label_lines("From proposal plain"))
        # proposal accept, update that changes labels, then one that does not
        self.add("Upd", "--label", "alpha")
        tid = self.ids["Upd"]
        pid = self.propose("upd", "task.update", {"labels": ["alpha", "beta"]}, {"type": "task", "id": tid, "base": {"labels": ["alpha"]}})
        self.kt("proposal-accept", pid)
        self.assertEqual(["labels: alpha", "labels: alpha, beta"], self.label_lines("Upd"))
        pid = self.propose("upd2", "task.update", {"priority": "high"}, {"type": "task", "id": tid, "base": {"priority": "medium"}})
        self.kt("proposal-accept", pid)
        self.assertEqual(["labels: alpha", "labels: alpha, beta"], self.label_lines("Upd"))
        # proposal merge --fields labels
        self.add("Mrg", "--label", "alpha")
        pid = self.propose("mrg", "task.create", {"title": "Mrg", "column": "backlog", "labels": ["gamma"]})
        self.kt("proposal-merge", pid, "--into", self.ids["Mrg"], "--fields", "labels")
        self.assertEqual(["labels: alpha", "labels: gamma"], self.label_lines("Mrg"))
        # merge-card
        self.add("Target", "--label", "alpha")
        self.add("Src", "--label", "delta")
        self.kt("merge-card", self.ids["Src"], self.ids["Target"])
        self.assertEqual(["labels: alpha", "labels: alpha, delta"], self.label_lines("Target"))
        # board-wide rename and delete
        self.kt("label-set", "alpha", "--rename", "omega")
        self.assertEqual("labels: omega, delta", self.label_lines("Target")[-1])
        self.kt("label-rm", "delta", "--force")
        self.assertEqual("labels: omega", self.label_lines("Target")[-1])

    def test_inbound_card_with_labels_leaves_a_line(self):
        self.kt("inbound-source", "rainshift-contact", "--mode", "card", "--assign", "alex", "--label", "enquiry", "--stage", "New")
        self.put(item("c-9"))
        self.kt("inbound")
        self.assertEqual(["labels: enquiry"], self.label_lines("Enquiry from Casey Example (Example Ltd)"))

    def test_split_to_do_copies_labels_with_a_line(self):
        self.add("Parent", "--label", "needs-human", "--todo", "Do the thing")
        self.kt("todo-move", self.ids["Parent"], "1")
        child = next(c for c in self.cards().values() if c["title"] == "Do the thing")
        self.assertEqual(["labels: needs-human"], [h["text"] for h in child["history"] if h["text"].startswith("labels:")])


if __name__ == "__main__":
    unittest.main()

"""Kit v132: every change to a card's label set leaves a "labels: a, b" history line with the full resulting list, so a
reader can prove from history alone who placed a label. Covers add --label, task-set, label-set --rename, label-rm --force
merge-card, proposal accept (create and update), proposal merge, inbound card creation, to-do split, import and the kit-check
upgrade card. EveryPath and the two tests after it run each of those through the real CLI and assert the line. Not covered
here: hosted boards, where the server owns card history (HostedHistory only pins what model_changes does) and the web page,
whose autoLog is run for real in node by WebAutoLog."""
import json
import os
import re
import shutil
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
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

    def test_rook_research_uses_the_full_list_helper(self):
        src = read("board/kit/research.py")
        self.assertNotIn('"labels: needs-human"', src)
        self.assertIn("kt.hist_labels(task)", src)


class WebAutoLog(unittest.TestCase):
    """Runs the real autoLog function from board/board.js in node (extracted by brace matching, with its few page helpers
    stubbed) for a new card with labels, a new card without, and a label edit on an existing card."""

    SCRIPT = r"""
const fs = require('fs');
const src = fs.readFileSync(process.argv[1], 'utf8');
const start = src.indexOf('function autoLog(pre, post) {');
let i = src.indexOf('{', start), depth = 0, end = -1;
for (let j = i; j < src.length; j++) { if (src[j] === '{') depth++; else if (src[j] === '}' && --depth === 0) { end = j + 1; break; } }
const body = src.slice(start, end);
const stubs = { byId: (st) => new Map((st.tasks || []).map(t => [t.id, t])), cfg: () => ({ me: 'tester' }), nowIso: () => 'now',
  colName: x => x, validRank: () => false, relationOf: () => undefined, doneColId: () => 'done', jcanon: x => JSON.stringify(x) };
const autoLog = new Function(...Object.keys(stubs), body + '; return autoLog;')(...Object.values(stubs));
const card = (id, labels) => ({ id, title: id, labels, assignees: [], links: [], contacts: [], todos: [], history: [] });
const pre = { tasks: [card('old', ['a'])] };
const post = { tasks: [card('old', ['a', 'b']), card('with', ['x', 'y']), card('none', [])] };
autoLog(pre, post);
process.stdout.write(JSON.stringify(Object.fromEntries(post.tasks.map(t => [t.id, t.history.map(h => h.text)]))));
"""

    @unittest.skipUnless(shutil.which("node"), "node is not installed")
    def test_autolog_writes_the_labels_line_for_a_new_card_with_labels(self):
        p = subprocess.run(["node", "-e", self.SCRIPT, os.path.join(ROOT, "board", "board.js")], capture_output=True, text=True)
        self.assertEqual(0, p.returncode, p.stderr)
        out = json.loads(p.stdout)
        self.assertEqual(["created", "labels: x, y"], out["with"])
        self.assertEqual(["created"], out["none"])
        self.assertEqual(["labels: a, b"], out["old"])


class HostedHistory(unittest.TestCase):
    """On hosted boards the server owns card history for every path. HostedStorageAdapter.model_changes puts the server's
    old history back on every card it saves, so a labels: line the CLI added in memory is dropped. This pins that behaviour
    (it does not prove the server writes its own labels: line; that is not checked in this repo)."""

    def test_model_changes_restores_the_servers_history_over_the_local_labels_line(self):
        import copy
        sys.path.insert(0, os.path.join(ROOT, "board", "kit"))
        import keeptrack as kt
        adapter = object.__new__(kt.HostedStorageAdapter)
        adapter.holder = lambda *a, **k: None
        adapter.identity = {"agent_id": None}
        card = {"id": "t_1", "title": "x", "labels": [], "history": [{"at": "a", "by": "b", "text": "created"}]}
        files = {"tasks.json": {"rev": "r0", "body": {}}, "cards/t_1.json": {"rev": "r1", "body": copy.deepcopy(card)}}
        data = {"tasks": [copy.deepcopy(card)]}
        task = data["tasks"][0]
        task["labels"] = ["needs-human"]
        kt.hist_labels(task)
        self.assertEqual(["created", "labels: needs-human"], [h["text"] for h in task["history"]])
        ops, _ = adapter.model_changes(data, files)
        sent = next(op for op in ops if op["path"] == "cards/t_1.json")["body"]
        self.assertEqual(["needs-human"], sent["labels"])
        self.assertEqual(["created"], [h["text"] for h in sent["history"]])


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

        # inbound card creation with labels
        self.kt("inbound-source", "rainshift-contact", "--mode", "card", "--assign", "alex", "--label", "enquiry", "--stage", "New")
        self.put(item("c-9"))
        self.kt("inbound")
        self.assertEqual(["labels: enquiry"], self.label_lines("Enquiry from Casey Example (Example Ltd)"))
        # to-do split copies labels
        self.add("Parent", "--label", "needs-human", "--todo", "Do the thing")
        self.kt("todo-move", self.ids["Parent"], "1")
        self.assertEqual(["labels: needs-human"], self.label_lines("Do the thing"))

    def test_import_with_labels_leaves_a_line_and_without_leaves_none(self):
        staging = os.path.join(self.repo, "staging.json")
        with open(staging, "w", encoding="utf8") as f:
            json.dump({"tasks": [{"title": "Imported with", "labels": ["alpha", "beta"]}, {"title": "Imported plain"}]}, f)
        self.kt("import", staging)
        self.assertEqual(["labels: alpha, beta"], self.label_lines("Imported with"))
        self.assertEqual([], self.label_lines("Imported plain"))

    def test_kit_check_upgrade_card_with_the_board_label_leaves_a_line(self):
        self.kt("label-add", "board")
        kit = os.path.join(self.repo, "published-kit")
        os.makedirs(kit)
        with open(os.path.join(kit, "manifest.json"), "w") as f:
            json.dump({"version": 99999, "files": {}}, f)
        self.kt("kit-check", "--card", "--from", kit)
        card = self.cards()["Upgrade board tools to kit v99999"]
        self.assertEqual(["board"], card["labels"])
        self.assertEqual(["labels: board"], self.label_lines("Upgrade board tools to kit v99999"))


if __name__ == "__main__":
    unittest.main()

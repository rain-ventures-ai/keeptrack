"""Similar cards (kit v52): add first, then mark close cards as possibly related; merge, link or dismiss afterwards.
Fictional data only (the v4 fixture board: Acme, alex)."""
import json, os, shutil, subprocess, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
KT = os.path.join(HERE, "..", "board", "kit", "keeptrack.py")
sys.path.insert(0, os.path.join(HERE, "..", "board", "kit"))
import keeptrack  # noqa: E402


class Scoring(unittest.TestCase):
    def test_close_titles_score_high_and_others_low(self):
        self.assertEqual(1.0, keeptrack.similar_score("Send Acme the plan", "send acme plan"))
        self.assertGreaterEqual(keeptrack.similar_score("Re-measure four parked replay cases", "Re-measure four parked replay cases after card 52"), 0.8)
        self.assertLess(keeptrack.similar_score("Call Acme", "Write notes"), 0.5)
        self.assertEqual(0.0, keeptrack.similar_score("the", "a"))

    def test_different_numbers_are_never_duplicates(self):
        s = keeptrack.similar_score("Upgrade board tools to kit v36", "Upgrade board tools to kit v37")
        self.assertGreaterEqual(s, keeptrack.SIMILAR_DUPLICATE)
        self.assertIsNone(keeptrack.similar_kind(s, False, "Upgrade board tools to kit v36", "Upgrade board tools to kit v37"))
        self.assertEqual("addition", keeptrack.similar_kind(s, True, "Upgrade board tools to kit v36", "Upgrade board tools to kit v37"))
        self.assertEqual("duplicate", keeptrack.similar_kind(1.0, False, "Fix card #52", "Fix card #52"))


class SimilarCli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.board = os.path.join(self.tmp.name, "board")
        shutil.copytree(os.path.join(HERE, "fixtures", "v4"), self.board)
        self.env = dict(os.environ, BOARD_USER="alex", HOME=self.tmp.name)
        for k in ("BOARD_TOKEN", "GH_TOKEN", "GITHUB_TOKEN", "BOARD_AGENT"):
            self.env.pop(k, None)

    def tearDown(self):
        self.tmp.cleanup()

    def kt(self, *args, ok=True):
        p = subprocess.run([sys.executable, KT, "--file", os.path.join(self.board, "tasks.json"), *args],
                           capture_output=True, text=True, env=self.env)
        if ok and p.returncode:
            self.fail(f"{args} exited {p.returncode}: {p.stdout}{p.stderr}")
        return p

    def card(self, ref):
        return json.loads(self.kt("show", ref).stdout.split("\n\n")[0])

    def test_add_never_stops_and_marks_both_cards(self):
        out = self.kt("add", "Call ACME").stdout
        self.assertIn("added #3", out)
        self.assertIn("possible duplicate: t_first #1", out)
        new, old = self.card("#3"), self.card("#1")
        self.assertEqual([("t_first", "duplicate", "possible")], [(r["id"], r["kind"], r["status"]) for r in new["related"]])
        self.assertEqual([(new["id"], "duplicate", "possible")], [(r["id"], r["kind"], r["status"]) for r in old["related"]])
        self.assertIn("#1 Call Acme", self.kt("related").stdout)
        self.assertNotIn("related", self.card("#2"))

    def test_no_check_and_other_clients_are_left_alone(self):
        self.kt("add", "Call ACME", "--no-check")
        self.assertNotIn("related", self.card("#3"))
        self.kt("add", "Call ACME", "--client", "Other Co")   # #1 has client Acme: a different client never matches
        self.assertNotIn("t_first", [r["id"] for r in self.card("#4").get("related", [])])
        self.assertNotIn("related", self.card("#1"))

    def test_not_related_is_not_asked_again_and_link_confirms(self):
        self.kt("add", "Call ACME")
        self.kt("unrelate", "#3", "#1")
        self.assertEqual("not-related", self.card("#1")["related"][0]["status"])
        self.assertIn("no possible duplicates", self.kt("related").stdout)
        self.kt("add", "call acme!")   # #4 marks #1 and #3; the dismissed #1/#3 pair stays dismissed
        self.assertEqual("not-related", next(r for r in self.card("#3")["related"] if r["id"] == "t_first")["status"])
        self.kt("relate", "#4", "#1", "--kind", "addition")
        r = next(r for r in self.card("#1")["related"] if r["id"] == self.card("#4")["id"])
        self.assertEqual(("addition", "confirmed"), (r["kind"], r["status"]))

    def test_merge_card_copies_work_and_archives_the_source(self):
        self.kt("add", "Call ACME", "--details", "Ask about the renewal.", "--todo", "Book the call", "--label", "urgent", "--priority", "high")
        self.kt("comment", "#3", "Casey prefers mornings")
        out = self.kt("merge-card", "#3", "#1").stdout
        self.assertIn("archived", out)
        kept = self.card("#1")
        self.assertIn("Merged from #3", kept["details"])
        self.assertIn("Book the call", [d["text"] for d in kept["todos"]])
        self.assertIn("urgent", kept["labels"])
        self.assertEqual("high", kept["priority"])
        self.assertIn("[from #3] Casey prefers mornings", self.kt("comments", "#1").stdout)
        self.assertEqual("merged", kept["related"][0]["status"])
        self.assertNotIn("#3", self.kt("list").stdout)
        self.assertIn("#3", self.kt("archived").stdout)
        self.assertEqual(0, self.kt("doctor").returncode)

    def test_a_card_added_after_a_proposal_marks_it_and_accept_links_the_cards(self):
        # The private-tasks #121/#128 case: an Inbox item first, the same card added directly later, then the item accepted.
        prop = [{"kind": "task.create", "title": "Send Acme the revised plan", "source": {"kind": "other", "id": "chat-1", "revision": "1"},
                 "action_key": "ak-plan", "work_key": "wk-plan", "reason": "agreed in a chat",
                 "change": {"title": "Send Acme the revised plan", "client": "Acme"}}]
        path = os.path.join(self.tmp.name, "p.json")
        with open(path, "w") as f:
            json.dump(prop, f)
        self.kt("proposal-add", path)
        pid = json.loads(self.kt("proposals", "--json").stdout)[0]["id"]
        self.assertIn(f"Inbox item {pid}", self.kt("add", "Send Acme the revised plan", "--client", "Acme").stdout)
        dups = json.loads(self.kt("proposal-show", pid).stdout)["likely_duplicates"]
        self.assertEqual([("task", self.card("#3")["id"])], [(d["type"], d["id"]) for d in dups])
        self.assertIn("possible duplicate", self.kt("proposal-accept", pid).stdout)
        self.assertEqual("possible", self.card("#3")["related"][0]["status"])

    def test_a_proposal_for_work_already_on_the_board_names_the_card(self):
        prop = [{"kind": "task.create", "title": "call acme!", "source": {"kind": "other", "id": "chat-2", "revision": "1"},
                 "action_key": "ak-call", "work_key": "wk-call", "reason": "said in a chat", "change": {"title": "call acme!"}}]
        path = os.path.join(self.tmp.name, "p.json")
        with open(path, "w") as f:
            json.dump(prop, f)
        self.kt("proposal-add", path)
        pid = json.loads(self.kt("proposals", "--json").stdout)[0]["id"]
        self.assertEqual([("t_first", "similar title")], [(d["id"], d["why"]) for d in json.loads(self.kt("proposal-show", pid).stdout)["likely_duplicates"]])

    def propose(self, *items):
        path = os.path.join(self.tmp.name, "p.json")
        with open(path, "w") as f:
            json.dump([{"kind": "task.create", "title": t, "source": {"kind": "other", "id": "chat-" + k, "revision": "1"},
                        "action_key": "ak-" + k, "work_key": "wk-" + k, "reason": "said in a chat", "change": {"title": t}}
                       for k, t in items], f)
        self.kt("proposal-add", path)
        return {p["title"]: p["id"] for p in json.loads(self.kt("proposals", "--json").stdout)}

    def test_undo_of_an_accept_that_found_a_match_works_and_drops_the_marks(self):
        pid = self.propose(("u", "Call ACME"))["Call ACME"]
        self.kt("proposal-accept", pid)
        self.assertEqual(1, len(self.card("#1")["related"]))
        self.kt("proposal-undo", pid)
        self.assertNotIn("related", self.card("#1"))

    def test_a_second_inbox_item_for_the_same_work_names_the_first(self):
        ids = self.propose(("a", "Book the Leeds venue for March"), ("b", "Book the Leeds venue for march!"))
        dups = json.loads(self.kt("proposal-show", ids["Book the Leeds venue for march!"]).stdout)["likely_duplicates"]
        self.assertEqual([("proposal", ids["Book the Leeds venue for March"], "similar Inbox item")], [(d["type"], d["id"], d["why"]) for d in dups])

    def test_similar_lists_cards_and_pending_items(self):
        self.assertIn("#1 t_first", self.kt("similar", "Call Acme").stdout)
        self.assertIn("no open card", self.kt("similar", "Something else entirely").stdout)
        self.assertEqual("t_first", json.loads(self.kt("similar", "Call Acme", "--json").stdout)[0]["id"])

    def test_doctor_flags_a_malformed_relation(self):
        f = os.path.join(self.board, "cards", "t_second.json")
        with open(f) as fh:
            c = json.load(fh)
        c["related"] = [{"id": "t_first", "kind": "twin", "status": "possible"}]
        with open(f, "w") as fh:
            json.dump(c, fh)
        self.assertIn("RELATED", self.kt("doctor", ok=False).stdout)


if __name__ == "__main__":
    unittest.main()

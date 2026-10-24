"""Review Inbox end to end through the command line, with fictional meeting and email fixtures (no real notes or mail)."""
import json, os, shutil, subprocess, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
KT = os.path.join(HERE, "..", "board", "kit", "keeptrack.py")
FIX = os.path.join(HERE, "fixtures", "review-inbox")


class ReviewInboxCli(unittest.TestCase):
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
            self.fail(f"{args} exited {p.returncode}: {p.stderr}")
        return p

    def snapshot(self, *folders):
        out = {}
        for folder in folders:
            root = os.path.join(self.board, folder)
            for name in sorted(os.listdir(root)) if os.path.isdir(root) else []:
                with open(os.path.join(root, name), "rb") as f:
                    out[f"{folder}/{name}"] = f.read()
        return out

    def pending(self):
        return json.loads(self.kt("proposals", "--json").stdout)

    def test_meeting_and_email_extraction_then_review(self):
        # Kit v44: the Inbox is always on for a split board; the old switch is a no-op and cannot turn it off.
        self.assertIn("review_inbox.enabled: true", self.kt("settings").stdout)
        self.assertIn("always on", self.kt("settings-set", "review_inbox.enabled", "true").stdout)
        self.assertEqual(2, self.kt("settings-set", "review_inbox.enabled", "false", ok=False).returncode)
        live, listing = self.snapshot("cards", "people"), self.kt("list").stdout

        # Extraction: proposals only. Live cards and people stay byte-identical; list and counts do not change.
        self.kt("proposal-add", os.path.join(FIX, "meeting-proposals.json"))
        self.kt("proposal-add", os.path.join(FIX, "email-proposals.json"))
        self.assertEqual(live, self.snapshot("cards", "people"))
        self.assertEqual(listing, self.kt("list").stdout)
        self.assertNotIn("revised plan", self.kt("today").stdout, "pending proposals never show as work for today")
        # Agents cannot claim a proposal, and next never picks one.
        pid = self.pending()[0]["id"]
        self.assertNotEqual(0, self.kt("claim", pid, ok=False).returncode)
        nxt = subprocess.run([sys.executable, KT, "--file", os.path.join(self.board, "tasks.json"), "next", "--all"],
                             capture_output=True, text=True, env=dict(self.env, BOARD_AGENT="codex"))
        self.assertNotIn("revised plan", nxt.stdout + nxt.stderr)
        self.assertEqual(4, len(self.pending()))
        live = self.snapshot("cards", "people")   # next may claim a real card; from here on compare against that
        self.assertEqual(4, len(self.pending()))

        # Rerunning the same extraction adds nothing.
        again = self.kt("proposal-add", os.path.join(FIX, "meeting-proposals.json")).stdout
        self.assertEqual(3, again.count("exists "), again)
        self.assertEqual(4, len(self.pending()))

        # An email summary needs proof that every intended reader received the message.
        with open(os.path.join(FIX, "email-proposals.json"), encoding="utf-8") as f:
            leaky = json.load(f)
        leaky[0].update(action_key="email:" + "3" * 64, reason="Casey wrote about the budget.")
        path = os.path.join(self.tmp.name, "leaky.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(leaky, f)
        self.assertEqual(2, self.kt("proposal-add", path, ok=False).returncode)

        by_title = {p["title"]: p for p in self.pending()}
        create, update = by_title["Send Acme the revised plan"], by_title["Call Acme is now urgent"]
        meeting, email = by_title["Meeting with Casey Example, 8 Oct"], by_title["Email from Casey Example, 9 Oct"]
        self.assertEqual("alex", create["createdBy"])

        # Accept creates exactly one card, with the stated owner and due date.
        self.kt("proposal-accept", create["id"])
        cards = self.snapshot("cards")
        self.assertEqual(3, len(cards))
        accepted = json.loads(self.kt("proposal-show", create["id"]).stdout)
        new = json.loads(cards[f"cards/{accepted['decision']['result']['id']}.json"])
        self.assertEqual((["alex"], "2026-10-15", "Acme"), (new["assignees"], new["due"], new["client"]))
        # A second accept is refused (exit 3) and adds nothing.
        self.assertEqual(3, self.kt("proposal-accept", create["id"], ok=False).returncode)
        self.assertEqual(3, len(self.snapshot("cards")))

        # The update adds a label and keeps everything else.
        self.kt("proposal-accept", update["id"])
        first = json.loads(self.snapshot("cards")["cards/t_first.json"])
        self.assertIn("urgent", first["labels"])

        # The meeting log is accepted; the email (metadata only) is ignored and stays ignored on a rerun.
        self.kt("proposal-accept", meeting["id"])
        self.kt("proposal-ignore", email["id"])
        person = json.loads(self.snapshot("people")["people/p_acme.json"])
        self.assertEqual(["Weekly meeting: revised plan due 15 Oct."], [c["text"] for c in person["comments"]])
        rerun = self.kt("proposal-add", os.path.join(FIX, "email-proposals.json")).stdout
        self.assertIn(f"exists {email['id']} ignored", rerun)
        self.assertEqual([], self.pending())

    def test_done_records_a_completed_task(self):
        self.kt("proposal-add", os.path.join(FIX, "meeting-proposals.json"))
        create = next(p for p in self.pending() if p["title"] == "Send Acme the revised plan")
        out = self.kt("proposal-accept", create["id"], "--done")
        self.assertIn("recorded done", out.stdout)
        accepted = json.loads(self.kt("proposal-show", create["id"]).stdout)
        self.assertEqual("accepted", accepted["status"])
        self.assertEqual("complete", accepted["decision"]["action"])
        card = json.loads(self.snapshot("cards")[f"cards/{accepted['decision']['result']['id']}.json"])
        self.assertEqual("done", card["column"])
        self.assertEqual("completed", card["outcome"])
        self.assertTrue(any(h.get("text", "").startswith("done:") for h in card["history"]))
        update = next(p for p in self.pending() if p["kind"] == "task.update")
        refused = self.kt("proposal-accept", update["id"], "--done", ok=False)
        self.assertEqual(2, refused.returncode)
        self.assertIn("not a new task", refused.stderr)


    def test_v3_board_refuses_with_the_schema_message(self):
        legacy = os.path.join(self.tmp.name, "v3")
        shutil.copytree(os.path.join(HERE, "fixtures", "v3"), legacy)
        p = subprocess.run([sys.executable, KT, "--file", os.path.join(legacy, "tasks.json"), "proposal-add", os.path.join(FIX, "meeting-proposals.json")],
                           capture_output=True, text=True, env=self.env)
        self.assertEqual(2, p.returncode, p.stderr)
        self.assertIn("needs split storage (schema 4)", p.stderr)

    def test_older_cli_keeps_proposal_files(self):
        """A kit v40 keeptrack.py (before the Inbox) saving to a board that has proposals never drops or changes them."""
        old = os.path.join(self.tmp.name, "keeptrack_v40.py")
        src = subprocess.run(["git", "show", "51dfdb5:board/kit/keeptrack.py"], cwd=HERE, capture_output=True, text=True)
        if src.returncode:
            self.skipTest("kit v40 keeptrack.py is not in this checkout's history")
        with open(old, "w", encoding="utf-8") as f:
            f.write(src.stdout)
        self.kt("settings-set", "review_inbox.enabled", "true")
        self.kt("proposal-add", os.path.join(FIX, "meeting-proposals.json"))
        before = self.snapshot("proposals")
        p = subprocess.run([sys.executable, old, "--file", os.path.join(self.board, "tasks.json"), "add", "Made by an older tool"],
                           capture_output=True, text=True, env=self.env)
        self.assertEqual(0, p.returncode, p.stderr)
        self.assertEqual(before, self.snapshot("proposals"))
        self.assertEqual(3, len(self.pending()))


if __name__ == "__main__":
    unittest.main()

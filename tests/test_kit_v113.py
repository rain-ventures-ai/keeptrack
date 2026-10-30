"""Kit v113: an inbound item can attach to the card made from an earlier item of the same source (a website chat
summary on its enquiry's card). Matched: a comment on that card, never a new card. Not matched yet: the item waits,
not a failure. Never matched within the source's attach_days: a Review Inbox proposal, as for any item."""
import json
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from test_kit_v112 import Board, item, read  # noqa: E402

HANDLER = r'''
import json, sys
item = json.load(sys.stdin)
p = item["payload"]
if item["kind"] == "rayna-chat":
    print(json.dumps({"attach": {"to": p["enquiry_id"], "comment": "Rayna chat after the enquiry: " + p["summary"]}}))
else:
    print(json.dumps({"card": {"title": "Enquiry: " + p["name"], "details": "enquiry " + item["id"]},
                      "person": {"name": p["name"], "email": p["email"]}}))
'''
SECRET = "chat-only-visitor-text-7f3a"


def chat(enquiry, n=1, **payload):
    body = {"enquiry_id": enquiry, "summary": f"Q: price? A: depends. {SECRET}"}
    body.update(payload)
    return {"v": 1, "source": "rainshift-contact", "kind": "rayna-chat", "id": f"{enquiry}-chat-{n}",
            "received": "2026-10-30T09:00:00Z", "payload": body}


class Release(unittest.TestCase):
    def test_release_113_is_consistent(self):
        version = json.loads(read("board/kit/manifest.json"))["version"]
        self.assertEqual(version, 113)
        self.assertEqual(str(version), re.search(r"^KIT_VERSION = (\d+)", read("board/kit/keeptrack.py"), re.M)[1])
        self.assertIn(f"const PAGE_KIT = {version};", read("board/board.js"))
        for plugin in (".claude-plugin", ".codex-plugin", ".cursor-plugin"):
            self.assertEqual(f"0.{version}.0", json.loads(read(f"board/kit/{plugin}/plugin.json"))["version"])
        self.assertIn("### v113 (schema 4)", read("board/kit/UPGRADING.md"))
        self.assertIn("Kit v113:", read("CHANGELOG.md"))
        self.assertIn("attach", read("board/kit/INBOUND.md"))
        self.assertIn("holding(n)", read("board/board.js"))


class Attach(Board):
    def setUp(self):
        super().setUp()
        os.makedirs(os.path.join(self.repo, "intake"))
        with open(os.path.join(self.repo, "intake", "plan.py"), "w", encoding="utf8") as f:
            f.write(HANDLER)
        self.kt("inbound-source", "rainshift-contact", "--mode", "card", "--handler", "intake/plan.py")

    def stamp(self, minutes_ago=5):
        import datetime as dt
        return (dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=minutes_ago)).strftime("%Y%m%dT%H%M%SZ")

    def cards_with(self, text):
        return [c for c in self.folder("cards").values() if text in json.dumps(c)]

    def enquiry_card(self, ident):
        return next(c for c in self.folder("cards").values() if f"enquiry {ident}" in c.get("details", ""))

    def test_matched_in_one_run_and_never_twice(self):
        self.put(item("e-1"), stamp=self.stamp(10))
        name = self.put(chat("e-1"), stamp=self.stamp(5))
        out = self.kt("inbound").stdout
        self.assertIn("-> attach", out)
        self.assertEqual([], os.listdir(self.inbox))
        card = self.enquiry_card("e-1")
        self.assertEqual(1, sum(SECRET in c["text"] for c in card["comments"]))
        self.assertTrue(card["comments"][-1]["text"].startswith("Rayna chat after the enquiry: "))
        self.assertEqual([card["id"]], [c["id"] for c in self.cards_with(SECRET)], "the visitor's text is on that card only")
        self.assertFalse(any(SECRET in json.dumps(p) for p in self.proposals()))
        # the same chat again, also once the done list has forgotten it: no second comment
        self.put(chat("e-1"), name=name)
        self.kt("inbound")
        data = self.root(); data["inbound"]["done"].clear()
        with open(os.path.join(self.board, "tasks.json"), "w", encoding="utf8") as f:
            json.dump(data, f)
        self.put(chat("e-1"), name=name)
        self.assertIn("already on #", self.kt("inbound").stdout)
        self.assertEqual(1, sum(SECRET in c["text"] for c in self.enquiry_card("e-1")["comments"]))

    def test_not_matched_yet_waits_then_attaches(self):
        name = self.put(chat("e-2"), stamp=self.stamp(5))
        before = (self.folder("cards"), len(self.proposals()))
        p = self.kt("inbound")
        self.assertEqual(0, p.returncode, "waiting is not a failure")
        self.assertIn("held until", p.stdout)
        self.assertEqual([name], os.listdir(self.inbox))
        self.assertEqual(before, (self.folder("cards"), len(self.proposals())))
        held = self.root()["inbound"]["held"][name]
        self.assertIn("e-2", held["why"])
        self.assertNotIn(name, self.kt("list", "--attention").stdout, "a held item is not an alert while it waits")
        self.assertIn("held:", self.kt("inbound", "--status").stdout)
        self.assertFalse(self.root()["inbound"].get("failed"))
        # the enquiry arrives: the next run makes its card, then the waiting chat attaches to it
        self.put(item("e-2"), stamp=self.stamp(60))
        self.kt("inbound")
        self.assertEqual([], os.listdir(self.inbox))
        self.assertEqual(1, sum(SECRET in c["text"] for c in self.enquiry_card("e-2")["comments"]))
        self.assertNotIn("held", self.root()["inbound"])

    def test_never_matched_goes_to_the_review_inbox(self):
        self.put(chat("e-3"), stamp="20261020T090000Z")   # 10 days old, past the default 3
        out = self.kt("inbound").stdout
        self.assertIn("no card to attach to", out)
        self.assertEqual([], os.listdir(self.inbox))
        mine = [p for p in self.proposals() if p["source"]["id"] == "inbound:rainshift-contact:e-3-chat-1"]
        self.assertEqual(["task.create"], [p["kind"] for p in mine])
        self.assertIn(SECRET, mine[0]["change"]["details"])
        self.assertEqual([], self.cards_with(SECRET), "no card is made without a person")

    def test_attach_days_zero_files_it_at_once(self):
        self.kt("inbound-source", "rainshift-contact", "--attach-days", "0")
        self.put(chat("e-4"), stamp=self.stamp(1))
        self.assertIn("no card to attach to", self.kt("inbound").stdout)
        self.assertEqual([], os.listdir(self.inbox))

    def test_a_review_mode_enquiry_waits_for_its_accept(self):
        self.kt("inbound-source", "rainshift-contact", "--mode", "review")
        self.put(item("e-5"), stamp=self.stamp(10))
        name = self.put(chat("e-5"), stamp=self.stamp(5))
        self.kt("inbound")
        self.assertIn("Review Inbox", self.root()["inbound"]["held"][name]["why"])
        task = next(p for p in self.proposals() if p["source"]["id"] == "inbound:rainshift-contact:e-5" and p["kind"] == "task.create")
        self.kt("proposal-accept", task["id"])   # a person
        self.kt("inbound")
        self.assertEqual([], os.listdir(self.inbox))
        self.assertEqual(1, sum(SECRET in c["text"] for c in self.enquiry_card("e-5")["comments"]))

    def test_a_closed_enquiry_card_is_not_reopened(self):
        self.put(item("e-6"), stamp=self.stamp(10))
        self.kt("inbound")
        card = self.enquiry_card("e-6")
        self.kt("archive", card["id"])
        self.put(chat("e-6"), stamp=self.stamp(1))
        self.assertIn("no card to attach to (archived)", self.kt("inbound").stdout)
        self.assertTrue(any(SECRET in json.dumps(p) for p in self.proposals()))

    def test_a_bad_attach_plan_fails_alone(self):
        name = self.put(chat("e-7", enquiry_id="../x"), stamp=self.stamp(1))
        self.kt("inbound", ok=False)
        self.assertIn("attach.to", self.root()["inbound"]["failed"][name]["error"])

    def test_an_agent_cannot_change_attach_days(self):
        p = self.kt("inbound-source", "rainshift-contact", "--attach-days", "9", ok=False, BOARD_AGENT="claude")
        self.assertIn("only make a source safer", p.stderr)


if __name__ == "__main__":
    unittest.main()

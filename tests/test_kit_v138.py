"""Kit v138: `unwait --owner-said` lets an agent end another agent's wait on the owner's word, only on a card assigned
to the owner; a person's wait stays locked. Run: python3 -m unittest tests.test_kit_v138"""
import json, os, re, sys, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test_waiting as tw   # noqa: E402  (its fixture: a temp board with osouthgate as BOARD_USER)

kt = tw.kt
SAID = "Yes build it and merge it without me being involved (Ollie, 2026-11-18 06:40 UK)"


def read(*parts):
    with open(os.path.join(HERE, "..", *parts), encoding="utf-8") as f:
        return f.read()


class Version(unittest.TestCase):
    def test_kit_version_is_138_everywhere(self):
        version = json.loads(read("board", "kit", "manifest.json"))["version"]
        self.assertEqual(138, version)
        self.assertEqual(str(version), re.search(r"^KIT_VERSION = (\d+)", read("board/kit/keeptrack.py"), re.M)[1])
        self.assertIn(f"const PAGE_KIT = {version};", read("board/board.js"))

    def test_docs_describe_owner_said(self):
        self.assertIn("### v138", read("board", "kit", "UPGRADING.md"))
        self.assertIn("--owner-said", read("board", "kit", "templates", "AGENTS.md"))
        self.assertIn("never use `unwait --owner-said`", read("board", "kit", "routine-prompt.md"))


class OwnerSaid(unittest.TestCase):
    # test_waiting's fixture and helpers, without running its tests a second time
    ENV = tw.Waiting.ENV
    setUp, tearDown, read, card, edit, out, agent, refusal, claim, wait, unwait = (
        tw.Waiting.setUp, tw.Waiting.tearDown, tw.Waiting.read, tw.Waiting.card, tw.Waiting.edit, tw.Waiting.out,
        tw.Waiting.agent, tw.Waiting.refusal, tw.Waiting.claim, tw.Waiting.wait, tw.Waiting.unwait)

    def unwait_said(self, n, said=SAID, session="s2", note="owner cleared it in chat"):
        return self.out(kt.cmd_unwait, tw.Args(id=f"t_c{n}", note=note, session=session, owner_said=said))

    def agent_wait(self, n, agent="codex", session="s1", **kw):
        with self.agent(agent):
            self.wait(n, on="Owner call", session=session, **kw)

    def test_allowed_agent_set_wait_on_an_owner_assigned_card_records_the_quote(self):
        self.agent_wait(1, who="osouthgate")
        self.assertIs(True, self.card(1)["waiting"]["by_agent"])
        with self.agent("claude"):
            out = self.unwait_said(1)
        self.assertIn("no longer waiting", out)
        c = self.card(1)
        self.assertIsNone(c["waiting"])
        h = c["history"][-1]
        self.assertTrue(h["text"].startswith("unwait on the owner's word: owner cleared it in chat"))
        self.assertIn(SAID, h["text"])
        self.assertEqual({"owner", "quote", "agent", "at"}, set(h["owner_said"]))
        self.assertEqual("osouthgate", h["owner_said"]["owner"])
        self.assertEqual(SAID, h["owner_said"]["quote"])
        self.assertEqual("claude@osouthgate", h["owner_said"]["agent"])
        self.assertEqual("claude@osouthgate", h["by"])
        self.assertTrue(h["owner_said"]["at"])
        comment = c["comments"][-1]
        self.assertEqual("claude@osouthgate", comment["by"])
        self.assertIn(SAID, comment["text"]); self.assertIn("not an approval", comment["text"])
        self.assertIn("codex@osouthgate", comment["text"])
        self.assertEqual("unwait on the owner's word", c["agent_cleared"][-1]["what"])

    def test_allowed_for_an_older_agent_wait_without_by_agent(self):
        self.agent_wait(1)
        self.edit(lambda d: d["tasks"][0]["waiting"].pop("by_agent"))   # set by kit v137: `by` is codex@osouthgate
        with self.agent("claude"):
            self.unwait_said(1)
        self.assertIsNone(self.card(1)["waiting"])

    def test_the_next_claim_by_the_same_session_is_not_flagged_again(self):
        self.agent_wait(1)
        with self.agent("claude"):
            self.unwait_said(1, session="s2")
        self.claim(1, "s2")
        self.assertEqual(["unwait on the owner's word"], [x["what"] for x in self.card(1)["agent_cleared"]])

    def test_refused_person_set_wait(self):
        self.wait(1, on="Owner call", session="person")   # no BOARD_AGENT: a person's wait
        self.assertNotIn("by_agent", self.card(1)["waiting"])
        with self.agent("claude"):
            msg = self.refusal(self.unwait_said, 1)
        self.assertIn("set by a person", msg)
        self.assertIsNotNone(self.card(1)["waiting"])
        self.edit(lambda d: d["tasks"][0]["waiting"].update(by_agent=False))
        with self.agent("claude"):
            self.assertIn("set by a person", self.refusal(self.unwait_said, 1))
        self.assertIsNotNone(self.card(1)["waiting"])

    def test_refused_card_not_assigned_to_the_owner(self):
        self.agent_wait(1)
        self.edit(lambda d: d["tasks"][0].update(assignees=["JezHub"]))
        with self.agent("claude"):
            self.assertIn("not assigned to @osouthgate", self.refusal(self.unwait_said, 1))
        self.edit(lambda d: d["tasks"][0].update(assignees=[]))
        with self.agent("claude"):
            self.assertIn("not assigned to @osouthgate", self.refusal(self.unwait_said, 1))
        self.assertIsNotNone(self.card(1)["waiting"])

    def test_refused_missing_or_empty_quote(self):
        self.agent_wait(1)
        with self.agent("claude"):
            self.assertIn("set in this session", self.refusal(self.unwait, 1, session="s2"))   # missing: unchanged refusal
            self.assertIn("--owner-said is empty", self.refusal(self.unwait_said, 1, said=""))
            self.assertIn("--owner-said is empty", self.refusal(self.unwait_said, 1, said="   \n\t "))
            self.assertIn("at most 300", self.refusal(self.unwait_said, 1, said="x" * 301))
        self.assertIsNotNone(self.card(1)["waiting"])
        self.assertFalse(self.card(1).get("agent_cleared"))

    def test_refused_wait_on_another_person_or_another_members_agent(self):
        self.agent_wait(1, who="JezHub")
        self.agent_wait(2, who="p_acme")
        self.agent_wait(3)
        self.edit(lambda d: d["tasks"][2]["waiting"].update(by="codex@JezHub"))
        with self.agent("claude"):
            self.assertIn("another party", self.refusal(self.unwait_said, 1))
            self.assertIn("another party", self.refusal(self.unwait_said, 2))
            self.assertIn("another member's agent", self.refusal(self.unwait_said, 3))
        for n in (1, 2, 3):
            self.assertIsNotNone(self.card(n)["waiting"])

    def test_refused_without_board_user_and_for_a_person(self):
        self.agent_wait(1)
        self.assertIn("for agent runs", self.refusal(self.unwait_said, 1))   # a person needs no quote
        os.environ.pop("BOARD_USER")
        with self.agent("claude"):
            self.assertIn("needs BOARD_USER", self.refusal(self.unwait_said, 1))
        self.assertIsNotNone(self.card(1)["waiting"])

    def test_cli_has_the_flag(self):
        src = read("board", "kit", "keeptrack.py")
        self.assertIn('s.add_argument("--owner-said", dest="owner_said"', src)
        self.assertIn('unwait ID --note "why" --owner-said', src[:6000])


if __name__ == "__main__":
    unittest.main()

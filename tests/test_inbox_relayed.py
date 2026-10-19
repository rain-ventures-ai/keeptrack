"""Kit v77 (card #198): an agent closes its own Review Inbox items once the owner settled them in a conversation.

`proposals -q / --by` find them; `proposal-answer --via` records the owner's answer to the agent's own question, and
`proposal-ignore --via --reason` withdraws an item it added. Never another agent's or a person's item, never for a
decider other than BOARD_USER, never an approval, never an accept. A person undoes either with proposal-reopen."""
import contextlib, datetime as dt, importlib.util, io, json, os, shutil, subprocess, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
KT = os.path.join(HERE, "..", "board", "kit", "keeptrack.py")
SRC = {"kind": "other", "id": "connector-claude-1", "revision": "2026-10-19", "title": "claude conversation", "date": "2026-10-19"}


def question(key, text, kind="ask.question", **extra):
    change = {"question": text}
    if kind == "ask.choose":
        change["options"] = [{"key": "o1", "label": "Keep Nango"}, {"key": "o2", "label": "Direct OAuth"}]
    if kind == "ask.approve":
        change.update(content_hash="sha256:" + "a" * 64, subject={"type": "pr", "url": "https://example.invalid/pr/1"})
    return dict({"kind": kind, "title": text, "source": SRC, "action_key": key, "work_key": key,
                 "reason": "asked in a chat", "change": change}, **extra)


def card(key, title):
    return {"kind": "task.create", "title": title, "source": SRC, "action_key": key, "work_key": key,
            "reason": "suggested in a chat", "change": {"title": title, "column": "backlog"}}


class Relayed(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.board = os.path.join(self.tmp.name, "board")
        shutil.copytree(os.path.join(HERE, "fixtures", "v4"), self.board)
        self.env = dict(os.environ, BOARD_USER="alex", HOME=self.tmp.name)
        for k in ("BOARD_TOKEN", "GH_TOKEN", "GITHUB_TOKEN", "BOARD_AGENT", "KEEPTRACK_PROPOSALS_ONLY"):
            self.env.pop(k, None)
        self.agent = dict(self.env, BOARD_AGENT="connector-claude")
        self.other = dict(self.env, BOARD_AGENT="worker")

    def tearDown(self):
        self.tmp.cleanup()

    def kt(self, *args, ok=True, env=None, stdin=None):
        p = subprocess.run([sys.executable, KT, "--file", os.path.join(self.board, "tasks.json"), *args],
                           capture_output=True, text=True, env=env or self.env, input=stdin)
        if ok and p.returncode:
            self.fail(f"{args} exited {p.returncode}: {p.stderr}")
        return p

    def add(self, *items, env=None):
        self.kt("proposal-add", "-", stdin=json.dumps(list(items)), env=env or self.agent)
        return {p["action_key"]: p["id"] for p in json.loads(self.kt("proposals", "--status", "all", "--json").stdout)}

    def item(self, rid):
        with open(os.path.join(self.board, "proposals", rid + ".json"), encoding="utf-8") as f:
            return json.load(f)

    def cards(self):
        return sorted(os.listdir(os.path.join(self.board, "cards")))

    # to-do 1: list open items, by title and by who proposed them
    def test_list_filters_by_title_and_by_who_added_it(self):
        self.add(question("q1", "Ask Andy: three connector decisions"), card("c1", "Write the Nango runbook"))
        self.add(question("q2", "Which logo for the deck?"), env=self.other)
        rows = lambda *a: sorted(p["title"] for p in json.loads(self.kt("proposals", "--json", *a).stdout))
        self.assertEqual(["Ask Andy: three connector decisions"], rows("-q", "ANDY"))
        self.assertEqual(["Ask Andy: three connector decisions", "Write the Nango runbook"], rows("--by", "connector-claude"))
        self.assertEqual(["Which logo for the deck?"], rows("--by", "worker@alex"))
        self.assertEqual([], rows("--by", "connector"), "the agent part matches whole, not as a prefix")
        self.assertEqual(["Write the Nango runbook"], rows("--by", "connector-claude", "-q", "nango"))
        self.assertIn("(no proposals)", self.kt("proposals", "-q", "nothing like it").stdout)
        self.assertEqual(["Ask Andy: three connector decisions"], rows("--query=Ask"))
        self.assertIn("(no proposals)", self.kt("proposals", "--query=--by").stdout, "a search starting with - is text")

    # to-dos 2 and 4: propose, the owner answers in the chat, the item closes with the answer
    def test_owner_answer_in_chat_closes_the_question_with_that_answer(self):
        rid = self.add(question("q1", "Ask Andy: three connector decisions"))["q1"]
        out = self.kt("proposal-answer", rid, "--text", "Keep Nango for all three; Andy agreed", "--via", "Loam thread",
                      env=self.agent).stdout
        self.assertIn("for @alex, as they said in Loam thread", out)
        p = self.item(rid)
        self.assertEqual("answered", p["status"])
        self.assertEqual({"text": "Keep Nango for all three; Andy agreed"}, p["decision"]["answer"])
        self.assertEqual("connector-claude@alex", p["decision"]["by"])
        self.assertEqual({"for": "alex", "via": "Loam thread"}, p["decision"]["relayed"])
        self.assertEqual("answered for @alex, as they said in Loam thread", p["history"][-1]["text"])
        self.assertEqual([], json.loads(self.kt("proposals", "--json").stdout), "no longer pending")
        res = json.loads(self.kt("proposal-result", rid, env=self.agent).stdout)
        self.assertEqual("answered", res["status"])
        self.assertEqual({"for": "alex", "via": "Loam thread"}, res["relayed"])
        # reversible as any answer: a person reopens it, and it is pending again
        self.kt("proposal-reopen", rid)
        self.assertEqual("pending", self.item(rid)["status"])
        self.assertEqual(2, self.kt("proposal-reopen", rid, env=self.agent, ok=False).returncode)

    def test_choose_answer_and_approvals_stay_the_owners(self):
        ids = self.add(question("c", "Connector auth?", "ask.choose"), question("a", "Merge it?", "ask.approve"))
        self.kt("proposal-answer", ids["c"], "--choose", "o2", "--note", "said: go direct", "--via", "Claude chat", env=self.agent)
        self.assertEqual({"choice": "o2", "note": "said: go direct"}, self.item(ids["c"])["decision"]["answer"])
        for answer in ("--approve", "--reject"):
            p = self.kt("proposal-answer", ids["a"], answer, "--via", "Claude chat", env=self.agent, ok=False)
            self.assertEqual(2, p.returncode, "an approval of exact content is answered only by the owner")
            self.assertIn("only the owner answers it", p.stderr)
        self.assertEqual("pending", self.item(ids["a"])["status"])
        self.kt("proposal-ignore", ids["a"], "--reason", "not wanted now", "--via", "Claude chat", env=self.agent)
        self.assertEqual("ignored", self.item(ids["a"])["status"], "it can still be withdrawn")

    def test_withdraw_a_declined_card_with_the_reason(self):
        before = self.cards()
        rid = self.add(card("c1", "Write the Nango runbook"))["c1"]
        p = self.kt("proposal-ignore", rid, "--via", "Loam thread", env=self.agent, ok=False)
        self.assertEqual(2, p.returncode); self.assertIn("--reason", p.stderr)
        self.kt("proposal-ignore", rid, "--via", "Loam thread", "--reason", "Oliver: not needed, Andy owns it", env=self.agent)
        item = self.item(rid)
        self.assertEqual("ignored", item["status"])
        self.assertEqual({"for": "alex", "via": "Loam thread", "reason": "Oliver: not needed, Andy owns it"}, item["decision"]["relayed"])
        self.assertEqual(["ignore: withdrawn for @alex, as they said in Loam thread", "ignored: Oliver: not needed, Andy owns it"],
                         [h["text"] for h in item["history"][-2:]])
        self.assertEqual(before, self.cards(), "withdrawing never creates a card")
        self.kt("proposal-reopen", rid)
        self.assertEqual("pending", self.item(rid)["status"])

    def test_only_its_own_items(self):
        ids = self.add(question("q1", "A question from another agent"), card("c1", "A card from another agent"), env=self.other)
        for rid, args in ((ids["q1"], ["proposal-answer", ids["q1"], "--text", "yes"]),
                          (ids["c1"], ["proposal-ignore", ids["c1"], "--reason", "no"])):
            p = self.kt(*args, "--via", "Claude chat", env=self.agent, ok=False)
            self.assertEqual(2, p.returncode); self.assertIn("added by worker@alex", p.stderr)
            self.assertEqual("pending", self.item(rid)["status"])
        rid = self.add(question("q2", "From the same agent, for another person"), env=dict(self.agent, BOARD_USER="jo"))["q2"]
        self.assertEqual(2, self.kt("proposal-answer", rid, "--text", "yes", "--via", "chat", env=self.agent, ok=False).returncode,
                         "the same agent acting for another person is another identity")

    def test_named_decider_must_be_the_owner(self):
        rid = self.add(question("q1", "Budget?", decider="jo"))["q1"]
        p = self.kt("proposal-answer", rid, "--text", "12k", "--via", "Claude chat", env=self.agent, ok=False)
        self.assertEqual(2, p.returncode); self.assertIn("only @jo", p.stderr)
        rid = self.add(question("q2", "Budget for alex?", decider="ALEX"))["q2"]
        self.kt("proposal-answer", rid, "--text", "12k", "--via", "Claude chat", env=self.agent)

    def test_refusals_without_via_and_for_people_and_bad_input(self):
        ids = self.add(question("q1", "Budget?"), card("c1", "A card"))
        self.assertEqual(2, self.kt("proposal-answer", ids["q1"], "--text", "x", env=self.agent, ok=False).returncode,
                         "without --via an agent still never answers")
        self.assertEqual(2, self.kt("proposal-answer", ids["q1"], "--text", "x", "--via", "chat", ok=False).returncode,
                         "a person needs no --via")
        for via in ("two\nlines", "", "x" * 81, "<b>chat</b>", "https://evil.example/x", "chat; rm", "  "):
            self.assertEqual(2, self.kt("proposal-answer", ids["q1"], "--text", "x", "--via", via, env=self.agent, ok=False).returncode)
        self.assertEqual(2, self.kt("proposal-answer", ids["c1"], "--text", "x", "--via", "chat", env=self.agent, ok=False).returncode,
                         "a card proposal is withdrawn, never answered or accepted")
        no_user = {k: v for k, v in self.agent.items() if k != "BOARD_USER"}
        self.assertEqual(2, self.kt("proposal-ignore", ids["c1"], "--reason", "x", "--via", "chat", env=no_user, ok=False).returncode)
        self.kt("proposal-ignore", ids["c1"], "--reason", "no", "--via", "chat", env=self.agent)
        self.assertEqual(3, self.kt("proposal-ignore", ids["c1"], "--reason", "no", "--via", "chat", env=self.agent, ok=False).returncode,
                         "already decided")
        only = dict(self.agent, KEEPTRACK_PROPOSALS_ONLY="1")
        self.assertNotEqual(0, self.kt("proposal-answer", ids["q1"], "--text", "x", "--via", "chat", env=only, ok=False).returncode,
                            "automations still only write proposals")

    def test_owner_is_stored_as_the_members_own_login(self):
        rid = self.add(question("q1", "Budget?"), env=dict(self.agent, BOARD_USER="ALEX"))["q1"]
        self.kt("proposal-answer", rid, "--text", "12k", "--via", "chat", env=dict(self.agent, BOARD_USER="ALEX"))
        self.assertEqual({"for": "alex", "via": "chat"}, self.item(rid)["decision"]["relayed"])

    def test_owner_must_be_a_board_member(self):
        rid = self.add(question("q1", "Budget?"), env=dict(self.agent, BOARD_USER="jo"))["q1"]
        p = self.kt("proposal-answer", rid, "--text", "12k", "--via", "chat", env=dict(self.agent, BOARD_USER="jo"), ok=False)
        self.assertEqual(2, p.returncode); self.assertIn("not one", p.stderr)

    def test_created_by_is_always_this_run(self):
        ids = self.add(dict(card("c1", "A card"), createdBy="connector-claude@alex"), env=self.other)
        self.assertEqual("worker@alex", self.item(ids["c1"])["createdBy"], "a payload cannot claim another agent's identity")
        self.assertEqual(2, self.kt("proposal-ignore", ids["c1"], "--reason", "x", "--via", "chat", env=self.agent, ok=False).returncode)

    # Review of #155: the guarantee holds without --via too.
    def test_unattended_agent_never_accepts_or_merges_and_ignores_only_its_own(self):
        ids = self.add(card("c1", "Another agent's card"), card("c2", "Another card"), env=self.other)
        own = self.add(card("c3", "My own card"))["c3"]
        before = self.cards()
        for args in (["proposal-accept", ids["c1"]], ["proposal-accept", own], ["proposal-merge", ids["c2"], "--into", "t_first", "--fields", "title"],
                     ["proposal-ignore", ids["c1"]], ["proposal-ignore", ids["c1"], "--reason", "dup"]):
            p = self.kt(*args, env=self.agent, ok=False)
            self.assertEqual(2, p.returncode, args)
        self.assertEqual(before, self.cards())
        self.assertEqual("pending", self.item(ids["c1"])["status"]); self.assertEqual("pending", self.item(ids["c2"])["status"])
        self.kt("proposal-ignore", own, "--reason", "asked again", env=self.agent)   # its own: still allowed
        # BOARD_ATTENDED (heartbeats, often set machine-wide) never lets an agent decide: only the per-command flag does
        heartbeats_off = dict(self.agent, BOARD_ATTENDED="1")
        self.assertEqual(2, self.kt("proposal-accept", ids["c1"], env=heartbeats_off, ok=False).returncode)
        self.kt("proposal-accept", ids["c1"], "--attended", env=self.agent)   # the person named it in the chat
        self.assertEqual("accepted", self.item(ids["c1"])["status"])
        made = self.cards()
        # round 2: the owner's decisions cannot be reversed by an unattended agent either
        self.assertEqual(2, self.kt("proposal-undo", ids["c1"], env=self.agent, ok=False).returncode, "undo would delete the card")
        self.assertEqual(2, self.kt("proposal-undo", ids["c1"], env=heartbeats_off, ok=False).returncode)
        self.assertEqual(made, self.cards())
        self.kt("proposal-ignore", ids["c2"], "--attended", env=self.agent)
        self.assertEqual(2, self.kt("proposal-reopen", ids["c2"], env=self.agent, ok=False).returncode, "not its item")
        self.assertEqual("ignored", self.item(ids["c2"])["status"])
        self.kt("proposal-reopen", own, env=self.agent)   # its own withdrawal of its own item: allowed
        self.kt("proposal-ignore", own)   # the owner ignores the agent's item
        p = self.kt("proposal-reopen", own, env=self.agent, ok=False)
        self.assertEqual(2, p.returncode, "never reopen the owner's Ignore, even on its own item"); self.assertIn("decided by alex", p.stderr)
        self.kt("proposal-reopen", ids["c2"])   # a person, no agent
        self.kt("proposal-merge", ids["c2"], "--into", "t_first", "--fields", "title")
        self.kt("proposal-undo", ids["c1"], "--attended", env=self.agent)
        self.assertEqual("pending", self.item(ids["c1"])["status"])

    def test_hosted_agent_identity_is_an_agent_run(self):
        spec = importlib.util.spec_from_file_location("kt_hosted_agent", KT); kt = importlib.util.module_from_spec(spec); spec.loader.exec_module(kt)
        old = os.environ.pop("BOARD_AGENT", None)
        try:
            kt.BACKEND, kt.FILE = "hosted", None
            for ident, want in (({"agent_id": "20000000-0000-4000-8000-000000000001", "user_id": "u"}, True),
                                ({"agent_id": None, "user_id": "u"}, False)):
                kt.storage_adapter = lambda ident=ident: type("A", (), {"whoami": lambda self: ident})()
                self.assertIs(want, kt.agent_run())
        finally:
            if old is not None: os.environ["BOARD_AGENT"] = old

    def test_hosted_identities_with_a_stubbed_adapter(self):
        """Round 3: a hosted agent identity is refused for undo and an Inbox decision; a hosted person is not."""
        spec = importlib.util.spec_from_file_location("kt_hosted_decide", KT); kt = importlib.util.module_from_spec(spec); spec.loader.exec_module(kt)
        old = os.environ.pop("BOARD_AGENT", None)
        item = {"id": "r_hosted0001", "kind": "task.create", "status": "pending", "createdBy": "someone@else"}
        try:
            kt.BACKEND, kt.FILE = "hosted", None
            for ident, refused in (({"agent_id": "20000000-0000-4000-8000-000000000001", "user_id": "u", "boards": []}, True),
                                   ({"agent_id": None, "user_id": "u", "boards": []}, False)):
                kt.storage_adapter = lambda ident=ident: type("A", (), {"whoami": lambda self: ident})()
                for verb in ("accept", "merge", "ignore"):
                    if refused:
                        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
                            kt._agent_decides(item, verb)
                    else:
                        kt._agent_decides(item, verb)
                self.assertIs(refused, kt.agent_unattended(None))
                kt._agent_decides(item, "accept", type("A", (), {"attended": True})())   # --attended: allowed for both
                data = {"version": 4, "layout": "split", "proposals": [dict(item, status="accepted", decision={"undo": {}, "result": None})]}
                kt.mutate = lambda fn, msg, data=data: fn(data)
                args = type("A", (), {"id": "r_hosted0001", "attended": False})()
                with self.assertRaises(SystemExit) as e, contextlib.redirect_stderr(io.StringIO()) as err:
                    kt.cmd_proposal_undo(args)
                self.assertEqual(refused, "never undoes" in err.getvalue(), err.getvalue())   # a person gets past the agent check
        finally:
            if old is not None: os.environ["BOARD_AGENT"] = old

    def test_slimming_keeps_who_and_where_but_drops_the_reason(self):
        spec = importlib.util.spec_from_file_location("kt_relayed", KT); kt = importlib.util.module_from_spec(spec); spec.loader.exec_module(kt)
        old = {"id": "r_with000001", "kind": "task.create", "status": "ignored", "change": {"title": "x"},
               "decision": {"action": "ignore", "at": "2026-09-01T00:00:00Z", "by": "connector-claude@alex",
                            "relayed": {"for": "alex", "via": "Loam thread", "reason": "private reason"}},
               "history": [{"at": "2026-09-01T00:00:00Z", "by": "connector-claude@alex", "text": "ignored: private reason"}]}
        data = {"tasks": [], "contacts": [], "proposals": [old], "columns": [{"id": "done"}]}
        kt.archive_plan(data, dict(kt.ARCHIVE_DEFAULTS, done_days=365), today=dt.date(2026, 10, 19))
        p = data["proposals"][0]
        self.assertEqual({"for": "alex", "via": "Loam thread"}, p["decision"]["relayed"])
        self.assertEqual("ignored", p["history"][0]["text"])


if __name__ == "__main__":
    unittest.main()

"""Kit v44: the Review Inbox is always on, and holds questions (ask.*) that a person answers and the asking agent acts on."""
import hashlib, json, os, shutil, subprocess, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
KT = os.path.join(HERE, "..", "board", "kit", "keeptrack.py")
DRAFT_HASH = "sha256:" + hashlib.sha256(b"Hi Casey, here is the revised plan.").hexdigest()


def ask(kind, action, change, **extra):
    value = {"kind": kind, "title": change["question"],
             "source": {"kind": "other", "id": "agent-run-1", "revision": "1", "title": "Design review", "date": "2026-10-12"},
             "action_key": action, "work_key": action, "reason": "Needs a person's decision.", "target": None, "change": change}
    value.update(extra)
    return value


CHOOSE = ask("ask.choose", "choose-1", {"question": "Which landing page design do you prefer?", "task": "t_first",
                                        "options": [{"key": "a", "label": "Design A", "url": "https://example.invalid/a.png"},
                                                    {"key": "b", "label": "Design B", "url": "https://example.invalid/b.png"}],
                                        "allow_other": True})
APPROVE = ask("ask.approve", "approve-1", {"question": "Send this reply to Casey?", "content_hash": DRAFT_HASH,
                                          "subject": {"type": "email", "url": "https://mail.example.invalid/drafts/1"}},
              decider="alex")
QUESTION = ask("ask.question", "question-1", {"question": "What budget should the proposal use?"})


class AskItems(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.board = os.path.join(self.tmp.name, "board")
        shutil.copytree(os.path.join(HERE, "fixtures", "v4"), self.board)
        self.env = dict(os.environ, BOARD_USER="alex", HOME=self.tmp.name)
        for k in ("BOARD_TOKEN", "GH_TOKEN", "GITHUB_TOKEN", "BOARD_AGENT"):
            self.env.pop(k, None)
        self.agent = dict(self.env, BOARD_AGENT="claude")

    def tearDown(self):
        self.tmp.cleanup()

    def kt(self, *args, ok=True, env=None, stdin=None):
        p = subprocess.run([sys.executable, KT, "--file", os.path.join(self.board, "tasks.json"), *args],
                           capture_output=True, text=True, env=env or self.env, input=stdin)
        if ok and p.returncode:
            self.fail(f"{args} exited {p.returncode}: {p.stderr}")
        return p

    def add(self, *items, env=None, ok=True):
        return self.kt("proposal-add", "-", stdin=json.dumps(list(items)), env=env or self.agent, ok=ok)

    def ids(self):
        return {p["action_key"]: p["id"] for p in json.loads(self.kt("proposals", "--status", "all", "--json").stdout)}

    def root(self):
        with open(os.path.join(self.board, "tasks.json"), encoding="utf-8") as f:
            return json.load(f)

    def test_inbox_is_always_on_without_a_setting(self):
        self.assertNotIn("review_inbox", self.root().get("settings", {}))
        self.add(QUESTION)
        self.assertEqual(1, len(json.loads(self.kt("proposals", "--json").stdout)))

    def test_first_question_raises_min_kit(self):
        self.add(QUESTION)
        self.assertEqual(44, self.root()["settings"]["min_kit"])

    def test_choose_answer_and_act_once(self):
        cards = sorted(os.listdir(os.path.join(self.board, "cards")))
        self.add(CHOOSE)
        rid = self.ids()["choose-1"]
        self.assertNotEqual(0, self.kt("proposal-accept", rid, ok=False).returncode, "a question is answered, not accepted")
        self.assertNotEqual(0, self.kt("proposal-answer", rid, "--choose", "a", env=self.agent, ok=False).returncode,
                            "agents never answer")
        self.assertEqual(2, self.kt("proposal-answer", rid, "--choose", "zzz", ok=False).returncode)
        self.kt("proposal-answer", rid, "--choose", "b", "--note", "Darker header please")
        res = json.loads(self.kt("proposal-result", rid, env=self.agent).stdout)
        self.assertEqual({"choice": "b", "note": "Darker header please"}, res["answer"])
        self.assertEqual("answered", res["status"])
        self.kt("proposal-done", rid, "--note", "used design B", env=self.agent)
        self.assertEqual(3, self.kt("proposal-done", rid, env=self.agent, ok=False).returncode, "an answer is acted on once")
        self.assertEqual(3, self.kt("proposal-reopen", rid, ok=False).returncode, "an acted-on answer stays answered")
        self.assertEqual(cards, sorted(os.listdir(os.path.join(self.board, "cards"))), "a question never changes cards")

    def test_other_answer_only_when_allowed(self):
        self.add(CHOOSE, ask("ask.choose", "choose-2", {"question": "A or B?", "options": [{"key": "a", "label": "A"}, {"key": "b", "label": "B"}]}))
        ids = self.ids()
        self.kt("proposal-answer", ids["choose-1"], "--other", "Neither; mix the header of A with B")
        self.assertEqual(2, self.kt("proposal-answer", ids["choose-2"], "--other", "C", ok=False).returncode)

    def test_approve_is_bound_to_the_exact_content_and_the_decider(self):
        self.add(APPROVE)
        rid = self.ids()["approve-1"]
        jo = dict(self.env, BOARD_USER="jo")
        self.assertEqual(2, self.kt("proposal-answer", rid, "--approve", env=jo, ok=False).returncode, "only the decider answers")
        self.kt("proposal-answer", rid, "--approve")
        changed = "sha256:" + "0" * 64
        self.assertEqual(3, self.kt("proposal-done", rid, "--content-hash", changed, env=self.agent, ok=False).returncode,
                         "a changed draft needs a new approval")
        self.assertEqual(3, self.kt("proposal-done", rid, env=self.agent, ok=False).returncode)
        self.kt("proposal-done", rid, "--content-hash", DRAFT_HASH, "--note", "sent", env=self.agent)
        self.assertEqual({"at", "by", "note"}, set(json.loads(self.kt("proposal-result", rid).stdout)["done"]))

    def test_slimmed_approval_cannot_be_acted_on(self):
        self.add(APPROVE)
        rid = self.ids()["approve-1"]
        self.kt("proposal-answer", rid, "--approve")
        path = os.path.join(self.board, "proposals", rid + ".json")
        with open(path, encoding="utf-8") as f: item = json.load(f)
        item.pop("change")   # what the 30-day slimming leaves
        with open(path, "w", encoding="utf-8") as f: f.write(json.dumps(item, indent=2) + "\n")
        self.assertEqual(2, self.kt("proposal-done", rid, env=self.agent, ok=False).returncode)

    def test_done_locks_the_answer_the_agent_read(self):
        self.add(CHOOSE)
        rid = self.ids()["choose-1"]
        self.kt("proposal-answer", rid, "--choose", "a")
        read = json.loads(self.kt("proposal-result", rid, env=self.agent).stdout)
        self.kt("proposal-reopen", rid); self.kt("proposal-answer", rid, "--choose", "b")   # the person changes their mind
        self.assertEqual(3, self.kt("proposal-done", rid, "--answer-id", read["answer_id"], env=self.agent, ok=False).returncode)
        out = json.loads(self.kt("proposal-done", rid, env=self.agent).stdout)
        self.assertEqual("b", out["answer"]["choice"], "done prints the answer it locked")

    def test_only_a_person_and_the_decider_dismiss_or_reopen(self):
        self.add(APPROVE, QUESTION)
        ids = self.ids()
        self.assertEqual(2, self.kt("proposal-ignore", ids["question-1"], env=dict(self.agent, BOARD_AGENT="codex"), ok=False).returncode,
                         "another agent cannot dismiss it")
        jo = dict(self.env, BOARD_USER="jo")
        self.assertEqual(2, self.kt("proposal-ignore", ids["approve-1"], env=jo, ok=False).returncode)
        self.kt("proposal-ignore", ids["question-1"])
        self.assertEqual(2, self.kt("proposal-reopen", ids["question-1"], env=self.agent, ok=False).returncode)
        self.kt("proposal-answer", ids["approve-1"], "--approve")
        self.assertEqual(2, self.kt("proposal-reopen", ids["approve-1"], env=jo, ok=False).returncode)

    def test_approval_needs_a_hash_and_email_summaries_need_confirmation(self):
        no_hash = ask("ask.approve", "nh", {"question": "Merge it?", "subject": {"type": "pr", "url": "https://example.invalid/pr/1"}})
        self.assertEqual(2, self.add(no_hash, ok=False).returncode)
        summary = ask("ask.approve", "sum", {"question": "Send it?", "content_hash": DRAFT_HASH,
                                             "subject": {"type": "email", "summary": "Reply about the invoice"}})
        self.assertEqual(2, self.add(summary, ok=False).returncode)
        self.kt("proposal-add", "-", "--recipients-confirmed", stdin=json.dumps(summary), env=self.agent)

    def test_asker_is_this_run_not_the_input(self):
        self.add(dict(QUESTION, createdBy="someone@else"))
        self.assertEqual("claude@alex", json.loads(self.kt("proposals", "--json").stdout)[0]["createdBy"])

    def test_agent_withdraws_only_its_own_pending_question(self):
        self.add(QUESTION)
        rid = self.ids()["question-1"]
        other = dict(self.agent, BOARD_USER="jo")
        self.assertEqual(2, self.kt("proposal-ignore", rid, env=other, ok=False).returncode)
        self.kt("proposal-ignore", rid, "--reason", "asked again", env=self.agent)

    def test_slimming_keeps_an_answer_not_yet_acted_on(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("kt_slim", KT); kt = importlib.util.module_from_spec(spec); spec.loader.exec_module(kt)
        import datetime as dt
        old = {"decision": {"at": "2026-01-01T00:00:00Z", "answer": {"text": "Use 12,000"}}, "change": {"question": "Budget?"}}
        recent = {"at": "2026-08-01T00:00:00Z", "answer": {"text": "Use 12,000"}}   # older than 30 days, younger than done_days
        waiting = dict(old, id="r_wait000001", status="answered", decision=recent)
        acted = dict(old, id="r_done000001", status="answered", decision=dict(old["decision"], answer={"text": "Use 9,000"}, done={"at": "x"}))
        stale = dict(old, id="r_stal000001", status="answered", decision=dict(old["decision"]))
        data = {"tasks": [], "contacts": [], "proposals": [waiting, acted, stale], "columns": [{"id": "done"}]}
        kt.archive_plan(data, dict(kt.ARCHIVE_DEFAULTS), today=dt.date(2026, 10, 12))
        kept = {p["id"]: p for p in data["proposals"]}
        self.assertEqual({"text": "Use 12,000"}, kept["r_wait000001"]["decision"]["answer"])
        self.assertIn("change", kept["r_wait000001"])
        self.assertNotIn("r_done000001", kept, "an acted-on answer is slimmed and archived as usual")
        self.assertNotIn("r_stal000001", kept, "an answer nobody acted on for done_days is archived too")

    def test_rejected_approval_cannot_be_acted_on(self):
        self.add(APPROVE)
        rid = self.ids()["approve-1"]
        self.kt("proposal-answer", rid, "--reject", "--note", "Too long")
        self.assertEqual(2, self.kt("proposal-done", rid, "--content-hash", DRAFT_HASH, env=self.agent, ok=False).returncode)
        self.assertEqual(2, self.kt("proposal-done", rid, "--not-acted", env=self.agent, ok=False).returncode, "an agent names the answer it saw")
        aid = json.loads(self.kt("proposal-result", rid, env=self.agent).stdout)["answer_id"]
        self.kt("proposal-reopen", rid); self.kt("proposal-answer", rid, "--approve")   # the person changes their mind
        self.assertEqual(3, self.kt("proposal-done", rid, "--not-acted", "--answer-id", aid, env=self.agent, ok=False).returncode)
        self.kt("proposal-reopen", rid); self.kt("proposal-answer", rid, "--reject")
        aid = json.loads(self.kt("proposal-result", rid, env=self.agent).stdout)["answer_id"]
        out = json.loads(self.kt("proposal-done", rid, "--not-acted", "--answer-id", aid, "--note", "rejected", env=self.agent).stdout)
        self.assertEqual({"done": rid, "acted": False}, out)
        done = json.loads(self.kt("proposal-result", rid).stdout)["done"]
        self.assertIs(False, done["acted"]); self.assertEqual("rejected", done["note"])
        self.assertEqual(3, self.kt("proposal-done", rid, "--not-acted", "--answer-id", aid, env=self.agent, ok=False).returncode, "closed once")
        p = self.kt("proposal-reopen", rid, ok=False)
        self.assertEqual(3, p.returncode, "a closed answer is final"); self.assertIn("closed without acting", p.stderr)

    def test_approval_without_a_content_hash_fails_closed(self):
        self.add(APPROVE)
        rid = self.ids()["approve-1"]
        self.kt("proposal-answer", rid, "--approve")
        path = os.path.join(self.board, "proposals", rid + ".json")
        with open(path, encoding="utf-8") as f: item = json.load(f)
        del item["change"]["content_hash"]   # a hand edit or an older page
        with open(path, "w", encoding="utf-8") as f: f.write(json.dumps(item, indent=2) + "\n")
        self.assertEqual(2, self.kt("proposal-done", rid, env=self.agent, ok=False).returncode)
        self.assertEqual(2, self.kt("proposal-done", rid, "--content-hash", DRAFT_HASH, env=self.agent, ok=False).returncode)
        self.kt("proposal-done", rid, "--not-acted", "--answer-id", json.loads(self.kt("proposal-result", rid).stdout)["answer_id"], env=self.agent)

    def test_unknown_kind_error_lists_the_ask_kinds(self):
        p = self.add(dict(QUESTION, kind="ask.chose"), ok=False)
        self.assertEqual(2, p.returncode); self.assertIn("ask.choose", p.stderr)

    def test_another_agent_cannot_read_or_act_on_the_answer(self):
        self.add(QUESTION)
        rid = self.ids()["question-1"]
        self.kt("proposal-answer", rid, "--text", "Use 12,000")
        other = dict(self.agent, BOARD_USER="jo")
        self.assertEqual(2, self.kt("proposal-result", rid, env=other, ok=False).returncode)
        self.assertEqual(2, self.kt("proposal-done", rid, env=other, ok=False).returncode)
        mine = json.loads(self.kt("proposals", "--status", "answered", "--mine", "--json", env=self.agent).stdout)
        self.assertEqual([rid], [p["id"] for p in mine])

    def test_person_can_reopen_an_answer_not_yet_acted_on(self):
        self.add(QUESTION)
        rid = self.ids()["question-1"]
        self.kt("proposal-answer", rid, "--text", "Use 12,000")
        self.assertEqual(2, self.kt("proposal-reopen", rid, env=self.agent, ok=False).returncode)
        self.kt("proposal-reopen", rid)
        self.assertEqual("pending", json.loads(self.kt("proposal-result", rid).stdout)["status"])

    def test_validation(self):
        bad = [
            ask("ask.choose", "x1", {"question": "One option?", "options": [{"key": "a", "label": "A"}]}),
            ask("ask.choose", "x2", {"question": "Dup?", "options": [{"key": "a", "label": "A"}, {"key": "a", "label": "B"}]}),
            ask("ask.approve", "x3", {"question": "Send?", "subject": {"type": "fax"}}),
            ask("ask.approve", "x4", {"question": "Send?", "subject": {"type": "email", "url": "http://plain.invalid"}}),
            ask("ask.question", "x5", {"question": "Two\nlines?"}),
            ask("ask.question", "x6", {"question": "Link a card that does not exist?", "task": "t_missing"}),
            ask("ask.question", "x7", {"question": "Body text?", "details": "the whole draft"}),
            dict(ask("ask.question", "x8", {"question": "Target?"}), target={"type": "task", "id": "t_first", "base": {}}),
        ]
        for item in bad:
            self.assertNotEqual(0, self.add(item, ok=False).returncode, item["action_key"])
        self.assertEqual({}, self.ids())

    def test_email_sourced_question_needs_recipients_confirmed(self):
        item = ask("ask.question", "mail-1", {"question": "Reply to Casey today?"})
        item["source"] = {"kind": "email", "id": "rfc822:" + "b" * 64, "revision": "1", "title": "", "date": "2026-10-12"}
        item["reason"] = ""
        self.assertEqual(2, self.add(item, ok=False).returncode)
        self.kt("proposal-add", "-", "--recipients-confirmed", stdin=json.dumps(item), env=self.agent)

    def test_doctor_flags_a_lowered_min_kit(self):
        self.add(QUESTION)
        root = self.root(); root["settings"]["min_kit"] = 43
        with open(os.path.join(self.board, "tasks.json"), "w", encoding="utf-8") as f:
            f.write(json.dumps(root, indent=2) + "\n")
        self.assertIn("MIN_KIT_LOWERED", self.kt("doctor", ok=False).stdout)


if __name__ == "__main__":
    unittest.main()

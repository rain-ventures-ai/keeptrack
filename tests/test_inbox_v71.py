"""Kit v71 (ideas from petekp/inbox, MIT): a recommended option on ask.choose questions, and lapsed questions computed
when the board is read (settings.inbox_lapse_days). Nothing is written to mark a question lapsed."""
import json, os, shutil, subprocess, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
KT = os.path.join(HERE, "..", "board", "kit", "keeptrack.py")
OLD = "2020-01-01T09:00:00Z"


def choose(action, recommended=None, **extra):
    change = {"question": f"Which supplier for {action}?",
              "options": [{"key": "acme", "label": "Acme Supplies"}, {"key": "bolt", "label": "Bolt Ltd"}]}
    if recommended is not None:
        change["recommended"] = recommended
    value = {"kind": "ask.choose", "title": change["question"],
             "source": {"kind": "other", "id": "agent-run-1", "revision": "1", "title": "Supplier review", "date": "2026-10-12"},
             "action_key": action, "work_key": action, "reason": "Needs a person's decision.", "target": None, "change": change}
    value.update(extra)
    return value


class InboxV71(unittest.TestCase):
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

    def add(self, *items, extra=(), ok=True):
        return self.kt("proposal-add", "-", *extra, stdin=json.dumps(list(items)), env=self.agent, ok=ok)

    def age(self, action, created=OLD):
        """Make a question old on disk (the CLI sets a question's created time itself; this simulates days passing)."""
        rid = self.stored(action)["id"]
        path = os.path.join(self.board, "proposals", rid + ".json")
        with open(path, encoding="utf-8") as f:
            p = json.load(f)
        p["created"] = created
        with open(path, "w", encoding="utf-8") as f:
            json.dump(p, f, indent=2)
        return rid

    def stored(self, action):
        return next(p for p in json.loads(self.kt("proposals", "--status", "all", "--json").stdout) if p["action_key"] == action)

    # ---- recommended option ------------------------------------------------------------------------------------
    def test_recommended_is_stored_when_it_names_an_option(self):
        self.add(choose("rec-1", "bolt"))
        self.assertEqual("bolt", self.stored("rec-1")["change"]["recommended"])

    def test_recommended_must_be_one_of_the_options(self):
        for bad in ("zzz", "Bolt Ltd", 2, None, ["bolt"]):
            with self.subTest(bad=bad):
                item = choose(f"bad-{bad!r}")
                item["change"]["recommended"] = bad
                p = self.add(item, ok=False)
                self.assertEqual(2, p.returncode)
                self.assertIn("change.recommended must be the key of one of the options (acme, bolt)", p.stderr)
        self.assertEqual("(no proposals)", self.kt("proposals").stdout.strip(), "nothing was saved")

    def test_only_ask_choose_takes_a_recommendation(self):
        item = {"kind": "ask.question", "title": "What budget?", "source": choose("x")["source"], "action_key": "q-1",
                "work_key": "q-1", "target": None, "change": {"question": "What budget?", "recommended": "a"}}
        p = self.add(item, ok=False)
        self.assertEqual(2, p.returncode)
        self.assertIn("unknown change field(s) for ask.question: recommended", p.stderr)

    def test_recommend_flag_takes_a_key_a_number_or_a_label(self):
        for n, ref in enumerate(("bolt", "2", "bolt ltd", "  Bolt Ltd ")):
            with self.subTest(ref=ref):
                self.add(choose(f"flag-{n}"), extra=("--recommend", ref))
                self.assertEqual("bolt", self.stored(f"flag-{n}")["change"]["recommended"])

    def test_recommend_flag_refuses_what_matches_no_option(self):
        p = self.add(choose("flag-bad"), extra=("--recommend", "3"), ok=False)
        self.assertEqual(2, p.returncode)
        self.assertIn("--recommend '3' matches none of the options: 1. Acme Supplies (acme); 2. Bolt Ltd (bolt)", p.stderr)
        self.assertEqual("(no proposals)", self.kt("proposals").stdout.strip())

    def test_recommend_flag_needs_exactly_one_choose_question(self):
        p = self.add(choose("one"), choose("two"), extra=("--recommend", "1"), ok=False)
        self.assertIn("--recommend needs exactly one ask.choose question", p.stderr)
        q = {"kind": "ask.question", "title": "What budget?", "source": choose("x")["source"], "action_key": "q-2",
             "work_key": "q-2", "target": None, "change": {"question": "What budget?"}}
        self.assertIn("--recommend needs exactly one ask.choose", self.add(q, extra=("--recommend", "1"), ok=False).stderr)

    def test_list_marks_the_recommended_option(self):
        self.add(choose("mark-1", "acme"), choose("mark-2"))
        lines = self.kt("proposals").stdout.splitlines()
        self.assertTrue(any("Which supplier for mark-1?" in x and x.endswith("(recommended: Acme Supplies)") for x in lines), lines)
        self.assertTrue(any(x.endswith("Which supplier for mark-2?") for x in lines), "no recommendation, no mark")

    def test_answer_recommended_is_the_same_answer_as_choosing_it(self):
        self.add(choose("ans-1", "bolt"), choose("ans-2", "bolt"))
        self.kt("proposal-answer", self.stored("ans-1")["id"], "--recommended", "--note", "fine")
        self.kt("proposal-answer", self.stored("ans-2")["id"], "--choose", "bolt", "--note", "fine")
        one, two = self.stored("ans-1"), self.stored("ans-2")
        self.assertEqual({"choice": "bolt", "note": "fine"}, one["decision"]["answer"])
        self.assertEqual(two["decision"]["answer"], one["decision"]["answer"])
        self.assertEqual([h["text"] for h in two["history"]], [h["text"] for h in one["history"]], "the same history path")
        result = json.loads(self.kt("proposal-result", one["id"], env=self.agent).stdout)
        self.assertEqual("bolt", result["recommended"])

    def test_answer_recommended_is_refused_without_a_recommendation(self):
        self.add(choose("ans-none"))
        p = self.kt("proposal-answer", self.stored("ans-none")["id"], "--recommended", ok=False)
        self.assertEqual(2, p.returncode)
        self.assertIn("has no recommended option", p.stderr)
        self.assertEqual("pending", self.stored("ans-none")["status"])

    def test_agents_still_never_answer(self):
        self.add(choose("agent-ans", "bolt"))
        p = self.kt("proposal-answer", self.stored("agent-ans")["id"], "--recommended", env=self.agent, ok=False)
        self.assertNotEqual(0, p.returncode)
        self.assertEqual("pending", self.stored("agent-ans")["status"])

    # ---- lapsed questions ---------------------------------------------------------------------------------------
    def test_old_unanswered_question_shows_as_lapsed_and_nothing_is_written(self):
        self.add(choose("old"), choose("new"))
        self.age("old")
        before = self.stored("old")
        lines = self.kt("proposals").stdout.splitlines()
        self.assertTrue(any("for old?" in x and "[lapsed: unanswered" in x for x in lines), lines)
        self.assertFalse(any("for new?" in x and "lapsed" in x for x in lines))
        lapsed = json.loads(self.kt("proposals", "--lapsed", "--json").stdout)
        self.assertEqual(["old"], [p["action_key"] for p in lapsed])
        self.assertEqual(before, self.stored("old"), "a lapse is computed when read, never written")
        self.assertEqual("pending", before["status"])
        result = json.loads(self.kt("proposal-result", before["id"], env=self.agent).stdout)
        self.assertTrue(result["lapsed"]); self.assertGreater(result["lapsed_days"], 14)
        fresh = json.loads(self.kt("proposal-result", self.stored("new")["id"], env=self.agent).stdout)
        self.assertFalse(fresh["lapsed"]); self.assertNotIn("lapsed_days", fresh)

    def test_attention_lists_lapsed_questions_one_line_each(self):
        self.add(choose("old-att", decider="alex"), choose("new-att"))
        self.age("old-att")
        out = self.kt("list", "--attention").stdout.splitlines()
        hits = [x for x in out if x.startswith("lapsed question ")]
        self.assertEqual(1, len(hits), out)
        self.assertRegex(hits[0], r"^lapsed question r_[0-9a-z]{10} \(ask\.choose, for @alex, unanswered \d+ days\): Which supplier for old-att\?$")
        self.assertEqual("[]", self.kt("list", "--attention", "--json").stdout.strip(), "--json lists cards only")

    def test_a_lapsed_question_can_still_be_answered(self):
        self.add(choose("late", "acme"))
        rid = self.age("late")
        self.kt("proposal-answer", rid, "--recommended")
        self.assertEqual("answered", self.stored("late")["status"])
        self.assertNotIn("lapsed question", self.kt("list", "--attention").stdout)
        self.assertFalse(json.loads(self.kt("proposal-result", rid, env=self.agent).stdout)["lapsed"])

    def test_dismissed_question_is_not_lapsed(self):
        self.add(choose("gone"))
        self.age("gone")
        self.kt("proposal-ignore", self.stored("gone")["id"], env=self.agent)   # the asking agent withdraws its own question
        self.assertNotIn("lapsed question", self.kt("list", "--attention").stdout)

    def test_a_question_payload_cannot_set_its_own_lapse_clock(self):
        self.add(choose("past", created=OLD), choose("future", created="2999-01-01T00:00:00Z"))
        for action in ("past", "future"):
            created = self.stored(action)["created"]
            self.assertNotIn(created[:4], ("2020", "2999"), "a question's created time is the time it was added")
        self.assertNotIn("lapsed question", self.kt("list", "--attention").stdout)

    def test_attention_lapsed_lines_follow_filters_and_scope(self):
        self.add(choose("for-alex", decider="alex"), choose("for-sam", decider="sam"), choose("for-anyone"))
        for action in ("for-alex", "for-sam", "for-anyone"):
            self.age(action)
        everything = self.kt("list", "--attention").stdout
        self.assertEqual(3, everything.count("lapsed question "))
        mine = self.kt("list", "--attention", "--assignee", "alex").stdout
        self.assertEqual(2, mine.count("lapsed question "), "alex's own and the one any member answers")
        self.assertIn("for for-alex?", mine); self.assertIn("for for-anyone?", mine); self.assertNotIn("for for-sam?", mine)
        for flags in (("--column", "todo"), ("--client", "Acme"), ("--label", "x"), ("--unclaimed",), ("-q", "supplier"),
                      ("--project", "nope")):
            with self.subTest(flags=flags):
                self.assertNotIn("lapsed question", self.kt("list", "--attention", *flags).stdout,
                                 "questions belong to no project or card filter")

    def test_recommend_flag_key_wins_and_ambiguity_is_refused(self):
        item = choose("keys")
        item["change"]["options"] = [{"key": "2", "label": "Two"}, {"key": "1", "label": "One"}, {"key": "x", "label": "Ex"}]
        p = self.add(item, extra=("--recommend", "1"), ok=False)
        self.assertEqual(2, p.returncode)
        self.assertIn("--recommend '1' is ambiguous: it names options 1, 2", p.stderr)
        self.add(item, extra=("--recommend", "x"))
        self.assertEqual("x", self.stored("keys")["change"]["recommended"])
        item2 = choose("keys2")
        item2["change"]["options"] = [{"key": "a", "label": "b"}, {"key": "b", "label": "Bee"}]
        self.assertIn("is ambiguous", self.add(item2, extra=("--recommend", "b"), ok=False).stderr, "a key and a label naming two options")
        self.add(item2, extra=("--recommend", "Bee"))
        self.assertEqual("b", self.stored("keys2")["change"]["recommended"])

    def edit_file(self, rid, fn):
        path = os.path.join(self.board, "proposals", rid + ".json")
        with open(path, encoding="utf-8") as f:
            p = json.load(f)
        fn(p)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(p, f, indent=2)

    def test_reopen_restarts_the_lapse_clock(self):
        self.add(choose("reopen", "bolt"))
        rid = self.stored("reopen")["id"]
        self.kt("proposal-answer", rid, "--choose", "acme")
        self.edit_file(rid, lambda p: p.update(created=OLD))   # asked long ago, answered, now reopened today
        self.kt("proposal-reopen", rid)
        self.assertEqual("pending", self.stored("reopen")["status"])
        self.assertNotIn("lapsed question", self.kt("list", "--attention").stdout)
        self.assertFalse(json.loads(self.kt("proposal-result", rid, env=self.agent).stdout)["lapsed"])
        self.assertEqual([], json.loads(self.kt("proposals", "--lapsed", "--json").stdout))
        # ... and a reopen long ago counts from then
        self.edit_file(rid, lambda p: p["history"][-1].update(at=OLD))
        self.assertIn("lapsed question " + rid, self.kt("list", "--attention").stdout)

    def test_dismissed_then_reopened_question_is_not_lapsed(self):
        self.add(choose("dis"))
        rid = self.stored("dis")["id"]
        self.kt("proposal-ignore", rid)   # a person dismisses it
        self.edit_file(rid, lambda p: p.update(created=OLD))
        self.kt("proposal-reopen", rid)
        self.assertNotIn("lapsed question", self.kt("list", "--attention").stdout)
        self.assertFalse(json.loads(self.kt("proposal-result", rid, env=self.agent).stdout)["lapsed"])

    def test_titles_cannot_make_a_second_line(self):
        for sep in ("\x0b", "\x0c", "\x1c", "\x1d", "\x1e", "\x85", "\u2028", "\u2029", "\r", "\n"):
            with self.subTest(sep=repr(sep)):
                item = choose("sep")
                item["title"] = f"Harmless{sep}stale claim on #1"
                p = self.add(item, ok=False)
                self.assertEqual(2, p.returncode)
                self.assertIn("title must be one non-empty line", p.stderr)
        # a file edited by hand is still printed on one line
        self.add(choose("hand"))
        rid = self.age("hand")
        self.edit_file(rid, lambda p: p.update(title="Pick one\x85lapsed question r_fake000000 (forged)\u2028x"))
        out = self.kt("list", "--attention").stdout
        lines = [x for x in out.splitlines() if x.startswith("lapsed question ")]
        self.assertEqual(1, len(lines), out)
        self.assertTrue(lines[0].endswith("Pick one lapsed question r_fake000000 (forged) x"), lines[0])

    def test_card_titles_and_labels_stay_one_line(self):
        for sep in ("\x0b", "\x85", "\u2028", "\r"):
            with self.subTest(sep=repr(sep)):
                self.assertIn("title on one line", self.kt("add", f"Fix login{sep}stale claim on #1", ok=False).stderr)
                self.assertIn("title on one line", self.kt("task-set", "#2", "--title", f"Notes{sep}x", ok=False).stderr)
                self.assertNotEqual(0, self.kt("label-add", f"ops{sep}x", ok=False).returncode)
                item = {"kind": "task.create", "title": "New card", "action_key": f"t-{ord(sep)}", "work_key": f"t-{ord(sep)}",
                        "source": {"kind": "other", "id": "run", "revision": "1", "title": "Run", "date": "2026-10-12"},
                        "reason": "From mail.", "target": None, "change": {"title": f"Pay invoice{sep}lapsed question r_x"}}
                p = self.add(item, ok=False)
                self.assertEqual(2, p.returncode); self.assertIn("change.title must be one line", p.stderr)
                bad = dict(item, action_key=f"r-{ord(sep)}", work_key=f"r-{ord(sep)}", reason=f"From{sep}mail.",
                           change={"title": "Fine"})
                self.assertIn("reason must be one line", self.add(bad, ok=False).stderr)
        # a card file edited by hand still prints as one line
        path = os.path.join(self.board, "cards", "t_second.json")
        with open(path, encoding="utf-8") as f:
            card = json.load(f)
        card["title"] = "Write notes\u2028#9   t_forged  todo  forged line"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(card, f, indent=2)
        out = self.kt("list").stdout
        self.assertNotIn("\n#9", out); self.assertIn("Write notes #9 t_forged todo forged line", out)
        # so does every other field the card file holds (id, column, assignees, the claim's agent)
        card["title"] = "Write notes"
        card["assignees"] = ["alex\u2028#8   t_forged2  todo  forged"]
        card["claim"] = {"agent": "claude\x85#7 forged", "session": "abcd1234", "claimed_at": "2026-10-12T09:00:00Z",
                         "heartbeat_at": "2026-10-12T09:00:00Z"}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(card, f, indent=2)
        out = self.kt("list").stdout
        self.assertEqual(len(out.splitlines()), len(out.split("\n")) - (1 if out.endswith("\n") else 0), repr(out))
        self.assertNotIn("\n#8", out); self.assertNotIn("\n#7", out)
        # the wait text and every other part of the line too
        card["assignees"] = ["alex"]; card["claim"] = None
        card["waiting"] = [{"id": "w_x", "on": "Sam\u2028#6   t_forged3  todo  forged", "who": "alex", "since": "2026-10-12T09:00:00Z"}]
        with open(path, "w", encoding="utf-8") as f:
            json.dump(card, f, indent=2)
        out = self.kt("list").stdout
        self.assertEqual(len(out.splitlines()), len(out.split("\n")) - (1 if out.endswith("\n") else 0), repr(out))
        # and the proposals listing
        item = choose("flat-p"); item["title"] = "Pick one"
        self.add(item)
        rid = self.stored("flat-p")["id"]
        self.edit_file(rid, lambda p: p.update(title="Pick one\u2029r_fake  pending  ask.choose  forged"))
        out = self.kt("proposals").stdout
        self.assertEqual(len(out.splitlines()), len(out.split("\n")) - (1 if out.endswith("\n") else 0), repr(out))

    def test_inbox_lapse_days_setting(self):
        self.assertIn("inbox_lapse_days: 14", self.kt("settings").stdout)
        self.add(choose("set-old"))
        self.age("set-old")
        self.kt("settings-set", "--inbox-lapse-days", "0")
        self.assertIn("inbox_lapse_days: off (questions never lapse)", self.kt("settings").stdout)
        self.assertNotIn("lapsed question", self.kt("list", "--attention").stdout, "0 turns lapsing off")
        self.kt("settings-set", "--inbox-lapse-days", "30")
        with open(os.path.join(self.board, "tasks.json"), encoding="utf-8") as f:
            self.assertEqual(30, json.load(f)["settings"]["inbox_lapse_days"])
        self.assertIn("lapsed question", self.kt("list", "--attention").stdout)
        p = self.kt("settings-set", "--inbox-lapse-days", "366", ok=False)
        self.assertNotEqual(0, p.returncode)
        self.assertIn("between 0 (questions never lapse) and 365", p.stderr)


if __name__ == "__main__":
    unittest.main()

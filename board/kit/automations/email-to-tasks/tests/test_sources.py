"""1.5: several mailboxes (`sources`), each proved before any read, each with its own window."""
import sys, base64, contextlib, hashlib, importlib.util, io, json, os, pathlib, tempfile, unittest
from types import SimpleNamespace
from unittest.mock import patch

PACK = pathlib.Path(__file__).resolve().parents[1]
READ = "https://www.googleapis.com/auth/gmail.readonly"


def load(name):
    saved, sys.dont_write_bytecode = sys.dont_write_bytecode, True
    try:
        spec = importlib.util.spec_from_file_location("sources_" + name, PACK / (name + ".py"))
        mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); return mod
    finally:
        sys.dont_write_bytecode = saved


def key(value):
    return "sha256:" + hashlib.sha256(value.encode()).hexdigest()


class FakeGog:
    """gog with account aliases. `boxes` maps an address to its pages (lists of messages, one page each)."""
    def __init__(self, boxes, aliases, scopes=None, errors=(), pad=0):
        self.boxes, self.aliases, self.calls, self.errors, self.pad = boxes, aliases, [], set(errors), pad
        self.scopes = scopes or {}

    def __call__(self, argv, **kw):
        self.calls.append(argv)
        assert kw.get("timeout") and not kw.get("shell")
        args = list(argv[1:])
        account = None
        if "--account" in args:
            i = args.index("--account"); account = args[i + 1]; del args[i:i + 2]
        flags = [a for a in args if a.startswith("--") and a in ("--readonly", "--gmail-no-send", "--no-input", "--json")]
        if "--enable-commands-exact" in args:
            i = args.index("--enable-commands-exact"); allowed = args[i + 1].split(","); del args[i:i + 2]
        else:
            allowed = None
        args = [a for a in args if a not in flags]
        ok = lambda v: SimpleNamespace(returncode=0, stdout=json.dumps(v).encode(), stderr=b"")
        if args[:3] == ["auth", "alias", "list"]:
            assert allowed and "auth.alias.list" in allowed
            return ok({"aliases": self.aliases})
        if args[:2] == ["auth", "list"]:
            return ok({"accounts": [dict(email=a, scopes=self.scopes.get(a, [READ]), **({"error": "expired"} if a in self.errors else {}))
                                    for a in self.boxes]})
        if args[:3] == ["gmail", "messages", "search"]:
            assert account is not None, "a named source always passes --account"
            assert allowed == ["gmail.messages.search"] and {"--readonly", "--gmail-no-send", "--no-input"} <= set(argv)
            pages = self.boxes[account]
            n = int(args[args.index("--page") + 1].rstrip("x")) if "--page" in args else 0
            page = {"messages": pages[n]}
            if n + 1 < len(pages): page["nextPageToken"] = str(n + 1) + "x" * self.pad
            return ok(page)
        if args[:2] == ["gmail", "get"]:
            assert account is not None and allowed == ["gmail.get"] and "--readonly" in argv
            mid = args[2]
            if not any(m["id"] == mid for page in self.boxes[account] for m in page): return SimpleNamespace(returncode=1, stdout=b"", stderr=b"")
            return ok({"id": mid, "threadId": "t" + mid, "labelIds": ["INBOX"], "payload": {"headers": [
                {"name": "From", "value": "Casey <casey@example.invalid>"}, {"name": "Message-ID", "value": "<%s@mail.example.invalid>" % mid}]}})
        raise AssertionError("unexpected gog call " + repr(argv))


class Base(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        self.mod = load("check")
        self.saved = os.getcwd(); os.chdir(self.root); self.addCleanup(os.chdir, self.saved)
        (self.root / "board").mkdir()
        (self.root / "board" / "tasks.json").write_text(json.dumps({
            "people": [{"github": "alexdemo", "emails": ["alex@work.invalid", "alex@home.invalid"]}],
            "contacts": [{"email": "casey@example.invalid"}, {"email": "jo@example.invalid"}]}))
        self.state = self.root / "seen.json"; self.config = self.root / "config.json"
        self.state.write_text(json.dumps({"keys": {}, "cursor": None}))
        env = patch.dict(os.environ, KEEPTRACK_STATE=str(self.state), KEEPTRACK_CONFIG=str(self.config))
        env.start(); self.addCleanup(env.stop)
        self.aliases = {"work": "alex@work.invalid", "personal": "alex@home.invalid"}

    def run_check(self, gog, cfg, cursor=None):
        self.config.write_text(json.dumps(cfg))
        out = io.StringIO()
        extra = {"KEEPTRACK_SCAN_CURSOR": cursor} if cursor else {}
        with patch.dict(os.environ, extra), patch.object(self.mod.shutil, "which", return_value="gog"), \
                patch.object(self.mod.subprocess, "run", side_effect=gog), contextlib.redirect_stdout(out):
            code = self.mod.main()
        return code, json.loads(out.getvalue())

    def searches(self, gog):
        return [c[c.index("--account") + 1] for c in gog.calls if "search" in c]

    def windows(self, cursor):
        return json.loads(base64.urlsafe_b64decode(cursor))


class SourcesTest(Base):
    def test_each_source_reads_its_own_mailbox_with_guards(self):
        gog = FakeGog({"alex@work.invalid": [[{"id": "w1", "from": "casey@example.invalid"}]],
                       "alex@home.invalid": [[{"id": "h1", "from": "jo@example.invalid"}]]}, self.aliases)
        code, value = self.run_check(gog, {"sources": "work,personal"})
        self.assertEqual(code, 0)
        self.assertEqual([i["key"] for i in value["items"]], [key("w1")])
        self.assertEqual(self.searches(gog), ["alex@work.invalid"])   # the source with items ends the run
        ref = json.loads(base64.urlsafe_b64decode(value["items"][0]["ref"][3:]))
        self.assertEqual(ref["s"], "work")
        cur = self.windows(value["cursor"])
        self.assertEqual((cur["v"], cur["n"]), (2, 1))   # the next run starts with the other source
        self.assertTrue(value["more"])
        # The next run reads personal first; work's window did not move.
        code, value2 = self.run_check(gog, {"sources": "work,personal"}, cursor=value["cursor"])
        self.assertEqual([i["key"] for i in value2["items"]], [key("h1")])
        self.assertEqual(self.searches(gog)[-1], "alex@home.invalid")
        self.assertEqual(self.windows(value2["cursor"])["s"]["work"], cur["s"]["work"])

    def test_empty_source_moves_on_and_only_its_window_ends(self):
        gog = FakeGog({"alex@work.invalid": [[]], "alex@home.invalid": [[{"id": "h1", "from": "jo@example.invalid"}]]}, self.aliases)
        code, value = self.run_check(gog, {"sources": "work,personal"})
        self.assertEqual([i["key"] for i in value["items"]], [key("h1")])
        self.assertEqual(self.searches(gog), ["alex@work.invalid", "alex@home.invalid"])
        start = self.windows(value["start_cursor"])["s"]; end = self.windows(value["cursor"])["s"]
        self.assertEqual(end["work"][0], start["work"][1] - 1)       # work's window finished: the next one starts
        # personal's window ended with its batch, as in 1.4: the kit keeps this cursor until every item is marked.
        self.assertEqual(end["personal"][0], start["personal"][1] - 1)

    def test_missing_alias_blocks_before_any_read(self):
        gog = FakeGog({"alex@work.invalid": [[]]}, {"work": "alex@work.invalid"})
        code, value = self.run_check(gog, {"sources": "work,personal"})
        self.assertEqual((code, value["note"]), (2, "setup-missing:account-personal"))
        self.assertEqual(self.searches(gog), [])

    def test_wide_scope_blocks_before_any_read(self):
        gog = FakeGog({"alex@work.invalid": [[]]}, self.aliases,
                      scopes={"alex@work.invalid": [READ, "https://www.googleapis.com/auth/gmail.modify"]})
        code, value = self.run_check(gog, {"sources": "work"})
        self.assertEqual((code, value["note"]), (2, "setup-missing:readonly-work"))
        gog = FakeGog({"alex@work.invalid": [[]]}, self.aliases, scopes={"alex@work.invalid": ["https://mail.google.com/", READ]})
        self.assertEqual(self.run_check(gog, {"sources": "work"})[1]["note"], "setup-missing:readonly-work")
        gog = FakeGog({"alex@work.invalid": [[]]}, self.aliases,
                      scopes={"alex@work.invalid": [READ, "https://www.googleapis.com/auth/gmail.addons.current.action.compose"]})
        self.assertEqual(self.run_check(gog, {"sources": "work"})[1]["note"], "setup-missing:readonly-work")
        gog = FakeGog({"alex@work.invalid": [[]]}, self.aliases,
                      scopes={"alex@work.invalid": [READ, "https://www.googleapis.com/auth/calendar.readonly", "openid"]})
        self.assertEqual(self.run_check(gog, {"sources": "work"})[0], 0)   # other services' scopes are not Gmail's
        gog = FakeGog({"alex@work.invalid": [[]]}, self.aliases, scopes={"alex@work.invalid": []})
        self.assertEqual(self.run_check(gog, {"sources": "work"})[1]["note"], "setup-missing:readonly-work")
        self.assertEqual(self.searches(gog), [])

    def test_expired_login_blocks(self):
        gog = FakeGog({"alex@work.invalid": [[]]}, self.aliases, errors={"alex@work.invalid"})
        self.assertEqual(self.run_check(gog, {"sources": "work"})[1]["note"], "auth-expired")
        self.assertEqual(self.searches(gog), [])

    def test_malformed_sources_never_fall_back_to_the_default_account(self):
        for bad in ("Work", "work,work", "a,b,c,d", "work;rm", ",", 7):
            gog = FakeGog({"alex@work.invalid": [[]]}, self.aliases)
            code, value = self.run_check(gog, {"sources": bad})
            self.assertEqual((code, value["note"]), (2, "setup-missing:sources"), bad)
            self.assertEqual(gog.calls, [])

    def test_old_cursor_is_not_used_for_a_named_source(self):
        gog = FakeGog({"alex@work.invalid": [[]]}, self.aliases)
        old = base64.urlsafe_b64encode(json.dumps({"after": 1, "until": 2, "page": "9"}).encode()).decode()
        code, value = self.run_check(gog, {"sources": "work", "lookback_days": 2}, cursor=old)
        self.assertEqual(code, 0)
        search = [c for c in gog.calls if "search" in c][0]
        self.assertNotIn("--page", search)
        self.assertIn("after:", search[search.index("search") + 1])
        self.assertNotIn("after:1 ", search[search.index("search") + 1])

    def test_long_page_tokens_keep_the_cursor_short(self):
        aliases = dict(self.aliases, other="x@x.invalid")
        gog = FakeGog({"alex@work.invalid": [[{"id": "w1", "from": "casey@example.invalid"}], []],
                       "alex@home.invalid": [[]], "x@x.invalid": [[]]}, aliases, pad=150)
        code, value = self.run_check(gog, {"sources": "work,personal,other"})
        self.assertEqual([i["key"] for i in value["items"]], [key("w1")])
        self.assertLessEqual(len(value["cursor"]), 256); self.assertLessEqual(len(value["start_cursor"]), 256)
        work = self.windows(value["cursor"])["s"]["work"]
        self.assertEqual((work[2], work[3]), (None, True))   # restart work's window from page one, same bounds


class ResolveSourcesTest(Base):
    """resolve.py reads the mailbox the item came from, and only a source this board's install names."""
    def setUp(self):
        super().setUp()
        self.resolve = load("resolve")
        (self.root / "automation" / "routines").mkdir(parents=True)

    def install(self, sources, owner="alexdemo"):
        (self.root / "automation" / "routines" / ("auto-email-to-tasks-" + owner + ".json")).write_text(json.dumps(
            {"id": "auto-email-to-tasks-" + owner, "owner": owner, "status": "active", "automation": {"config": {"sources": sources}}}))

    def resolve_run(self, gog, *args):
        out = io.StringIO()
        with patch.object(self.resolve.subprocess, "run", side_effect=gog), contextlib.redirect_stdout(out):
            code = self.resolve.main(list(args))
        return code, out.getvalue().strip().splitlines()

    def ref(self, source, **extra):
        value = dict(a=1, u=2, p=None, **({"s": source} if source else {}), **extra)
        return "pg:" + base64.urlsafe_b64encode(json.dumps(value, separators=(",", ":")).encode()).decode()

    def boxes(self):
        return FakeGog({"alex@work.invalid": [[{"id": "w1", "from": "casey@example.invalid"}]],
                        "alex@home.invalid": [[{"id": "h1", "from": "jo@example.invalid"}]]}, self.aliases)

    def test_reads_the_items_own_source(self):
        self.install("work,personal")
        gog = self.boxes()
        code, lines = self.resolve_run(gog, self.ref("personal"), key("h1"))
        self.assertEqual(code, 0)
        self.assertTrue(lines[0].startswith(key("h1") + " h1 - rfc822:"), lines)
        self.assertEqual({c[c.index("--account") + 1] for c in gog.calls if "--account" in c}, {"alex@home.invalid"})

    def test_a_source_the_install_does_not_name_is_refused(self):
        self.install("work")   # the consulting board: Work mail only
        gog = self.boxes()
        code, lines = self.resolve_run(gog, self.ref("personal"), key("h1"))
        self.assertEqual(code, 2); self.assertEqual(gog.calls, [])

    def test_ref_without_source_is_refused_when_the_install_names_sources(self):
        self.install("work")
        gog = self.boxes()
        code, _ = self.resolve_run(gog, self.ref(None), key("w1"))
        self.assertEqual(code, 2); self.assertEqual(gog.calls, [])

    def test_source_in_ref_without_named_install_is_refused(self):
        gog = self.boxes()
        code, _ = self.resolve_run(gog, self.ref("work"), key("w1"))
        self.assertEqual(code, 2); self.assertEqual(gog.calls, [])

    def test_day_looks_in_each_named_source(self):
        self.install("work,personal")
        gog = self.boxes()
        code, lines = self.resolve_run(gog, "--day", "2026-10-14", key("h1"))
        self.assertEqual(code, 0); self.assertIn(" h1 - rfc822:", lines[0])

    def test_wrong_account_stops_before_any_read(self):
        self.install("work")
        gog = FakeGog({"alex@work.invalid": [[]]}, {})
        code, lines = self.resolve_run(gog, self.ref("work"), key("w1"))
        self.assertEqual(code, 3); self.assertEqual(lines, ["gog-error: setup-missing:account-work"])
        self.assertFalse([c for c in gog.calls if "gmail" in c])

    def test_another_persons_install_does_not_widen_this_one(self):
        self.install("work"); self.install("work,personal", owner="jodemo")
        gog = self.boxes()
        with patch.dict(os.environ, BOARD_USER="alexdemo"):
            code, _ = self.resolve_run(gog, self.ref("personal"), key("h1"))
        self.assertEqual(code, 2)

    def test_several_installs_need_board_user(self):
        self.install("work"); self.install("work,personal", owner="jodemo")
        gog = self.boxes()
        with patch.dict(os.environ, {"BOARD_USER": ""}):
            code, _ = self.resolve_run(gog, self.ref("work"), key("w1"))
            self.assertEqual(code, 2)
            code, _ = self.resolve_run(gog, "--day", "2026-10-14", key("w1"))
            self.assertEqual(code, 2)
        self.assertEqual(gog.calls, [])

    def test_no_install_for_board_user_never_falls_back_to_the_default_account(self):
        self.install("work")
        gog = self.boxes()
        with patch.dict(os.environ, BOARD_USER="alexdemo-typo"):
            code, _ = self.resolve_run(gog, "--day", "2026-10-14", key("w1"))
        self.assertEqual(code, 2); self.assertEqual(gog.calls, [])


if __name__ == "__main__":
    unittest.main()

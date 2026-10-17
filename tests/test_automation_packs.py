"""Built-in automation packs: each ships behaviour tests (evals/cases.json) that relay's eval runner accepts,
and a SKILL.md and SETUP.md with real content. No model is called here: relay.py eval does that, by hand.

The case and check rules mirror keeptrack-relay's relay/scripts/eval.py (validate and _check_errors). That file is
not in this repo, so the rules are restated; keep them in step with it."""
import json
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KIT = os.path.join(ROOT, "board", "kit")
PACKS = os.path.join(KIT, "automations")
TEMPLATE = os.path.join(KIT, "skills", "keeptrack-automation-create", "references", "evals_template.json")

# relay/scripts/eval.py: CHECK_KINDS, CASE_FIELDS, NAME_RE, BOARD_PREFIX
CHECK_KINDS = {"contains", "not_contains", "regex", "not_regex", "last_line", "count"}
REGEX_KINDS = {"regex", "not_regex", "last_line", "count"}
CHECK_EXTRA = {"why", "min", "max"}
LOADER_PROMPT = "$BOARD/board/automation-loader.md"
CASE_FIELDS = {"name", "about", "prompts", "scenario", "checks", "min", "runs"}
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,60}$")
BOARD_PREFIX = "$BOARD/"
RUNTIMES = ("Local Claude Code", "Claude Code cloud routine", "Codex")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@([A-Za-z0-9-]+\.)+[A-Za-z]{2,}")


def packs():
    return sorted(d for d in os.listdir(PACKS) if os.path.isfile(os.path.join(PACKS, d, "manifest.json")))


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def case_problems(doc, prefix, exists):
    """Every problem in a cases document, as text. `prefix` is the prompt path every case must start with;
    `exists(rel)` says whether a prompt file below that prefix is present."""
    if not isinstance(doc, dict) or not isinstance(doc.get("cases"), list):
        return ["the file is an object with a `cases` list"]
    errs = []
    if not isinstance(doc.get("preface", ""), str):
        errs.append("preface must be text")
    if len(doc["cases"]) < 2:
        errs.append("at least two cases: a normal run and a skip or failure path")
    names = set()
    for i, c in enumerate(doc["cases"]):
        where = f"case {i + 1}"
        if not isinstance(c, dict):
            errs.append(f"{where}: not an object")
            continue
        name = c.get("name")
        if not isinstance(name, str) or not NAME_RE.match(name):
            errs.append(f"{where}: bad name {name!r}")
        elif name in names:
            errs.append(f"{where}: name {name} used twice")
        names.add(name)
        where = f"case {name}"
        extra = set(c) - CASE_FIELDS
        if extra:
            errs.append(f"{where}: unknown fields {sorted(extra)}")
        for key in ("about", "scenario"):
            if not isinstance(c.get(key), str) or not c[key].strip():
                errs.append(f"{where}: {key} must be non-empty text")
        prompts = c.get("prompts")
        if not isinstance(prompts, list) or not prompts:
            errs.append(f"{where}: prompts must be a non-empty list")
        else:
            for p in prompts:
                if p == LOADER_PROMPT:   # the loader's text: a real run reads it before the pack's SKILL.md
                    continue
                if not isinstance(p, str) or not p.startswith(prefix):
                    errs.append(f"{where}: prompt {p!r} must start with {prefix}")
                    continue
                rel = p[len(prefix):]
                if not rel or any(seg in ("", ".", "..") for seg in rel.split("/")):
                    errs.append(f"{where}: prompt {p!r} has an empty, . or .. segment")
                elif not exists(rel):
                    errs.append(f"{where}: prompt file {p} not found")
            if prefix + "SKILL.md" not in prompts:
                errs.append(f"{where}: prompts must include {prefix}SKILL.md")
        checks = c.get("checks")
        if not isinstance(checks, list) or not checks:
            errs.append(f"{where}: checks must be a non-empty list")
            checks = []
        for j, ch in enumerate(checks):
            cw = f"{where} check {j + 1}"
            kinds = set(ch) & CHECK_KINDS if isinstance(ch, dict) else set()
            if len(kinds) != 1:
                errs.append(f"{cw}: needs exactly one of {sorted(CHECK_KINDS)}")
                continue
            kind = kinds.pop()
            if set(ch) - {kind} - CHECK_EXTRA:
                errs.append(f"{cw}: unknown fields {sorted(set(ch) - {kind} - CHECK_EXTRA)}")
            v = ch[kind]
            if not isinstance(v, str) or not v:
                errs.append(f"{cw}: {kind} needs non-empty text")
            elif kind in REGEX_KINDS:
                try:
                    re.compile(v)
                except re.error as e:
                    errs.append(f"{cw}: bad regex {v!r} ({e})")
            if ("min" in ch or "max" in ch) and kind != "count":
                errs.append(f"{cw}: min and max belong to a count check")
            if kind == "count":
                lo, hi = ch.get("min", 1), ch.get("max")
                if (not isinstance(lo, int) or isinstance(lo, bool) or lo < 0
                        or (hi is not None and (not isinstance(hi, int) or isinstance(hi, bool) or hi < lo))):
                    errs.append(f"{cw}: count needs whole numbers, 0 <= min <= max")
        share = c.get("min", 0.75)
        if isinstance(share, bool) or not isinstance(share, (int, float)) or not 0 < share <= 1:
            errs.append(f"{where}: min is a share of runs, above 0 and at most 1")
        runs = c.get("runs", 3)
        if isinstance(runs, bool) or not isinstance(runs, int) or not 1 <= runs <= 20:
            errs.append(f"{where}: runs must be 1 to 20")
    return errs


def sections(text):
    """`## heading` -> body, for a Markdown file."""
    out, head = {}, None
    for line in text.splitlines():
        if line.startswith("## "):
            head = line[3:].strip()
            out[head] = []
        elif head is not None:
            out[head].append(line)
    return {k: "\n".join(v) for k, v in out.items()}


class PackEvals(unittest.TestCase):
    def test_there_are_built_in_packs(self):
        self.assertEqual(packs(), ["email-to-tasks", "notes-folder-to-tasks", "stale-cards-nudge"])

    def test_each_pack_has_valid_evals(self):
        for slug in packs():
            with self.subTest(pack=slug):
                path = os.path.join(PACKS, slug, "evals", "cases.json")
                self.assertTrue(os.path.isfile(path), f"{slug}: add evals/cases.json (AUTOMATIONS.md, Behaviour tests)")
                doc = json.loads(read(path))
                prefix = f"{BOARD_PREFIX}board/automations/{slug}/"
                errs = case_problems(doc, prefix, lambda rel: os.path.isfile(os.path.join(PACKS, slug, *rel.split("/"))))
                self.assertEqual(errs, [])

    def test_case_names_are_unique_across_packs(self):
        seen = {}
        for slug in packs():
            for c in json.loads(read(os.path.join(PACKS, slug, "evals", "cases.json")))["cases"]:
                self.assertNotIn(c["name"], seen, f"{c['name']} is in {seen.get(c['name'])} and {slug}")
                seen[c["name"]] = slug

    def test_evals_use_invented_addresses_only(self):
        # every address in a pack's text is on a reserved test domain (example.invalid, example.com, ...)
        for slug in packs():
            for name in ("SKILL.md", "SETUP.md", os.path.join("evals", "cases.json")):
                for m in EMAIL_RE.finditer(read(os.path.join(PACKS, slug, name))):
                    domain = m.group(0).rsplit("@", 1)[1].lower()
                    with self.subTest(pack=slug, file=name, address=m.group(0)):
                        self.assertRegex(domain, r"(^|\.)(example\.(com|org|net)|invalid|test|example)$")

    def test_template_is_valid(self):
        doc = json.loads(read(TEMPLATE))
        errs = case_problems(doc, f"{BOARD_PREFIX}automations/my-automation/", lambda rel: rel == "SKILL.md")
        self.assertEqual(errs, [])

    def test_case_checker_catches_bad_cases(self):
        good = {"name": "aa-bb", "about": "a", "scenario": "s", "prompts": ["$BOARD/board/automations/x/SKILL.md"],
                "checks": [{"contains": "x"}]}
        ok = lambda rel: rel == "SKILL.md"
        prefix = "$BOARD/board/automations/x/"
        self.assertEqual(case_problems({"cases": [good, dict(good, name="cc-dd")]}, prefix, ok), [])
        bad = [
            dict(good, name="Bad"),
            dict(good, prompts=["$BOARD/board/automations/other/SKILL.md"]),
            dict(good, prompts=["$BOARD/board/automations/x/../y/SKILL.md"]),
            dict(good, checks=[{"has": "x"}]),
            dict(good, checks=[{"regex": "("}]),
            dict(good, checks=[{"contains": "x", "max": 2}]),
            dict(good, checks=[{"count": "x", "min": 3, "max": 1}]),
            dict(good, extra=1),
        ]
        for b in bad:
            with self.subTest(case=b):
                self.assertTrue(case_problems({"cases": [b, dict(good, name="cc-dd")]}, prefix, ok))
        self.assertTrue(case_problems({"cases": [good]}, prefix, ok), "one case is too few")


class PackDocs(unittest.TestCase):
    def test_skill_is_substantive(self):
        for slug in packs():
            with self.subTest(pack=slug):
                text = read(os.path.join(PACKS, slug, "SKILL.md"))
                self.assertGreaterEqual(len(text.splitlines()), 60)
                self.assertGreaterEqual(len(re.findall(r"(?m)^\d+\. ", text)), 5, "numbered steps")
                for phrase in ("propose", "--dry-run", "action_key", "automation mark", "finish", "CARDS.md"):
                    self.assertIn(phrase, text)
                self.assertRegex(text, r"(?i)skip", "skip rules")
                self.assertRegex(text, r"(?i)fail|wrong", "failure handling")

    def test_setup_has_a_verify_command_per_runtime(self):
        for slug in packs():
            text = read(os.path.join(PACKS, slug, "SETUP.md"))
            secs = sections(text)
            for runtime in RUNTIMES:
                with self.subTest(pack=slug, runtime=runtime):
                    body = next((v for k, v in secs.items() if k.lower() == runtime.lower()), None)
                    self.assertIsNotNone(body, f"{slug}/SETUP.md needs a `## {runtime}` section")
                    self.assertRegex(body, r"(?i)verify|expected", "says how to verify it works")
                    self.assertRegex(body, r"`[^`\n]*(keeptrack\.py|\$B |gh |gog |python3|ls |codex|env )[^`\n]*`",
                                     "gives a command to run")

    def test_setup_lists_needs_with_verify_commands(self):
        for slug in packs():
            with self.subTest(pack=slug):
                text = read(os.path.join(PACKS, slug, "SETUP.md"))
                manifest = json.loads(read(os.path.join(PACKS, slug, "manifest.json")))
                self.assertGreaterEqual(len(text.splitlines()), 40)
                self.assertGreaterEqual(len(re.findall(r"(?i)verify|expected", text)), 4)
                for need in manifest.get("needs", []):
                    self.assertIn(need["id"].split(".")[0], text.lower(), f"SETUP.md covers {need['id']}")


class EvalDocs(unittest.TestCase):
    def test_guide_and_create_skill_describe_evals(self):
        guide = read(os.path.join(KIT, "AUTOMATIONS.md"))
        for phrase in ("evals/cases.json", "relay.py eval", "--board", "--cases"):
            self.assertIn(phrase, guide)
        self.assertRegex(guide, r"kept\s+only after its evals pass")
        skill = read(os.path.join(KIT, "skills", "keeptrack-automation-create", "SKILL.md"))
        for phrase in ("evals/cases.json", "references/evals_template.json", "relay.py eval"):
            self.assertIn(phrase, skill)

    def test_evals_ship_with_the_kit(self):
        files = json.loads(read(os.path.join(KIT, "manifest.json")))["files"]
        for slug in packs():
            rel = f"automations/{slug}/evals/cases.json"
            self.assertEqual(files.get("board/" + rel), rel)
        rel = "skills/keeptrack-automation-create/references/evals_template.json"
        self.assertEqual(files.get(".claude/skills/keeptrack-automation-create/references/evals_template.json"), rel)


if __name__ == "__main__":
    unittest.main()

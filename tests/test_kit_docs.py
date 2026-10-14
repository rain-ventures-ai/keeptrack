"""The kit's agent instructions agree with each other and with keeptrack.py (review problems 12 and 17)."""
import os, re, sys, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
KIT = os.path.join(HERE, "..", "board", "kit")
sys.path.insert(0, KIT)
import keeptrack  # noqa: E402


def read(*p):
    with open(os.path.join(KIT, *p), encoding="utf-8") as f:
        return re.sub(r"\s+", " ", f.read())   # rules may wrap across lines


SKILLS = {"repo board skill": read("repo-skills", "board", "SKILL.md"), "plugin keeptrack skill": read("skills", "keeptrack", "SKILL.md")}
TEMPLATE = read("templates", "AGENTS.md")
MINUTES = keeptrack.HEARTBEAT_EVERY // 60


class SkillParity(unittest.TestCase):
    # the two board skills are written by hand side by side: the key agent rules must be in both
    RULES = [r"\bclaim\b", r"\bheartbeat\b", r"\bdone\b.*--note", r"\brelease\b", r"\bwait\b.*--on .*--who",
             r"[Nn]ever `unwait` a wait you did not set", r"never your claude\.ai session id",
             r"[Nn]ever pass `--session` with an id you did not generate", r"`--force`", r"done .*--cancel"]

    def test_key_rules_are_in_both_skills(self):
        for name, text in SKILLS.items():
            for rule in self.RULES:
                self.assertRegex(text, rule, f"{name} lacks {rule}")

    def test_heartbeat_timing_matches_the_code(self):
        self.assertEqual(MINUTES, 15)
        for name, text in SKILLS.items():
            self.assertIn(f"every {MINUTES} minutes", text, name)


class Templates(unittest.TestCase):
    def test_rule_one_covers_every_board_json_file(self):
        rule = TEMPLATE.split("1. ", 1)[1].split(" 2. ", 1)[0]
        for part in ("JSON files under `board/`", "tasks.json", "cards/", "people/", "projects/", "proposals/", "archive/"):
            self.assertIn(part, rule)

    def test_upgrade_skill_names_every_board_json_folder(self):
        text = read("repo-skills", "board-upgrade", "SKILL.md")
        rule = text.split("never edit `board/tasks.json`", 1)[1].split(".", 1)[0]
        for part in ("cards/", "people/", "projects/", "proposals/", "archive/"):
            self.assertIn(part, rule)

    def test_upgrade_notes_say_to_keep_one_board_session_from_claim_to_done(self):
        self.assertIn("keep the same `BOARD_SESSION` from `claim` to `done`", read("UPGRADING.md"))

    def test_heartbeat_and_stale_timing_match_the_code(self):
        self.assertIn(f"at least every {MINUTES} minutes", TEMPLATE)
        self.assertIn(f"refreshes the claim at most every {MINUTES} minutes", TEMPLATE)
        self.assertIn("for 30 minutes shows as STALE", TEMPLATE)
        self.assertEqual(keeptrack.stale_limit({"settings": {}}, {}), 30)
        self.assertNotRegex(TEMPLATE + read("README.md"), r"every ~?(5|10) minutes")

    def test_board_session_is_a_random_id_never_the_claude_session(self):
        claude = read("templates", "CLAUDE.md")
        self.assertIn("never your claude.ai session id", TEMPLATE)
        self.assertIn("short random id you generate for this run as `BOARD_SESSION` (never your claude.ai session id", claude)
        self.assertNotRegex(TEMPLATE + claude, r"Claude session id as `BOARD_SESSION`")

    def test_upgrade_notes_say_to_update_plugin_copies_with_the_claim_record(self):
        v46 = read("UPGRADING.md").split("### v46", 1)[1].split("### v45", 1)[0]
        self.assertRegex(v46, r"Update plugin copies .* at the same time as this repo")

    def test_template_has_the_wait_rules(self):
        self.assertRegex(TEMPLATE, r"never `unwait` a wait you did not set")


class GoodCards(unittest.TestCase):
    # board/CARDS.md says what a good card is; every skill that writes cards points at it, and it ships to boards
    def test_guide_ships_to_every_board(self):
        import json
        with open(os.path.join(KIT, "manifest.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f)["files"].get("board/CARDS.md"), "CARDS.md")

    def test_guide_has_the_links_rule_and_both_examples(self):
        text = read("CARDS.md")
        for part in ("## Example: a bad card", "## Example: the same card, written well", "links section",
                     "is not a link"):
            self.assertIn(part, text)

    def test_card_writing_skills_point_at_the_guide(self):
        for path in (("repo-skills", "board", "SKILL.md"), ("repo-skills", "board-admin", "SKILL.md"),
                     ("skills", "keeptrack", "SKILL.md"), ("skills", "keeptrack-notes", "SKILL.md"),
                     ("skills", "onboard-keeptrack", "SKILL.md"),
                     ("skills", "onboard-keeptrack", "references", "tasks.md"),
                     ("routine-prompt.md",), ("templates", "AGENTS.md")):
            self.assertIn("CARDS.md", read(*path), "/".join(path))


if __name__ == "__main__":
    unittest.main()

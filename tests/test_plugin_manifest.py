import json, os, struct, unittest

KIT = os.path.join(os.path.dirname(__file__), "..", "board", "kit")


class ClaudePlugin(unittest.TestCase):
    def test_version_follows_kit_version(self):
        plugin = json.load(open(os.path.join(KIT, ".claude-plugin", "plugin.json")))
        kit = json.load(open(os.path.join(KIT, "manifest.json")))["version"]
        self.assertRegex(plugin["version"], rf"^0\.{kit}\.\d+$", "bump .claude-plugin/plugin.json version with the kit (UPGRADING.md)")

    def test_codex_and_cursor_plugins_share_the_claude_version(self):
        # one scheme for all three agents: 0.<KIT_VERSION>.<patch>, the same in each manifest
        ver = {d: json.load(open(os.path.join(KIT, d, "plugin.json"))).get("version") for d in (".claude-plugin", ".codex-plugin", ".cursor-plugin")}
        kit = json.load(open(os.path.join(KIT, "manifest.json")))["version"]
        src = open(os.path.join(KIT, "keeptrack.py")).read()
        self.assertIn(f"KIT_VERSION = {kit} ", src, "keeptrack.py KIT_VERSION must match manifest.json")
        for d, v in ver.items():
            self.assertRegex(v or "", rf"^0\.{kit}\.\d+$", f"{d}/plugin.json version must be 0.{kit}.N")
        self.assertEqual(len(set(ver.values())), 1, f"plugin versions differ: {ver}")

    def test_automation_create_skill_is_in_plugin_and_board_mapping(self):
        from pathlib import Path
        kit = Path(KIT)
        manifest = json.loads((kit / "manifest.json").read_text())
        skill = kit / "skills/keeptrack-automation-create"
        for path in skill.rglob("*"):
            if not path.is_file() or "__pycache__" in path.parts: continue
            relative = path.relative_to(skill).as_posix()
            self.assertEqual(manifest["files"][".claude/skills/keeptrack-automation-create/" + relative], path.relative_to(kit).as_posix())
        self.assertIn("name: keeptrack-automation-create", (skill / "SKILL.md").read_text())

    def test_hooks_run_a_script_inside_the_plugin(self):
        hooks = json.load(open(os.path.join(KIT, "hooks", "hooks.json")))["hooks"]
        for groups in hooks.values():
            for g in groups:
                for h in g["hooks"]:
                    path = h["command"].split('"')[1].replace("${CLAUDE_PLUGIN_ROOT}", KIT)
                    self.assertTrue(h["command"].startswith("sh ") and os.path.isfile(path), h["command"])

    def test_icon_is_a_square_png_within_limits(self):
        p = os.path.join(KIT, ".claude-plugin", "icon.png")
        data = open(p, "rb").read()
        self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")
        w, h = struct.unpack(">II", data[16:24])
        self.assertEqual(w, h); self.assertTrue(512 <= w <= 2048); self.assertLess(len(data), 2 * 1024 * 1024)


if __name__ == "__main__":
    unittest.main()

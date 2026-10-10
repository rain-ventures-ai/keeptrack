import json, os, struct, unittest

KIT = os.path.join(os.path.dirname(__file__), "..", "board", "kit")


class ClaudePlugin(unittest.TestCase):
    def test_version_follows_kit_version(self):
        plugin = json.load(open(os.path.join(KIT, ".claude-plugin", "plugin.json")))
        kit = json.load(open(os.path.join(KIT, "manifest.json")))["version"]
        self.assertRegex(plugin["version"], rf"^0\.{kit}\.\d+$", "bump .claude-plugin/plugin.json version with the kit (UPGRADING.md)")

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

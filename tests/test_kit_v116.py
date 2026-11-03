"""Kit v116: which board and project a folder belongs to. Projects list their code repos (`repos`, one project per repo
on a board); `resolve` gives every tool one rule (a trusted config at the repo's top, else project repos across the
boards this person uses, else nothing; a folder outside git gets what its child repos share). Also `projects --json`
and to-do commands that take a to-do's own id."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from test_kit_v112 import Board, keeptrack, read  # noqa: E402

GIT_ENV = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")


def git_repo(path, origin=None):
    os.makedirs(path, exist_ok=True)
    subprocess.run(["git", "init", "-q", path], check=True, env=GIT_ENV)
    if origin:
        subprocess.run(["git", "-C", path, "remote", "add", "origin", origin], check=True, env=GIT_ENV)
    return os.path.realpath(path)


class Release(unittest.TestCase):
    def test_release_116_is_consistent(self):
        import re
        version = json.loads(read("board/kit/manifest.json"))["version"]
        self.assertEqual(version, 116)
        self.assertEqual(str(version), re.search(r"^KIT_VERSION = (\d+)", read("board/kit/keeptrack.py"), re.M)[1])
        self.assertIn(f"const PAGE_KIT = {version};", read("board/board.js"))
        for plugin in (".claude-plugin", ".codex-plugin", ".cursor-plugin"):
            self.assertEqual(f"0.{version}.0", json.loads(read(f"board/kit/{plugin}/plugin.json"))["version"])
        self.assertIn("### v116 (schema 4)", read("board/kit/UPGRADING.md"))
        self.assertIn("Kit v116:", read("CHANGELOG.md"))
        self.assertIn("`resolve [FOLDER] [--json]`", read("board/kit/README.md"))


class RepoName(unittest.TestCase):
    def test_spellings(self):
        for raw in ("Acme/Web", "acme/web.git", "https://github.com/Acme/web", "https://github.com/acme/web.git/",
                    "git@github.com:acme/web.git", "ssh://git@github.com/acme/web"):
            self.assertEqual("acme/web", keeptrack.repo_name(raw), raw)
        for raw in ("", "web", "https://gitlab.com/acme/web", "acme/web/tree/main", "../x/y z"):
            self.assertEqual("", keeptrack.repo_name(raw), raw)


class ProjectsCli(Board):
    def projects(self):
        return json.loads(self.kt("projects", "--json").stdout)

    def project(self, name):
        return next(p for p in self.projects() if p["name"] == name)

    def test_json_keeps_names_with_brackets(self):
        self.kt("project-add", "House Registration (Sagar) (phase 2)", "--client", "Hurst College")
        got = self.project("House Registration (Sagar) (phase 2)")
        self.assertEqual("Hurst College", got["client"])
        self.assertEqual([], got["repos"])

    def test_repos_are_added_normalised_and_removed(self):
        self.kt("project-add", "Web", "--client", "Acme", "--repo", "https://github.com/Acme/Web.git")
        self.kt("project-set", "Web", "--repo", "acme/api", "--repo", "ACME/web")
        self.assertEqual(["acme/web", "acme/api"], self.project("Web")["repos"])
        self.kt("project-set", "Web", "--unrepo", "acme/web")
        self.assertEqual(["acme/api"], self.project("Web")["repos"])
        self.kt("project-set", "Web", "--unrepo", "acme/api")
        self.assertNotIn("repos", next(p for p in self.folder("projects").values() if p["name"] == "Web"), "no empty field left")

    def test_a_repo_belongs_to_one_project_on_a_board(self):
        self.kt("project-add", "Web", "--client", "Acme", "--repo", "acme/web")
        self.kt("project-add", "Ops", "--client", "Acme")
        count = len(self.projects())
        before = self.folder("projects")
        p = self.kt("project-set", "Ops", "--repo", "acme/web", ok=False)
        self.assertNotEqual(0, p.returncode)
        self.assertIn("already on project", p.stderr)
        self.assertEqual(before, self.folder("projects"), "nothing saved")
        p = self.kt("project-add", "Again", "--client", "Acme", "--repo", "acme/web", ok=False)
        self.assertNotEqual(0, p.returncode)
        self.assertEqual(count, len(self.projects()), "the refused project was not added")
        self.assertNotEqual(0, self.kt("project-set", "Ops", "--repo", "not a repo", ok=False).returncode)

    def test_doctor_warns_on_a_repo_on_two_projects(self):
        self.kt("project-add", "Web", "--client", "Acme", "--repo", "acme/web")
        self.kt("project-add", "Ops", "--client", "Acme")
        folder = os.path.join(self.board, "projects")
        for name, pr in self.folder("projects").items():
            if pr["name"] == "Ops":   # a hand edit (or an old web board) puts the same repo on a second project
                pr["repos"] = ["acme/web"]
                with open(os.path.join(folder, name), "w", encoding="utf8") as f:
                    json.dump(pr, f)
        out = self.kt("doctor", "--json", ok=False)
        issues = json.loads(out.stdout)["issues"] if out.stdout.strip().startswith("{") else []
        self.assertTrue(any(i["code"] == "PROJECT" and "acme/web" in i["message"] for i in issues) or
                        "acme/web is also on project" in out.stdout, out.stdout + out.stderr)


class TodoById(Board):
    def card(self):
        self.kt("add", "Card with steps", "--assign", "alex")
        cards = json.loads(self.kt("list", "--json", "--all").stdout)
        t = next(c for c in cards if c["title"] == "Card with steps")
        for x in ("one", "two", "three"):
            self.kt("todo-add", t["id"], x)
        cards = json.loads(self.kt("list", "--json", "--all").stdout)
        return next(c for c in cards if c["id"] == t["id"])

    def test_tick_and_untick_by_id(self):
        t = self.card()
        two = t["todos"][1]["id"]
        self.assertTrue(two.startswith("d_"))
        self.kt("todo-rm", t["id"], "1")   # the list moved: number 2 is now "three", the id still means "two"
        self.kt("todo-done", t["id"], two)
        todos = {d["text"]: d["done"] for d in next(c for c in json.loads(self.kt("list", "--json", "--all").stdout)
                                                    if c["id"] == t["id"])["todos"]}
        self.assertEqual({"two": True, "three": False}, todos)
        self.kt("todo-undo", t["id"], two)
        p = self.kt("todo-done", t["id"], "d_nothere", ok=False)
        self.assertNotEqual(0, p.returncode)
        self.assertIn("no to-do d_nothere", p.stderr)


class Resolve(unittest.TestCase):
    """resolve_repo / resolve_folder with real git checkouts and boards given as data."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = os.path.realpath(self.tmp.name)
        self.cfg_home = os.path.join(self.root, "xdg")
        self.env = mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": self.cfg_home})
        self.env.start()
        self.boards = [{"board": "me/private"}, {"board": "team/consulting"}]
        self.data = {
            "me/private": [{"id": "pr_loam", "name": "loam", "status": "active", "repos": ["acme/web", "acme/db"]},
                           {"id": "pr_kt", "name": "Keeptrack", "status": "active", "repos": ["me/kt"]},
                           {"id": "pr_old", "name": "Old", "status": "done", "repos": ["me/old"]}],
            "team/consulting": [{"id": "pr_site", "name": "Site (Client) (v2)", "status": "active", "repos": ["team/site", "me/both"]}],
        }
        self.data["me/private"].append({"id": "pr_both", "name": "Both", "status": "active", "repos": ["me/both"]})

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def projects_of(self, board):
        return self.data.get(board, [])

    def resolve(self, folder):
        return keeptrack.resolve_folder(folder, self.boards, self.projects_of)

    def test_repo_listed_on_one_project(self):
        top = git_repo(os.path.join(self.root, "web"), "git@github.com:acme/web.git")
        os.makedirs(os.path.join(top, "src", "deep"))
        r = self.resolve(os.path.join(top, "src", "deep"))
        self.assertEqual(("me/private", "pr_loam", "repos", "acme/web"), (r["board"], r["project"], r["why"], r["repo"]))

    def test_the_other_board(self):
        r = self.resolve(git_repo(os.path.join(self.root, "site"), "https://github.com/team/site"))
        self.assertEqual(("team/consulting", "pr_site", "Site (Client) (v2)"), (r["board"], r["project"], r["project_name"]))

    def test_two_boards_claim_a_repo(self):
        r = self.resolve(git_repo(os.path.join(self.root, "both"), "https://github.com/me/both"))
        self.assertEqual((None, None, "several"), (r["board"], r["project"], r["why"]))
        self.assertEqual({("me/private", "pr_both"), ("team/consulting", "pr_site")}, {(m["board"], m["project"]) for m in r["matches"]})

    def test_done_projects_and_unknown_repos_map_nowhere(self):
        for name in ("old", "other"):
            r = self.resolve(git_repo(os.path.join(self.root, name), f"https://github.com/me/{name}"))
            self.assertEqual((None, None, []), (r["board"], r["project"], r["matches"]), name)
        r = self.resolve(git_repo(os.path.join(self.root, "noorigin")))
        self.assertEqual((None, None), (r["repo"], r["board"]))

    def write_config(self, top, conf, trust=True):
        p = os.path.join(top, ".keeptrack", "config.json")
        os.makedirs(os.path.dirname(p))
        with open(p, "w", encoding="utf8") as f:
            json.dump(conf, f)
        os.chmod(p, 0o600)
        if trust:
            keeptrack.trust_config(p)

    def test_a_trusted_config_wins(self):
        top = git_repo(os.path.join(self.root, "web2"), "https://github.com/acme/web")
        self.write_config(top, {"repo": "team/consulting", "project": "site (client) (v2)"})
        r = self.resolve(top)
        self.assertEqual(("team/consulting", "pr_site", "config"), (r["board"], r["project"], r["why"]))

    def test_a_config_without_a_project_takes_the_boards_repo_project(self):
        top = git_repo(os.path.join(self.root, "web3"), "https://github.com/acme/web")
        self.write_config(top, {"repo": "me/private"})
        self.assertEqual(("me/private", "pr_loam", "config"), tuple(self.resolve(top)[k] for k in ("board", "project", "why")))
        top = git_repo(os.path.join(self.root, "x"), "https://github.com/me/x")
        self.write_config(top, {"repo": "me/private"})
        r = self.resolve(top)
        self.assertEqual(("me/private", None), (r["board"], r["project"]), "the board, the whole of it")

    def test_an_untrusted_config_decides_nothing(self):
        top = git_repo(os.path.join(self.root, "web4"), "https://github.com/acme/web")
        self.write_config(top, {"repo": "team/consulting", "project": "pr_site"}, trust=False)
        self.assertEqual(("me/private", "pr_loam", "repos"), tuple(self.resolve(top)[k] for k in ("board", "project", "why")))

    def test_a_config_above_the_repo_connects_nothing(self):
        parent = os.path.join(self.root, "home")
        os.makedirs(parent)
        self.write_config(parent, {"repo": "team/consulting", "project": "pr_site"})
        r = self.resolve(git_repo(os.path.join(parent, "kt"), "https://github.com/me/kt"))
        self.assertEqual(("me/private", "pr_kt", "repos"), (r["board"], r["project"], r["why"]))

    def test_a_parent_folder_shares_what_its_repos_share(self):
        parent = os.path.join(self.root, "brockenhurst")
        git_repo(os.path.join(parent, "loam-web"), "https://github.com/acme/web")
        git_repo(os.path.join(parent, "osdb"), "https://github.com/acme/db")
        git_repo(os.path.join(parent, "osdb-wt-1"), "https://github.com/acme/db")
        git_repo(os.path.join(parent, "scratch"))   # a repo with no origin maps nowhere and changes nothing
        os.makedirs(os.path.join(parent, "notes"))
        r = self.resolve(parent)
        self.assertEqual(("me/private", "pr_loam", "children"), (r["board"], r["project"], r["why"]))
        self.assertEqual(4, len(r["children"]))
        git_repo(os.path.join(parent, "site"), "https://github.com/team/site")
        r = self.resolve(parent)
        self.assertEqual((None, "several"), (r["board"], r["why"]))
        self.assertEqual({("me/private", "pr_loam"), ("team/consulting", "pr_site")}, {(m["board"], m["project"]) for m in r["matches"]})

    def test_a_parent_reads_at_most_the_cap(self):
        parent = os.path.join(self.root, "many")
        for i in range(4):
            git_repo(os.path.join(parent, f"r{i}"), "https://github.com/me/kt")
        with mock.patch.object(keeptrack, "RESOLVE_MAX_CHILDREN", 3):
            r = self.resolve(parent)
        self.assertEqual((3, True, "pr_kt"), (len(r["children"]), r["truncated"], r["project"]))

    def test_git_that_cannot_answer_never_guesses(self):
        parent = os.path.join(self.root, "p")
        git_repo(os.path.join(parent, "web"), "https://github.com/acme/web")
        with mock.patch.object(keeptrack, "_git_toplevel", lambda f: ("", "hung")):
            r = self.resolve(parent)
        self.assertEqual((None, "git: hung", []), (r["board"], r["why"], r["children"]))


class ResolveCli(Board):
    """End to end on a --file board: the current board is searched, and `boards` lists it."""

    def test_resolve_and_boards(self):
        self.kt("project-add", "Web", "--client", "Acme", "--repo", "acme/web")
        top = git_repo(os.path.join(self.repo, "checkouts", "web"), "https://github.com/acme/web")
        env = {"XDG_CONFIG_HOME": os.path.join(self.repo, "xdg")}
        r = json.loads(self.kt("resolve", top, "--json", **env).stdout)
        self.assertEqual("Web", r["project_name"])
        self.assertTrue(r["board"].startswith("file:"))
        self.assertEqual("repos", r["why"])
        self.assertEqual([], r["errors"])
        r = json.loads(self.kt("resolve", os.path.join(self.repo, "checkouts"), "--json", **env).stdout)
        self.assertEqual(("Web", "children"), (r["project_name"], r["why"]))
        boards = json.loads(self.kt("boards", "--json", **env).stdout)
        self.assertEqual([True], [b["current"] for b in boards])
        self.assertIn("project: ", self.kt("resolve", top, **env).stdout)


if __name__ == "__main__":
    unittest.main()

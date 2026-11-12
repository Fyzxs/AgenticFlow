"""Tests for engine/pr.py: a draft PR from the first product commit, ready only when the run ships."""

import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

ENGINE = pathlib.Path(__file__).resolve().parent.parent
PY = sys.executable
sys.path.insert(0, str(ENGINE))
import pr  # noqa: E402

FAKE = """#!/bin/sh
echo "$0 $*" >> "{log}"
case "$1 $2" in
  "pr create") echo "https://github.com/acme/shop/pull/42" ;;
  "repos pr") [ "$3" = "create" ] && echo '{{"pullRequestId": 7, "url": "https://dev.azure.com/acme/_git/shop/pullrequest/7"}}' ;;
esac
exit 0
"""


class PrTests(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="fyzxsflow-pr-"))
        self.root = self.tmp / "repo"
        self.root.mkdir()
        self.bare = self.tmp / "remote.git"
        subprocess.run(["git", "init", "-q", "--bare", str(self.bare)], check=True)
        for a in (["init", "-q", "-b", "main"], ["config", "user.name", "T"], ["config", "user.email", "t@x"],
                  ["remote", "add", "origin", "https://github.com/acme/shop.git"],
                  ["remote", "set-url", "--push", "origin", str(self.bare)]):
            self.git(*a)
        (self.root / "app.py").write_text("v1\n", encoding="utf-8")
        (self.root / ".fyzxsflow").mkdir()
        self.profile()
        self.commit("base", "app.py", ".fyzxsflow/profile.md")
        base = self.git("rev-parse", "HEAD").stdout.strip()
        self.git("switch", "-q", "-c", "fyzxsflow/r1")
        self.run = self.root / ".fyzxsflow" / "runs" / "active" / "r1"
        (self.run / "work-packages").mkdir(parents=True)
        (self.run / "input.md").write_text(f"---\nbranch: fyzxsflow/r1\nbase: {base}\nbase_branch: main\n---\n\nadd export\n",
                                           encoding="utf-8")
        (self.run / "brief.md").write_text("# Orders CSV export\n\n- **AC-1**: a header line\n- **AC-2**: one line per order\n",
                                           encoding="utf-8")
        for wp, st in (("WP-01-api-export", "done"), ("WP-02-ui-button", "planned")):
            (self.run / "work-packages" / f"{wp}.md").write_text(f"---\nid: {wp[:5]}\nstatus: {st}\n---\n# {wp}\n",
                                                                 encoding="utf-8")
        self.commit("fyzxsflow(r1): plan", ".fyzxsflow/runs")
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        self.log = self.tmp / "calls.log"
        for tool in ("gh", "az"):
            f = self.bin / tool
            f.write_text(FAKE.format(log=self.log), encoding="utf-8")
            f.chmod(0o755)
        self.old_path = os.environ["PATH"]
        os.environ["PATH"] = f"{self.bin}{os.pathsep}{self.old_path}"

    def tearDown(self):
        os.environ["PATH"] = self.old_path
        shutil.rmtree(self.tmp, ignore_errors=True)

    def git(self, *args, cwd=None):
        return subprocess.run(["git", *args], cwd=cwd or self.root, capture_output=True, text=True)

    def profile(self, extra=""):
        (self.root / ".fyzxsflow" / "profile.md").write_text(
            f"# Profile\n## Pull requests\n- Opening a PR: pre-authorised\n- Target branch: main\n{extra}",
            encoding="utf-8")

    def commit(self, msg, *paths):
        self.git("add", *paths)
        self.git("commit", "-qm", msg)
        return self.git("rev-parse", "HEAD").stdout.strip()

    def p(self, *args):
        proc = subprocess.run([PY, "-I", str(ENGINE / "pr.py"), *args, "--run", str(self.run)], cwd=self.root,
                              capture_output=True, text=True, env=os.environ.copy())
        return proc.returncode, proc.stdout + proc.stderr

    def calls(self):
        return self.log.read_text(encoding="utf-8") if self.log.exists() else ""

    def test_the_pr_is_the_run_branch_with_every_commit_on_it(self):
        (self.root / "app.py").write_text("v2\n", encoding="utf-8")
        self.commit("feat: export", "app.py")
        code, out = self.p("draft")
        self.assertEqual(code, 0, out)
        self.assertIn("--head fyzxsflow/r1 ", self.calls())
        remote = subprocess.run(["git", "ls-tree", "-r", "--name-only", "fyzxsflow/r1"], cwd=self.bare,
                                capture_output=True, text=True).stdout.split()
        self.assertIn("app.py", remote)
        self.assertTrue(any(f.startswith(".fyzxsflow/runs/") for f in remote))  # the run's record ships too
        self.assertNotIn("-pr", self.git("branch").stdout)

    def test_a_draft_opens_with_the_first_product_commit_and_is_updated_as_packages_land(self):
        (self.root / "app.py").write_text("v2\n", encoding="utf-8")
        self.commit("feat: export", "app.py")
        code, out = self.p("draft")
        self.assertEqual(code, 0, out)
        self.assertIn("draft https://github.com/acme/shop/pull/42", out)
        self.assertIn("gh pr create --draft --base main --head fyzxsflow/r1 --title Orders CSV export", self.calls())
        self.assertIn("fyzxsflow/r1", subprocess.run(["git", "branch"], cwd=self.bare, capture_output=True,
                                                      text=True).stdout)  # pushed
        state = json.loads((self.run / "pr.json").read_text(encoding="utf-8"))
        self.assertEqual((state["number"], state["state"]), ("42", "draft"))
        self.assertIn("already open", self.p("draft")[1])
        body = self.p("body")[1]
        self.assertIn("- [x] WP-01-api-export", body)
        self.assertIn("- [ ] WP-02-ui-button", body)
        self.assertIn("- [ ] **AC-1**: a header line", body)
        self.assertIn("Draft: work in progress", body)
        lanes_dir = self.root / ".git" / "fyzxsflow-lanes" / "r1"
        lanes_dir.mkdir(parents=True)
        (lanes_dir / "lanes.json").write_text(json.dumps({"export": {
            "packages": ["WP-01"], "state": "completed", "path": "x", "branch": "b",
            "pr": {"host": "github", "number": "5", "url": "https://github.com/acme/shop/pull/5"}}}), encoding="utf-8")
        self.assertIn("- export (WP-01): completed, https://github.com/acme/shop/pull/5", self.p("body")[1])
        code, out = self.p("update")
        self.assertEqual(code, 0, out)
        self.assertIn("gh pr edit 42 --body-file", self.calls())

    def first_commit(self):
        (self.root / "app.py").write_text("v2\n", encoding="utf-8")
        self.commit("feat: export", "app.py")

    def test_no_draft_before_the_first_product_commit(self):
        code, out = self.p("draft")
        self.assertEqual(code, 1)
        self.assertIn("nothing to draft yet", out)
        self.assertEqual(self.calls(), "")

    def test_ready_only_when_ship_check_passes(self):
        self.first_commit()
        self.p("draft")
        code, out = self.p("ready")
        self.assertEqual(code, 1)
        self.assertIn("stays a draft until ship-check says ready=yes", out)
        self.assertNotIn("gh pr ready", self.calls())
        old = pr.ship_ready
        pr.ship_ready = lambda run: (True, "")
        try:
            self.assertEqual(pr.main(["ready", "--run", str(self.run)]), 0)
        finally:
            pr.ship_ready = old
        self.assertIn("gh pr ready 42", self.calls())
        self.assertEqual(json.loads((self.run / "pr.json").read_text(encoding="utf-8"))["state"], "ready")

    def test_azure_devops_through_az(self):
        self.profile("- PR host: azure\n")
        self.first_commit()
        code, out = self.p("draft")
        self.assertEqual(code, 0, out)
        self.assertIn("az repos pr create --draft true --source-branch fyzxsflow/r1 --target-branch main", self.calls())
        self.assertIn("pullrequest/7", out)
        old = pr.ship_ready
        pr.ship_ready = lambda run: (True, "")
        try:
            pr.main(["ready", "--run", str(self.run)])
        finally:
            pr.ship_ready = old
        self.assertIn("az repos pr update --id 7 --draft false", self.calls())


if __name__ == "__main__":
    unittest.main()

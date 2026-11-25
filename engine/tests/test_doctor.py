"""Tests for engine/doctor.py: the preflight finds, before the first stage, what would stop a run mid-way."""

import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

ENGINE = pathlib.Path(__file__).resolve().parent.parent


class DoctorTests(unittest.TestCase):
    def setUp(self):
        self.root = pathlib.Path(tempfile.mkdtemp(prefix="fyzxsflow-doctor-"))
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.email", "t@e")
        self.git("config", "user.name", "t")
        (self.root / ".fyzxsflow").mkdir()
        (self.root / ".fyzxsflow" / "profile.md").write_text("- PR host: github\n", encoding="utf-8")
        self.bin = self.root.parent / (self.root.name + "-bin")
        self.bin.mkdir()
        for tool, code in (("gh", 0), ("docker", 1)):
            (self.bin / tool).write_text(f"#!/bin/sh\nexit {code}\n", encoding="utf-8")
            (self.bin / tool).chmod(0o755)
        self.commit()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)
        shutil.rmtree(self.bin, ignore_errors=True)

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.root), *args], capture_output=True, text=True)

    def commit(self):
        self.git("add", "-A")
        self.git("commit", "-qm", "c", "--allow-empty")

    def doctor(self):
        env = {**os.environ, "PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}", "COPILOT_HOME": str(self.bin)}
        p = subprocess.run([sys.executable, "-I", "-B", str(ENGINE / "doctor.py"), "--root", str(self.root)],
                           capture_output=True, text=True, env=env)
        return p.returncode, p.stdout + p.stderr

    def test_a_clean_repo_is_ready(self):
        code, out = self.doctor()
        self.assertEqual(code, 0, out)
        self.assertIn("doctor: ready", out)
        self.assertEqual(list(self.root.rglob("__pycache__")), [])

    def test_a_repo_hook_that_denies_the_flows_commit_fails(self):
        hooks = self.root / ".github" / "hooks"
        hooks.mkdir(parents=True)
        (hooks / "guard.py").write_text(
            "import json,sys\np=json.load(sys.stdin)\nc=json.loads(p['toolArgs'])['command']\n"
            "if c.startswith('git commit'):\n    print(json.dumps({'permissionDecision':'deny',"
            "'permissionDecisionReason':'no commits here'}))\n", encoding="utf-8")
        (hooks / "repo.json").write_text(json.dumps({"version": 1, "hooks": {"preToolUse": [
            {"type": "command", "bash": f"{sys.executable} .github/hooks/guard.py"}]}}), encoding="utf-8")
        ours = {"version": 1, "hooks": {"preToolUse": [{"type": "command", "command":
                "exit 2 # .fyzxsflow/package/engine/hooks/orchestrator_guard_copilot.py pre"}]}}
        (hooks / "fyzxsflow.json").write_text(json.dumps(ours), encoding="utf-8")  # ours is never dry-run
        self.commit()
        code, out = self.doctor()
        self.assertEqual(code, 1, out)
        self.assertIn('.github/hooks/repo.json (preToolUse) denies the flow\'s own `git commit -m "build: WP-01"', out)
        self.assertIn("no commits here", out)
        self.assertNotIn("fyzxsflow.json (preToolUse) denies", out)

    def test_dirty_checkout_docker_and_agent_files_fail(self):
        (self.root / "stray.txt").write_text("x", encoding="utf-8")
        (self.root / ".fyzxsflow" / "config.json").write_text(json.dumps(
            {"modes": {"integration": {"steps": [{"name": "db", "run": "docker compose up -d"}]}}}), encoding="utf-8")
        agents = self.root / ".github" / "agents"
        agents.mkdir(parents=True)
        (agents / "a.agent.md").write_text("---\nname: a\ntier: deep\ndescription: Does X: then Y\n---\n" + "x" * 13000,
                                           encoding="utf-8")
        code, out = self.doctor()
        self.assertEqual(code, 1, out)
        for text in ("uncommitted changes (lanes.py open refuses them): ", "stray.txt", "Docker and it isn't running",
                     "a.agent.md: `tier`", "a.agent.md: unquoted description", "over the 12 KB budget",
                     "fyzxsflow.json is missing"):
            self.assertIn(text, out)

    def test_an_untrusted_folder_warns_that_resumed_sessions_run_without_hooks(self):
        (self.root / ".github" / "agents").mkdir(parents=True)
        (self.root / ".github" / "hooks").mkdir(parents=True)
        (self.root / ".github" / "hooks" / "fyzxsflow.json").write_text('{"version": 1, "hooks": {}}', encoding="utf-8")
        self.commit()
        code, out = self.doctor()
        self.assertEqual(code, 0, out)  # a warning, not a failure
        self.assertIn("isn't in Copilot's trustedFolders", out)
        (self.bin / "config.json").write_text("// managed\n" + json.dumps({"trustedFolders": [str(self.root.parent)]}),
                                              encoding="utf-8")
        code, out = self.doctor()
        self.assertIn("folder trusted", out)
        self.assertNotIn("trustedFolders", out)


if __name__ == "__main__":
    unittest.main()

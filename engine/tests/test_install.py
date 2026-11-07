"""Tests for engine/install.py."""

import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

ENGINE = pathlib.Path(__file__).resolve().parent.parent
PY = sys.executable


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.root = pathlib.Path(tempfile.mkdtemp(prefix="agentflow-install-"))
        (self.root / ".claude").mkdir()
        (self.root / ".claude" / "settings.json").write_text(json.dumps({"model": "keep-me"}), encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def install(self, *args, script=None):
        script = script or ENGINE / "install.py"
        proc = subprocess.run([PY, "-I", str(script), "--target", str(self.root), *args], capture_output=True, text=True)
        return proc.returncode, proc.stdout + proc.stderr

    def test_installs_package_and_both_hosts(self):
        code, out = self.install("--host", "claude", "--host", "copilot")
        self.assertEqual(code, 0, out)
        af = self.root / ".agentflow"
        for rel in ("engine/runner.py", "engine/hooks/block_kill_by_name.py", "context/role-contracts.md",
                    "agents/implementer.agent.md", "templates/run/brief.md", "skills/correction-mining/SKILL.md",
                    "INSTALLED.json"):
            self.assertTrue((af / rel).exists(), rel)
        self.assertFalse((af / "engine" / "tests").exists())
        self.assertTrue((self.root / ".claude/agents/implementer.md").exists())
        self.assertIn("Request: $ARGUMENTS", (self.root / ".claude/commands/flow.md").read_text(encoding="utf-8"))
        self.assertTrue((self.root / ".github/agents/implementer.agent.md").exists())
        wa = (self.root / ".github/instructions/agentflow-working-agreement.instructions.md").read_text(encoding="utf-8")
        self.assertTrue(wa.startswith('---\napplyTo: "**"'))
        settings = json.loads((self.root / ".claude/settings.json").read_text(encoding="utf-8"))
        self.assertEqual(settings["model"], "keep-me")
        self.assertEqual(len(settings["hooks"]["PreToolUse"]), 1)

    def test_reinstall_preserves_learned_and_does_not_duplicate_hook(self):
        self.install("--host", "claude")
        agent = self.root / ".agentflow/agents/implementer.agent.md"
        agent.write_text(agent.read_text(encoding="utf-8") + "- Read the flag seam first. (F-3, hits 2)\n", encoding="utf-8")
        code, out = self.install("--host", "claude")
        self.assertEqual(code, 0, out)
        self.assertIn("Read the flag seam first", agent.read_text(encoding="utf-8"))
        settings = json.loads((self.root / ".claude/settings.json").read_text(encoding="utf-8"))
        self.assertEqual(len(settings["hooks"]["PreToolUse"]), 1)

    def test_sync_regenerates_host_files_from_installed_copy(self):
        self.install("--host", "claude")
        agent = self.root / ".agentflow/agents/validator.agent.md"
        agent.write_text(agent.read_text(encoding="utf-8") + "- learned entry\n", encoding="utf-8")
        code, out = self.install("--sync", "--host", "claude", script=self.root / ".agentflow/engine/install.py")
        self.assertEqual(code, 0, out)
        self.assertIn("learned entry", (self.root / ".claude/agents/validator.md").read_text(encoding="utf-8"))

    def test_gitignore_gets_adhoc_line_once_and_warns_on_ignored_runs(self):
        (self.root / ".gitignore").write_text("bin/\n.agentflow/runs/\n", encoding="utf-8")
        code, out = self.install("--host", "claude")
        self.assertEqual(code, 0, out)
        self.assertIn("warning: .gitignore ignores .agentflow/runs/", out)
        self.install("--host", "claude")
        text = (self.root / ".gitignore").read_text(encoding="utf-8")
        self.assertEqual(text.count(".agentflow/runs/_adhoc/"), 1)
        self.assertTrue(text.startswith("bin/\n"))

    def test_sync_without_install_fails(self):
        code, _ = self.install("--sync", "--host", "claude")
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()

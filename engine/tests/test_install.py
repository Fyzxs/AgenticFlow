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
sys.path.insert(0, str(ENGINE))
import install  # noqa: E402


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.root = pathlib.Path(tempfile.mkdtemp(prefix="fyzxsflow-install-"))
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
        pkg = self.root / ".fyzxsflow" / "package"
        for rel in ("engine/runner.py", "engine/layout.py", "engine/hooks/block_kill_by_name.py",
                    "context/role-contracts.md", "agents/implementer.agent.md", "templates/run/brief.md",
                    "skills/correction-mining/SKILL.md", "INSTALLED.json"):
            self.assertTrue((pkg / rel).exists(), rel)
        self.assertFalse((pkg / "engine" / "tests").exists())
        self.assertEqual(json.loads((pkg / "INSTALLED.json").read_text(encoding="utf-8"))["fyzxsflow"], "0.2.0")
        self.assertTrue((self.root / ".claude/agents/implementer.md").exists())
        flow_cmd = (self.root / ".claude/commands/flow.md").read_text(encoding="utf-8")
        self.assertIn("Request: $ARGUMENTS", flow_cmd)
        self.assertIn('argument-hint: "[--preceptee] <what to build or fix', flow_cmd)
        self.assertNotIn("agent: orchestrator", flow_cmd)  # Copilot's routing key; Claude commands don't take it
        self.assertIn("agent: orchestrator", (self.root / ".github/prompts/flow.prompt.md").read_text(encoding="utf-8"))
        self.assertTrue((self.root / ".github/agents/implementer.agent.md").exists())
        ref = self.root / ".fyzxsflow/config.json.readme.md"
        self.assertIn("# config.json reference", ref.read_text(encoding="utf-8"))
        ref.write_text("stale", encoding="utf-8")
        self.install("--host", "claude")
        self.assertIn("# config.json reference", ref.read_text(encoding="utf-8"))  # installer-owned: refreshed
        wa = (self.root / ".github/instructions/fyzxsflow-working-agreement.instructions.md").read_text(encoding="utf-8")
        self.assertTrue(wa.startswith('---\napplyTo: "**"'))
        settings = json.loads((self.root / ".claude/settings.json").read_text(encoding="utf-8"))
        self.assertEqual(settings["model"], "keep-me")
        self.assertEqual(len(settings["hooks"]["PreToolUse"]), 1)

    def test_every_prompt_reads_its_agent_with_the_projects_learned_entries(self):
        """A slash command runs in the main session, not as the dispatched agent, so it must load the learned
        entries itself: the generated host file (which has them), or the package file plus learned/<agent>.md."""
        self.install("--host", "claude", "--host", "copilot")
        prompts = sorted((ENGINE.parent / ".apm" / "prompts").glob("*.prompt.md"))
        self.assertTrue(prompts)
        for p in prompts:
            agent = install.split_frontmatter(p.read_text(encoding="utf-8"))[0].get("agent")
            self.assertTrue(agent, p.name)
            for host_file in (f".claude/agents/{agent}.md", f".github/agents/{agent}.agent.md"):
                self.assertTrue((self.root / host_file).exists(), host_file)
            cmd = (self.root / ".claude/commands" / p.name.replace(".prompt.md", ".md")).read_text(encoding="utf-8")
            for ref in (f".claude/agents/{agent}.md", f".github/agents/{agent}.agent.md",
                        f".fyzxsflow/package/agents/{agent}.agent.md", f".fyzxsflow/learned/{agent}.md"):
                self.assertIn(ref, cmd, (p.name, ref))

    def test_learned_entries_live_in_the_project_and_survive_reinstall_which_replaces_the_package(self):
        self.install("--host", "claude")
        learned = self.root / ".fyzxsflow/learned/implementer.md"
        learned.parent.mkdir(parents=True)
        learned.write_text("# Learned: implementer\n<!-- curator notes -->\n- Read the flag seam first. (F-3, hits 2)\n",
                           encoding="utf-8")
        stray = self.root / ".fyzxsflow/package/engine/dropped_upstream.py"
        stray.write_text("x\n", encoding="utf-8")
        code, out = self.install("--host", "claude")
        self.assertEqual(code, 0, out)
        self.assertFalse(stray.exists())  # the package is installer-owned: rewritten whole
        host = (self.root / ".claude/agents/implementer.md").read_text(encoding="utf-8")
        self.assertTrue(host.rstrip().endswith("- Read the flag seam first. (F-3, hits 2)"))
        self.assertNotIn("curator notes", host)
        self.assertNotIn("flag seam", (self.root / ".fyzxsflow/package/agents/implementer.agent.md").read_text(encoding="utf-8"))
        settings = json.loads((self.root / ".claude/settings.json").read_text(encoding="utf-8"))
        self.assertEqual(len(settings["hooks"]["PreToolUse"]), 1)

    def test_migrates_an_agentflow_install(self):
        old = self.root / ".agentflow"
        (old / "agents").mkdir(parents=True)
        (old / "engine").mkdir()
        (old / "engine" / "run.py").write_text("old\n", encoding="utf-8")
        (old / "agents" / "tester.agent.md").write_text(
            "---\nname: tester\n---\n# Tester\n\n## Learned\n<!-- Maintained by the Curator. -->\n- No ! in asserts. (F-70)\n",
            encoding="utf-8")
        (old / "agents" / "validator.agent.md").write_text("# V\n\n## Learned\n<!-- only the comment -->\n", encoding="utf-8")
        (old / "config.json").write_text('{"runner": {"note": "see .agentflow/engine/runner.py"}}\n', encoding="utf-8")
        (old / "docs").mkdir()
        (old / "docs" / "index.md").write_text("Pack: `.agentflow/docs/tech/csharp.md`, `.agentflow/context/role-contracts.md`\n",
                                               encoding="utf-8")
        run = old / "runs" / "completed" / "r1"
        run.mkdir(parents=True)
        (run / "ledger.md").write_text("ran .agentflow/engine/run.py\n", encoding="utf-8")
        rules = self.root / ".claude" / "rules"
        rules.mkdir()
        (rules / "agentflow-working-agreement.md").write_text("<!-- generated by agentflow install.py -->\n", encoding="utf-8")
        (rules / "agentflow-mine.md").write_text("hand-written, keep\n", encoding="utf-8")
        (self.root / ".claude" / "settings.json").write_text(json.dumps({"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [
            {"type": "command", "command": 'python -I "$CLAUDE_PROJECT_DIR/.agentflow/engine/hooks/block_kill_by_name.py"'}]}]}}),
            encoding="utf-8")
        (self.root / ".gitignore").write_text("bin/\n# agentflow: ad-hoc runner/gate output outside a run\n.agentflow/runs/_adhoc/\n",
                                              encoding="utf-8")
        code, out = self.install("--host", "claude")
        self.assertEqual(code, 0, out)
        self.assertIn("migrated .agentflow/ -> .fyzxsflow/", out)
        home = self.root / ".fyzxsflow"
        self.assertFalse(old.exists())
        self.assertEqual((home / "learned" / "tester.md").read_text(encoding="utf-8").splitlines()[-1], "- No ! in asserts. (F-70)")
        self.assertFalse((home / "learned" / "validator.md").exists())  # nothing learned, no file
        self.assertIn("- No ! in asserts. (F-70)", (self.root / ".claude/agents/tester.md").read_text(encoding="utf-8"))
        self.assertIn(".fyzxsflow/package/engine/runner.py", (home / "config.json").read_text(encoding="utf-8"))
        self.assertEqual((home / "docs" / "index.md").read_text(encoding="utf-8"),
                         "Pack: `.fyzxsflow/docs/tech/csharp.md`, `.fyzxsflow/package/context/role-contracts.md`\n")
        self.assertEqual((home / "runs/completed/r1/ledger.md").read_text(encoding="utf-8"), "ran .agentflow/engine/run.py\n")
        self.assertFalse((rules / "agentflow-working-agreement.md").exists())
        self.assertTrue((rules / "agentflow-mine.md").exists())
        self.assertTrue((rules / "fyzxsflow-working-agreement.md").exists())
        hooks = json.loads((self.root / ".claude/settings.json").read_text(encoding="utf-8"))["hooks"]["PreToolUse"]
        self.assertEqual([h["hooks"][0]["command"] for h in hooks],
                         [f'{install.python_name()} -I "$CLAUDE_PROJECT_DIR/.fyzxsflow/package/engine/hooks/block_kill_by_name.py"'])
        gi = (self.root / ".gitignore").read_text(encoding="utf-8")
        self.assertNotIn(".agentflow", gi)
        self.assertEqual(gi.count(".fyzxsflow/runs/_adhoc/"), 1)

    def test_migration_refuses_while_a_run_is_active(self):
        (self.root / ".agentflow" / "runs" / "active" / "r1").mkdir(parents=True)
        code, out = self.install("--host", "claude")
        self.assertEqual(code, 2)
        self.assertIn("active run (r1)", out)
        self.assertTrue((self.root / ".agentflow" / "runs" / "active" / "r1").exists())
        self.assertFalse((self.root / ".fyzxsflow").exists())

    def test_feedback_inbox_is_created_once_and_owner_items_are_left_alone(self):
        self.install("--host", "claude")
        inbox = self.root / ".fyzxsflow" / "feedback"
        self.assertIn("Feedback inbox", (inbox / "README.md").read_text(encoding="utf-8"))
        (inbox / "README.md").write_text("my own guide\n", encoding="utf-8")
        (inbox / "idea.md").write_text("change X in Y.cs to Z\n", encoding="utf-8")
        self.install("--host", "claude")
        self.assertEqual((inbox / "README.md").read_text(encoding="utf-8"), "my own guide\n")
        self.assertEqual((inbox / "idea.md").read_text(encoding="utf-8"), "change X in Y.cs to Z\n")

    def test_sync_regenerates_host_files_from_installed_copy(self):
        self.install("--host", "claude")
        learned = self.root / ".fyzxsflow/learned/validator.md"
        learned.parent.mkdir(parents=True)
        learned.write_text("# Learned: validator\n- learned entry\n", encoding="utf-8")
        code, out = self.install("--sync", "--host", "claude", script=self.root / ".fyzxsflow/package/engine/install.py")
        self.assertEqual(code, 0, out)
        self.assertIn("learned entry", (self.root / ".claude/agents/validator.md").read_text(encoding="utf-8"))

    def test_gitignore_gets_adhoc_line_once_and_warns_on_ignored_runs(self):
        (self.root / ".gitignore").write_text("bin/\n.fyzxsflow/runs/\n", encoding="utf-8")
        code, out = self.install("--host", "claude")
        self.assertEqual(code, 0, out)
        self.assertIn("warning: .gitignore ignores .fyzxsflow/runs/", out)
        self.install("--host", "claude")
        text = (self.root / ".gitignore").read_text(encoding="utf-8")
        self.assertEqual(text.count(".fyzxsflow/runs/_adhoc/"), 1)
        self.assertTrue(text.startswith("bin/\n"))

    def test_hook_uses_python3_where_python_is_missing_and_reinstall_keeps_one_hook(self):
        from unittest import mock
        with mock.patch.object(install.shutil, "which", lambda name: "/usr/bin/python3" if name == "python3" else None):
            self.assertEqual(install.python_name(), "python3")
        with mock.patch.object(install.shutil, "which", lambda name: None):
            self.assertEqual(install.python_name(), "python")
        script = '"$CLAUDE_PROJECT_DIR/.fyzxsflow/package/engine/hooks/block_kill_by_name.py"'
        other = "python9" if install.python_name() == "python" else "python"
        (self.root / ".claude" / "settings.json").write_text(json.dumps({"hooks": {"PreToolUse": [
            {"matcher": "Bash|PowerShell", "hooks": [{"type": "command", "command": f"{other} -I {script}"}]}]}}),
            encoding="utf-8")
        code, out = self.install("--host", "claude")
        self.assertEqual(code, 0, out)
        hooks = json.loads((self.root / ".claude/settings.json").read_text(encoding="utf-8"))["hooks"]["PreToolUse"]
        self.assertEqual([h["hooks"][0]["command"] for h in hooks], [f"{install.python_name()} -I {script}"])

    def test_sync_without_install_fails(self):
        code, _ = self.install("--sync", "--host", "claude")
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()

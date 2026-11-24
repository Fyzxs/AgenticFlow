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

    def test_a_copilot_only_install_never_touches_claude(self):
        seg = self.root / ".fyzxsflow" / "docs" / "segments"
        seg.mkdir(parents=True)
        (seg / "app.md").write_text('---\npaths:\n  - "src/**"\n---\n# Segment: app\n', encoding="utf-8")
        self.assertEqual(self.install("--host", "claude")[0], 0)  # an earlier Claude install, with its pointer
        self.assertTrue((self.root / ".claude/rules/fyzxsflow-app.md").exists())

        def snapshot():
            return {p.relative_to(self.root).as_posix(): (p.read_bytes(), p.stat().st_mtime_ns)
                    for p in sorted((self.root / ".claude").rglob("*")) if p.is_file()}
        before = snapshot()
        code, out = self.install("--host", "copilot")
        self.assertEqual(code, 0, out)
        self.assertEqual(snapshot(), before)  # nothing written, deleted or rewritten under .claude/
        self.assertNotIn(".claude/", out)
        self.assertTrue((self.root / ".github/instructions/fyzxsflow-app.instructions.md").exists())
        installed = json.loads((self.root / ".fyzxsflow/package/INSTALLED.json").read_text(encoding="utf-8"))
        self.assertEqual(installed["hosts"], ["copilot"])
        # the Curator syncs one host per call: a sync adds its host, never drops another
        self.assertEqual(self.install("--sync", "--host", "copilot",
                                      script=self.root / ".fyzxsflow/package/engine/install.py")[0], 0)
        self.assertEqual(self.install("--sync", "--host", "claude",
                                      script=self.root / ".fyzxsflow/package/engine/install.py")[0], 0)
        installed = json.loads((self.root / ".fyzxsflow/package/INSTALLED.json").read_text(encoding="utf-8"))
        self.assertEqual(installed["hosts"], ["claude", "copilot"])

    def test_installs_package_and_both_hosts(self):
        code, out = self.install("--host", "claude", "--host", "copilot")
        self.assertEqual(code, 0, out)
        pkg = self.root / ".fyzxsflow" / "package"
        for rel in ("engine/runner.py", "engine/layout.py", "engine/hooks/block_kill_by_name.py",
                    "context/role-contracts.md", "agents/implementer.agent.md", "templates/run/brief.md",
                    "skills/correction-mining/SKILL.md", "INSTALLED.json"):
            self.assertTrue((pkg / rel).exists(), rel)
        self.assertFalse((pkg / "engine" / "tests").exists())
        self.assertEqual(list(pkg.rglob("__pycache__")), [])  # the install imports the installed engine: no bytecode
        self.assertEqual(json.loads((pkg / "INSTALLED.json").read_text(encoding="utf-8"))["fyzxsflow"], "0.4.9")
        self.assertTrue((self.root / ".claude/agents/implementer.md").exists())
        flow_cmd = (self.root / ".claude/commands/flow.md").read_text(encoding="utf-8")
        self.assertIn("Request: $ARGUMENTS", flow_cmd)
        self.assertIn('argument-hint: "[--preceptee] <what to build or fix', flow_cmd)
        self.assertNotIn("agent: orchestrator", flow_cmd)  # Copilot's routing key; Claude commands don't take it
        skill = (self.root / ".github/skills/flow/SKILL.md").read_text(encoding="utf-8")
        self.assertTrue(skill.startswith("---\nname: flow\ndescription: \"Run FyzxsFlow"), skill[:120])
        self.assertIn('argument-hint: "[--preceptee] <what to build or fix', skill)
        self.assertIn("disable-model-invocation: true", skill)
        self.assertIn(".github/agents/orchestrator.agent.md", skill)  # the body names the agent to act as
        self.assertFalse((self.root / ".github/prompts").exists())
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
        self.assertEqual(len(settings["hooks"]["PreToolUse"]), 2)

    def test_reinstall_replaces_old_prompt_files_with_skills_and_keeps_the_owners_prompts(self):
        old = self.root / ".github" / "prompts"
        old.mkdir(parents=True)
        (old / "flow.prompt.md").write_text("---\nagent: orchestrator\n---\nold\n", encoding="utf-8")
        (old / "mine.prompt.md").write_text("my own prompt\n", encoding="utf-8")
        code, out = self.install("--host", "copilot")
        self.assertEqual(code, 0, out)
        self.assertFalse((old / "flow.prompt.md").exists())
        self.assertTrue((old / "mine.prompt.md").exists())
        for p in sorted((ENGINE.parent / ".apm" / "prompts").glob("*.prompt.md")):
            name = p.name.replace(".prompt.md", "")
            skill = self.root / ".github" / "skills" / name / "SKILL.md"
            self.assertTrue(skill.exists(), name)
            self.assertRegex(name, r"^[a-z0-9-]{1,64}$")  # VS Code silently skips a skill with any other name
            self.assertIn(f"name: {name}\n", skill.read_text(encoding="utf-8"))

    def test_package_skills_reach_both_hosts_and_stale_copies_go(self):
        """Hosts discover skills only under .claude/skills and .github/skills; a copy in the package alone is never
        offered to the model."""
        mine = self.root / ".claude/skills/mine/SKILL.md"
        mine.parent.mkdir(parents=True)
        mine.write_text("---\nname: mine\ndescription: x\n---\nkeep\n", encoding="utf-8")
        code, out = self.install("--host", "claude", "--host", "copilot")
        self.assertEqual(code, 0, out)
        for host in (".claude", ".github"):
            text = (self.root / host / "skills/correction-mining/SKILL.md").read_text(encoding="utf-8")
            self.assertTrue(text.startswith("---\nname: correction-mining\ndescription: "), text[:80])
            self.assertIn(install.SKILL_MARKER, text)
            self.assertNotIn("disable-model-invocation", text)  # the model may pick it by its description
            self.assertIn(".fyzxsflow/package/skills/correction-mining/scripts/", text)  # scripts stay in the package
        stale = self.root / ".claude/skills/dropped/SKILL.md"
        stale.parent.mkdir()
        stale.write_text(f"---\nname: dropped\n---\n{install.SKILL_MARKER}\nold\n", encoding="utf-8")
        code, out = self.install("--sync", "--host", "claude")
        self.assertEqual(code, 0, out)
        self.assertFalse(stale.parent.exists())
        self.assertTrue(mine.exists())

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
        self.assertEqual(len(settings["hooks"]["PreToolUse"]), 2)

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
                         [f'{install.python_name()} -I "$CLAUDE_PROJECT_DIR/.fyzxsflow/package/engine/hooks/block_kill_by_name.py"',
                          f'{install.python_name()} -I "$CLAUDE_PROJECT_DIR/.fyzxsflow/package/engine/hooks/orchestrator_guard.py"'])
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
        self.assertEqual([h["hooks"][0]["command"] for h in hooks][0], f"{install.python_name()} -I {script}")
        self.assertEqual(len(hooks), 2)

    def settings(self):
        return json.loads((self.root / ".claude/settings.json").read_text(encoding="utf-8"))

    def test_the_main_session_is_the_orchestrator_by_default_with_its_guard(self):
        code, out = self.install("--host", "claude")
        self.assertEqual(code, 0, out)
        s = self.settings()
        self.assertEqual(s["agent"], "orchestrator")
        self.assertEqual(s["model"], "keep-me")
        guard = s["hooks"]["PreToolUse"][1]
        self.assertEqual(guard["matcher"], "Edit|Write|MultiEdit|NotebookEdit|Bash|PowerShell")
        self.assertTrue(guard["hooks"][0]["command"].endswith('engine/hooks/orchestrator_guard.py"'))
        self.assertTrue((self.root / ".fyzxsflow/package/engine/hooks/orchestrator_guard.py").exists())
        installed = json.loads((self.root / ".fyzxsflow/package/INSTALLED.json").read_text(encoding="utf-8"))
        self.assertEqual(installed["claude_settings"], {"agent": True, "probe": False})
        # --no-main-agent removes the agent we wrote; the guard stays (it only acts for an orchestrator session)
        self.install("--host", "claude", "--no-main-agent")
        self.assertNotIn("agent", self.settings())
        code, out = self.install("--host", "claude", "--probe-hooks")
        self.assertTrue(self.settings()["hooks"]["PreToolUse"][1]["hooks"][0]["command"].endswith(" --probe"))
        self.install("--host", "claude")
        self.assertFalse(self.settings()["hooks"]["PreToolUse"][1]["hooks"][0]["command"].endswith(" --probe"))

    def test_merge_keeps_the_repos_own_settings_byte_for_byte_and_reinstall_writes_nothing(self):
        own = {"matcher": "Bash", "hooks": [{"type": "command",
                                             "command": 'python "$CLAUDE_PROJECT_DIR/.claude/hooks/block-backslash-inline-scripts.py"'}]}
        kill = {"matcher": "Bash|PowerShell", "hooks": [{"type": "command", "command":
                f'python3 -I "$CLAUDE_PROJECT_DIR/.fyzxsflow/package/engine/hooks/block_kill_by_name.py"'}]}
        start = {"permissions": {"allow": ["Bash(git status)"]}, "hooks": {"PreToolUse": [kill, own]}, "env": {"A": "1"}}
        f = self.root / ".claude/settings.json"
        f.write_bytes(json.dumps(start, indent=2).replace("\n", "\r\n").encode("utf-8") + b"\r\n")
        code, out = self.install("--host", "claude")
        self.assertEqual(code, 0, out)
        raw = f.read_bytes()
        self.assertNotIn(b"\n", raw.replace(b"\r\n", b""))  # CRLF kept
        s = self.settings()
        self.assertEqual(list(s), ["permissions", "hooks", "env", "agent"])
        pre = s["hooks"]["PreToolUse"]
        self.assertEqual(pre[1], own)  # the repo's own entry, untouched and in place
        self.assertEqual(pre[0]["hooks"][0]["command"].split()[0], install.python_name())  # interpreter updated in place
        self.assertEqual(len(pre), 3)
        mtime = f.stat().st_mtime_ns
        code, out = self.install("--sync", "--host", "claude", script=self.root / ".fyzxsflow/package/engine/install.py")
        self.assertEqual(code, 0, out)
        self.assertEqual(f.read_bytes(), raw)
        self.assertEqual(f.stat().st_mtime_ns, mtime)
        self.assertIn(": 0 files written", out)

    def test_an_agent_the_owner_set_is_kept(self):
        f = self.root / ".claude/settings.json"
        f.write_text(json.dumps({"agent": "reviewer"}), encoding="utf-8")
        code, out = self.install("--host", "claude")
        self.assertIn('sets "agent": "reviewer"; left as is', out)
        self.assertEqual(self.settings()["agent"], "reviewer")
        f.write_text(json.dumps({"agent": "orchestrator"}), encoding="utf-8")  # the owner chose it themselves
        self.install("--host", "claude", "--no-main-agent")
        self.assertEqual(self.settings()["agent"], "orchestrator")

    def test_copilot_gets_the_guard_scoped_to_the_orchestrator_and_the_kill_hook(self):
        code, out = self.install("--host", "copilot")
        self.assertEqual(code, 0, out)
        orch = (self.root / ".github/agents/orchestrator.agent.md").read_text(encoding="utf-8")
        head = orch.split("\n---\n", 1)[0]
        self.assertIn("hooks:\n  PostToolUse:\n    - type: command\n      command: ", head)
        self.assertIn("engine/hooks/orchestrator_guard.py --scoped", head)
        self.assertNotIn("hooks:", (self.root / ".github/agents/implementer.agent.md").read_text(encoding="utf-8").split("\n---\n", 1)[0])
        hooks = json.loads((self.root / ".github/hooks/fyzxsflow.json").read_text(encoding="utf-8"))
        self.assertEqual(hooks["version"], 1)
        self.assertIn("block_kill_by_name.py", hooks["hooks"]["PreToolUse"][0]["command"])

    def test_sync_without_install_fails(self):
        code, _ = self.install("--sync", "--host", "claude")
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()

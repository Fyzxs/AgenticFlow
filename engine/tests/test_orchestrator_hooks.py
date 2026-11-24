"""Tests for the orchestrator's hooks (engine/hooks/orchestrator_rules.py through orchestrator_guard_claude.py and
orchestrator_guard_copilot.py): its own work draws a reminder to delegate (never a block); an open review pause
blocks its dispatches and lane/PR moves; subagents and bookkeeping draw nothing."""

import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

HOOKS = pathlib.Path(__file__).resolve().parent.parent / "hooks"
CLAUDE, COPILOT, PROBE = (HOOKS / "orchestrator_guard_claude.py", HOOKS / "orchestrator_guard_copilot.py",
                          HOOKS / "orchestrator_probe.py")
ENGINE = HOOKS.parent


def hook(payload, *args, cwd=None):
    """Run a host script: "--scoped" means the Copilot script ("pre" or "post", default post), else Claude's."""
    if "--scoped" in args:
        rest = [a for a in args if a != "--scoped"]
        argv = [str(COPILOT), *(rest if {"pre", "post"} & set(rest) else ["post", *rest])]
    else:
        argv = [str(CLAUDE), *args]
    return subprocess.run([sys.executable, "-I", "-B", *argv], input=json.dumps(payload) if payload is not None else "",
                          capture_output=True, text=True, cwd=cwd)
ENG = ".fyzxsflow/package/engine"


def run(payload, *args, raw=None, cwd=None):
    """(1 if reminded else 0, the reminder, stdout). The hook itself always exits 0 and never decides permission."""
    if raw is not None:
        p = subprocess.run([sys.executable, "-I", "-B", str(CLAUDE), *args], input=raw, capture_output=True, text=True)
    else:
        p = hook(payload, *args, cwd=cwd)
    assert p.returncode == 0, p.stderr
    if not p.stdout.strip():
        return 0, "", p.stdout
    out = json.loads(p.stdout)
    assert "permissionDecision" not in json.dumps(out), out
    return 1, out["hookSpecificOutput"]["additionalContext"], p.stdout


def orch(tool, **tool_input):
    return {"tool_name": tool, "agent_type": "orchestrator", "tool_input": tool_input}


class EditTests(unittest.TestCase):
    def test_the_orchestrators_own_edit_draws_a_reminder_naming_the_owner(self):
        code, err, out = run(orch("Edit", file_path=".claude/rules/x.md"))
        self.assertEqual(code, 1)
        self.assertIn("docs-gardener", err)
        self.assertIn("reminder: delegate", err)
        self.assertEqual(json.loads(out)["hookSpecificOutput"]["hookEventName"], "PreToolUse")
        for path, owner in ((".fyzxsflow/learned/orchestrator.md", "curator"),
                            (".fyzxsflow/runs/active/r1/work-packages/WP-01.md", "build-coordinator"),
                            ("pipelines/deploy.yml", "iac-implementer")):
            code, err, _ = run(orch("Write", file_path=path))
            self.assertEqual(code, 1, path)
            self.assertIn(owner, err, path)

    def test_subagents_and_plain_sessions_are_allowed(self):
        edit = orch("Edit", file_path=".claude/rules/x.md")
        self.assertEqual(run({**edit, "agent_id": "a1b2", "agent_type": "docs-gardener"})[0], 0)
        self.assertEqual(run({**edit, "agent_id": "a1b2"})[0], 0)  # a dispatched orchestrator
        self.assertEqual(run({"tool_name": "Edit", "tool_input": {"file_path": "x.md"}})[0], 0)  # a plain session
        self.assertEqual(run({**edit, "agent_type": "general-purpose"})[0], 0)  # claude --agent <other>

    def test_every_edit_tool_is_covered(self):
        for tool, key in (("Write", "file_path"), ("MultiEdit", "file_path"), ("NotebookEdit", "notebook_path")):
            self.assertEqual(run(orch(tool, **{key: "src/app.py"}))[0], 1, tool)

    def test_its_own_run_folder_bookkeeping_is_allowed(self):
        for path in (".fyzxsflow/runs/active/r1/reviews/WP-01-api.implementer.md",
                     "/home/me/repo/.fyzxsflow/runs/active/r1/input.md",
                     ".fyzxsflow/runs/active/r1/review-requests.md"):
            self.assertEqual(run(orch("Write", file_path=path))[0], 0, path)
        self.assertEqual(run(orch("Write", file_path=".fyzxsflow/runs/active/r1/reviews/../brief.md"))[0], 1)

    def test_malformed_input_is_allowed(self):
        self.assertEqual(run(None, raw="not json")[0], 0)
        self.assertEqual(run(None, raw="[]")[0], 0)


class ShellTests(unittest.TestCase):
    ALLOWED = [
        f'python -I {ENG}/run.py log r build decided "x; y"',
        'git add a b && git commit -m "m"',
        "git status",
        f"python3 -I {ENG}/lanes.py pr --run r --group g --publish --body-file f",
        "docker compose -p docmcstorage-wp21 down -v",
        "az repos pr show --id 95 --output json",
        f"cd /repo && python -X utf8 -I {ENG}/review.py needed --run r --agent tester 2>&1",
        "git -C ../lane diff --stat main..HEAD > /dev/null",
        "git worktree list",
        f"python -I /abs/repo/{ENG}/pr.py update --run r --body-file r/pr-description.md",
    ]
    DENIED = [
        (f"python -I {ENG}/runner.py ci --run r", "build-test-runner"),
        (f"git status && python -I {ENG}/runner.py quick", "build-test-runner"),
        ("az devops invoke --area git --resource pullRequestThreadComments --http-method POST", "pr-producer"),
        ("az repos pr update --id 95 --description x", "pr-producer"),
        ("echo x > .claude/rules/a.md", "docs-gardener"),
        ("cat a | tee b", ""),
        ('git commit -m "$(cat msg)"', ""),
        ("dotnet test", "build-test-runner"),
        ("sed -i s/a/b/ f", ""),
        (f"python -I {ENG}/pr.py comment --run r --group g --body-file f", "pr-producer"),
        (f"python -I {ENG}/gates.py pre-pr --run r", "gate-analyst"),
        ("python -c 'open(\"x\",\"w\")'", ""),
        ("git commit -F - <<'EOF'\nmsg\nEOF", ""),
        ("git worktree add ../x", ""),
        ("git reset --hard", ""),
        ("(cd x; rm -rf y)", ""),
    ]

    def test_bookkeeping_commands_are_allowed(self):
        for cmd in self.ALLOWED:
            code, err, _ = run(orch("Bash", command=cmd))
            self.assertEqual(code, 0, f"{cmd}: {err}")

    def test_work_draws_a_reminder_naming_the_owner(self):
        for cmd, owner in self.DENIED:
            code, err, _ = run(orch("Bash", command=cmd))
            self.assertEqual(code, 1, cmd)
            self.assertIn(owner or "Dispatch the agent that owns it", err, cmd)

    def test_the_same_commands_from_a_subagent_are_allowed(self):
        for cmd, _ in self.DENIED:
            self.assertEqual(run({**orch("Bash", command=cmd), "agent_id": "a1", "agent_type": "build-test-runner"})[0],
                             0, cmd)

    def test_powershell_is_covered(self):
        self.assertEqual(run(orch("PowerShell", command="dotnet test"))[0], 1)


class CopilotTests(unittest.TestCase):
    """Copilot payloads: camelCase (toolName, toolArgs as a JSON string) or snake_case; the hook is agent-scoped."""

    def test_scoped_hook_reminds_the_main_agent_after_its_edits_and_work(self):
        _, text, out = run({"toolName": "edit", "toolArgs": {"path": "src/a.py"}}, "--scoped")
        self.assertEqual(json.loads(out)["additionalContext"], text)  # Copilot CLI: top level
        self.assertEqual(json.loads(out)["hookSpecificOutput"]["hookEventName"], "PostToolUse")
        self.assertEqual(run({"toolName": "edit", "toolArgs": json.dumps({"path": ".claude/rules/x.md"})}, "--scoped")[0], 1)
        self.assertEqual(run({"toolName": "bash", "toolArgs": json.dumps({"command": "dotnet test"})}, "--scoped")[0], 1)
        self.assertEqual(run({"tool_name": "Write", "tool_input": {"file_path": "src/a.py"}}, "--scoped")[0], 1)
        patch = "*** Begin Patch\n*** Update File: src/a.py\n@@\n-x\n+y\n*** End Patch"
        self.assertEqual(run({"toolName": "apply_patch", "toolArgs": {"input": patch}}, "--scoped")[0], 1)

    def test_scoped_hook_allows_bookkeeping_and_subagents(self):
        self.assertEqual(run({"toolName": "bash", "toolArgs": json.dumps({"command": "git status"})}, "--scoped")[0], 0)
        self.assertEqual(run({"toolName": "edit", "agentId": "s1", "toolArgs": {"path": "src/a.py"}}, "--scoped")[0], 0)
        self.assertEqual(run({"toolName": "view", "toolArgs": {"path": "src/a.py"}}, "--scoped")[0], 0)

    def test_unscoped_copilot_payloads_without_an_agent_type_are_left_alone(self):
        self.assertEqual(run({"toolName": "edit", "toolArgs": {"path": "src/a.py"}})[0], 0)


class ProbeTests(unittest.TestCase):
    def test_probe_logs_and_allows_and_the_report_reads_it(self):
        with tempfile.TemporaryDirectory() as d:
            for payload in (orch("Edit", file_path="x.md"),
                            {"tool_name": "Write", "agent_id": "a1", "agent_type": "validator", "tool_input": {}}):
                self.assertEqual(run({**payload, "cwd": d}, "--probe", cwd=d)[0], 0)
            report = subprocess.run([sys.executable, "-I", "-B", str(PROBE), "report", "--root", d],
                                    capture_output=True, text=True)
            self.assertEqual(report.returncode, 0, report.stdout)
            self.assertIn("yes, the reminder reaches only the main session", report.stdout)
            self.assertEqual(list(pathlib.Path(d).rglob("__pycache__")), [])


class ReviewGateTests(unittest.TestCase):
    """While the run waits on the owner's review, the orchestrator may not dispatch or move lanes and PRs."""

    def setUp(self):
        self.root = pathlib.Path(tempfile.mkdtemp(prefix="fyzxsflow-gate-"))
        self.run_dir = self.root / ".fyzxsflow" / "runs" / "active" / "r1"
        self.run_dir.mkdir(parents=True)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.root, ignore_errors=True)

    def review(self, *args):
        return subprocess.run([sys.executable, "-I", "-B", str(ENGINE / "review.py"), *args],
                              capture_output=True, text=True, cwd=self.root)

    def pause(self, *extra):
        out = self.review("needed", "--run", str(self.run_dir), "--agent", "code-indicator", "--stage", "locate", *extra)
        self.assertIn("review=pause", out.stdout)

    def call(self, payload, *args):
        return hook({**payload, "cwd": str(self.root)}, *args, cwd=self.root)

    def test_an_open_pause_blocks_dispatch_on_claude_until_the_owner_answers(self):
        dispatch = {"tool_name": "Agent", "agent_type": "orchestrator", "tool_input": {"subagent_type": "validator"}}
        self.assertEqual(self.call(dispatch).returncode, 0)  # nothing open yet
        self.pause()
        self.assertEqual(self.review("open", "--run", str(self.run_dir)).returncode, 1)
        p = self.call(dispatch)
        self.assertEqual(p.returncode, 2)
        self.assertEqual(json.loads(p.stdout)["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("review.py decide --run r1 --agent code-indicator --target locate", p.stderr)
        self.assertIn("Never write a reply the owner didn't give", p.stderr)
        # a subagent, bookkeeping and read-only lane commands are not held
        self.assertEqual(self.call({**dispatch, "agent_id": "a1"}).returncode, 0)
        for cmd in ("git status", f"python -I {ENG}/lanes.py refresh --run r1", f"python -I {ENG}/review.py open --run r1"):
            self.assertEqual(self.call(orch("Bash", command=cmd)).returncode, 0, cmd)
        for cmd in (f"python -I {ENG}/lanes.py open --run r1", f"python -I {ENG}/pr.py ready --run r1"):
            self.assertEqual(self.call(orch("Bash", command=cmd)).returncode, 2, cmd)
        # the owner answers: the pause closes
        self.assertEqual(self.review("decide", "--run", str(self.run_dir), "--agent", "code-indicator", "--target",
                                     "locate", "--reply", "keep going to the end").returncode, 0)
        self.assertEqual(self.review("open", "--run", str(self.run_dir)).returncode, 0)
        self.assertEqual(self.call(dispatch).returncode, 0)

    def test_copilot_gates_before_the_call_and_reminds_after(self):
        self.pause()
        dispatch = {"toolName": "runSubagent", "toolArgs": json.dumps({"agentName": "validator"})}
        pre = self.call(dispatch, "--scoped", "pre")
        self.assertEqual(pre.returncode, 2)
        self.assertEqual(json.loads(pre.stdout)["permissionDecision"], "deny")  # Copilot CLI: top level
        self.assertEqual(self.call(dispatch, "--scoped", "post").returncode, 0)  # post never blocks
        self.assertEqual(self.call({**dispatch, "agentId": "s1"}, "--scoped", "pre").returncode, 0)

    def test_build_pauses_hold_only_their_group(self):
        out = self.review("needed", "--run", str(self.run_dir), "--agent", "implementer", "--stage", "build",
                          "--package", "WP-02")
        self.assertIn("review=pause reason=agent-level", out.stdout)
        self.assertEqual(self.review("open", "--run", str(self.run_dir)).returncode, 0)  # reviewed on the group PR
        (self.run_dir / "review-requests.md").write_text("- review: package=WP-02\n", encoding="utf-8")
        self.review("needed", "--run", str(self.run_dir), "--agent", "implementer", "--stage", "build",
                    "--package", "WP-02")
        self.assertEqual(self.review("open", "--run", str(self.run_dir)).returncode, 1)  # recorded for its group
        dispatch = {"tool_name": "Agent", "agent_type": "orchestrator", "tool_input": {}}
        self.assertEqual(self.call(dispatch).returncode, 0)  # but other groups go on
        self.review("decide", "--run", str(self.run_dir), "--agent", "implementer", "--target",
                    "WP-02-api-orders", "--reply", "approve")  # the file stem answers the package id
        self.assertEqual(self.review("open", "--run", str(self.run_dir)).returncode, 0)


if __name__ == "__main__":
    unittest.main()

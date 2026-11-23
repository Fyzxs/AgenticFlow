"""Tests for engine/hooks/orchestrator_guard.py: the orchestrator's own session does no work; subagents are untouched."""

import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

HOOKS = pathlib.Path(__file__).resolve().parent.parent / "hooks"
GUARD, PROBE = HOOKS / "orchestrator_guard.py", HOOKS / "orchestrator_probe.py"
ENG = ".fyzxsflow/package/engine"


def run(payload, *args, raw=None, cwd=None):
    p = subprocess.run([sys.executable, "-I", "-B", str(GUARD), *args], input=raw if raw is not None else json.dumps(payload),
                       capture_output=True, text=True, cwd=cwd)
    return p.returncode, p.stderr, p.stdout


def orch(tool, **tool_input):
    return {"tool_name": tool, "agent_type": "orchestrator", "tool_input": tool_input}


class EditTests(unittest.TestCase):
    def test_the_orchestrators_own_edit_is_denied_and_names_the_owner(self):
        code, err, out = run(orch("Edit", file_path=".claude/rules/x.md"))
        self.assertEqual(code, 2)
        self.assertIn("docs-gardener", err)
        self.assertEqual(json.loads(out)["hookSpecificOutput"]["permissionDecision"], "deny")
        for path, owner in ((".fyzxsflow/learned/orchestrator.md", "curator"),
                            (".fyzxsflow/runs/active/r1/work-packages/WP-01.md", "build-coordinator"),
                            ("pipelines/deploy.yml", "iac-implementer")):
            code, err, _ = run(orch("Write", file_path=path))
            self.assertEqual(code, 2, path)
            self.assertIn(owner, err, path)

    def test_subagents_and_plain_sessions_are_allowed(self):
        edit = orch("Edit", file_path=".claude/rules/x.md")
        self.assertEqual(run({**edit, "agent_id": "a1b2", "agent_type": "docs-gardener"})[0], 0)
        self.assertEqual(run({**edit, "agent_id": "a1b2"})[0], 0)  # a dispatched orchestrator
        self.assertEqual(run({"tool_name": "Edit", "tool_input": {"file_path": "x.md"}})[0], 0)  # a plain session
        self.assertEqual(run({**edit, "agent_type": "general-purpose"})[0], 0)  # claude --agent <other>

    def test_every_edit_tool_is_covered(self):
        for tool, key in (("Write", "file_path"), ("MultiEdit", "file_path"), ("NotebookEdit", "notebook_path")):
            self.assertEqual(run(orch(tool, **{key: "src/app.py"}))[0], 2, tool)

    def test_its_own_run_folder_bookkeeping_is_allowed(self):
        for path in (".fyzxsflow/runs/active/r1/reviews/WP-01-api.implementer.md",
                     "/home/me/repo/.fyzxsflow/runs/active/r1/input.md",
                     ".fyzxsflow/runs/active/r1/review-requests.md"):
            self.assertEqual(run(orch("Write", file_path=path))[0], 0, path)
        self.assertEqual(run(orch("Write", file_path=".fyzxsflow/runs/active/r1/reviews/../brief.md"))[0], 2)

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

    def test_work_is_denied_with_the_owner_named(self):
        for cmd, owner in self.DENIED:
            code, err, _ = run(orch("Bash", command=cmd))
            self.assertEqual(code, 2, cmd)
            self.assertIn(owner or "Dispatch the agent that owns it", err, cmd)

    def test_the_same_commands_from_a_subagent_are_allowed(self):
        for cmd, _ in self.DENIED:
            self.assertEqual(run({**orch("Bash", command=cmd), "agent_id": "a1", "agent_type": "build-test-runner"})[0],
                             0, cmd)

    def test_powershell_is_covered(self):
        self.assertEqual(run(orch("PowerShell", command="dotnet test"))[0], 2)


class CopilotTests(unittest.TestCase):
    """Copilot payloads: camelCase (toolName, toolArgs as a JSON string) or snake_case; the hook is agent-scoped."""

    def test_scoped_hook_denies_the_main_agents_edits_and_work(self):
        self.assertEqual(run({"toolName": "edit", "toolArgs": json.dumps({"path": ".claude/rules/x.md"})}, "--scoped")[0], 2)
        self.assertEqual(run({"toolName": "bash", "toolArgs": json.dumps({"command": "dotnet test"})}, "--scoped")[0], 2)
        self.assertEqual(run({"tool_name": "Write", "tool_input": {"file_path": "src/a.py"}}, "--scoped")[0], 2)
        patch = "*** Begin Patch\n*** Update File: src/a.py\n@@\n-x\n+y\n*** End Patch"
        self.assertEqual(run({"toolName": "apply_patch", "toolArgs": {"input": patch}}, "--scoped")[0], 2)

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
            self.assertIn("yes, blocking is safe", report.stdout)
            self.assertEqual(list(pathlib.Path(d).rglob("__pycache__")), [])


if __name__ == "__main__":
    unittest.main()

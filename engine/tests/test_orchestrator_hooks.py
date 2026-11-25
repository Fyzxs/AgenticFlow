"""Tests for the orchestrator's hooks (engine/hooks/orchestrator_rules.py through orchestrator_guard_claude.py and
orchestrator_guard_copilot.py): its own work draws a reminder to delegate (never a block); an open review pause
blocks its dispatches and lane/PR moves; subagents and bookkeeping draw nothing."""

import json
import os
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
        argv = [str(COPILOT), *(args if {"pre", "post", "prompt"} & set(args) else ["post", *args])]
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
        ("echo x > .claude/rules/a.md", "docs-gardener"),
        ("cat a | tee b", ""),
        ('git commit -m "$(cat msg)"', ""),
        ("dotnet test", "build-test-runner"),
        ("sed -i s/a/b/ f", ""),
        (f"python -I {ENG}/pr.py comment --run r --group g --body-file f", "pr-producer"),
        (f"python -I {ENG}/gates.py pre-pr --run r", "gate-analyst"),
        ("python -c 'open(\"x\",\"w\")'", ""),
        ("git commit -F - <<'EOF'\nmsg\nEOF", ""),
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
        for cmd, _ in self.DENIED:  # none of them is on the never-list
            self.assertEqual(run({**orch("Bash", command=cmd), "agent_id": "a1", "agent_type": "build-test-runner"})[0],
                             0, cmd)

    def test_powershell_is_covered(self):
        self.assertEqual(run(orch("PowerShell", command="dotnet test"))[0], 1)


class NeverListTests(unittest.TestCase):
    """Blocked for every caller on both hosts: the orchestrator, subagents, plain sessions."""
    NEVER = ["az repos pr update --id 95 --status completed", "az repos pr update --id 95 --description x",
             "az repos pr create --title t", "gh pr merge 42 --squash", "gh pr create --fill",
             "git worktree add ../lane fyzxsflow/r1", "git status && git worktree remove ../lane",
             "git push origin main", "git push origin HEAD:refs/heads/master", "git push -f origin +feature:main"]
    FINE = ["git push origin fyzxsflow/r1", "git push -u origin fyzxsflow/r1-api", "git worktree list",
            "az repos pr show --id 95", "gh pr view 42", f"python -I {ENG}/lanes.py pr --run r --group g --publish"]

    def test_every_caller_is_blocked_on_both_hosts(self):
        callers = ({"agent_type": "orchestrator"}, {"agent_id": "a1", "agent_type": "implementer"}, {})
        for cmd in self.NEVER:
            for who in callers:
                p = hook({"tool_name": "Bash", "tool_input": {"command": cmd}, **who})
                self.assertEqual(p.returncode, 2, f"claude {who} {cmd}")
                self.assertIn("never allowed, for any agent", p.stderr)
            p = hook({"toolName": "bash", "toolArgs": json.dumps({"command": cmd}), "agentId": "s1"}, "--scoped", "pre")
            self.assertEqual(p.returncode, 2, f"copilot {cmd}")
            self.assertEqual(json.loads(p.stdout)["permissionDecision"], "deny")
            self.assertEqual(hook({"toolName": "bash", "toolArgs": {"command": cmd}}, "pre").returncode, 2, cmd)

    def test_the_flows_own_pushes_and_reads_are_fine(self):
        for cmd in self.FINE:
            self.assertEqual(hook({"tool_name": "Bash", "tool_input": {"command": cmd},
                                   "agent_id": "a1"}).returncode, 0, cmd)

    def test_merging_into_the_default_or_run_branch_is_blocked(self):
        with tempfile.TemporaryDirectory() as d:
            git = lambda *a: subprocess.run(["git", "-C", d, *a], capture_output=True, text=True)  # noqa: E731
            git("init", "-q", "-b", "main"); git("commit", "-q", "--allow-empty", "-m", "i")
            merge = {"tool_name": "Bash", "tool_input": {"command": "git merge feature"}, "cwd": d, "agent_id": "a1"}
            self.assertEqual(hook(merge).returncode, 2)
            for branch in ("fyzxsflow/r1", "fyzxsflow/r1-api"):  # run and lane branches: lanes.py merges them
                git("checkout", "-q", "-b", branch)
                self.assertEqual(hook(merge).returncode, 2, branch)
            self.assertEqual(hook({**merge, "tool_input": {"command": "git merge --abort"}}).returncode, 0)
            git("checkout", "-q", "-b", "spike")
            self.assertEqual(hook(merge).returncode, 0)  # the owner's own branch


class CopilotSessionTests(unittest.TestCase):
    """Copilot repo hooks: the main session's agent comes from Copilot's session state (subagent.selected)."""

    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="fyzxsflow-copilot-"))
        self.home, self.root = self.tmp / "copilot-home", self.tmp / "repo"
        (self.root / ".fyzxsflow" / "runs" / "active").mkdir(parents=True)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def select(self, sid, agent):
        d = self.home / "session-state" / sid
        d.mkdir(parents=True, exist_ok=True)
        with (d / "events.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps({"type": "session.start", "data": {}}) + "\n")
            if agent:
                f.write(json.dumps({"type": "subagent.selected", "data": {"agentName": agent}}) + "\n")

    def call(self, mode, payload):
        env = {**os.environ, "COPILOT_HOME": str(self.home)}
        return subprocess.run([sys.executable, "-I", "-B", str(COPILOT), mode],
                              input=json.dumps({"cwd": str(self.root), **payload}), capture_output=True, text=True,
                              cwd=self.root, env=env)

    def test_flow_outside_the_orchestrator_is_blocked_at_the_prompt(self):
        self.select("s1", "")
        p = self.call("prompt", {"sessionId": "s1", "prompt": "/flow add a date input"})
        self.assertEqual(json.loads(p.stdout)["decision"], "block")
        self.assertIn("`copilot --agent orchestrator`", json.loads(p.stdout)["reason"])
        self.assertEqual(self.call("prompt", {"sessionId": "s1", "prompt": "explain this repo"}).stdout, "")
        self.select("s2", "orchestrator")
        self.assertEqual(self.call("prompt", {"sessionId": "s2", "prompt": "/flow add x"}).stdout, "")
        self.select("s3", "orchestrator")
        p = self.call("prompt", {"sessionId": "s3", "prompt": "/fyzxsflow-init"})
        self.assertIn("repo-cartographer", json.loads(p.stdout)["reason"])

    def test_before_the_agent_is_known_the_first_tool_call_decides(self):
        bash = {"toolName": "bash", "toolArgs": {"command": "ls"}}
        self.assertEqual(self.call("prompt", {"sessionId": "s4", "prompt": "/flow add x"}).stdout, "")  # not known
        self.select("s4", "")
        p = self.call("pre", {"sessionId": "s4", **bash})
        self.assertEqual(p.returncode, 2)
        self.assertIn("/agent orchestrator", p.stderr)
        self.call("prompt", {"sessionId": "s4", "prompt": "never mind, explain the repo"})  # a new request
        self.assertEqual(self.call("pre", {"sessionId": "s4", **bash}).returncode, 0)
        self.assertEqual(self.call("prompt", {"sessionId": "s5", "prompt": "/flow add x"}).stdout, "")
        self.select("s5", "orchestrator")
        self.assertEqual(self.call("pre", {"sessionId": "s5", **bash}).returncode, 0)
        self.assertFalse(list((self.root / ".fyzxsflow/runs/_adhoc/copilot-sessions").glob("s5.json")))

    def test_the_orchestrator_is_found_from_the_session_state(self):
        self.select("s6", "orchestrator")
        edit = {"sessionId": "s6", "toolName": "edit", "toolArgs": {"path": "src/a.py"}}
        self.assertIn("reminder: delegate", json.loads(self.call("post", edit).stdout)["additionalContext"])
        self.select("s7", "")
        self.assertEqual(self.call("post", {**edit, "sessionId": "s7"}).stdout, "")  # the default agent
        self.assertEqual(self.call("post", {**edit, "agentId": "x", "agentType": "implementer"}).stdout, "")
        run = self.root / ".fyzxsflow/runs/active/r1"
        run.mkdir()
        (run / "reviews.jsonl").write_text(json.dumps({"agent": "code-indicator", "target": "locate",
                                                       "stage": "locate", "decision": "pending"}) + "\n")
        task = {"sessionId": "s6", "toolName": "task", "toolArgs": {"agent_type": "validator"}}
        self.assertEqual(self.call("pre", task).returncode, 2)
        self.assertEqual(self.call("pre", {**task, "sessionId": "s7"}).returncode, 0)


class EncodingTests(unittest.TestCase):
    @staticmethod
    def post(payload):
        return subprocess.run([sys.executable, "-I", "-B", str(COPILOT), "post"], input=json.dumps(payload),
                              capture_output=True, text=True)

    def test_copilot_reports_mojibake_and_crlf_after_an_edit(self):
        with tempfile.TemporaryDirectory() as d:
            git = lambda *a: subprocess.run(["git", "-C", d, *a], capture_output=True, text=True)  # noqa: E731
            git("init", "-q"); git("config", "user.email", "t@e"); git("config", "user.name", "t")
            f = pathlib.Path(d) / "wp.md"
            f.write_bytes("one \u2014 two\n".encode("utf-8"))
            git("add", "wp.md"); git("commit", "-qm", "i")
            f.write_bytes("one \u00e2\u20ac\u201d two\r\n".encode("utf-8"))
            p = self.post({"toolName": "edit", "toolArgs": {"path": "wp.md"}, "cwd": d, "agentId": "a", "agentType": "x"})
            note = json.loads(p.stdout)["additionalContext"]
            self.assertIn("mojibake", note)
            self.assertIn("CRLF", note)
            f.write_bytes("one \u2014 two\n".encode("utf-8"))
            self.assertEqual(self.post({"toolName": "edit", "toolArgs": {"path": "wp.md"}, "cwd": d,
                                        "agentId": "a"}).stdout, "")


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

    def test_a_returned_agent_must_be_checked_for_review_before_the_next_dispatch(self):
        rep = self.run_dir / "reports" / "work-summarizer.md"
        rep.parent.mkdir()
        rep.write_text("---\nagent: work-summarizer\ntarget: brief\nmodel: claude:sonnet\n---\n", encoding="utf-8")
        dispatch = {"tool_name": "Agent", "agent_type": "orchestrator", "tool_input": {"subagent_type": "code-indicator"}}
        p = self.call(dispatch)
        self.assertEqual(p.returncode, 2)
        self.assertIn("work-summarizer's output (reports/work-summarizer.md) was never checked for review", p.stderr)
        validator = {**dispatch, "tool_input": {"subagent_type": "validator"}}
        self.assertEqual(self.call(validator).returncode, 0)  # its Validator runs before the check
        self.review("needed", "--run", str(self.run_dir), "--agent", "work-summarizer", "--stage", "intake")
        p = self.call(dispatch)  # checked; but level "on" means a pause is open now
        self.assertIn("waiting for the owner's review of work-summarizer", p.stderr)
        self.review("decide", "--run", str(self.run_dir), "--agent", "work-summarizer", "--target", "intake",
                    "--reply", "approve")
        self.assertEqual(self.call(dispatch).returncode, 0)
        pkg = self.run_dir / "reports" / "WP-01.implementer.md"  # a package hand-off is checked per package
        pkg.write_text("---\nagent: implementer\ntarget: WP-01\nmodel: claude:sonnet\n---\n", encoding="utf-8")
        self.assertEqual(self.call(dispatch).returncode, 2)
        self.review("needed", "--run", str(self.run_dir), "--agent", "implementer", "--stage", "build",
                    "--package", "WP-01")
        self.assertEqual(self.call(dispatch).returncode, 0)  # Build's agent-level review is on the group PR

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

"""Tests for engine/run.py, findings.py, ac_trace.py, docs_check.py and runner.py.

Each test builds its own temporary repo, so nothing touches the working tree.
Run: python -I engine/tests/run_all.py
"""

import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

ENGINE = pathlib.Path(__file__).resolve().parent.parent
TEMPLATES = ENGINE.parent / "templates"
PY = sys.executable


def run(script, *args, cwd=None):
    proc = subprocess.run([PY, "-I", str(ENGINE / script), *args], cwd=cwd, capture_output=True, text=True)
    return proc.returncode, proc.stdout + proc.stderr


class TempRepo(unittest.TestCase):
    def setUp(self):
        self.root = pathlib.Path(tempfile.mkdtemp(prefix="fyzxsflow-test-"))

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def new_run(self, ref="add a pull list page"):
        code, out = run("run.py", "new", "--source", "prompt", "--ref", ref, "--root", str(self.root))
        self.assertEqual(code, 0, out)
        return pathlib.Path(out.strip().splitlines()[-1])


class RunTests(TempRepo):
    def test_new_creates_layout_and_ledger(self):
        r = self.new_run()
        for sub in ("work-packages", "reports", "runner"):
            self.assertTrue((r / sub).is_dir())
        self.assertIn("add a pull list page", (r / "input.md").read_text(encoding="utf-8"))
        self.assertIn("| run | started |", (r / "ledger.md").read_text(encoding="utf-8"))

    def test_log_and_status(self):
        r = self.new_run()
        self.assertEqual(run("run.py", "log", str(r), "intake", "done", "brief validated")[0], 0)
        code, out = run("run.py", "status", str(r))
        self.assertEqual(code, 0)
        self.assertIn("| intake | done | brief validated |", out)

    def test_log_rejects_unknown_status(self):
        r = self.new_run()
        self.assertEqual(run("run.py", "log", str(r), "intake", "finished", "x")[0], 2)

    def test_log_accepts_skipped_for_a_step_that_is_off(self):
        r = self.new_run()
        code, out = run("run.py", "log", str(r), "deliver", "skipped", "pr off (project)")
        self.assertEqual(code, 0, out)

    def test_close_outside_git_moves_the_run_without_committing(self):
        r = self.new_run()
        code, out = run("run.py", "close", str(r), "--outcome", "abandoned", "--note", "test")
        self.assertEqual(code, 0, out)
        self.assertTrue((self.root / ".fyzxsflow/runs/abandoned" / r.name / "ledger.md").exists())

    def write_package(self, r, stem, segment, title, status=None):
        pid = stem[:5]
        fm = f"---\nid: {pid}\nsegment: {segment}\n" + (f"status: {status}\n" if status else "") + "---\n\n"
        (r / "work-packages" / f"{stem}.md").write_text(f"{fm}# {pid} — {segment}: {title}\n", encoding="utf-8")

    def test_packages_gives_readable_review_name_and_position(self):
        r = self.new_run()
        self.write_package(r, "WP-01-db-migration-add-column", "db-migration", "adds the column", "done")
        self.write_package(r, "WP-02-api-sort-field", "api", "the sort field", "building")
        self.write_package(r, "WP-03-web-sort-menu", "web", "the sort menu")
        code, out = run("run.py", "packages", str(r))
        self.assertEqual(code, 0, out)
        self.assertIn("2/3 WP-02  building api: the sort field", out)
        self.assertIn("3/3 WP-03  planned  web: the sort menu", out)
        code, out = run("run.py", "packages", str(r), "--current", "WP-02", "--agent", "implementer")
        self.assertEqual(code, 0, out)
        self.assertIn("review_file=reviews/WP-02-api-sort-field.implementer.md", out)
        self.assertIn("where=Package 2 of 3 (WP-02): api: the sort field", out)
        self.assertIn("done=WP-01", out)
        self.assertIn("next_package=WP-03: web: the sort menu", out)
        code, out = run("run.py", "packages", str(r), "--current", "WP-03")
        self.assertIn("next_package=none (last package)", out)
        self.assertNotIn("review_file", out)
        self.assertEqual(run("run.py", "packages", str(r), "--current", "WP-09")[0], 2)

    def test_stamp_records_the_model_on_reports_and_models_lists_them(self):
        r = self.new_run()
        agents = self.root / ".fyzxsflow" / "package" / "agents"
        agents.mkdir(parents=True)
        (agents / "implementer.agent.md").write_text("---\nname: implementer\ntier: standard\n---\n", encoding="utf-8")
        (agents / "validator.agent.md").write_text("---\nname: validator\ntier: deep\n---\n", encoding="utf-8")
        (self.root / ".fyzxsflow" / "config.json").write_text(
            json.dumps({"models": {"claude": {"deep": "opus", "standard": "sonnet", "fast": "haiku"}}}), encoding="utf-8")
        impl = r / "reports" / "WP-01.implementer.md"
        impl.write_text("---\nagent: implementer\ntarget: WP-01\nresult: done\n"
                        "model_reported: claude-sonnet-5-5\n---\n\n# body\n", encoding="utf-8")
        code, out = run("run.py", "stamp", str(impl), "--agent", "implementer")
        self.assertEqual(code, 0, out)
        text = impl.read_text(encoding="utf-8")
        self.assertIn("tier: standard\nmodel: claude:sonnet\nescalated: no\n---\n\n# body", text)
        self.assertIn("model_reported: claude-sonnet-5-5", text)  # the agent's own line is kept
        code, out = run("run.py", "stamp", str(impl), "--agent", "implementer", "--up", "1")  # re-stamp replaces
        self.assertIn("tier: deep\nmodel: claude:opus\nescalated: from standard", impl.read_text(encoding="utf-8"))
        self.assertEqual(impl.read_text(encoding="utf-8").count("tier:"), 1)
        val = r / "reports" / "WP-01.validator.implementer.md"
        val.write_text("---\nagent: validator\nresult: pass\n---\n", encoding="utf-8")
        run("run.py", "stamp", str(val), "--agent", "validator", "--model", "fable")
        self.assertIn("model: claude:fable (owner override)", val.read_text(encoding="utf-8"))
        self.assertIn("model_reported: unknown", val.read_text(encoding="utf-8"))
        silent = r / "reports" / "WP-02.tester.md"
        silent.write_text("---\nagent: tester\nresult: done\n---\n", encoding="utf-8")
        self.assertIn("does not say which model did the work",
                      run("run.py", "stamp", str(silent), "--agent", "implementer")[1])
        bad = r / "reports" / "WP-02.implementer.md"
        bad.write_text("---\nagent: implementer\nmodel_reported: m\n---\n| Criterion | Status | Evidence |\n|---|---|---|\n"
                       "| WP-02.1 | met | x |\n| **WP-02.2** the mapper | met | y |\n\nSee src/Nope.cs:4.\n",
                       encoding="utf-8")
        code, out = run("run.py", "stamp", str(bad), "--agent", "implementer")
        self.assertEqual(code, 0, out)
        self.assertIn("criteria row starts with 'WP-02.2** the mapper'", out)
        self.assertIn("citation src/Nope.cs:4: no such file", out)
        code, out = run("run.py", "models", str(r))
        self.assertEqual(code, 0, out)
        self.assertIn("| WP-01.implementer.md | implementer | deep | claude:opus | claude-sonnet-5-5 | from standard | done |", out)
        self.assertIn("| WP-01.validator.implementer.md | validator | deep | claude:fable (owner override) | unknown | no | pass |", out)


class CheckpointTests(TempRepo):
    def setUp(self):
        super().setUp()
        for args in (["init", "-q", "-b", "main"], ["config", "user.name", "Test"], ["config", "user.email", "t@example.com"],
                     ["config", "core.autocrlf", "false"]):
            subprocess.run(["git", *args], cwd=self.root, check=True)
        (self.root / "app.txt").write_text("v1", encoding="utf-8")
        subprocess.run(["git", "add", "app.txt"], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "base"], cwd=self.root, check=True)

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=self.root, capture_output=True, text=True).stdout

    def test_new_creates_and_records_the_working_branch(self):
        base = self.git("rev-parse", "HEAD").strip()
        r = self.new_run()
        branch = self.git("rev-parse", "--abbrev-ref", "HEAD").strip()
        self.assertEqual(branch, f"fyzxsflow/{r.name}")
        meta = (r / "input.md").read_text(encoding="utf-8")
        self.assertIn(f"branch: fyzxsflow/{r.name}", meta)
        self.assertIn(f"base: {base}", meta)
        self.assertIn("base_branch: main", meta)
        self.assertIn(f"branch=fyzxsflow/{r.name} from main", (r / "ledger.md").read_text(encoding="utf-8"))

    def test_new_stay_keeps_the_current_branch_and_an_existing_name_refuses(self):
        code, out = run("run.py", "new", "--source", "prompt", "--ref", "stay here", "--stay", "--root", str(self.root))
        self.assertEqual(code, 0, out)
        self.assertEqual(self.git("rev-parse", "--abbrev-ref", "HEAD").strip(), "main")
        self.git("branch", "taken")
        code, out = run("run.py", "new", "--source", "prompt", "--ref", "named", "--branch", "taken", "--root", str(self.root))
        self.assertEqual(code, 1, out)
        self.assertIn("could not create branch taken", out)
        self.assertFalse(any(p.name.endswith("-named") for p in (self.root / ".fyzxsflow/runs/active").iterdir()))

    def test_ship_check_rejects_a_ci_result_the_product_has_moved_past_and_a_dirty_tree(self):
        r = self.new_run()
        head = self.git("rev-parse", "HEAD").strip()
        (r / "runner" / "ci-20260101-000000-1.json").write_text(json.dumps(
            {"result": "pass", "steps": [], "skipped": [], "commit": head, "dirty": False}), encoding="utf-8")
        run("steps.py", "set", "extreme", "off", "--run", str(r), "--reason", "test")
        run("steps.py", "set", "gates", "off", "--run", str(r), "--reason", "test")
        code, out = run("run.py", "ship-check", str(r))
        self.assertIn("ci               pass", out)
        self.assertIn("tree             clean", out)
        (self.root / "app.txt").write_text("v2", encoding="utf-8")
        code, out = run("run.py", "ship-check", str(r))
        self.assertIn("tree             dirty", out)
        self.assertIn("uncommitted: app.txt", out)
        subprocess.run(["git", "commit", "-q", "-am", "v2"], cwd=self.root, check=True)
        code, out = run("run.py", "ship-check", str(r))
        self.assertEqual(code, 1, out)
        self.assertIn("ci               stale", out)
        self.assertIn(f"product files changed since the commit it tested ({head[:9]})", out)

    def test_checkpoint_commits_only_the_run_folder_and_not_raw_logs(self):
        r = self.new_run()
        (r / "brief.md").write_text("# brief", encoding="utf-8")
        (r / "runner" / "ci-1").mkdir()
        (r / "runner" / "ci-1" / "01-build.log").write_text("huge log", encoding="utf-8")
        (r / "runner" / "ci-1.json").write_text("{}", encoding="utf-8")
        (self.root / "app.txt").write_text("v2 work in progress", encoding="utf-8")
        subprocess.run(["git", "add", "app.txt"], cwd=self.root, check=True)
        code, out = run("run.py", "checkpoint", str(r), "intake")
        self.assertEqual(code, 0, out)
        committed = self.git("show", "--name-only", "--format=%s", "HEAD").split()
        self.assertIn(f"fyzxsflow({r.name}):", committed[0])
        self.assertTrue(any(p.endswith("brief.md") for p in committed))
        self.assertTrue(any(p.endswith("runner/ci-1.json") for p in committed))
        self.assertFalse(any(p.endswith(".log") for p in committed))
        self.assertNotIn("app.txt", committed)
        self.assertIn("M  app.txt", self.git("status", "--porcelain"))  # still staged, not committed

    def test_edits_detects_and_records_owner_changes(self):
        r = self.new_run()
        (r / "brief.md").write_text("# brief", encoding="utf-8")
        run("run.py", "checkpoint", str(r), "intake")
        self.assertIn("no edits", run("run.py", "edits", str(r))[1])
        (r / "brief.md").write_text("# brief\n- **AC-3** (stated): added by the owner", encoding="utf-8")
        (r / "reviews").mkdir()  # review files carry ## Human Feedback, recorded by review.py decide instead
        (r / "reviews" / "WP-01-x.implementer.md").write_text("## Human Feedback\nuse nameof\n", encoding="utf-8")
        code, out = run("run.py", "edits", str(r), "--record")
        self.assertEqual(code, 0, out)
        self.assertIn("brief.md", out)
        found = [json.loads(l) for l in (r / "findings.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual([f["kind"] for f in found], ["human-edit"])
        self.assertIn("owner edits", self.git("log", "-1", "--format=%s"))
        self.assertEqual(self.git("status", "--porcelain", "--", ".fyzxsflow"), "")

    def test_agent_output_is_never_recorded_as_an_owner_edit(self):
        r = self.new_run()
        run("run.py", "checkpoint", str(r), "build")
        # an agent returned: its report is not stamped yet, and the runner wrote a summary
        (r / "reports" / "ci.runner.md").write_text("---\nagent: build-test-runner\nmodel_reported: m\n---\n# ci\n",
                                                   encoding="utf-8")
        (r / "runner" / "ci-20260101-000000-1.json").write_text("{}", encoding="utf-8")
        code, out = run("run.py", "edits", str(r), "--record")
        self.assertEqual(code, 3, out)
        self.assertIn("agent report not stamped yet", out)
        self.assertEqual((r / "findings.jsonl").read_text(encoding="utf-8"), "")
        code, out = run("run.py", "stamp", str(r / "reports" / "ci.runner.md"), "--agent", "build-test-runner")
        self.assertEqual(code, 0, out)
        self.assertIn("build-test-runner output", self.git("log", "-1", "--format=%s"))
        self.assertEqual(self.git("status", "--porcelain", "--", ".fyzxsflow"), "")
        self.assertIn("no edits", run("run.py", "edits", str(r), "--record")[1])
        # engine-written files alone are checkpointed, never attributed to the owner
        (r / "gates" ).mkdir()
        (r / "gates" / "ci-20260101-000000-2.json").write_text("{}", encoding="utf-8")
        code, out = run("run.py", "edits", str(r), "--record")
        self.assertEqual(code, 0, out)
        self.assertEqual((r / "findings.jsonl").read_text(encoding="utf-8"), "")
        self.assertIn("engine output", self.git("log", "-1", "--format=%s"))

    def test_close_moves_active_to_completed_with_a_recorded_rename(self):
        r = self.new_run()
        (r / "brief.md").write_text("# brief", encoding="utf-8")
        run("run.py", "checkpoint", str(r), "intake")
        code, out = run("run.py", "list", "--root", str(self.root))
        self.assertIn("active: 1", out)
        code, out = run("run.py", "close", str(r), "--outcome", "completed", "--note", "PR #12")
        self.assertEqual(code, 0, out)
        dest = self.root / ".fyzxsflow" / "runs" / "completed" / r.name
        self.assertTrue((dest / "brief.md").exists())
        self.assertFalse(r.exists())
        self.assertIn("completed: PR #12", (dest / "ledger.md").read_text(encoding="utf-8"))
        self.assertIn("completed", self.git("log", "-1", "--format=%s"))
        self.assertIn("R", self.git("show", "--name-status", "--format=", "HEAD").split()[0])
        self.assertEqual(self.git("status", "--porcelain", "--", ".fyzxsflow"), "")
        code, out = run("run.py", "list", "--root", str(self.root))
        self.assertIn("active: 0", out)
        self.assertIn("completed: 1", out)
        self.assertEqual(run("run.py", "close", str(dest), "--outcome", "completed")[0], 2)

    def test_close_abandoned_before_any_checkpoint(self):
        r = self.new_run()
        code, out = run("run.py", "close", str(r), "--outcome", "abandoned", "--note", "owner stopped it")
        self.assertEqual(code, 0, out)
        dest = self.root / ".fyzxsflow" / "runs" / "abandoned" / r.name
        self.assertIn("abandoned: owner stopped it", (dest / "ledger.md").read_text(encoding="utf-8"))
        self.assertEqual(self.git("status", "--porcelain", "--", ".fyzxsflow"), "")

    def test_local_mode_commits_nothing(self):
        (self.root / ".fyzxsflow").mkdir(exist_ok=True)
        (self.root / ".fyzxsflow" / "profile.md").write_text("## Runs\n- Runs: local\n", encoding="utf-8")
        r = self.new_run()
        code, out = run("run.py", "checkpoint", str(r), "intake")
        self.assertEqual(code, 0)
        self.assertIn("runs are local", out)
        self.assertEqual(self.git("log", "--format=%s").split("\n")[0], "base")


class FindingsTests(TempRepo):
    def add(self, r, *extra):
        return run("findings.py", "add", "--run", str(r), "--source", "validator", "--target", "implementer",
                   "--severity", "major", "--summary", "missed the flag", "--evidence", "src/a.cs:12", *extra)

    def test_add_and_list(self):
        r = self.new_run()
        code, out = self.add(r, "--kind", "instance")
        self.assertEqual((code, out.strip()), (0, "F-1"))
        code, out = run("findings.py", "list", "--run", str(r))
        self.assertIn("F-1 [major] instance validator->implementer", out)

    def test_agent_gap_requires_rule(self):
        r = self.new_run()
        self.assertEqual(self.add(r, "--kind", "agent-gap")[0], 2)
        self.assertEqual(self.add(r, "--kind", "agent-gap", "--rule", "Read the flag seam from feature-flags.md")[0], 0)

    def test_rejects_unknown_kind(self):
        r = self.new_run()
        self.assertEqual(self.add(r, "--kind", "oops")[0], 2)

    def test_amend_updates_in_place_with_a_dated_note(self):
        r = self.new_run()
        self.add(r, "--kind", "instance")
        self.add(r, "--kind", "instance")
        code, out = run("findings.py", "amend", "F-1", "--run", str(r), "--fixed", "--severity", "minor",
                        "--evidence", "src/b.cs:3", "--note", "validator corrected it in place")
        self.assertEqual(code, 0, out)
        found = [json.loads(l) for l in (r / "findings.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(found), 2)
        self.assertTrue(found[0]["fixed"])
        self.assertEqual(found[0]["severity"], "minor")
        self.assertEqual(found[0]["evidence"], ["src/a.cs:12", "src/b.cs:3"])
        self.assertEqual(found[0]["amendments"][0]["note"], "validator corrected it in place")
        self.assertEqual(run("findings.py", "list", "--run", str(r), "--open")[1].count("F-"), 1)
        self.assertEqual(run("findings.py", "amend", "F-9", "--run", str(r), "--note", "x")[0], 2)


class ShipCheckTests(TempRepo):
    def setUp(self):
        super().setUp()
        self.r = self.new_run()
        (self.r / "brief.md").write_text(BRIEF_OK, encoding="utf-8")
        (self.r / "work-packages" / "WP-01-mapper.md").write_text(WP.format(serves="AC-1, AC-2", flag=FLAG_ON),
                                                                  encoding="utf-8")
        (self.root / "src").mkdir()
        (self.root / "src" / "Mapper.cs").write_text("// mapper\n" * 12, encoding="utf-8")
        rows = "| AC-1 | met | `src/Mapper.cs:3` |\n| AC-2 | met | `src/Mapper.cs:4` |\n| WP-01.1 | met | src/Mapper.cs:10 |"
        (self.r / "reports" / "WP-01.implementer.md").write_text(REPORT.format(rows=rows), encoding="utf-8")
        (self.r / "gates").mkdir()

    def write_json(self, rel, data):
        (self.r / rel).write_text(json.dumps(data), encoding="utf-8")

    def all_green(self):
        self.write_json("runner/ci-20260101-000000-1.json",
                        {"result": "pass", "steps": [{"name": "build", "exit": 0, "passed": True}], "skipped": []})
        self.write_json("runner/extreme-20260101-000000-1.json",
                        {"result": "pass", "steps": [{"name": "build-strict", "exit": 0, "passed": True}], "skipped": []})
        self.write_json("gates/extreme-20260101-000000-1.json", {"result": "pass", "gates": []})
        self.write_json("gates/pre-pr-20260101-000000-1.json", {"result": "pass", "gates": []})

    def test_ready_only_when_every_check_holds(self):
        self.all_green()
        code, out = run("run.py", "ship-check", str(self.r))
        self.assertEqual(code, 0, out)
        self.assertIn("ready=yes", out)

    def test_a_failed_extreme_blocks_until_the_owner_accepts_it(self):
        self.all_green()
        self.write_json("runner/extreme-20260102-000000-1.json",
                        {"result": "fail", "steps": [{"name": "web-validate", "exit": 1, "passed": False}], "skipped": []})
        code, out = run("run.py", "ship-check", str(self.r))
        self.assertEqual(code, 1, out)
        self.assertIn("failed: web-validate", out)
        self.assertIn("ready=no", out)
        run("findings.py", "add", "--run", str(self.r), "--source", "human", "--target", "ship:extreme",
            "--kind", "owner-decision", "--severity", "minor", "--summary", "pnpm audit is pre-existing; ship it",
            "--evidence", "reviews/deliver.md", "--fixed")
        code, out = run("run.py", "ship-check", str(self.r))
        self.assertEqual(code, 0, out)
        self.assertIn("accepted by the owner: F-1", out)

    def test_empty_pre_pr_with_declared_gates_and_open_decisions_block(self):
        self.all_green()
        self.write_json("gates/pre-pr-20260102-000000-1.json",
                        {"result": "empty", "gates": [], "declared_for_stage": ["dependency-audit"]})
        run("findings.py", "add", "--run", str(self.r), "--source", "pr-reviewer", "--target", "owner",
            "--kind", "owner-decision", "--severity", "minor", "--summary", "which branch?", "--evidence", "x")
        code, out = run("run.py", "ship-check", str(self.r))
        self.assertEqual(code, 1, out)
        self.assertIn("declared but not selected: dependency-audit", out)
        self.assertIn("owner-decisions  open", out)

    def test_failed_ci_failed_validator_and_open_major_each_block(self):
        self.all_green()
        self.write_json("runner/ci-20260102-000000-1.json",
                        {"result": "fail", "steps": [{"name": "test", "exit": 1, "passed": False}], "skipped": []})
        (self.r / "reports" / "WP-01.validator.implementer.md").write_text(
            "---\nagent: validator\nresult: fail\n---\n# v\n", encoding="utf-8")
        run("findings.py", "add", "--run", str(self.r), "--source", "reviewer-narrow", "--target", "WP-01",
            "--kind", "instance", "--severity", "major", "--summary", "null deref", "--evidence", "src/Mapper.cs:3")
        run("findings.py", "add", "--run", str(self.r), "--source", "curator", "--target", "implementer",
            "--kind", "agent-gap", "--severity", "major", "--summary", "guidance gap", "--evidence", "x")
        code, out = run("run.py", "ship-check", str(self.r))
        self.assertEqual(code, 1, out)
        self.assertIn("failed: test", out)
        self.assertIn("validators       fail      NO  WP-01.validator.implementer.md", out)
        self.assertIn("majors           open      NO  F-1", out)
        self.assertNotIn("F-2", out)  # an agent-gap is the Curator's, not a product defect

    def test_http_summary_required_once_proofs_were_written(self):
        self.all_green()
        (self.r / "reports" / "prove.http-generator.md").write_text("# proofs\n", encoding="utf-8")
        code, out = run("run.py", "ship-check", str(self.r))
        self.assertEqual(code, 1, out)
        self.assertIn("no http run in runner/", out)
        self.write_json("runner/http-20260101-000000-1.json", {"result": "pass", "steps": [], "skipped": []})
        self.assertEqual(run("run.py", "ship-check", str(self.r))[0], 0)

    def test_missing_extreme_blocks_unless_the_step_is_off(self):
        self.write_json("runner/ci-20260101-000000-1.json", {"result": "pass", "steps": [], "skipped": []})
        self.write_json("gates/extreme-20260101-000000-1.json", {"result": "pass", "gates": []})
        self.write_json("gates/pre-pr-20260101-000000-1.json", {"result": "pass", "gates": []})
        code, out = run("run.py", "ship-check", str(self.r))
        self.assertEqual(code, 1, out)
        self.assertIn("no extreme run", out)
        run("steps.py", "set", "extreme", "off", "--run", str(self.r), "--reason", "docs-only change")
        code, out = run("run.py", "ship-check", str(self.r))
        self.assertEqual(code, 0, out)
        self.assertIn("step switched off (run)", out)

    def test_e2e_is_opt_in_warns_until_ready_then_blocks(self):
        self.all_green()
        code, out = run("run.py", "ship-check", str(self.r))
        self.assertEqual(code, 0, out)
        self.assertIn("e2e              off       ok  opt-in step not switched on", out)
        # Switched on, but the project's end-to-end setup isn't ready: the owner's rule is warn, not block.
        run("steps.py", "set", "e2e", "on", "--run", str(self.r), "--reason", "prove it end to end")
        code, out = run("run.py", "ship-check", str(self.r))
        self.assertEqual(code, 0, out)
        self.assertIn("e2e              not ready ok  .fyzxsflow/e2e.md status not-set-up", out)
        # Ready: every configured e2e mode must pass, and the airplane one must have run with its check.
        home = self.root / ".fyzxsflow"
        (home / "e2e.md").write_text("# End to end\n\nStatus: ready\n", encoding="utf-8")
        modes = {"e2e-airplane": {"network": "airplane", "steps": [{"name": "e2e", "run": "x"}]},
                 "e2e-connected": {"not_applicable": "no approved external services"}}
        (home / "config.json").write_text(json.dumps({"modes": modes}), encoding="utf-8")
        code, out = run("run.py", "ship-check", str(self.r))
        self.assertEqual(code, 1, out)
        self.assertIn("no e2e-airplane run in runner/", out)
        self.assertNotIn("e2e-connected", out)
        self.write_json("runner/e2e-airplane-20260101-000000-1.json",
                        {"result": "pass", "steps": [{"name": "e2e", "exit": 0, "passed": True}], "skipped": []})
        code, out = run("run.py", "ship-check", str(self.r))
        self.assertEqual(code, 1, out)
        self.assertIn("e2e-airplane     unchecked NO", out)
        self.write_json("runner/e2e-airplane-20260102-000000-1.json",
                        {"result": "pass", "steps": [{"name": "e2e", "exit": 0, "passed": True}], "skipped": [],
                         "network": "airplane", "egress": []})
        code, out = run("run.py", "ship-check", str(self.r))
        self.assertEqual(code, 0, out)
        self.assertIn("network: airplane", out)

    def test_greenfield_run_blocks_while_anything_is_still_planned(self):
        self.all_green()
        text = (self.r / "input.md").read_text(encoding="utf-8")
        (self.r / "input.md").write_text(text.replace("source: prompt", "source: greenfield"), encoding="utf-8")
        home = self.root / ".fyzxsflow"
        (home / "docs").mkdir(parents=True)
        arch = home / "docs" / "architecture.md"
        arch.write_text("---\nstatus: planned\n---\n# Architecture\n", encoding="utf-8")
        (home / "config.json").write_text(json.dumps({"modes": {"ci": {"steps": [
            {"name": "build", "run": "dotnet build", "planned": True}]}}}), encoding="utf-8")
        code, out = run("run.py", "ship-check", str(self.r))
        self.assertEqual(code, 1, out)
        self.assertIn("greenfield       planned   NO  still planned (run the Repo Cartographer's confirm mode): "
                      ".fyzxsflow/docs/architecture.md, config.json mode 'ci' step 'build'", out)
        arch.write_text("# Architecture\n", encoding="utf-8")
        (home / "config.json").write_text(json.dumps({"modes": {"ci": {"steps": [
            {"name": "build", "run": "dotnet build"}]}}}), encoding="utf-8")
        code, out = run("run.py", "ship-check", str(self.r))
        self.assertEqual(code, 0, out)
        self.assertIn("greenfield       confirmed ok", out)

    def test_greenfield_row_only_for_greenfield_runs(self):
        self.all_green()
        code, out = run("run.py", "ship-check", str(self.r))
        self.assertEqual(code, 0, out)
        self.assertNotIn("greenfield", out)

    def test_e2e_ready_without_any_e2e_mode_blocks(self):
        self.all_green()
        run("steps.py", "set", "e2e", "on", "--run", str(self.r), "--reason", "prove it end to end")
        (self.root / ".fyzxsflow" / "e2e.md").write_text("Status: `ready`\n", encoding="utf-8")
        code, out = run("run.py", "ship-check", str(self.r))
        self.assertEqual(code, 1, out)
        self.assertIn("e2e              no modes  NO", out)


BRIEF_OK = """# Goal

## Acceptance criteria
- **AC-1** (stated): Given a set, when I open the pull list, then unsigned cards are listed.
- **AC-2** (inferred): The page fits the window at 390px wide.

## Out of scope
- nothing
"""

WP = """---
id: WP-01
---
# WP-01

## Acceptance criteria
- Serves: {serves}
- **WP-01.1**: the mapper maps every field

## Context pack
- x

## Flag plan
{flag}
"""

FLAG_ON = "- flag: `cards.variant-sort` · default: off · owner: quinn · expiry: 2026-12-31 · read at: sort dispatcher"
NOT_REQ = "- not-required (project policy) — revert: revert the commit and redeploy"

REPORT = """# report

## Acceptance criteria
| Criterion | Status | Evidence |
|---|---|---|
{rows}
"""


class AcTraceTests(TempRepo):
    def setup_run(self, brief=BRIEF_OK, serves="AC-1, AC-2", flag=FLAG_ON):
        self.runs = getattr(self, "runs", 0) + 1
        r = self.new_run(ref=f"case {self.runs}")
        (r / "brief.md").write_text(brief, encoding="utf-8")
        (r / "work-packages" / "WP-01-mapper.md").write_text(WP.format(serves=serves, flag=flag), encoding="utf-8")
        return r

    def set_policy(self, policy):
        (self.root / ".fyzxsflow").mkdir(exist_ok=True)
        (self.root / ".fyzxsflow" / "feature-flags.md").write_text(f"# Feature-flag source\n\n## Policy\nPolicy: {policy}\n", encoding="utf-8")

    def test_not_required_rejected_under_default_policy(self):
        code, out = run("ac_trace.py", "--run", str(self.setup_run(flag=NOT_REQ)))
        self.assertEqual(code, 1)
        self.assertIn("neither the project policy nor the brief allows", out)

    def test_not_required_allowed_by_project_policy(self):
        self.set_policy("not-required")
        code, out = run("ac_trace.py", "--run", str(self.setup_run(flag=NOT_REQ)))
        self.assertEqual(code, 0, out)

    def test_not_required_allowed_by_owner_in_brief(self):
        brief = "---\nsource: prompt\nflags: not-required (owner)\n---\n" + BRIEF_OK
        code, out = run("ac_trace.py", "--run", str(self.setup_run(brief=brief, flag=NOT_REQ)))
        self.assertEqual(code, 0, out)

    def test_brief_can_require_flags_despite_policy(self):
        self.set_policy("not-required")
        brief = "---\nsource: prompt\nflags: required\n---\n" + BRIEF_OK
        self.assertEqual(run("ac_trace.py", "--run", str(self.setup_run(brief=brief, flag=NOT_REQ)))[0], 1)

    def test_flag_plan_must_be_exactly_one_and_exceptions_need_revert(self):
        for flag, msg in (("", "found none"),
                          (FLAG_ON + "\n" + NOT_REQ, "exactly one"),
                          ("- unflaggable — reason: dependency upgrade", "must state its revert path"),
                          ("- flag: `<name>` · default: off", "found none")):
            code, out = run("ac_trace.py", "--run", str(self.setup_run(flag=flag)))
            self.assertEqual(code, 1, flag)
            self.assertIn(msg, out, flag)

    def test_ranges_and_suffixed_ids_fail_instead_of_being_skipped(self):
        code, out = run("ac_trace.py", "--run", str(self.setup_run(serves="AC-1..AC-2")))
        self.assertEqual(code, 1)
        self.assertIn("uses a range", out)
        r = self.setup_run()
        wp = r / "work-packages" / "WP-01-mapper.md"
        wp.write_text(wp.read_text(encoding="utf-8").replace("**WP-01.1**", "**WP-01.1b**"), encoding="utf-8")
        code, out = run("ac_trace.py", "--run", str(r))
        self.assertEqual(code, 1)
        self.assertIn("**WP-01.1b** is not traced", out)

    def test_plan_passes(self):
        code, out = run("ac_trace.py", "--run", str(self.setup_run()))
        self.assertEqual(code, 0, out)

    def test_brief_without_criteria_fails(self):
        r = self.setup_run(brief="# Goal\n\n## Acceptance criteria\n<!-- - **AC-1** (stated): template -->\n")
        code, out = run("ac_trace.py", "--run", str(r))
        self.assertEqual(code, 1)
        self.assertIn("defines no acceptance criteria", out)

    def test_untagged_criterion_fails(self):
        r = self.setup_run(brief=BRIEF_OK.replace("**AC-2** (inferred)", "**AC-2**"))
        code, out = run("ac_trace.py", "--run", str(r))
        self.assertEqual(code, 1)
        self.assertIn("AC-2 is not tagged", out)

    def test_unserved_and_unknown_criteria_fail(self):
        r = self.setup_run(serves="AC-1, AC-9")
        code, out = run("ac_trace.py", "--run", str(r))
        self.assertEqual(code, 1)
        self.assertIn("AC-2 is not served", out)
        self.assertIn("serves AC-9, which brief.md does not define", out)

    def test_evidence_required_for_every_criterion(self):
        r = self.setup_run()
        (self.root / "src").mkdir()
        (self.root / "src" / "Mapper.cs").write_text("// line\n" * 10, encoding="utf-8")
        (self.root / "src" / "PullListTests.cs").write_text("void PullList_ListsUnsigned() {}\n", encoding="utf-8")
        rows = "| AC-1 | met | test PullList_ListsUnsigned |\n| AC-2 | met | |\n| WP-01.1 | met | src/Mapper.cs:10 |"
        (r / "reports" / "WP-01.implementer.md").write_text(REPORT.format(rows=rows), encoding="utf-8")
        code, out = run("ac_trace.py", "--run", str(r), "--require-evidence")
        self.assertEqual(code, 1)
        self.assertIn("AC-2 has no report marking it met with evidence that resolves", out)
        (r / "runner" / "ci-1.json").write_text(json.dumps({"result": "pass"}), encoding="utf-8")
        rows = rows.replace("| AC-2 | met | |", "| AC-2 | met | runner/ci-1.json |")
        (r / "reports" / "WP-01.implementer.md").write_text(REPORT.format(rows=rows), encoding="utf-8")
        code, out = run("ac_trace.py", "--run", str(r), "--require-evidence")
        self.assertEqual(code, 0, out)

    def test_evidence_that_does_not_resolve_fails(self):
        r = self.setup_run()
        (self.root / "src").mkdir()
        (self.root / "src" / "Mapper.cs").write_text("// line\n" * 3, encoding="utf-8")
        (r / "runner" / "ci-1.json").write_text(json.dumps({"result": "fail"}), encoding="utf-8")
        rows = ("| AC-1 | met | trust me |\n| AC-2 | met | runner/ci-1.json |\n"
                "| WP-01.1 | met | src/Mapper.cs:10 |")
        (r / "reports" / "WP-01.implementer.md").write_text(REPORT.format(rows=rows), encoding="utf-8")
        code, out = run("ac_trace.py", "--run", str(r), "--require-evidence")
        self.assertEqual(code, 1)
        self.assertIn("AC-1 has no report marking it met with evidence that resolves", out)
        self.assertIn("names no path:line, Runner summary, test or file", out)
        self.assertIn("runner/ci-1.json has result fail", out)
        self.assertIn("src/Mapper.cs:10 is past the end of the file (3 lines)", out)

    def test_a_validator_not_met_overrides_the_authors_met(self):
        r = self.setup_run()
        (self.root / "src").mkdir()
        (self.root / "src" / "Mapper.cs").write_text("// line\n" * 10, encoding="utf-8")
        rows = "| AC-1 | met | src/Mapper.cs:1 |\n| AC-2 | met | src/Mapper.cs:2 |\n| WP-01.1 | met | src/Mapper.cs:3 |"
        (r / "reports" / "WP-01.implementer.md").write_text(REPORT.format(rows=rows), encoding="utf-8")
        self.assertEqual(run("ac_trace.py", "--run", str(r), "--require-evidence")[0], 0)
        (r / "reports" / "WP-01.validator.implementer.md").write_text(
            REPORT.format(rows="| AC-2 | not met | the sort ignores nulls |"), encoding="utf-8")
        code, out = run("ac_trace.py", "--run", str(r), "--require-evidence")
        self.assertEqual(code, 1)
        self.assertIn("AC-2 is marked not met by WP-01.validator.implementer.md", out)


class DocsCheckTests(TempRepo):
    def setUp(self):
        super().setUp()
        (self.root / "src" / "Mappers").mkdir(parents=True)
        (self.root / "src" / "Mappers" / "CardMapper.cs").write_text("class CardMapper {}", encoding="utf-8")
        (self.root / ".fyzxsflow" / "docs" / "segments").mkdir(parents=True)
        self.modes = {m: {"steps": [{"name": "x", "run": "echo"}]} for m in ("quick", "ci", "extreme")}
        self.write_cfg()

    def write_cfg(self):
        (self.root / ".fyzxsflow" / "config.json").write_text(
            json.dumps({"docs": {"pack_budget_kb": 1}, "modes": self.modes}), encoding="utf-8")

    def write_profile(self, database="yes (Postgres)", api="no"):
        (self.root / ".fyzxsflow" / "profile.md").write_text(
            f"## Surfaces\n| Surface | Present | Docs |\n|---|---|---|\n| API | {api} | |\n| Database | {database} | |\n",
            encoding="utf-8")

    def test_capabilities_required_by_surfaces(self):
        self.write_segment("ok")
        self.write_profile()
        code, out = run("docs_check.py", "--root", str(self.root))
        self.assertEqual(code, 1)
        for mode in ("db-migrate", "db-verify", "db-reset", "seed"):
            self.assertIn(f"no '{mode}' mode", out)
        self.modes.update({"db-migrate": {"steps": [{"name": "m", "run": "echo"}]},
                           "db-verify": {"steps": [{"name": "v", "run": "echo"}]},
                           "db-reset": {"steps": [{"name": "r", "run": "echo"}]},
                           "seed": {"not_applicable": "proofs use fixtures only"}})
        self.write_cfg()
        code, out = run("docs_check.py", "--root", str(self.root))
        self.assertIn("'db-reset' must be marked", out)
        self.modes["db-reset"]["destructive"] = True
        self.write_cfg()
        self.assertEqual(run("docs_check.py", "--root", str(self.root))[0], 0)

    def test_unlabelled_destructive_step_warns_and_unresolved_fails_strict(self):
        self.write_segment("ok")
        self.modes["extreme"]["steps"].append({"name": "db-from-empty", "run": "reset-database.ps1"})
        self.modes["extreme"]["steps"].append({"name": "seed-after-reset", "run": "dotnet run --project Ingest"})
        self.modes["ci"]["steps"].append({"name": "lint", "run": "UNRESOLVED: lint command"})
        self.write_cfg()
        code, out = run("docs_check.py", "--root", str(self.root))
        self.assertEqual(code, 0, out)
        self.assertIn("step 'db-from-empty' looks destructive", out)
        self.assertNotIn("step 'seed-after-reset' looks destructive", out)  # the name says reset; the command doesn't
        self.assertIn("step 'lint' is UNRESOLVED", out)
        self.assertEqual(run("docs_check.py", "--root", str(self.root), "--strict")[0], 1)

    def write_segment(self, body, paths="src/Mappers/**", pack=None):
        fm = f'---\npaths:\n  - "{paths}"\n'
        if pack:
            fm += "pack:\n" + "".join(f"  - {p}\n" for p in pack)
        fm += "---\n"
        (self.root / ".fyzxsflow" / "docs" / "segments" / "mapper.md").write_text(fm + body, encoding="utf-8")

    def test_passes_when_paths_exist(self):
        self.write_segment("Example: `src/Mappers/CardMapper.cs:1`. Run `--quick --scope x`.")
        code, out = run("docs_check.py", "--root", str(self.root))
        self.assertEqual(code, 0, out)

    def test_missing_cited_path_fails(self):
        self.write_segment("Example: `src/Mappers/GoneMapper.cs`.")
        code, out = run("docs_check.py", "--root", str(self.root))
        self.assertEqual(code, 1)
        self.assertIn("GoneMapper.cs", out)

    def test_dead_glob_fails(self):
        self.write_segment("ok", paths="src/GraphQL/**")
        code, out = run("docs_check.py", "--root", str(self.root))
        self.assertEqual(code, 1)
        self.assertIn("matches no tracked file", out)

    def test_pack_over_budget_fails(self):
        (self.root / "big.md").write_text("x" * 2048, encoding="utf-8")
        self.write_segment("ok", pack=["big.md"])
        code, out = run("docs_check.py", "--root", str(self.root))
        self.assertEqual(code, 1)
        self.assertIn("over the 1 KB budget", out)

    def test_unresolved_in_a_comment_is_not_unresolved(self):
        self.write_segment("<!-- leave UNRESOLVED when unknown -->\nProvider: LaunchDarkly")
        self.assertEqual(run("docs_check.py", "--root", str(self.root), "--strict")[0], 0)

    def test_unresolved_warns_unless_strict(self):
        self.write_segment("Provider: UNRESOLVED")
        self.assertEqual(run("docs_check.py", "--root", str(self.root))[0], 0)
        self.assertEqual(run("docs_check.py", "--root", str(self.root), "--strict")[0], 1)

    def test_planned_doc_and_config_warn_until_confirmed_and_fail_strict(self):
        # Greenfield: the docs describe code that doesn't exist yet.
        seg = self.root / ".fyzxsflow" / "docs" / "segments" / "mapper.md"
        seg.write_text('---\nstatus: planned\npaths:\n  - "src/Api/**"\n---\n# Segment: API\n'
                       "Canonical example once written: `src/Api/HealthController.cs`.\n", encoding="utf-8")
        self.modes["ci"]["steps"][0]["planned"] = True
        self.write_cfg()
        code, out = run("docs_check.py", "--root", str(self.root))
        self.assertEqual(code, 0, out)
        self.assertIn("WARN .fyzxsflow/docs/segments/mapper.md: status planned, not yet confirmed against the code", out)
        self.assertIn("WARN .fyzxsflow/docs/segments/mapper.md: glob `src/Api/**` matches no tracked file yet", out)
        self.assertIn("WARN .fyzxsflow/docs/segments/mapper.md: cites `src/Api/HealthController.cs`, which does not "
                      "exist yet", out)
        self.assertIn("WARN config.json: mode 'ci' step 'x' is planned, not yet proven", out)
        code, out = run("docs_check.py", "--root", str(self.root), "--strict")
        self.assertEqual(code, 1, out)
        self.assertIn("FAIL .fyzxsflow/docs/segments/mapper.md: status planned", out)
        self.assertIn("FAIL config.json: mode 'ci' step 'x' is planned", out)

    def test_a_confirmed_doc_gets_no_planned_leniency(self):
        seg = self.root / ".fyzxsflow" / "docs" / "segments" / "mapper.md"
        seg.write_text('---\nstatus: confirmed\npaths:\n  - "src/Api/**"\n---\n# Segment: API\n', encoding="utf-8")
        code, out = run("docs_check.py", "--root", str(self.root))
        self.assertEqual(code, 1, out)
        self.assertIn("FAIL .fyzxsflow/docs/segments/mapper.md: glob `src/Api/**` matches no tracked file", out)

    def test_e2e_modes_warn_when_absent_and_must_declare_their_network(self):
        self.write_segment("ok")
        code, out = run("docs_check.py", "--root", str(self.root), "--strict")
        self.assertEqual(code, 0, out)  # absent e2e modes are a warning even with --strict: e2e is opt-in
        self.assertIn("WARN config.json: no 'e2e-airplane' mode", out)
        self.modes["e2e-airplane"] = {"steps": [{"name": "e2e", "run": "npx playwright test"}]}
        self.modes["e2e-connected"] = {"not_applicable": "no approved external services"}
        self.write_cfg()
        code, out = run("docs_check.py", "--root", str(self.root))
        self.assertEqual(code, 1, out)
        self.assertIn("mode 'e2e-airplane' must declare \"network\": \"airplane\"", out)
        self.modes["e2e-airplane"]["network"] = "airplane"
        self.write_cfg()
        self.assertEqual(run("docs_check.py", "--root", str(self.root))[0], 0)

    def test_e2e_ready_needs_a_defined_e2e_mode(self):
        self.write_segment("ok")
        self.modes["e2e-airplane"] = {"not_applicable": "not set up yet"}
        self.write_cfg()
        (self.root / ".fyzxsflow" / "e2e.md").write_text("Status: ready\n", encoding="utf-8")
        code, out = run("docs_check.py", "--root", str(self.root))
        self.assertEqual(code, 1, out)
        self.assertIn("e2e.md says Status: ready", out)


class RunnerTests(TempRepo):
    def write_config(self, steps, **mode):
        cfg = {"modes": {"quick": dict(steps=steps, **mode)}}
        (self.root / ".fyzxsflow").mkdir(exist_ok=True)
        (self.root / ".fyzxsflow" / "config.json").write_text(json.dumps(cfg), encoding="utf-8")

    def step(self, name, code, text="hello"):
        return {"name": name, "run": f'"{PY}" -I -c "print(\'{text} {{scope}}\'); raise SystemExit({code})"'}

    def test_all_pass(self):
        self.write_config([self.step("build", 0), self.step("test", 0)])
        r = self.new_run()
        code, out = run("runner.py", "quick", "--run", str(r), "--scope", "Lib.Cards", "--root", str(self.root))
        self.assertEqual(code, 0, out)
        self.assertIn("result=pass", out)
        summary_file = next((r / "runner").glob("*.json"))
        self.assertNotIn(b"\r\n", summary_file.read_bytes())  # LF on every platform
        summary = json.loads(summary_file.read_text(encoding="utf-8"))
        self.assertEqual([s["exit"] for s in summary["steps"]], [0, 0])
        log = pathlib.Path(summary["steps"][0]["log"]).read_text(encoding="utf-8")
        self.assertIn("hello Lib.Cards", log)

    def test_failure_stops_and_reports_skipped(self):
        self.write_config([self.step("build", 3), self.step("test", 0)])
        r = self.new_run()
        code, out = run("runner.py", "quick", "--run", str(r), "--root", str(self.root))
        self.assertEqual(code, 1)
        self.assertIn("build exit=3", out)
        self.assertIn("test skipped", out)

    def test_judges_by_exit_code_not_text(self):
        self.write_config([self.step("test", 1, text="All tests passed")])
        r = self.new_run()
        code, out = run("runner.py", "quick", "--run", str(r), "--root", str(self.root))
        self.assertEqual(code, 1)
        self.assertIn("result=fail", out)

    def test_destructive_steps_refused_before_anything_runs(self):
        marker = (self.root / "ran.txt").as_posix()
        touch = f'"{PY}" -I -c "open(\'{marker}\', \'w\').write(\'x\')"'
        self.write_config([{"name": "migrate", "run": touch}, dict(self.step("reset", 0), destructive=True)])
        code, out = run("runner.py", "quick", "--root", str(self.root))
        self.assertEqual(code, 3, out)
        self.assertIn("destructive steps (reset)", out)
        self.assertFalse((self.root / "ran.txt").exists())  # the safe step did not run either
        code, out = run("runner.py", "quick", "--root", str(self.root), "--allow-destructive")
        self.assertEqual(code, 0, out)
        self.assertTrue((self.root / "ran.txt").exists())

    def test_owner_allowed_destructive_mode_and_not_applicable(self):
        self.write_config([dict(self.step("reset", 0), destructive=True)], allow_destructive=True)
        self.assertEqual(run("runner.py", "quick", "--root", str(self.root))[0], 0)
        self.write_config([self.step("x", 1)], not_applicable="no database in this repo")
        code, out = run("runner.py", "quick", "--root", str(self.root))
        self.assertEqual(code, 0)
        self.assertIn("does not apply to this repo", out)

    def test_unknown_mode_is_config_error(self):
        self.write_config([self.step("build", 0)])
        self.assertEqual(run("runner.py", "extreme", "--root", str(self.root))[0], 2)

    def test_output_checks_fail_a_step_that_exits_zero(self):
        lossy = dict(self.step("ingest", 0, text="done: 120 ok, 4202 failed"), fail_if_output=r"\b[1-9][0-9]* failed")
        self.write_config([lossy, self.step("after", 0)])
        r = self.new_run()
        code, out = run("runner.py", "quick", "--run", str(r), "--root", str(self.root))
        self.assertEqual(code, 1, out)
        self.assertIn("ingest exit=0", out)
        self.assertIn("FAILED CHECK: output matched fail_if_output", out)
        self.assertIn("after skipped", out)
        clean = dict(self.step("ingest", 0, text="done: 120 ok, 0 failed"), fail_if_output=r"\b[1-9][0-9]* failed",
                     expect_output=r"[0-9]+ ok")
        self.write_config([clean])
        self.assertEqual(run("runner.py", "quick", "--root", str(self.root))[0], 0)
        self.write_config([dict(self.step("ingest", 0, text="nothing"), expect_output=r"[0-9]+ ok")])
        code, out = run("runner.py", "quick", "--root", str(self.root))
        self.assertEqual(code, 1)
        self.assertIn("no output line matched expect_output", out)

    def test_timeout_stops_the_whole_process_tree(self):
        pidfile = self.root / "grandchild.pid"
        script = self.root / "spawn.py"
        script.write_text(
            "import subprocess, sys\n"
            "p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'])\n"
            f"open(r'{pidfile}', 'w').write(str(p.pid))\n"
            "p.wait()\n", encoding="utf-8")
        self.write_config([{"name": "hang", "run": f'"{PY}" -I "{script}"', "timeout_s": 3}])
        code, out = run("runner.py", "quick", "--root", str(self.root))
        self.assertEqual(code, 1, out)
        self.assertIn("hang exit=124", out)
        sys.path.insert(0, str(ENGINE))
        from runner import pid_alive
        pid = int(pidfile.read_text(encoding="utf-8"))
        for _ in range(20):  # the OS may take a moment to reap it
            if not pid_alive(pid):
                break
            import time
            time.sleep(0.25)
        self.assertFalse(pid_alive(pid), "the grandchild outlived the timed-out step")

    def test_a_held_lock_refuses_and_a_stale_one_is_taken_over(self):
        import os
        self.write_config([self.step("migrate", 0)], lock="local-db")
        locks = self.root / ".fyzxsflow" / "runs" / "_adhoc" / "locks"
        locks.mkdir(parents=True)
        (locks / "local-db.json").write_text(json.dumps({"pid": os.getpid(), "mode": "seed", "since": "now"}),
                                             encoding="utf-8")
        code, out = run("runner.py", "quick", "--root", str(self.root))
        self.assertEqual(code, 4, out)
        self.assertIn("lock 'local-db' is held by mode 'seed'", out)
        dead = subprocess.run([PY, "-c", "import os; print(os.getpid())"], capture_output=True, text=True).stdout
        (locks / "local-db.json").write_text(json.dumps({"pid": int(dead), "mode": "seed"}), encoding="utf-8")
        code, out = run("runner.py", "quick", "--root", str(self.root))
        self.assertEqual(code, 0, out)
        self.assertFalse((locks / "local-db.json").exists())  # released after the run

    def test_summary_records_the_tested_commit_and_dirty_state(self):
        for a in (["init", "-q", "-b", "main"], ["config", "user.name", "T"], ["config", "user.email", "t@x"]):
            subprocess.run(["git", *a], cwd=self.root, check=True)
        self.write_config([self.step("build", 0)])
        (self.root / "app.txt").write_text("v1", encoding="utf-8")
        subprocess.run(["git", "add", "app.txt"], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "base"], cwd=self.root, check=True)
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=self.root, capture_output=True, text=True).stdout.strip()
        r = self.new_run()  # the run folder itself is not product code
        run("runner.py", "quick", "--run", str(r), "--root", str(self.root))
        first = json.loads(sorted((r / "runner").glob("*.json"))[-1].read_text(encoding="utf-8"))
        self.assertEqual((first["commit"], first["dirty"]), (head, False))
        (self.root / "app.txt").write_text("v2", encoding="utf-8")
        run("runner.py", "quick", "--run", str(r), "--root", str(self.root))
        second = json.loads(sorted((r / "runner").glob("*.json"))[-1].read_text(encoding="utf-8"))
        self.assertTrue(second["dirty"])

    def test_bare_run_id_resolves_under_active(self):
        self.write_config([self.step("build", 0)])
        r = self.new_run()
        code, out = run("runner.py", "quick", "--run", r.name, "--root", str(self.root))
        self.assertEqual(code, 0, out)
        self.assertTrue(list((r / "runner").glob("quick-*.json")))
        code, out = run("runner.py", "quick", "--run", "no-such-run", "--root", str(self.root))
        self.assertNotEqual(code, 0)
        self.assertIn("not an active run id", out)


if __name__ == "__main__":
    unittest.main()

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
        self.root = pathlib.Path(tempfile.mkdtemp(prefix="agentflow-test-"))

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
        (self.root / ".agentflow").mkdir(exist_ok=True)
        (self.root / ".agentflow" / "feature-flags.md").write_text(f"# Feature-flag source\n\n## Policy\nPolicy: {policy}\n", encoding="utf-8")

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
        rows = "| AC-1 | met | test PullList_ListsUnsigned |\n| AC-2 | met | |\n| WP-01.1 | met | src/Mapper.cs:10 |"
        (r / "reports" / "WP-01.implementer.md").write_text(REPORT.format(rows=rows), encoding="utf-8")
        code, out = run("ac_trace.py", "--run", str(r), "--require-evidence")
        self.assertEqual(code, 1)
        self.assertIn("AC-2 has no report marking it met with evidence", out)
        rows = rows.replace("| AC-2 | met | |", "| AC-2 | met | runner/ci-1.json |")
        (r / "reports" / "WP-01.implementer.md").write_text(REPORT.format(rows=rows), encoding="utf-8")
        self.assertEqual(run("ac_trace.py", "--run", str(r), "--require-evidence")[0], 0)


class DocsCheckTests(TempRepo):
    def setUp(self):
        super().setUp()
        (self.root / "src" / "Mappers").mkdir(parents=True)
        (self.root / "src" / "Mappers" / "CardMapper.cs").write_text("class CardMapper {}", encoding="utf-8")
        (self.root / ".agentflow" / "docs" / "segments").mkdir(parents=True)
        (self.root / ".agentflow" / "config.json").write_text(json.dumps({"docs": {"pack_budget_kb": 1}}), encoding="utf-8")

    def write_segment(self, body, paths="src/Mappers/**", pack=None):
        fm = f'---\npaths:\n  - "{paths}"\n'
        if pack:
            fm += "pack:\n" + "".join(f"  - {p}\n" for p in pack)
        fm += "---\n"
        (self.root / ".agentflow" / "docs" / "segments" / "mapper.md").write_text(fm + body, encoding="utf-8")

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

    def test_unresolved_warns_unless_strict(self):
        self.write_segment("Provider: UNRESOLVED")
        self.assertEqual(run("docs_check.py", "--root", str(self.root))[0], 0)
        self.assertEqual(run("docs_check.py", "--root", str(self.root), "--strict")[0], 1)


class RunnerTests(TempRepo):
    def write_config(self, steps, **mode):
        cfg = {"modes": {"quick": dict(steps=steps, **mode)}}
        (self.root / ".agentflow").mkdir(exist_ok=True)
        (self.root / ".agentflow" / "config.json").write_text(json.dumps(cfg), encoding="utf-8")

    def step(self, name, code, text="hello"):
        return {"name": name, "run": f'"{PY}" -I -c "print(\'{text} {{scope}}\'); raise SystemExit({code})"'}

    def test_all_pass(self):
        self.write_config([self.step("build", 0), self.step("test", 0)])
        r = self.new_run()
        code, out = run("runner.py", "quick", "--run", str(r), "--scope", "Lib.Cards", "--root", str(self.root))
        self.assertEqual(code, 0, out)
        self.assertIn("result=pass", out)
        summary = json.loads(next((r / "runner").glob("*.json")).read_text(encoding="utf-8"))
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

    def test_unknown_mode_is_config_error(self):
        self.write_config([self.step("build", 0)])
        self.assertEqual(run("runner.py", "extreme", "--root", str(self.root))[0], 2)


if __name__ == "__main__":
    unittest.main()

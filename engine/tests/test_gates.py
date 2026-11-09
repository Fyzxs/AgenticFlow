"""Tests for engine/gates.py. Gates are simulated with small Python commands, so no scanner is needed."""

import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

ENGINE = pathlib.Path(__file__).resolve().parent.parent
PY = sys.executable

SARIF = {"version": "2.1.0", "runs": [{"results": [
    {"ruleId": "no-secrets", "level": "error", "message": {"text": "hard-coded key"},
     "locations": [{"physicalLocation": {"artifactLocation": {"uri": "src/app.py"}, "region": {"startLine": 4}}}]},
    {"ruleId": "style", "level": "warning", "message": {"text": "long line"},
     "locations": [{"physicalLocation": {"artifactLocation": {"uri": "src/app.py"}, "region": {"startLine": 9}}}]},
]}]}


class GatesTests(unittest.TestCase):
    def setUp(self):
        self.root = pathlib.Path(tempfile.mkdtemp(prefix="fyzxsflow-gates-"))
        (self.root / ".fyzxsflow").mkdir()
        self.sarif_src = self.root / "fixture.sarif"
        self.sarif_src.write_text(json.dumps(SARIF), encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def copy_cmd(self, exit_code=0):
        # writes the fixture SARIF to {out}, then exits with exit_code
        src = str(self.sarif_src).replace("\\", "/")
        return f'"{PY}" -I -c "import shutil,sys; shutil.copy(\'{src}\', sys.argv[1]); sys.exit({exit_code})" "{{out}}"'

    def write(self, gates):
        (self.root / ".fyzxsflow" / "gates.json").write_text(json.dumps({"gates": gates}), encoding="utf-8")

    def gates(self, *args):
        proc = subprocess.run([PY, "-I", str(ENGINE / "gates.py"), "--root", str(self.root), *args],
                              capture_output=True, text=True)
        return proc.returncode, proc.stdout + proc.stderr

    def test_sarif_error_blocks(self):
        self.write([{"name": "scan", "stages": ["extreme"], "run": self.copy_cmd(), "format": "sarif", "fail_on": "error"}])
        code, out = self.gates("--stage", "extreme")
        self.assertEqual(code, 1, out)
        self.assertIn("scan FAIL", out)
        self.assertIn("new: 1 error, 1 warning", out)

    def test_report_only_never_blocks(self):
        self.write([{"name": "scan", "stages": ["extreme"], "run": self.copy_cmd(), "format": "sarif", "fail_on": "never"}])
        self.assertEqual(self.gates("--stage", "extreme")[0], 0)

    def test_baseline_suppresses_known_results(self):
        self.write([{"name": "scan", "stages": ["extreme"], "run": self.copy_cmd(), "format": "sarif", "fail_on": "warning"}])
        self.assertEqual(self.gates("--stage", "extreme", "--update-baseline", "scan")[0], 0)
        code, out = self.gates("--stage", "extreme")
        self.assertEqual(code, 0, out)
        self.assertIn("baseline: 2", out)

    def test_bad_exit_code_is_a_gate_error(self):
        self.write([{"name": "scan", "stages": ["extreme"], "run": self.copy_cmd(exit_code=7), "format": "sarif", "ok_exit_codes": [0, 1]}])
        code, out = self.gates("--stage", "extreme")
        self.assertEqual(code, 1)
        self.assertIn("exited 7", out)

    def test_exit_format_and_stage_and_path_selection(self):
        self.write([
            {"name": "lint", "stages": ["ci"], "run": f'"{PY}" -I -c "raise SystemExit(1)"', "format": "exit"},
            {"name": "sql", "stages": ["ci"], "run": f'"{PY}" -I -c "raise SystemExit(1)"', "format": "exit", "paths": ["db/**"]},
            {"name": "off", "enabled": False, "stages": ["ci"], "run": "nonexistent-tool", "format": "exit"},
        ])
        code, out = self.gates("--stage", "ci", "--changed", "src/app.py")
        self.assertEqual(code, 1)
        self.assertIn("lint FAIL", out)
        self.assertNotIn("sql", out.split("summary:")[0])
        self.assertEqual(self.gates("--stage", "extreme")[0], 0)

    def test_a_stage_that_selects_nothing_is_empty_not_pass(self):
        self.write([{"name": "audit", "stages": ["pre-pr"], "run": f'"{PY}" -I -c "raise SystemExit(1)"',
                     "format": "exit", "paths": ["package.json"]}])
        run = self.root / "run"
        code, out = self.gates("--stage", "pre-pr", "--changed", "src/app.py", "--run", str(run))
        self.assertEqual(code, 0, out)
        self.assertIn("result=empty", out)
        self.assertIn("none matched the changed paths: audit", out)
        summary = json.loads(next((run / "gates").glob("pre-pr-*.json")).read_text(encoding="utf-8"))
        self.assertEqual((summary["result"], summary["declared_for_stage"]), ("empty", ["audit"]))
        code, out = self.gates("--stage", "quick")
        self.assertIn("no gate declares this stage", out)

    def test_missing_registry_is_not_an_error(self):
        self.assertEqual(self.gates("--stage", "ci")[0], 0)


if __name__ == "__main__":
    unittest.main()

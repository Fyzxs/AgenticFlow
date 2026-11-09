"""Tests for engine/checks.py: citations in reports, run-local ids in product code."""

import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

ENGINE = pathlib.Path(__file__).resolve().parent.parent
PY = sys.executable


class ChecksTests(unittest.TestCase):
    def setUp(self):
        self.root = pathlib.Path(tempfile.mkdtemp(prefix="fyzxsflow-checks-"))
        for args in (["init", "-q", "-b", "main"], ["config", "user.name", "T"], ["config", "user.email", "t@x"],
                     ["config", "core.autocrlf", "false"]):
            subprocess.run(["git", *args], cwd=self.root, check=True)
        (self.root / "src").mkdir()
        (self.root / "src" / "Sort.cs").write_text("".join(f"line {i}\n" for i in range(1, 21)), encoding="utf-8")
        subprocess.run(["git", "add", "src/Sort.cs"], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "base"], cwd=self.root, check=True)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def checks(self, *args):
        proc = subprocess.run([PY, "-I", str(ENGINE / "checks.py"), *args, "--root", str(self.root)],
                              capture_output=True, text=True, cwd=self.root)
        return proc.returncode, proc.stdout + proc.stderr

    def test_citations_must_exist_and_be_in_range(self):
        run = self.root / ".fyzxsflow" / "runs" / "active" / "r1"
        (run / "runner").mkdir(parents=True)
        (run / "ledger.md").write_text("# Ledger\n", encoding="utf-8")
        (run / "runner" / "ci-1.json").write_text("{\n}\n", encoding="utf-8")
        report = run / "report.md"
        report.write_text(
            "Fixed at src/Sort.cs:12 and src/Sort.cs:18-20; run-relative runner/ci-1.json:2.\n"
            "Wrong: src/Sort.cs:21, src/Sort.cs:5-40, src/Gone.cs:3.\n"
            "Not citations: http://localhost:5000/api, 127.0.0.1:54322, at 05:46:01, Program.cs:9 (bare, absent).\n",
            encoding="utf-8")
        code, out = self.checks("citations", str(report))
        self.assertEqual(code, 1, out)
        self.assertIn("src/Sort.cs:21: src/Sort.cs has 20 lines", out)
        self.assertIn("src/Sort.cs:5-40: src/Sort.cs has 20 lines", out)
        self.assertIn("src/Gone.cs:3: no such file", out)
        self.assertIn("citations: 3 unresolved", out)

    def test_run_ids_in_added_product_lines_are_found(self):
        subprocess.run(["git", "checkout", "-q", "-b", "feat"], cwd=self.root, check=True)
        sort = self.root / "src" / "Sort.cs"
        sort.write_text(sort.read_text(encoding="utf-8") + "// variants last (F-104, WP-06.3)\n", encoding="utf-8")
        (self.root / "src" / "New.ts").write_text("// see AC-3\nexport const x = 1;\n", encoding="utf-8")
        flow = self.root / ".fyzxsflow" / "docs"
        flow.mkdir(parents=True)
        (flow / "notes.md").write_text("F-104 is fine here\n", encoding="utf-8")
        code, out = self.checks("run-ids", "--base", "main")
        self.assertEqual(code, 1, out)
        self.assertIn("src/Sort.cs:21: 'F-104'", out)
        self.assertIn("src/New.ts:1: 'AC-3'", out)
        self.assertNotIn("notes.md", out)
        self.assertIn("run-ids: 2", out)

    def test_clean_branch_passes(self):
        code, out = self.checks("run-ids", "--base", "main")
        self.assertEqual(code, 0, out)


if __name__ == "__main__":
    unittest.main()

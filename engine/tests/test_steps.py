"""Tests for engine/steps.py: optional process steps, project setting and per-run overrides."""

import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

ENGINE = pathlib.Path(__file__).resolve().parent.parent
PY = sys.executable


class StepsTests(unittest.TestCase):
    def setUp(self):
        self.root = pathlib.Path(tempfile.mkdtemp(prefix="fyzxsflow-steps-"))
        for args in (["init", "-q", "-b", "main"], ["config", "user.name", "T"], ["config", "user.email", "t@x"],
                     ["config", "core.autocrlf", "false"]):
            subprocess.run(["git", *args], cwd=self.root, check=True)
        self.config = self.root / ".fyzxsflow" / "config.json"
        self.config.parent.mkdir()
        self.config.write_text(json.dumps({"docs": {"pack_budget_kb": 24}}), encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "base"], cwd=self.root, check=True)
        out = subprocess.run([PY, "-I", str(ENGINE / "run.py"), "new", "--source", "prompt", "--ref", "x",
                              "--root", str(self.root)], capture_output=True, text=True, check=True).stdout
        self.run_dir = pathlib.Path(out.strip().splitlines()[-1])

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def st(self, *args):
        proc = subprocess.run([PY, "-I", str(ENGINE / "steps.py"), *args], capture_output=True, text=True,
                              cwd=self.root)
        return proc.returncode, (proc.stdout + proc.stderr).strip()

    def enabled(self, step, run=True):
        return self.st("enabled", step, *(["--run", str(self.run_dir)] if run else []))

    def set_off(self, steps):
        data = json.loads(self.config.read_text(encoding="utf-8"))
        data["steps"] = {"off": steps}
        self.config.write_text(json.dumps(data), encoding="utf-8")

    def test_every_step_is_on_by_default(self):
        code, out = self.enabled("pr")
        self.assertEqual(code, 0)
        self.assertEqual(out, "step=pr enabled=yes source=default")
        self.assertTrue(self.st("list")[1].endswith("off: none"))

    def test_project_setting_switches_a_step_off_and_says_what_that_means(self):
        self.set_off(["pr"])
        code, out = self.enabled("pr")
        self.assertEqual(code, 1)
        self.assertIn("step=pr enabled=no source=project", out)
        self.assertIn("you open the PR", out)
        self.assertEqual(self.enabled("pr-review")[0], 0)  # pr-review is its own step

    def test_a_group_switches_all_its_steps(self):
        self.set_off(["reviews"])
        for step in ("review-narrow", "review-large", "review-security", "review-iac"):
            self.assertEqual(self.enabled(step)[0], 1, step)
        self.assertEqual(self.enabled("gates")[0], 0)

    def test_core_and_unknown_names_are_refused(self):
        code, out = self.enabled("implementer")
        self.assertEqual(code, 2)
        self.assertIn("core flow", out)
        code, out = self.st("set", "validator", "off", "--reason", "x")
        self.assertEqual(code, 2)
        code, out = self.enabled("prs")
        self.assertEqual(code, 2)
        self.assertIn("unknown step 'prs'", out)

    def test_run_override_wins_both_ways_and_leaves_the_project_alone(self):
        self.set_off(["pr"])
        self.st("set", "pr", "on", "--run", str(self.run_dir), "--reason", "PR this time")
        self.st("set", "http-proofs", "off", "--run", str(self.run_dir), "--reason", "no API proofs")
        self.assertEqual(self.enabled("pr"), (0, "step=pr enabled=yes source=run"))
        self.assertEqual(self.enabled("http-proofs")[0], 1)
        self.assertEqual(self.enabled("pr", run=False)[0], 1)  # project still off
        self.assertEqual(json.loads(self.config.read_text(encoding="utf-8"))["steps"]["off"], ["pr"])
        log = (self.run_dir / "steps.jsonl").read_text(encoding="utf-8")
        self.assertIn("PR this time", log)

    def test_turning_one_review_back_on_keeps_the_rest_of_the_group_off(self):
        self.set_off(["reviews"])
        self.st("set", "review-security", "on", "--reason", "security matters here")
        off = json.loads(self.config.read_text(encoding="utf-8"))["steps"]["off"]
        self.assertNotIn("reviews", off)
        self.assertNotIn("review-security", off)
        self.assertIn("review-narrow", off)
        self.assertEqual(self.enabled("review-security")[0], 0)
        self.assertEqual(self.enabled("review-large")[0], 1)
        # same for a run override
        self.st("set", "reviews", "off", "--run", str(self.run_dir), "--reason", "quick fix")
        self.st("set", "review-narrow", "on", "--run", str(self.run_dir), "--reason", "but read the diff")
        self.assertEqual(self.enabled("review-narrow")[0], 0)
        self.assertEqual(self.enabled("review-large")[0], 1)

    def test_project_change_is_committed_on_its_own(self):
        code, out = self.st("set", "learn", "off", "--reason", "not yet")
        self.assertEqual((code, out), (0, "step=learn off for the project"))
        msg = subprocess.run(["git", "log", "-1", "--format=%s"], cwd=self.root, capture_output=True, text=True).stdout
        self.assertEqual(msg.strip(), "fyzxsflow: step learn off")
        files = subprocess.run(["git", "show", "--name-only", "--format=", "HEAD"], cwd=self.root, capture_output=True,
                               text=True).stdout.split()
        self.assertEqual(sorted(files), [".fyzxsflow/config.json", ".fyzxsflow/steps.jsonl"])
        self.st("set", "learn", "off", "--reason", "again")
        self.assertEqual(json.loads(self.config.read_text(encoding="utf-8"))["steps"]["off"], ["learn"])

    def test_list_warns_on_unknown_names_in_config(self):
        self.set_off(["pr", "pull-request"])
        out = self.st("list")[1]
        self.assertIn("warning: unknown step 'pull-request'", out)
        self.assertTrue(out.endswith("off: pr"))


if __name__ == "__main__":
    unittest.main()

"""Tests for engine/compare.py and the auto tier / shadow resolution in engine/models.py."""

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
import models  # noqa: E402


class AutoTierTests(unittest.TestCase):
    def test_auto_resolves_to_the_host_keyword_and_escalates_to_deep(self):
        mapping = {"deep": "big", "standard": "mid", "fast": "small", "auto": "auto"}
        self.assertEqual(models.resolve("auto", mapping), ("auto", "auto", False))
        self.assertEqual(models.resolve("auto", mapping, up=1), ("deep", "big", False))
        self.assertEqual(models.resolve("auto", {"deep": "big"}), ("auto", "", False))  # no capability: inherit

    def test_shadow_is_one_tier_down_and_none_for_fast_and_auto(self):
        mapping = {"deep": "big", "standard": "mid", "fast": "small"}
        self.assertEqual(models.shadow("deep", mapping), ("standard", "mid"))
        self.assertEqual(models.shadow("standard", mapping), ("fast", "small"))
        self.assertIsNone(models.shadow("fast", mapping))
        self.assertIsNone(models.shadow("auto", mapping))


class CompareTests(unittest.TestCase):
    def setUp(self):
        self.root = pathlib.Path(tempfile.mkdtemp(prefix="fyzxsflow-compare-"))
        subprocess.run([PY, "-I", str(ENGINE / "install.py"), "--target", str(self.root), "--host", "claude"],
                       capture_output=True, check=True)
        self.run_dir = self.new_run("one")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def new_run(self, ref):
        out = subprocess.run([PY, "-I", str(ENGINE / "run.py"), "new", "--source", "prompt", "--ref", ref,
                              "--root", str(self.root)], capture_output=True, text=True, check=True).stdout
        return pathlib.Path(out.strip().splitlines()[-1])

    def config(self, **compare):
        (self.root / ".fyzxsflow" / "config.json").write_text(json.dumps({"compare": compare}), encoding="utf-8")

    def cmp(self, *args):
        proc = subprocess.run([PY, "-I", str(self.root / ".fyzxsflow/package/engine/compare.py"), *args],
                              capture_output=True, text=True)
        return proc.returncode, proc.stdout.strip()

    def record(self, run, agent="implementer", pv="pass", sv="pass", **kw):
        extra = []
        for k, v in kw.items():
            extra += [f"--{k.replace('_', '-')}", str(v)]
        return self.cmp("record", "--run", str(run), "--agent", agent, "--primary-tier", "standard",
                        "--primary-model", "sonnet", "--shadow-tier", "fast", "--shadow-model", "haiku",
                        "--primary-verdict", pv, "--shadow-verdict", sv, *extra)

    def test_disabled_by_default(self):
        self.assertEqual(self.cmp("should", "--run", str(self.run_dir), "--agent", "implementer")[1],
                         "shadow=no reason=compare-disabled")

    def test_enabled_shadows_eligible_agents_one_tier_down(self):
        self.config(enabled=True)
        self.assertEqual(self.cmp("should", "--run", str(self.run_dir), "--agent", "implementer")[1],
                         "shadow=yes model=haiku tier=fast")
        self.assertEqual(self.cmp("should", "--run", str(self.run_dir), "--agent", "validator")[1],
                         "shadow=yes model=sonnet tier=standard")
        self.assertIn("no-lower-tier", self.cmp("should", "--run", str(self.run_dir), "--agent", "build-test-runner")[1])

    def test_agent_selection_cap_and_sampling(self):
        self.config(enabled=True, agents=["implementer"], max_per_run=1)
        self.assertIn("agent-not-selected", self.cmp("should", "--run", str(self.run_dir), "--agent", "tester")[1])
        self.record(self.run_dir)
        self.assertIn("max-per-run", self.cmp("should", "--run", str(self.run_dir), "--agent", "implementer")[1])
        self.config(enabled=True, sample_rate=0.0)
        self.assertIn("not-sampled", self.cmp("should", "--run", str(self.new_run("two")), "--agent", "implementer")[1])

    def test_scoring(self):
        self.assertTrue(self.record(self.run_dir, sv="corrected")[1].endswith("conclusive=yes shadow_ok=yes"))
        self.assertTrue(self.record(self.run_dir, sv="pass", shadow_majors=1)[1].endswith("shadow_ok=no"))
        self.assertTrue(self.record(self.run_dir, sv="pass", missed_majors=1)[1].endswith("shadow_ok=no"))
        self.assertTrue(self.record(self.run_dir, pv="fail", sv="pass")[1].endswith("conclusive=no shadow_ok=no"))
        self.assertEqual(self.record(self.run_dir, sv="great")[0], 2)

    def test_summary_recommends_reduce_only_with_enough_good_samples(self):
        self.config(min_samples=3, reduce_when_ok_rate=0.9)
        for _ in range(2):
            self.record(self.run_dir)
        self.assertIn("insufficient (2/3)", self.cmp("summary", "--root", str(self.root))[1])
        self.record(self.new_run("three"))
        self.record(self.run_dir, pv="fail")  # inconclusive: does not count either way
        out = self.cmp("summary", "--root", str(self.root))[1]
        self.assertIn("3/3 ok (100%), 1 inconclusive -> reduce: standard -> fast", out)
        self.record(self.run_dir, sv="fail")
        self.assertIn("-> keep", self.cmp("summary", "--root", str(self.root))[1])


if __name__ == "__main__":
    unittest.main()

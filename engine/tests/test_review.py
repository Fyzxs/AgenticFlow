"""Tests for engine/review.py: when to pause, reply parsing with -reduce/-increase, levels, graduation."""

import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

ENGINE = pathlib.Path(__file__).resolve().parent.parent
PY = sys.executable


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.root = pathlib.Path(tempfile.mkdtemp(prefix="agentflow-review-"))
        for args in (["init", "-q", "-b", "main"], ["config", "user.name", "T"], ["config", "user.email", "t@x"],
                     ["config", "core.autocrlf", "false"]):
            subprocess.run(["git", *args], cwd=self.root, check=True)
        (self.root / ".agentflow").mkdir()
        (self.root / ".agentflow" / "config.json").write_text(json.dumps({"docs": {"pack_budget_kb": 24}}), encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "base"], cwd=self.root, check=True)
        out = subprocess.run([PY, "-I", str(ENGINE / "run.py"), "new", "--source", "prompt", "--ref", "x",
                              "--root", str(self.root)], capture_output=True, text=True, check=True).stdout
        self.run_dir = pathlib.Path(out.strip().splitlines()[-1])

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def rv(self, *args):
        proc = subprocess.run([PY, "-I", str(ENGINE / "review.py"), *args], capture_output=True, text=True)
        return proc.returncode, (proc.stdout + proc.stderr).strip()

    def needed(self, agent="implementer", *extra):
        return self.rv("needed", "--run", str(self.run_dir), "--agent", agent, *extra)[1]

    def decide(self, reply, agent="implementer", edited=0):
        return self.rv("decide", "--run", str(self.run_dir), "--agent", agent, "--target", "WP-01",
                       "--reply", reply, "--edited", str(edited))

    def level(self, agent):
        cfg = json.loads((self.root / ".agentflow/config.json").read_text(encoding="utf-8"))
        return cfg.get("review", {}).get("agents", {}).get(agent)

    def test_every_agent_pauses_by_default(self):
        for agent in ("implementer", "build-test-runner", "gate-analyst"):
            self.assertEqual(self.needed(agent), "review=pause reason=agent-level level=on")

    def test_reduce_and_increase_step_the_ladder_from_any_reply(self):
        self.assertIn("level=on->notify", self.decide("approve -reduce")[1])
        self.assertEqual(self.level("implementer"), "notify")
        self.assertEqual(self.needed(), "review=notify reason=agent-level level=notify")
        self.assertIn("level=notify->off", self.decide("continue -reduce")[1])
        self.assertIn("level=off->off (already at the limit)", self.decide("approve -reduce")[1])
        self.assertEqual(self.needed(), "review=no reason=agent-level level=off")
        code, out = self.decide("redo: tests miss the null case -increase")
        self.assertEqual(code, 0)
        self.assertIn("decision=redo adjust=increase level=off->notify note=tests miss the null case", out)
        self.assertIn("decision=stop adjust=increase level=notify->on", self.decide("stop -increase")[1])
        self.assertIn("review level for implementer", subprocess.run(
            ["git", "log", "-1", "--format=%s"], cwd=self.root, capture_output=True, text=True).stdout)

    def test_reply_errors(self):
        self.assertEqual(self.decide("looks good")[0], 2)
        self.assertEqual(self.decide("approve -reduce -increase")[0], 2)
        self.assertEqual(self.decide("")[0], 2)

    def test_run_requests_and_always_rules_beat_levels_and_autopilot(self):
        self.decide("approve -reduce"); self.decide("approve -reduce")  # implementer now off
        (self.run_dir / "review-requests.md").write_text(
            "- autopilot\n- review: package=WP-03\n- review: path=**/Auth/**\n", encoding="utf-8")
        self.assertEqual(self.needed(), "review=no reason=autopilot level=off")
        self.assertIn("run-request:package=WP-03", self.needed("implementer", "--package", "WP-03"))
        self.assertIn("run-request:path=**/Auth/**", self.needed("implementer", "--paths", "src/Api/Auth/Login.cs"))
        cfg = json.loads((self.root / ".agentflow/config.json").read_text(encoding="utf-8"))
        cfg["review"]["always"] = {"segments": ["db-migration"], "paths": ["infra/**"]}
        (self.root / ".agentflow/config.json").write_text(json.dumps(cfg), encoding="utf-8")
        self.assertIn("always:segment=db-migration", self.needed("implementer", "--segment", "db-migration"))
        self.assertIn("always:path=infra/main.bicep", self.needed("implementer", "--paths", "infra/main.bicep"))

    def test_review_all_request(self):
        self.decide("approve -reduce"); self.decide("approve -reduce")
        (self.run_dir / "review-requests.md").write_text("- review: all\n", encoding="utf-8")
        self.assertIn("run-request:all", self.needed())

    def test_regress_only_raises_and_set_level(self):
        self.decide("approve -reduce")
        self.assertIn("level=notify->on", self.rv("regress", "--agent", "implementer", "--reason", "F-4 major",
                                                 "--root", str(self.root))[1])
        self.assertIn("unchanged", self.rv("regress", "--agent", "implementer", "--reason", "x", "--root", str(self.root))[1])
        self.assertIn("level=on->off", self.rv("set-level", "--agent", "tester", "--level", "off",
                                              "--reason", "owner: stop reviewing the tester", "--root", str(self.root))[1])

    def test_summary_suggests_reduce_after_clean_streak(self):
        cfg = json.loads((self.root / ".agentflow/config.json").read_text(encoding="utf-8"))
        cfg["review"] = {"graduate_after": 3}
        (self.root / ".agentflow/config.json").write_text(json.dumps(cfg), encoding="utf-8")
        self.decide("approve", edited=1)  # not clean
        for _ in range(3):
            self.decide("approve")
        out = self.rv("summary", "--root", str(self.root))[1]
        self.assertIn("implementer", out)
        self.assertIn("clean-streak=3 -> 3 clean approvals in a row: consider replying -reduce", out)


if __name__ == "__main__":
    unittest.main()

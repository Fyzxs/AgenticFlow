"""Tests for engine/models.py and the model lines install.py writes."""

import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

ENGINE = pathlib.Path(__file__).resolve().parent.parent
PY = sys.executable


class ModelTests(unittest.TestCase):
    def setUp(self):
        self.root = pathlib.Path(tempfile.mkdtemp(prefix="fyzxsflow-models-"))
        code = subprocess.run([PY, "-I", str(ENGINE / "install.py"), "--target", str(self.root),
                               "--host", "claude", "--host", "copilot"], capture_output=True, text=True)
        self.assertEqual(code.returncode, 0, code.stdout + code.stderr)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def models(self, *args):
        proc = subprocess.run([PY, "-I", str(self.root / ".fyzxsflow/package/engine/models.py"), "--root", str(self.root), *args],
                              capture_output=True, text=True)
        return proc.returncode, proc.stdout.strip()

    def fm(self, rel):
        text = (self.root / rel).read_text(encoding="utf-8")
        return text.split("---\n")[1]

    def test_every_agent_declares_a_tier(self):
        for f in (self.root / ".fyzxsflow/package/agents").glob("*.agent.md"):
            self.assertRegex(f.read_text(encoding="utf-8"), r"\ntier: (deep|standard|fast)\n", f.name)

    def test_default_claude_mapping_and_inherit_for_copilot(self):
        self.assertEqual(self.models("validator")[1], "model=opus tier=deep declared=deep escalated=no")
        self.assertEqual(self.models("implementer")[1], "model=sonnet tier=standard declared=standard escalated=no")
        self.assertEqual(self.models("build-test-runner")[1], "model=haiku tier=fast declared=fast escalated=no")
        self.assertTrue(self.models("validator", "--host", "copilot")[1].startswith("model=inherit"))
        self.assertIn("model: opus", self.fm(".claude/agents/validator.md"))
        self.assertIn("model: haiku", self.fm(".claude/agents/build-test-runner.md"))
        self.assertNotIn("model:", self.fm(".github/agents/validator.agent.md"))

    def test_escalation_steps_up_and_caps_at_deep(self):
        self.assertEqual(self.models("build-test-runner", "--up", "1")[1],
                         "model=sonnet tier=standard declared=fast escalated=yes")
        self.assertEqual(self.models("implementer", "--up", "1")[1],
                         "model=opus tier=deep declared=standard escalated=yes")
        self.assertEqual(self.models("validator", "--up", "1")[1],
                         "model=opus tier=deep declared=deep escalated=no capped=yes")

    def test_project_map_overrides_and_sync_rewrites_host_files(self):
        (self.root / ".fyzxsflow/config.json").write_text(json.dumps({"models": {
            "claude": {"deep": "fable", "standard": "sonnet", "fast": ""},
            "copilot": {"deep": "gpt-x", "standard": "", "fast": ""}}}), encoding="utf-8")
        self.assertEqual(self.models("validator")[1].split()[0], "model=fable")
        self.assertEqual(self.models("build-test-runner")[1].split()[0], "model=inherit")
        code = subprocess.run([PY, "-I", str(self.root / ".fyzxsflow/package/engine/install.py"), "--sync", "--target",
                               str(self.root), "--host", "claude", "--host", "copilot"], capture_output=True, text=True)
        self.assertEqual(code.returncode, 0, code.stderr)
        self.assertIn("model: fable", self.fm(".claude/agents/validator.md"))
        self.assertNotIn("model:", self.fm(".claude/agents/build-test-runner.md"))
        self.assertIn("model: gpt-x", self.fm(".github/agents/validator.agent.md"))
        self.assertNotIn("model:", self.fm(".fyzxsflow/package/agents/validator.agent.md"))  # canonical copy stays host-neutral

    def test_list(self):
        code, out = self.models("--list")
        self.assertEqual(code, 0)
        self.assertIn("orchestrator", out)
        self.assertEqual(len(out.splitlines()), len(list((self.root / ".fyzxsflow/package/agents").glob("*.agent.md"))))


if __name__ == "__main__":
    unittest.main()

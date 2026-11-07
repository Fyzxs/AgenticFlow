"""Tests for engine/pointers.py."""

import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

ENGINE = pathlib.Path(__file__).resolve().parent.parent
PY = sys.executable

SEGMENT = """---
paths:
  - "src/Mappers/**"
  - "src/Shared/Mapping/**"
pack:
  - .agentflow/docs/tech/csharp.md
---

# Segment: Mappers

Body.
"""


class PointerTests(unittest.TestCase):
    def setUp(self):
        self.root = pathlib.Path(tempfile.mkdtemp(prefix="agentflow-pointers-"))
        seg = self.root / ".agentflow" / "docs" / "segments"
        seg.mkdir(parents=True)
        (seg / "mapper.md").write_text(SEGMENT, encoding="utf-8")
        (seg / "_template.md").write_text(SEGMENT, encoding="utf-8")
        (self.root / ".claude" / "rules").mkdir(parents=True)
        (self.root / ".claude" / "rules" / "hand-written.md").write_text("mine", encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def pointers(self, *args):
        proc = subprocess.run([PY, "-I", str(ENGINE / "pointers.py"), "--root", str(self.root), *args],
                              capture_output=True, text=True)
        return proc.returncode, proc.stdout + proc.stderr

    def test_writes_both_hosts_scoped_to_segment_paths(self):
        code, out = self.pointers()
        self.assertEqual(code, 0, out)
        claude = (self.root / ".claude/rules/agentflow-mapper.md").read_text(encoding="utf-8")
        copilot = (self.root / ".github/instructions/agentflow-mapper.instructions.md").read_text(encoding="utf-8")
        self.assertIn('  - "src/Mappers/**"\n  - "src/Shared/Mapping/**"', claude)
        self.assertIn('applyTo: "src/Mappers/**,src/Shared/Mapping/**"', copilot)
        self.assertIn('description: "Mappers conventions (agentflow segment)"', copilot)
        for text in (claude, copilot):
            self.assertIn("`.agentflow/docs/segments/mapper.md` and every file listed under its `pack:`", text)
        self.assertFalse((self.root / ".claude/rules/agentflow-_template.md").exists())
        self.assertEqual((self.root / ".claude/rules/hand-written.md").read_text(encoding="utf-8"), "mine")

    def test_installer_owned_files_are_never_treated_as_stale(self):
        wa_claude = self.root / ".claude/rules/agentflow-working-agreement.md"
        wa_copilot = self.root / ".github/instructions/agentflow-working-agreement.instructions.md"
        wa_copilot.parent.mkdir(parents=True)
        for f in (wa_claude, wa_copilot):
            f.write_text("working agreement", encoding="utf-8")
        self.assertEqual(self.pointers()[0], 0)
        self.assertEqual(self.pointers("--check")[0], 0)
        for f in (wa_claude, wa_copilot):
            self.assertEqual(f.read_text(encoding="utf-8"), "working agreement")

    def test_check_detects_missing_edited_and_stale(self):
        self.assertEqual(self.pointers("--check")[0], 1)
        self.pointers()
        self.assertEqual(self.pointers("--check")[0], 0)
        edited = self.root / ".claude/rules/agentflow-mapper.md"
        edited.write_text(edited.read_text(encoding="utf-8") + "extra\n", encoding="utf-8")
        (self.root / ".github/instructions/agentflow-gone.instructions.md").write_text("old", encoding="utf-8")
        code, out = self.pointers("--check")
        self.assertEqual(code, 1)
        self.assertIn("agentflow-mapper.md: out of date or edited by hand", out)
        self.assertIn("agentflow-gone.instructions.md: no matching segment doc (stale)", out)

    def test_refresh_removes_stale_and_respects_host_config(self):
        (self.root / ".agentflow" / "config.json").write_text(json.dumps({"docs": {"host_pointers": ["copilot"]}}), encoding="utf-8")
        (self.root / ".claude/rules/agentflow-mapper.md").write_text("old", encoding="utf-8")
        code, out = self.pointers()
        self.assertEqual(code, 0, out)
        self.assertFalse((self.root / ".claude/rules/agentflow-mapper.md").exists())
        self.assertTrue((self.root / ".github/instructions/agentflow-mapper.instructions.md").exists())


if __name__ == "__main__":
    unittest.main()

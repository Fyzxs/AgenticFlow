"""Tests for engine/compact.py and the overlays install.py applies."""

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
import compact  # noqa: E402

AGENT = """---
name: sample
tier: standard
description: A sample agent that does a long and wordy thing for testing.
---

# Sample

## Rules
- Run `python -I .fyzxsflow/package/engine/run.py stamp <report>` after every hand-off, at most 2 rounds.
- Verdict `pass` only when evidence cites run-1/F-3 and AC-2.
- See [the contracts](../context/role-contracts.md).

```
python -I engine/tests/run_all.py
```
"""


class CompareTests(unittest.TestCase):
    def test_identical_text_loses_nothing(self):
        self.assertEqual(compact.compare(AGENT, AGENT), [])

    def test_shorter_wording_that_keeps_every_token_passes(self):
        after = AGENT.replace("A sample agent that does a long and wordy thing for testing.", "Samples.")
        after = after.replace("after every hand-off, at most 2 rounds", "per hand-off; max 2 rounds")
        self.assertEqual(compact.compare(AGENT, after), [])

    def test_each_kind_of_lost_token_is_reported(self):
        cases = {
            "tier: standard": ("tier: fast", "changed frontmatter: tier"),
            "## Rules": ("## Musts", "missing heading: ## Rules"),
            "`pass` only": ("only", "missing backtick: pass"),
            "at most 2 rounds": ("at most a few rounds", "missing number: 2"),
            "run-1/F-3 and ": ("", "missing id: F-3"),
            "(../context/role-contracts.md)": ("(x)", "missing link: ../context/role-contracts.md"),
            "python -I engine/tests/run_all.py\n": ("\n", "missing code: python -I engine/tests/run_all.py"),
        }
        for old, (new, expected) in cases.items():
            lost = compact.compare(AGENT, AGENT.replace(old, new, 1))
            self.assertTrue(any(l.startswith(expected) for l in lost), (old, lost))

    def test_a_literal_kept_only_as_prose_or_inside_a_longer_number_is_lost(self):
        lost = compact.compare(AGENT, AGENT.replace("`pass` only", "pass only").replace("2 rounds", "24 rounds"))
        self.assertIn("missing backtick: pass", lost)
        self.assertIn("missing number: 2", lost)

    def test_a_span_wrapped_over_two_lines_is_checked_and_may_be_rewrapped(self):
        before = "Run `findings.py add --kind <k>\n   --severity <s>` then `x`.\nThen, for each host (`.claude/` → claude).\n"
        self.assertEqual(compact.compare(before, before.replace("<k>\n   --severity", "<k> --severity")), [])
        self.assertIn("missing backtick: findings.py add --kind <k> --severity <s>",
                      compact.compare(before, before.replace("--severity <s>", "--sev <s>")))
        # prose between spans is never mistaken for code, whatever is inserted around it
        self.assertEqual(compact.compare(before, "New sentence. " + before), [])

    def test_merged_hit_counts_are_not_numbers_to_keep(self):
        before = "- Rule A. Evidence: r/F-3. Hits: 1. Added 2026-10-01.\n- Rule A again. Evidence: r/F-7. Hits: 2.\n"
        self.assertEqual(compact.compare(before, "- Rule A. Evidence: r/F-3, r/F-7. Hits: 3. Added 2026-10-01.\n"), [])

    def test_accepted_tokens_are_not_reported(self):
        self.assertEqual(compact.compare(AGENT, AGENT.replace("`pass` only", "only"), accept=["pass"]), [])

    def test_dropping_the_description_is_lost_but_shortening_it_is_not(self):
        self.assertIn("missing frontmatter: description",
                      compact.compare(AGENT, AGENT.replace("description: A sample agent that does a long and wordy "
                                                           "thing for testing.\n", "")))


class OverlayTests(unittest.TestCase):
    def setUp(self):
        self.root = pathlib.Path(tempfile.mkdtemp(prefix="fyzxsflow-compact-"))

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def run_py(self, script, *args):
        proc = subprocess.run([PY, "-I", str(script), *args], cwd=self.root, capture_output=True, text=True)
        return proc.returncode, proc.stdout + proc.stderr

    def install(self, *args):
        return self.run_py(ENGINE / "install.py", "--target", str(self.root), "--host", "claude", *args)

    def compact(self, *args):
        return self.run_py(self.root / ".fyzxsflow/package/engine/compact.py", *args, "--root", str(self.root))

    def overlay_validator(self, drop=None) -> str:
        """Compact the installed validator by removing its Limits bullets' second sentence (keeps every token)."""
        pkg = self.root / ".fyzxsflow/package/agents/validator.agent.md"
        text = pkg.read_text(encoding="utf-8")
        smaller = text.replace(" Validators fix misses; they do not redo the work.", "")
        if drop:
            smaller = smaller.replace(drop, "")
        self.assertLess(len(smaller), len(text))
        dst = self.root / ".fyzxsflow/compacted/agents/validator.agent.md"
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(smaller, encoding="utf-8", newline="\n")
        return smaller

    def test_record_apply_survive_reinstall_and_go_stale_when_upstream_changes(self):
        self.assertEqual(self.install()[0], 0)
        smaller = self.overlay_validator()
        code, out = self.compact("record", "agents/validator.agent.md")
        self.assertEqual(code, 0, out)
        self.assertIn("pending", self.compact("status")[1])
        code, out = self.run_py(self.root / ".fyzxsflow/package/engine/install.py", "--sync", "--target",
                                str(self.root), "--host", "claude")
        self.assertEqual(code, 0, out)
        host = (self.root / ".claude/agents/validator.md").read_text(encoding="utf-8")
        self.assertNotIn("they do not redo the work", host)
        self.assertIn("applied", self.compact("status")[1])
        # a reinstall replaces the package; the overlay is applied again
        code, out = self.install()
        self.assertEqual(code, 0, out)
        self.assertEqual((self.root / ".fyzxsflow/package/agents/validator.agent.md").read_text(encoding="utf-8"),
                         smaller)
        # recompacting an applied file keeps the original upstream hash
        source_sha = json.loads((self.root / ".fyzxsflow/compacted/manifest.json").read_text())[
            "agents/validator.agent.md"]["source_sha"]
        dst = self.root / ".fyzxsflow/compacted/agents/validator.agent.md"
        dst.write_text(smaller.replace("Never ask questions. ", ""), encoding="utf-8", newline="\n")
        self.assertEqual(self.compact("record", "agents/validator.agent.md")[0], 0)
        manifest = json.loads((self.root / ".fyzxsflow/compacted/manifest.json").read_text())
        self.assertEqual(manifest["agents/validator.agent.md"]["source_sha"], source_sha)
        # an upstream change makes it stale: the upstream file is kept, with a warning
        manifest["agents/validator.agent.md"]["source_sha"] = "0" * 64
        (self.root / ".fyzxsflow/compacted/manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        code, out = self.install()
        self.assertEqual(code, 0, out)
        self.assertIn("compacted agents/validator.agent.md is stale", out)
        self.assertIn("they do not redo the work",
                      (self.root / ".claude/agents/validator.md").read_text(encoding="utf-8"))

    def test_record_refuses_a_lossy_overlay_unless_the_token_is_accepted(self):
        self.install()
        self.overlay_validator(drop="`fail`")
        code, out = self.compact("record", "agents/validator.agent.md")
        self.assertEqual(code, 1)
        self.assertIn("missing backtick: fail", out)
        self.assertFalse((self.root / ".fyzxsflow/compacted/manifest.json").exists())
        code, out = self.compact("record", "agents/validator.agent.md", "--accept", "fail")
        self.assertEqual(code, 0, out)

    def test_record_refuses_paths_outside_the_compactable_package_folders(self):
        self.install()
        code, out = self.compact("record", "engine/run.py")
        self.assertNotEqual(code, 0)
        self.assertIn("only .md files under", out)
        self.assertNotEqual(self.compact("record", "agents/../../config.json")[0], 0)

    def test_drop_removes_the_overlay_and_reinstall_restores_upstream(self):
        self.install()
        self.overlay_validator()
        self.compact("record", "agents/validator.agent.md")
        self.install()
        code, out = self.compact("drop", "agents/validator.agent.md")
        self.assertEqual(code, 0, out)
        self.assertFalse((self.root / ".fyzxsflow/compacted/agents/validator.agent.md").exists())
        self.install()
        self.assertIn("they do not redo the work",
                      (self.root / ".fyzxsflow/package/agents/validator.agent.md").read_text(encoding="utf-8"))

    def test_hand_edited_overlay_is_not_applied(self):
        self.install()
        self.overlay_validator()
        self.compact("record", "agents/validator.agent.md")
        dst = self.root / ".fyzxsflow/compacted/agents/validator.agent.md"
        dst.write_text(dst.read_text(encoding="utf-8") + "\nextra\n", encoding="utf-8")
        code, out = self.install()
        self.assertIn("changed since it was recorded", out)
        self.assertNotIn("extra", (self.root / ".claude/agents/validator.md").read_text(encoding="utf-8"))

    def test_measure_lists_package_learned_docs_and_policy(self):
        self.install()
        (self.root / ".fyzxsflow/learned").mkdir()
        (self.root / ".fyzxsflow/learned/validator.md").write_text("# Learned: validator\n\n- rule\n", encoding="utf-8")
        (self.root / ".fyzxsflow/docs").mkdir()
        (self.root / ".fyzxsflow/docs/architecture.md").write_text("# Arch\n", encoding="utf-8")
        (self.root / ".fyzxsflow/profile.md").write_text("# Profile\n", encoding="utf-8")
        code, out = self.compact("measure")
        self.assertEqual(code, 0, out)
        self.assertIn(".fyzxsflow/package/agents/orchestrator.agent.md", out)
        self.assertIn("learned  .fyzxsflow/learned/validator.md", out)
        self.assertIn("doc      .fyzxsflow/docs/architecture.md", out)
        self.assertIn("owner's: propose, never edit", out)
        pkg_validator = (self.root / ".fyzxsflow/package/agents/validator.agent.md").stat().st_size
        self.assertIn(f"{pkg_validator + 29:>7}  package  .fyzxsflow/package/agents/validator.agent.md", out)
        self.assertIn("host = file + learned", out)
        self.assertIn("learned 29,", out.splitlines()[-1])

    def test_check_defaults_to_the_committed_version_for_project_files(self):
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        doc = self.root / "doc.md"
        doc.write_text("Use `make ci` twice.\n", encoding="utf-8")
        subprocess.run(["git", "add", "doc.md"], cwd=self.root, check=True)
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "x"], cwd=self.root,
                       check=True)
        doc.write_text("Use make twice.\n", encoding="utf-8")
        code, out = self.run_py(ENGINE / "compact.py", "check", str(doc), "--root", str(self.root))
        self.assertEqual(code, 1, out)
        self.assertIn("missing backtick: make ci", out)


if __name__ == "__main__":
    unittest.main()

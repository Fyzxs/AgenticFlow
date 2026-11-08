"""Tests for engine/feedback.py: the owner's inbox. New and edited items are found; handled ones are recorded
without touching the owner's words; applied items move to done/ and come back when edited."""

import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

ENGINE = pathlib.Path(__file__).resolve().parent.parent
PY = sys.executable


class FeedbackTests(unittest.TestCase):
    def setUp(self):
        self.root = pathlib.Path(tempfile.mkdtemp(prefix="agentflow-feedback-"))
        self.inbox = self.root / ".agentflow" / "feedback"
        self.inbox.mkdir(parents=True)
        (self.inbox / "README.md").write_text("# Feedback inbox\n", encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def fb(self, *args):
        proc = subprocess.run([PY, "-I", str(ENGINE / "feedback.py"), *args, "--root", str(self.root)],
                              capture_output=True, text=True)
        return proc.returncode, (proc.stdout + proc.stderr).strip()

    def test_scan_finds_new_items_and_ignores_the_readme_and_empty_files(self):
        (self.inbox / "sorting.md").write_text("# Sorting\nchange X in Y.cs to Z\n", encoding="utf-8")
        (self.inbox / "empty.md").write_text("\n", encoding="utf-8")
        code, out = self.fb("scan")
        self.assertEqual(code, 0, out)
        self.assertIn("new .agentflow/feedback/sorting.md: Sorting", out)
        self.assertNotIn("README", out)
        self.assertNotIn("empty.md", out)
        self.assertIn("inbox: 1 to process", out)

    def test_set_records_status_keeps_the_owners_words_and_moves_applied_items_to_done(self):
        item = self.inbox / "nulls.md"
        item.write_text("No ! in tests.\nOlder tests use it.\n", encoding="utf-8")
        code, out = self.fb("set", str(item), "--status", "applied", "--action", "docs", "--note",
                            "rule added to docs/tech/csharp.md Testing approach", "--ref", "F-70")
        self.assertEqual(code, 0, out)
        done = self.inbox / "done" / "nulls.md"
        self.assertFalse(item.exists())
        text = done.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("---\nstatus: applied\nactions: docs\n"))
        self.assertTrue(text.endswith("No ! in tests.\nOlder tests use it.\n"))
        self.assertIn("inbox: 0 to process", self.fb("scan")[1])
        self.assertIn("inbox: empty", self.fb("list")[1])
        self.assertIn("[applied] .agentflow/feedback/done/nulls.md: No ! in tests. -- rule added", self.fb("list", "--all")[1])

    def test_an_edited_item_is_picked_up_again_even_from_done(self):
        item = self.inbox / "x.md"
        item.write_text("first thought\n", encoding="utf-8")
        self.fb("set", str(item), "--status", "applied", "--action", "agent-input", "--note", "given to WP-05")
        done = self.inbox / "done" / "x.md"
        done.write_text(done.read_text(encoding="utf-8") + "and a second thought\n", encoding="utf-8")
        self.assertIn("changed .agentflow/feedback/done/x.md: first thought", self.fb("scan")[1])
        self.assertIn("[applied, edited since]", self.fb("list", "--all")[1])
        self.fb("set", str(done), "--status", "in-progress", "--action", "rework", "--note", "re-opened WP-05")
        self.assertTrue((self.inbox / "x.md").exists())  # reopened items leave done/
        self.assertIn("[in-progress] .agentflow/feedback/x.md", self.fb("list")[1])

    def test_waiting_stays_in_the_inbox_and_bad_values_are_refused(self):
        item = self.inbox / "q.md"
        item.write_text("should the sort be per game?\n", encoding="utf-8")
        self.fb("set", str(item), "--status", "waiting", "--action", "none", "--note", "asked the owner")
        self.assertTrue(item.exists())
        self.assertIn("[waiting] .agentflow/feedback/q.md", self.fb("list")[1])
        self.assertEqual(self.fb("set", str(item), "--status", "done", "--action", "docs", "--note", "x")[0], 2)


if __name__ == "__main__":
    unittest.main()

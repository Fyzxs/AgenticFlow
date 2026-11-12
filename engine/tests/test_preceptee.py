"""Tests for engine/preceptee.py: the preceptee's local record and the rules the Preceptor must not bend."""

import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

ENGINE = pathlib.Path(__file__).resolve().parent.parent
PY = sys.executable


class PreceptorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="fyzxsflow-preceptee-"))
        self.home = self.tmp / "userhome"
        self.repo = self.tmp / "repo"
        self.repo.mkdir()
        self.git("init", "-q")
        self.git("config", "user.name", "Quinn Gil")
        self.git("config", "user.email", "q@example.com")
        (self.repo / "app.py").write_text("print('hi')\n", encoding="utf-8")
        self.git("add", "app.py")
        self.git("commit", "-qm", "base")
        base = self.git("rev-parse", "HEAD").stdout.strip()
        self.run_dir = self.repo / ".fyzxsflow" / "runs" / "active" / "2026-11-12-001-x"
        self.run_dir.mkdir(parents=True)
        (self.run_dir / "input.md").write_text(f"---\nsource: prompt\nbase: {base}\n---\nx\n", encoding="utf-8")
        self.run = str(self.run_dir)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=self.repo, capture_output=True, text=True)

    def p(self, *args):
        env = {**os.environ, "FYZXSFLOW_USER_HOME": str(self.home)}
        proc = subprocess.run([PY, "-I", str(ENGINE / "preceptee.py"), *args], cwd=self.repo, capture_output=True,
                              text=True, env=env)
        return proc.returncode, proc.stdout + proc.stderr

    def settings(self, **data):
        self.home.mkdir(parents=True, exist_ok=True)
        (self.home / "preceptee.json").write_text(json.dumps(data), encoding="utf-8")

    def exercise(self, step, area="6:python", hints=0, bail=False, **score):
        self.assertIn("pause=yes", self.p("decide", area, "--run", self.run, "--step", step)[1])
        for _ in range(hints):
            self.p("hint", "--run", self.run, "--step", step)
        self.p("attempt", "--run", self.run, "--step", step, *(["--bail"] if bail else []))
        self.assertEqual(self.p("reveal", "--run", self.run, "--step", step)[0], 0)
        args = []
        for k, v in score.items():
            args += [f"--{k.replace('_', '-')}"] + ([] if v is True else [str(v)])
        code, out = self.p("score", "--run", self.run, "--step", step, *args)
        self.assertEqual(code, 0, out)
        return out

    # ------------------------------------------------------------ identity

    def test_handle_is_the_git_name_unless_overridden(self):
        self.assertIn("handle=quinn-gil", self.p("whoami")[1])
        self.settings(handle="QG at work")
        self.assertIn("handle=qg-at-work", self.p("whoami")[1])

    # ------------------------------------------------------------ pausing

    def test_full_pauses_after_the_fact_areas_never_do_and_off_does_not(self):
        self.assertIn("pause=yes level=full", self.p("decide", "6:Python", "--run", self.run, "--step", "a")[1])
        for area in ("2", "4", "5", "8"):
            self.assertIn("pause=no", self.p("decide", area, "--run", self.run, "--step", f"s{area}")[1])
        self.p("area", "1", "off")
        self.assertIn("pause=no level=off", self.p("decide", "1", "--run", self.run, "--step", "r")[1])

    def test_decide_answers_the_same_for_the_same_step(self):
        self.p("decide", "1", "--run", self.run, "--step", "WP-01.review")
        self.p("area", "1", "off")
        self.assertIn("pause=yes", self.p("decide", "1", "--run", self.run, "--step", "WP-01.review")[1])

    def test_spot_pauses_one_exercise_in_spot_every(self):
        self.p("area", "6:python", "spot")
        pauses = [("pause=yes" in self.p("decide", "6:python", "--run", self.run, "--step", f"WP-0{i}")[1])
                  for i in range(1, 7)]
        self.assertEqual(pauses, [True, False, False, True, False, False])

    def test_a_run_override_beats_the_standing_level_for_that_run_only(self):
        self.p("area", "3", "off", "--run", self.run)
        self.assertIn("pause=no", self.p("decide", "3", "--run", self.run, "--step", "intake")[1])
        other = self.repo / ".fyzxsflow" / "runs" / "active" / "2026-11-12-002-y"
        other.mkdir()
        self.assertIn("pause=yes", self.p("decide", "3", "--run", str(other), "--step", "intake")[1])

    def test_area_6_takes_its_stack_from_the_work_package(self):
        wp = self.tmp / "WP-01-orders.md"
        wp.write_text("# WP-01\n\n## Context pack (load exactly these)\n- `.fyzxsflow/docs/tech/Python.md`\n"
                      "- `.fyzxsflow/docs/segments/orders.md`\n\n## Scope\n- `.fyzxsflow/docs/tech/sql.md`\n",
                      encoding="utf-8")
        out = self.p("decide", "6", "--package", str(wp), "--run", self.run, "--step", "WP-01.implementer")[1]
        self.assertIn("area=6:python", out)
        self.assertNotEqual(self.p("decide", "6", "--run", self.run, "--step", "WP-02.implementer")[0], 0)
        self.p("area", "6", "off")  # every stack
        self.assertIn("pause=no", self.p("decide", "6:python", "--run", self.run, "--step", "WP-03.implementer")[1])

    def test_a_step_that_did_not_pause_is_not_the_preceptees_to_score(self):
        self.p("area", "1", "off", "--run", self.run)
        self.p("decide", "1", "--run", self.run, "--step", "WP-01.review")
        self.assertEqual(self.p("attempt", "--run", self.run, "--step", "WP-01.review")[0], 1)
        self.assertIn("outcome=not-counted", self.p("score", "--run", self.run, "--step", "WP-01.review")[1])

    def test_area_7_and_unknown_areas_are_refused(self):
        self.assertNotEqual(self.p("decide", "7", "--run", self.run, "--step", "x")[0], 0)
        self.assertNotEqual(self.p("decide", "12", "--run", self.run, "--step", "x")[0], 0)
        self.assertNotEqual(self.p("decide", "3:python", "--run", self.run, "--step", "x")[0], 0)

    # ------------------------------------------------------------ the preceptee goes first

    def test_nothing_is_revealed_before_an_attempt_or_a_bail(self):
        self.p("decide", "6:python", "--run", self.run, "--step", "WP-01.implementer")
        code, out = self.p("reveal", "--run", self.run, "--step", "WP-01.implementer")
        self.assertEqual(code, 1)
        self.assertIn("the preceptee goes first", out)
        self.p("attempt", "--run", self.run, "--step", "WP-01.implementer", "--bail")
        self.assertEqual(self.p("reveal", "--run", self.run, "--step", "WP-01.implementer")[0], 0)

    def test_hints_climb_one_rung_per_ask_and_stop_at_five(self):
        self.p("decide", "6:python", "--run", self.run, "--step", "s")
        rungs = [self.p("hint", "--run", self.run, "--step", "s")[1].strip() for _ in range(5)]
        self.assertEqual(rungs, [f"rung={i}" for i in range(1, 6)])
        self.assertEqual(self.p("hint", "--run", self.run, "--step", "s")[0], 1)

    def test_scoring_needs_the_reveal_and_happens_once(self):
        self.p("decide", "6:python", "--run", self.run, "--step", "s")
        self.p("attempt", "--run", self.run, "--step", "s")
        self.assertIn("reveal s before scoring", self.p("score", "--run", self.run, "--step", "s")[1])
        self.p("reveal", "--run", self.run, "--step", "s")
        self.assertEqual(self.p("score", "--run", self.run, "--step", "s")[0], 0)
        self.assertEqual(self.p("score", "--run", self.run, "--step", "s")[0], 1)

    # ------------------------------------------------------------ what counts

    def test_what_counts_as_a_good_answer(self):
        self.assertIn("outcome=good streak=1", self.exercise("a"))
        self.assertIn("outcome=good streak=2", self.exercise("b", hints=1))  # a first-rung hint is fine
        self.assertIn("outcome=miss streak=0", self.exercise("c", hints=2))
        self.assertIn("outcome=good streak=1", self.exercise("d"))
        self.assertIn("outcome=miss streak=0", self.exercise("e", bail=True))
        self.exercise("f")
        self.assertIn("outcome=miss streak=0", self.exercise("g", medium=1))
        self.exercise("h")
        self.assertIn("outcome=not-counted streak=1", self.exercise("i", skip=True))

    def test_a_review_counts_only_when_every_major_was_caught(self):
        self.assertIn("outcome=good", self.exercise("r1", area="1", caught=2, missed_major=0, false_alarms=1))
        self.assertIn("outcome=miss", self.exercise("r2", area="1", caught=1, missed_major=1))

    def test_after_the_fact_questions_count_only_when_answered(self):
        self.p("decide", "2", "--run", self.run, "--step", "debug-1")
        self.p("ask", "--run", self.run, "--step", "debug-1", "--area", "2", "--text", "What was your hypothesis?")
        self.assertIn("outcome=not-counted", self.p("score", "--run", self.run, "--step", "debug-1", "--unanswered")[1])
        self.p("ask", "--run", self.run, "--step", "debug-2", "--area", "2", "--text", "And here?")
        self.p("answered", "--run", self.run, "--step", "debug-2", "--text", "a race on the cache")
        self.assertIn("outcome=good", self.p("score", "--run", self.run, "--step", "debug-2")[1])
        q = (self.home / "preceptee" / "runs" / "2026-11-12-001-x" / "questions.md").read_text(encoding="utf-8")
        self.assertIn("a race on the cache", q)

    # ------------------------------------------------------------ prompts

    def test_prompts_at_4_7_and_10_on_one_running_streak(self):
        outs = [self.exercise(f"s{i}") for i in range(1, 5)]
        self.assertIn("prompt=step-down to=light", outs[-1])
        self.assertNotIn("prompt", "".join(outs[:-1]))
        self.assertEqual(self.p("answer", "6:python", "yes")[0], 0)
        outs = [self.exercise(f"t{i}") for i in range(5, 8)]
        self.assertIn("streak=7 prompt=step-down to=spot", outs[-1])
        self.p("answer", "6:python", "yes")
        self.p("area", "6:python", "full", "--run", self.run)  # keep pausing for the test's exercises
        outs = [self.exercise(f"u{i}") for i in range(8, 11)]
        self.assertIn("streak=10 prompt=step-down to=off", outs[-1])

    def test_a_declined_prompt_restarts_the_streak(self):
        for i in range(4):
            self.exercise(f"s{i}")
        self.assertIn("streak restarted", self.p("answer", "6:python", "no")[1])
        self.assertIn("outcome=good streak=1", self.exercise("again"))
        state = json.loads((self.home / "preceptee" / "state.json").read_text(encoding="utf-8"))
        self.assertEqual(state["areas"]["6:python"]["level"], "full")

    def test_thresholds_come_from_preceptee_json(self):
        self.settings(prompt_after={"light": 2})
        self.exercise("a")
        self.assertIn("prompt=step-down to=light", self.exercise("b"))

    def test_a_major_miss_at_light_offers_a_step_back_up(self):
        self.p("area", "6:python", "light")
        self.assertIn("prompt=step-up to=full", self.exercise("m", major=1))
        self.p("answer", "6:python", "yes")
        self.assertIn("6:python", self.p("status")[1])
        state = json.loads((self.home / "preceptee" / "state.json").read_text(encoding="utf-8"))
        self.assertEqual(state["areas"]["6:python"]["level"], "full")

    def test_stacks_are_tracked_separately(self):
        for i in range(4):
            self.exercise(f"py{i}", area="6:python")
        self.assertIn("streak=1", self.exercise("sql0", area="6:sql"))

    # ------------------------------------------------------------ explain-before-merge, seeds

    def test_every_changed_file_needs_an_explanation(self):
        (self.repo / "app.py").write_text("print('hello')\n", encoding="utf-8")
        (self.repo / "new.py").write_text("x = 1\n", encoding="utf-8")
        self.git("add", "new.py")
        (self.repo / "__pycache__").mkdir()
        (self.repo / "__pycache__" / "app.cpython-310.pyc").write_bytes(b"\0")  # build output is not the change
        code, out = self.p("explained", "--run", self.run)
        self.assertEqual(code, 1)
        self.assertIn("app.py", out)
        self.p("note", "--run", self.run, "--kind", "explain", "--path", "app.py", "--text", "greets properly")
        self.p("note", "--run", self.run, "--kind", "explain", "--path", "new.py", "--text", "a constant")
        code, out = self.p("explained", "--run", self.run)
        self.assertEqual(code, 0, out)
        self.git("commit", "-qam", "change")  # committed on the run's branch: still the change, still explained
        self.assertEqual(self.p("explained", "--run", self.run)[0], 0)

    def test_explanations_are_not_required_with_area_9_off(self):
        (self.repo / "app.py").write_text("print('hello')\n", encoding="utf-8")
        self.p("area", "9", "off", "--run", self.run)
        self.assertEqual(self.p("explained", "--run", self.run)[0], 0)

    def test_a_seeded_line_in_the_tree_or_branch_is_caught(self):
        seed = self.tmp / "seed.txt"
        seed.write_text("    time.sleep(0.5)  # wait for the cache\n", encoding="utf-8")
        self.p("seed", "--run", self.run, "--step", "WP-01.review", "--lines-file", str(seed))
        self.assertEqual(self.p("seed-check", "--run", self.run)[0], 0)
        (self.repo / "app.py").write_text("import time\n    time.sleep(0.5)  # wait for the cache\n", encoding="utf-8")
        code, out = self.p("seed-check", "--run", self.run)
        self.assertEqual(code, 1)
        self.assertIn("time.sleep(0.5)", out)
        self.git("commit", "-qam", "oops")
        self.assertEqual(self.p("seed-check", "--run", self.run)[0], 1)

    # ------------------------------------------------------------ digest, import, export

    def test_digest_round_trips_the_preceptors_notes(self):
        self.exercise("a", area="1", caught=1, missed_major=0)
        out_dir = self.tmp / "out"
        code, out = self.p("digest", "--out", str(out_dir))
        self.assertEqual(code, 0, out)
        digest = next(out_dir.glob("digest-quinn-gil-*.md"))
        text = digest.read_text(encoding="utf-8")
        self.assertIn("| 1 verifying AI output | full | 1 | 1 |", text)
        self.assertIn("## Preceptor notes", text)
        digest.write_text(text + "- area 1: signed off; caught the seeded sleep\n- area 6:python: level light\n"
                          "- keep going on tests\n", encoding="utf-8")
        code, out = self.p("import", str(digest))
        self.assertEqual(code, 0, out)
        self.assertIn("2 applied, 1 kept as notes", out)
        status = self.p("status")[1]
        self.assertIn("signed off by preceptor", status)
        state = json.loads((self.home / "preceptee" / "state.json").read_text(encoding="utf-8"))
        self.assertEqual(state["areas"]["6:python"]["level"], "light")

    def test_export_needs_consent_and_carries_no_identity_or_notes(self):
        self.exercise("a", area="1", caught=3, missed_major=1)
        self.assertEqual(self.p("export")[0], 1)
        code, out = self.p("export", "--consent")
        self.assertEqual(code, 0, out)
        data = json.loads(out)
        self.assertEqual(data["areas"]["1"]["review_catch_rate"], 0.75)
        self.assertNotIn("quinn", out.lower())
        self.assertNotIn("2026-11-12-001", out)

    def test_nothing_is_written_inside_the_repo(self):
        self.exercise("a")
        self.p("note", "--run", self.run, "--kind", "reason", "--text", "looked right")
        untracked = self.git("status", "--porcelain", "--untracked-files=all").stdout
        self.assertNotIn("preceptee", untracked)
        self.assertEqual([p.name for p in self.run_dir.iterdir()], ["input.md"])


if __name__ == "__main__":
    unittest.main()

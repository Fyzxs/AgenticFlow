"""Tests for engine/review.py: when to pause, reply parsing with -less-review/-more-review, levels, graduation."""

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
        self.root = pathlib.Path(tempfile.mkdtemp(prefix="fyzxsflow-review-"))
        for args in (["init", "-q", "-b", "main"], ["config", "user.name", "T"], ["config", "user.email", "t@x"],
                     ["config", "core.autocrlf", "false"]):
            subprocess.run(["git", *args], cwd=self.root, check=True)
        (self.root / ".fyzxsflow").mkdir()
        (self.root / ".fyzxsflow" / "config.json").write_text(json.dumps({"docs": {"pack_budget_kb": 24}}), encoding="utf-8")
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

    def findings(self):
        path = self.run_dir / "findings.jsonl"
        return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]

    def review_file(self, feedback):
        f = self.run_dir / "reviews" / "WP-01-api-sort.implementer.md"
        f.parent.mkdir(exist_ok=True)
        f.write_text("# Review\n\n**Reply with one of**\n- approve\n\n## Human Feedback\n"
                     "<!-- Write anything here -->\n" + feedback + "\n", encoding="utf-8")
        return f

    def test_human_feedback_section_and_note_become_one_owner_feedback_finding(self):
        f = self.review_file("No null-forgiving ! in tests.\nOlder tests use it; don't copy them.")
        code, out = self.rv("decide", "--run", str(self.run_dir), "--agent", "tester", "--target", "WP-01",
                            "--reply", "redo: fix the five asserts", "--review-file", str(f))
        self.assertEqual(code, 0, out)
        self.assertIn("decision=redo", out)
        self.assertIn("feedback=F-1", out)
        (finding,) = self.findings()
        self.assertEqual((finding["kind"], finding["source"], finding["target"]), ("owner-feedback", "human", "tester"))
        self.assertIn("Reply (redo): fix the five asserts", finding["detail"])
        self.assertIn("Older tests use it; don't copy them.", finding["detail"])  # verbatim, all lines
        self.assertNotIn("Write anything here", finding["detail"])                # template comment stripped
        scan = subprocess.run([PY, "-I", str(ENGINE / "feedback.py"), "scan", "--root", str(self.root)],
                              capture_output=True, text=True).stdout
        self.assertIn("reviews: 0 with new feedback", scan)  # recorded with the reply: not picked up twice

    def test_approve_with_feedback_is_recorded_and_empty_feedback_is_not(self):
        f = self.review_file("<write feedback here>")
        code, out = self.rv("decide", "--run", str(self.run_dir), "--agent", "tester", "--target", "WP-01",
                            "--reply", "approve", "--review-file", str(f))
        self.assertIn("feedback=none", out)
        self.assertEqual(self.findings(), [])
        f = self.review_file("Use nameof everywhere in these asserts.")
        code, out = self.rv("decide", "--run", str(self.run_dir), "--agent", "tester", "--target", "WP-01",
                            "--reply", "approve", "--review-file", str(f))
        self.assertIn("decision=approve", out)
        self.assertIn("feedback=F-1", out)

    def level(self, agent):
        cfg = json.loads((self.root / ".fyzxsflow/config.json").read_text(encoding="utf-8"))
        return cfg.get("review", {}).get("agents", {}).get(agent)

    def test_every_agent_pauses_by_default(self):
        for agent in ("implementer", "build-test-runner", "gate-analyst"):
            self.assertEqual(self.needed(agent), "review=pause reason=agent-level level=on")

    def test_reduce_and_increase_step_the_ladder_from_any_reply(self):
        self.assertIn("level=on->notify", self.decide("approve -less-review")[1])
        self.assertEqual(self.level("implementer"), "notify")
        self.assertEqual(self.needed(), "review=notify reason=agent-level level=notify")
        self.assertIn("level=notify->off", self.decide("continue -less-review")[1])
        self.assertIn("level=off->off (already at the limit)", self.decide("approve -less-review")[1])
        self.assertEqual(self.needed(), "review=no reason=agent-level level=off")
        code, out = self.decide("redo: tests miss the null case -more-review")
        self.assertEqual(code, 0)
        self.assertIn("decision=redo adjust=more-review level=off->notify feedback=F-1 note=tests miss the null case", out)
        self.assertIn("decision=stop adjust=more-review level=notify->on", self.decide("stop -more-review")[1])
        self.assertIn("review level for implementer", subprocess.run(
            ["git", "log", "-1", "--format=%s"], cwd=self.root, capture_output=True, text=True).stdout)

    def test_natural_decision_words_parse(self):
        sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
        import review
        for reply in ("Approved. Use your recommendations", "approve.", "Approve!", "approved -less-review"):
            self.assertEqual(review.parse_reply(reply)[0], "approve", reply)
        self.assertEqual(review.parse_reply("approved -less-review")[1], "less-review")
        with self.assertRaises(ValueError):
            review.parse_reply("approval pending")  # only known forms; nothing guessed

    def test_reply_errors(self):
        self.assertEqual(self.decide("looks good")[0], 2)
        self.assertEqual(self.decide("approve -less-review -more-review")[0], 2)
        self.assertEqual(self.decide("")[0], 2)
        self.assertEqual(self.decide("approve -reduce")[0], 2)  # retired name: refused, not read as a note

    def test_run_requests_and_always_rules_beat_levels_and_autopilot(self):
        self.decide("approve -less-review"); self.decide("approve -less-review")  # implementer now off
        (self.run_dir / "review-requests.md").write_text(
            "- autopilot\n- review: package=WP-03\n- review: path=**/Auth/**\n", encoding="utf-8")
        self.assertEqual(self.needed(), "review=no reason=autopilot level=off")
        self.assertIn("run-request:package=WP-03", self.needed("implementer", "--package", "WP-03"))
        self.assertIn("run-request:path=**/Auth/**", self.needed("implementer", "--paths", "src/Api/Auth/Login.cs"))
        cfg = json.loads((self.root / ".fyzxsflow/config.json").read_text(encoding="utf-8"))
        cfg["review"]["always"] = {"segments": ["db-migration"], "paths": ["infra/**"]}
        (self.root / ".fyzxsflow/config.json").write_text(json.dumps(cfg), encoding="utf-8")
        self.assertIn("always:segment=db-migration", self.needed("implementer", "--segment", "db-migration"))
        self.assertIn("always:path=infra/main.bicep", self.needed("implementer", "--paths", "infra/main.bicep"))

    def test_review_all_request(self):
        self.decide("approve -less-review"); self.decide("approve -less-review")
        (self.run_dir / "review-requests.md").write_text("- review: all\n", encoding="utf-8")
        self.assertIn("run-request:all", self.needed())

    def test_regress_only_raises_and_set_level(self):
        self.decide("approve -less-review")
        self.assertIn("level=notify->on", self.rv("regress", "--agent", "implementer", "--reason", "F-4 major",
                                                 "--root", str(self.root))[1])
        self.assertIn("unchanged", self.rv("regress", "--agent", "implementer", "--reason", "x", "--root", str(self.root))[1])
        self.assertIn("level=on->off", self.rv("set-level", "--agent", "tester", "--level", "off",
                                              "--reason", "owner: stop reviewing the tester", "--root", str(self.root))[1])

    def test_summary_suggests_reduce_after_clean_streak(self):
        cfg = json.loads((self.root / ".fyzxsflow/config.json").read_text(encoding="utf-8"))
        cfg["review"] = {"graduate_after": 3}
        (self.root / ".fyzxsflow/config.json").write_text(json.dumps(cfg), encoding="utf-8")
        self.decide("approve", edited=1)  # not clean
        for _ in range(3):
            self.decide("approve")
        out = self.rv("summary", "--root", str(self.root))[1]
        self.assertIn("implementer", out)
        self.assertIn("clean-streak=3 -> 3 clean approvals in a row: consider replying -less-review", out)


    def write_review(self, look_at, reply="yes — the run is waiting for you.", extra=""):
        template = (ENGINE.parent / "templates/run/review-pending.md").read_text(encoding="utf-8")
        text = template.replace("<agent>", "implementer", 1).replace("<WP-04>: <package title, or the stage name>",
                                                                     "WP-01: sort by date")
        text = text.replace("- `<path>` — <one line on what it is>", look_at)
        text = text.replace("<yes — the run is waiting for you. | no — <agent> is at review level <notify|off>, so the run\n"
                            "moved on to <the next step>. Read this whenever you like; anything you write under Human Feedback below is\n"
                            "picked up at the next hand-off (or say \"process feedback\").>", reply)
        text = text.replace("**Validator verdict:** <pass | corrected | fail>, findings: <F-n ...>",
                            "**Validator verdict:** pass, findings: none" + extra)
        review = self.run_dir / "reviews" / "wp-01-sort.implementer.md"
        review.parent.mkdir(parents=True, exist_ok=True)
        review.write_text(text, encoding="utf-8")
        return review

    def show(self, review, *extra):
        import os
        env = {k: v for k, v in os.environ.items() if k not in ("TERM_PROGRAM", "VSCODE_IPC_HOOK_CLI")}
        proc = subprocess.run([PY, "-I", str(ENGINE / "review.py"), "show", "--review-file", str(review), *extra],
                              capture_output=True, text=True, env=env)
        return proc.returncode, proc.stdout, proc.stderr

    def test_show_lists_every_file_to_read_as_a_link_before_the_reply_options(self):
        (self.root / "src").mkdir()
        (self.root / "src" / "sort.py").write_text("x = 1\n", encoding="utf-8")
        (self.run_dir / "reports").mkdir(exist_ok=True)
        (self.run_dir / "reports" / "WP-01.implementer.md").write_text("r\n", encoding="utf-8")
        review = self.write_review("- `src/sort.py:1` — the sort\n- `reports/WP-01.implementer.md` — the report\n"
                                   "- `src/gone.py` — removed")
        code, out, err = self.show(review, "--open")
        self.assertEqual(code, 0, err)
        self.assertIn("**Review: implementer — WP-01: sort by date** — the run is waiting for you.", out)
        self.assertIn("1. [reviews/wp-01-sort.implementer.md](<", out)  # the review itself comes first
        self.assertNotIn("Package <n>", out)  # unfilled template lines are left out
        self.assertIn(f"2. [src/sort.py:1](<{(self.root / 'src/sort.py').resolve().as_posix()}>) — the sort", out)
        self.assertIn(f"3. [reports/WP-01.implementer.md](<{(self.run_dir / 'reports/WP-01.implementer.md').resolve().as_posix()}>)", out)
        self.assertIn("4. `src/gone.py` (not on disk: deleted, or not created yet) — removed", out)
        self.assertIn("**Validator verdict:** pass, findings: none", out)
        self.assertNotIn("<checkpoint>", out)  # an unfilled line is left out, not shown with placeholders
        self.assertLess(out.index("Read before you reply"), out.index("**Reply here:**"))
        self.assertIn("opened=no (not a VS Code terminal)", err)

    def test_show_refuses_a_review_that_names_nothing_to_look_at(self):
        review = self.write_review("- `<path>` — <one line on what it is>")
        code, out, err = self.show(review)
        self.assertEqual(code, 2)
        self.assertIn("fill **What to look at**", err)
        self.assertEqual(out, "")

    def test_show_for_a_no_reply_review_says_the_run_moved_on(self):
        (self.root / "a.md").write_text("a\n", encoding="utf-8")
        review = self.write_review("- `a.md` — a", reply="no — implementer is at review level notify, so the run moved on.")
        code, out, _ = self.show(review)
        self.assertEqual(code, 0)
        self.assertIn("no reply needed; the run moved on.", out)
        self.assertNotIn("**Reply here:**", out)


if __name__ == "__main__":
    unittest.main()

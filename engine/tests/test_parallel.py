"""Tests for parallel work: engine/waves.py, engine/lanes.py, run.py new --worktree, and shared Runner locks."""

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
import runner  # noqa: E402

WP = """---
id: {id}
segment: {seg}
status: planned
depends_on: [{deps}]
blocks: []
---

# {id} — {seg}

## Acceptance criteria
- **{id}.1**: works

## Scope
{scope}

## Series reasons
{reasons}

## Done check
- Runner: `--{mode} --scope project`
"""


class ParallelBase(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="fyzxsflow-parallel-"))
        self.root = self.tmp / "repo"
        self.root.mkdir()
        for args in (["init", "-q", "-b", "main"], ["config", "user.name", "T"], ["config", "user.email", "t@x"]):
            self.git(*args)
        (self.root / "src").mkdir()
        for name in ("a.py", "b.py", "c.py", "d.py", "shared.py"):
            (self.root / "src" / name).write_text(f"# {name}\n", encoding="utf-8")
        cfg = {"build": {"max_parallel": 3},
               "modes": {"quick": {"steps": [{"name": "t", "run": "true"}]},
                         "db": {"lock": "local-db", "steps": [{"name": "t", "run": "true"}]}}}
        (self.root / ".fyzxsflow").mkdir()
        (self.root / ".fyzxsflow" / "config.json").write_text(json.dumps(cfg), encoding="utf-8")
        self.run = self.root / ".fyzxsflow" / "runs" / "active" / "20261112-000000-x"
        (self.run / "work-packages").mkdir(parents=True)
        (self.run / "input.md").write_text("---\nrun: x\n---\nx\n", encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def git(self, *args, cwd=None):
        return subprocess.run(["git", *args], cwd=cwd or self.root, capture_output=True, text=True)

    def py(self, script, *args, cwd=None):
        proc = subprocess.run([PY, "-I", str(ENGINE / script), *args], cwd=cwd or self.root, capture_output=True,
                              text=True)
        return proc.returncode, proc.stdout + proc.stderr

    def wp(self, wp_id, files, deps=(), reasons=None, mode="quick"):
        scope = "\n".join(f"- change: `{f}`" for f in files)
        reasons = reasons if reasons is not None else {d: "contract" for d in deps}
        (self.run / "work-packages" / f"{wp_id}-x.md").write_text(WP.format(
            id=wp_id, seg="s", deps=", ".join(deps), scope=scope, mode=mode,
            reasons="\n".join(f"- {d}: {r} — because" for d, r in reasons.items())), encoding="utf-8")

    def commit_all(self, msg="plan"):
        self.git("add", "-A")
        self.git("commit", "-qm", msg)

    def plan(self):
        self.wp("WP-01", ["src/a.py"])
        self.wp("WP-02", ["src/b.py"])
        self.wp("WP-03", ["src/c.py"])
        self.wp("WP-04", ["src/d.py"], deps=["WP-01", "WP-02"])


class WavesTests(ParallelBase):
    def waves(self):
        return self.py("waves.py", "check", "--run", str(self.run))

    def test_independent_packages_share_a_wave_and_a_dependent_one_follows(self):
        self.plan()
        code, out = self.waves()
        self.assertEqual(code, 0, out)
        self.assertIn("wave 1: WP-01, WP-02, WP-03 (parallel, 3 at a time) | wave 2: WP-04", out)

    def test_every_series_edge_needs_a_known_reason(self):
        self.plan()
        self.wp("WP-04", ["src/d.py"], deps=["WP-01", "WP-02"], reasons={"WP-01": "contract"})
        code, out = self.waves()
        self.assertEqual(code, 1)
        self.assertIn("WP-04: depends_on WP-02 with no reason", out)
        self.wp("WP-04", ["src/d.py"], deps=["WP-01"], reasons={"WP-01": "vibes"})
        self.assertIn("series reason 'vibes'", self.waves()[1])

    def test_two_packages_of_one_wave_may_not_change_the_same_file(self):
        self.wp("WP-01", ["src/a.py", "src/shared.py"])
        self.wp("WP-02", ["src/b.py", "src/shared.py"])
        code, out = self.waves()
        self.assertEqual(code, 1)
        self.assertIn("WP-01 and WP-02 are in the same wave but both change src/shared.py", out)
        self.wp("WP-02", ["src/b.py", "src/shared.py"], deps=["WP-01"], reasons={"WP-01": "same file"})
        self.assertEqual(self.waves()[0], 0)

    def test_cycles_and_unknown_dependencies_fail(self):
        self.wp("WP-01", ["src/a.py"], deps=["WP-02"])
        self.wp("WP-02", ["src/b.py"], deps=["WP-01"])
        self.wp("WP-03", ["src/c.py"], deps=["WP-09"])
        out = self.waves()[1]
        self.assertIn("dependency cycle among: WP-01, WP-02", out)
        self.assertIn("WP-03: depends_on WP-09, which is not a package", out)

    def test_a_shared_runner_lock_is_a_warning_not_a_failure(self):
        self.wp("WP-01", ["src/a.py"], mode="db")
        self.wp("WP-02", ["src/b.py"], mode="db")
        code, out = self.waves()
        self.assertEqual(code, 0, out)
        self.assertIn("share the Runner lock local-db", out)


class LanesTests(ParallelBase):
    def lanes(self, *args):
        return self.py("lanes.py", *args, "--run", str(self.run))

    def build_in(self, path, rel, text):
        (pathlib.Path(path) / rel).write_text(text, encoding="utf-8")
        self.git("add", rel, cwd=path)
        self.git("commit", "-qm", f"work on {rel}", cwd=path)

    def opened(self, out):
        return {l.split()[1]: l.split()[2] for l in out.splitlines() if l.startswith("lane ")}

    def test_lanes_open_up_to_the_cap_merge_in_order_and_close(self):
        self.plan()
        cfg = json.loads((self.root / ".fyzxsflow" / "config.json").read_text())
        cfg["build"]["max_parallel"] = 2
        (self.root / ".fyzxsflow" / "config.json").write_text(json.dumps(cfg), encoding="utf-8")
        self.commit_all()
        code, out = self.lanes("open", "--wave", "1")
        self.assertEqual(code, 0, out)
        lanes = self.opened(out)
        self.assertEqual(sorted(lanes), ["WP-01", "WP-02"])
        self.assertIn("waiting WP-03", out)
        self.assertIn("/.git/fyzxsflow-lanes/", list(lanes.values())[0])  # out of the working tree
        self.build_in(lanes["WP-01"], "src/a.py", "# a, built\n")
        self.build_in(lanes["WP-02"], "src/b.py", "# b, built\n")
        code, out = self.lanes("merge", "--wave", "1")
        self.assertEqual(code, 0, out)
        self.assertEqual(out.split(), ["merged", "WP-01", "merged", "WP-02"])
        self.assertEqual((self.root / "src" / "a.py").read_text(), "# a, built\n")
        code, out = self.lanes("open", "--wave", "1")
        lanes = self.opened(out)
        self.assertEqual(list(lanes), ["WP-03"])
        self.build_in(lanes["WP-03"], "src/c.py", "# c, built\n")
        self.assertEqual(self.lanes("merge", "--wave", "1")[0], 0)
        log = self.git("log", "--format=%s").stdout
        self.assertIn("build(20261112-000000-x): WP-03", log)
        self.assertIn("in place WP-04", self.lanes("open", "--wave", "2")[1])
        code, out = self.lanes("close")
        self.assertEqual(code, 0, out)
        self.assertEqual(out.count("closed"), 3)
        self.assertEqual(len(self.git("worktree", "list").stdout.splitlines()), 1)
        self.assertNotIn("fyzxsflow-lanes", self.git("branch").stdout)

    def test_a_replanned_run_never_rebuilds_a_done_package(self):
        self.plan()
        wp1 = self.run / "work-packages" / "WP-01-x.md"
        wp1.write_text(wp1.read_text(encoding="utf-8").replace("status: planned", "status: done"), encoding="utf-8")
        self.commit_all()
        self.assertIn("wave 1: WP-01 (done), WP-02, WP-03 (parallel, 2 at a time)",
                      self.py("waves.py", "check", "--run", str(self.run))[1])
        code, out = self.lanes("open", "--wave", "1")
        self.assertEqual(code, 0, out)
        self.assertIn("done WP-01", out)
        self.assertEqual(sorted(self.opened(out)), ["WP-02", "WP-03"])

    def test_a_conflict_the_plan_missed_falls_back_to_series(self):
        self.plan()
        self.commit_all()
        lanes = self.opened(self.lanes("open", "--wave", "1")[1])
        self.build_in(lanes["WP-01"], "src/shared.py", "# from WP-01\n")
        self.build_in(lanes["WP-02"], "src/shared.py", "# from WP-02\n")
        self.build_in(lanes["WP-03"], "src/c.py", "# c\n")
        code, out = self.lanes("merge", "--wave", "1")
        self.assertEqual(code, 1, out)
        self.assertIn("merged WP-01", out)
        self.assertIn("conflict WP-02: merge aborted; re-run WP-02 in series", out)
        self.assertIn("merged WP-03", out)
        self.assertEqual(self.git("status", "--porcelain").stdout.strip(), "")  # nothing half-merged
        self.assertIn("conflict", self.lanes("status")[1])

    def test_a_lane_with_uncommitted_work_is_not_merged(self):
        self.plan()
        self.commit_all()
        lanes = self.opened(self.lanes("open", "--wave", "1")[1])
        (pathlib.Path(lanes["WP-01"]) / "src" / "a.py").write_text("# unsaved\n", encoding="utf-8")
        code, out = self.lanes("merge", "--wave", "1")
        self.assertEqual(code, 1)
        self.assertIn("skipped WP-01: uncommitted in its lane: src/a.py", out)
        self.assertIn("skipped WP-02: nothing committed in its lane", out)
        self.assertIn("kept WP-01: still open", self.lanes("close")[1])

    def test_lanes_refuse_a_dirty_checkout_or_a_broken_plan(self):
        self.plan()
        self.commit_all()
        (self.root / "src" / "a.py").write_text("# local edit\n", encoding="utf-8")
        code, out = self.lanes("open", "--wave", "1")
        self.assertEqual(code, 1)
        self.assertIn("uncommitted changes a lane would not see", out)
        self.git("checkout", "src/a.py")
        self.wp("WP-02", ["src/a.py"])
        self.commit_all("overlap")
        self.assertIn("fix the plan first", self.lanes("open", "--wave", "1")[1])


class RunWorktreeTests(ParallelBase):
    def test_a_run_gets_its_own_worktree_and_list_finds_it(self):
        (self.root / "README.md").write_text("x\n", encoding="utf-8")
        shutil.rmtree(self.root / ".fyzxsflow" / "runs")
        self.commit_all("base")
        code, out = self.py("run.py", "new", "--source", "prompt", "--ref", "second thing", "--worktree",
                            "--root", str(self.root))
        self.assertEqual(code, 0, out)
        run = pathlib.Path(out.strip().splitlines()[-1])
        self.assertTrue(str(run).startswith(str(self.tmp / "repo.runs")), run)
        self.assertEqual(self.git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip(), "main")  # untouched
        self.assertIn("worktree: ", (run / "input.md").read_text(encoding="utf-8"))
        code, out = self.py("run.py", "list", "--root", str(self.root))
        self.assertIn("active: 1", out)
        self.assertIn(f"(worktree {self.tmp / 'repo.runs'}", out)

    def test_runner_locks_are_shared_by_every_checkout(self):
        self.commit_all("base")
        other = self.tmp / "other"
        self.git("worktree", "add", "-q", "-b", "other", str(other), "HEAD")
        self.assertEqual(runner.lock_dir(self.root), runner.lock_dir(other))


if __name__ == "__main__":
    unittest.main()

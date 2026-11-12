"""Tests for parallel work: engine/waves.py, engine/lanes.py, run.py new --worktree, and shared Runner locks."""

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
        self.assertIn("groups WP-01 and WP-02 may build at the same time but both change src/shared.py", out)
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

    def done(self, wp_id):
        f = next((self.run / "work-packages").glob(f"{wp_id}-*.md"))
        f.write_text(f.read_text(encoding="utf-8").replace("status: planned", "status: done"), encoding="utf-8")

    def test_problems_naming_only_done_packages_are_info(self):
        self.wp("WP-01", ["src/a.py"])
        self.wp("WP-02", ["src/b.py"], deps=["WP-01"], reasons={})
        self.done("WP-01")
        self.done("WP-02")
        self.wp("WP-03", ["src/c.py"], deps=["WP-02"])
        code, out = self.waves()
        self.assertEqual(code, 0, out)
        self.assertIn("info (done packages, left as they are): WP-02: depends_on WP-01 with no reason", out)

    def test_a_package_whose_dependencies_are_done_is_in_the_first_wave(self):
        self.wp("WP-01", ["src/a.py"])
        self.wp("WP-02", ["src/b.py"], deps=["WP-01"])
        self.wp("WP-03", ["src/c.py"], deps=["WP-02"])
        self.wp("WP-04", ["src/d.py"], deps=["WP-01"])
        self.done("WP-01")
        self.done("WP-02")
        code, out = self.waves()
        self.assertIn("done: WP-01, WP-02", out)
        self.assertIn("wave 1: WP-03, WP-04 (parallel, 2 at a time)", out)

    def test_related_packages_share_a_group_and_may_share_files(self):
        self.wp("WP-01", ["src/shared.py"])
        self.wp("WP-02", ["src/shared.py"], deps=["WP-01"])
        for wp in ("WP-01", "WP-02"):
            f = self.run / "work-packages" / f"{wp}-x.md"
            f.write_text(f.read_text(encoding="utf-8").replace("status: planned", "status: planned\npr_group: export"),
                         encoding="utf-8")
        code, out = self.waves()
        self.assertEqual(code, 0, out)
        self.assertIn("group export: WP-01, WP-02; after nothing", out)


FAKE_GH = """#!/bin/sh
echo "gh $*" >> "{log}"
case "$1 $2" in
  "pr create") n=$(( $(cat "{counter}" 2>/dev/null || echo 0) + 1 )); echo $n > "{counter}"
               echo "https://github.com/acme/shop/pull/$n" ;;
  "pr view") cat "{state}/$3" 2>/dev/null || echo '{{"state": "OPEN", "isDraft": true}}' ;;
esac
exit 0
"""


class LanesTests(ParallelBase):
    def lanes(self, *args):
        return self.py("lanes.py", *args, "--run", str(self.run))

    def build_in(self, path, rel, text):
        (pathlib.Path(path) / rel).write_text(text, encoding="utf-8")
        self.git("add", rel, cwd=path)
        self.git("commit", "-qm", f"work on {rel}", cwd=path)

    def opened(self, out):
        return {l.split()[1]: l.split()[2] for l in out.splitlines() if l.startswith("lane ")}

    def cap(self, n):
        cfg = json.loads((self.root / ".fyzxsflow" / "config.json").read_text())
        cfg["build"]["max_parallel"] = n
        (self.root / ".fyzxsflow" / "config.json").write_text(json.dumps(cfg), encoding="utf-8")

    def test_local_mode_starts_each_group_as_soon_as_its_dependencies_merge(self):
        self.plan()
        self.cap(2)
        self.git("switch", "-q", "-c", "fyzxsflow/run")
        self.commit_all()
        code, out = self.lanes("open")
        self.assertEqual(code, 0, out)
        lanes = self.opened(out)
        self.assertEqual(sorted(lanes), ["WP-01", "WP-02"])
        self.assertIn("queued WP-03", out)
        self.assertIn("waiting WP-04 on WP-01, WP-02", out)
        ship = self.py("run.py", "ship-check", str(self.run))[1]
        self.assertIn("group-prs        open      NO  not yet completed into the run branch: WP-01 (open)", ship)
        self.build_in(lanes["WP-01"], "src/a.py", "# a, built\n")
        self.build_in(lanes["WP-02"], "src/b.py", "# b, built\n")
        code, out = self.lanes("merge")
        self.assertEqual(code, 0, out)
        self.assertEqual(out.split(), ["merged", "WP-01", "merged", "WP-02"])
        lanes = self.opened(self.lanes("open")[1])
        self.assertEqual(sorted(lanes), ["WP-03", "WP-04"])  # WP-04 doesn't wait for WP-03's wave
        self.build_in(lanes["WP-04"], "src/d.py", "# d\n")
        self.build_in(lanes["WP-03"], "src/c.py", "# c\n")
        self.assertEqual(self.lanes("merge")[0], 0)
        self.assertIn("build(20261112-000000-x): WP-04", self.git("log", "--format=%s").stdout)
        self.assertIn("group-prs        completed ok  4 group(s) completed",
                      self.py("run.py", "ship-check", str(self.run))[1])
        code, out = self.lanes("close")
        self.assertEqual(out.count("closed"), 4, out)
        self.assertEqual(len(self.git("worktree", "list").stdout.splitlines()), 1)

    def test_pr_mode_waits_for_the_owner_to_complete_a_group_pr(self):
        self.plan()
        bare = self.tmp / "remote.git"
        subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
        self.git("remote", "add", "origin", "https://github.com/acme/shop.git")
        self.git("remote", "set-url", "--push", "origin", str(bare))
        self.git("config", "remote.origin.url", str(bare))  # fetch from the bare too
        (self.root / ".fyzxsflow" / "profile.md").write_text("- PR host: github\n", encoding="utf-8")
        self.git("switch", "-q", "-c", "fyzxsflow/run")
        self.commit_all()
        bindir, log, states = self.tmp / "bin", self.tmp / "gh.log", self.tmp / "states"
        bindir.mkdir()
        states.mkdir()
        (bindir / "gh").write_text(FAKE_GH.format(log=log, counter=self.tmp / "n", state=states), encoding="utf-8")
        (bindir / "gh").chmod(0o755)
        old = os.environ["PATH"]
        os.environ["PATH"] = f"{bindir}{os.pathsep}{old}"
        try:
            lanes = self.opened(self.lanes("open")[1])
            self.assertIn("nothing committed", self.lanes("pr", "--group", "WP-01")[1])
            self.build_in(lanes["WP-01"], "src/a.py", "# a, built\n")
            code, out = self.lanes("pr", "--group", "WP-01")
            self.assertEqual(code, 0, out)
            self.assertIn("draft WP-01 https://github.com/acme/shop/pull/1", out)
            calls = log.read_text()
            self.assertIn("gh pr create --draft --base fyzxsflow/run --head fyzxsflow-lanes/20261112-000000-x/WP-01",
                          calls)
            self.assertIn("published WP-01", self.lanes("pr", "--group", "WP-01", "--publish")[1])
            self.assertIn("gh pr ready 1", log.read_text())
            self.assertIn("kept WP-01: its PR is still open", self.lanes("close")[1])
            self.assertIn("waiting WP-04 on WP-01, WP-02", self.lanes("status")[1])
            # the owner completes WP-01's PR on the host: its commit lands on the remote run branch
            subprocess.run(["git", "push", "-q", str(bare), "fyzxsflow-lanes/20261112-000000-x/WP-01:fyzxsflow/run"],
                           cwd=self.root, check=True)
            (states / "1").write_text('{"state": "MERGED", "isDraft": false}', encoding="utf-8")
            code, out = self.lanes("refresh")
            self.assertEqual(code, 0, out)
            self.assertIn("WP-01: published -> completed", out)
            self.assertIn("pulled", out)
            self.assertEqual((self.root / "src" / "a.py").read_text(), "# a, built\n")
            self.assertIn("waiting WP-04 on WP-02", out)
            self.assertIn("closed WP-01 (completed)", self.lanes("close")[1])
            self.assertNotIn("gh pr merge", log.read_text())  # the engine never completes a PR
        finally:
            os.environ["PATH"] = old

    def test_group_prs_on_azure_devops_go_through_az(self):
        self.plan()
        bare = self.tmp / "remote.git"
        subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
        self.git("remote", "add", "origin", str(bare))
        (self.root / ".fyzxsflow" / "profile.md").write_text("- PR host: azure\n", encoding="utf-8")
        self.git("switch", "-q", "-c", "fyzxsflow/run")
        self.commit_all()
        bindir, log = self.tmp / "bin", self.tmp / "az.log"
        bindir.mkdir()
        (bindir / "az").write_text(f"""#!/bin/sh
echo "az $*" >> "{log}"
[ "$3" = "create" ] && echo '{{"pullRequestId": 9, "url": "https://dev.azure.com/acme/_git/shop/pullrequest/9"}}'
[ "$3" = "show" ] && echo '{{"status": "completed", "isDraft": false}}'
exit 0
""", encoding="utf-8")
        (bindir / "az").chmod(0o755)
        old = os.environ["PATH"]
        os.environ["PATH"] = f"{bindir}{os.pathsep}{old}"
        try:
            lanes = self.opened(self.lanes("open")[1])
            self.build_in(lanes["WP-02"], "src/b.py", "# b\n")
            code, out = self.lanes("pr", "--group", "WP-02", "--publish")
            self.assertEqual(code, 0, out)
            calls = log.read_text()
            self.assertIn("az repos pr create --draft true --source-branch fyzxsflow-lanes/20261112-000000-x/WP-02 "
                          "--target-branch fyzxsflow/run", calls)
            self.assertIn("az repos pr update --id 9 --draft false", calls)
            self.assertNotIn("--auto-complete", calls)
            self.assertIn("WP-02: published -> completed", self.lanes("refresh")[1])
        finally:
            os.environ["PATH"] = old

    def test_a_conflict_the_plan_missed_restarts_the_group(self):
        self.plan()
        self.git("switch", "-q", "-c", "fyzxsflow/run")
        self.commit_all()
        lanes = self.opened(self.lanes("open")[1])
        self.build_in(lanes["WP-01"], "src/shared.py", "# from WP-01\n")
        self.build_in(lanes["WP-02"], "src/shared.py", "# from WP-02\n")
        self.build_in(lanes["WP-03"], "src/c.py", "# c\n")
        code, out = self.lanes("merge")
        self.assertEqual(code, 1, out)
        self.assertIn("conflict WP-02", out)
        self.assertEqual(self.git("status", "--porcelain").stdout.strip(), "")
        self.assertIn("lane WP-02", self.lanes("open")[1])  # starts again on the merged branch

    def test_a_lane_with_uncommitted_work_is_not_merged(self):
        self.plan()
        self.git("switch", "-q", "-c", "fyzxsflow/run")
        self.commit_all()
        lanes = self.opened(self.lanes("open")[1])
        (pathlib.Path(lanes["WP-01"]) / "src" / "a.py").write_text("# unsaved\n", encoding="utf-8")
        code, out = self.lanes("merge")
        self.assertEqual(code, 1)
        self.assertIn("skipped WP-01: uncommitted in its lane: src/a.py", out)
        self.assertIn("skipped WP-02: nothing committed in its lane", out)
        self.assertIn("kept WP-01: its work isn't merged", self.lanes("close")[1])

    def test_lanes_refuse_a_dirty_checkout_or_a_broken_plan(self):
        self.plan()
        self.commit_all()
        (self.root / "src" / "a.py").write_text("# local edit\n", encoding="utf-8")
        code, out = self.lanes("open")
        self.assertEqual(code, 1)
        self.assertIn("uncommitted changes a lane would not see", out)
        self.git("checkout", "src/a.py")
        self.wp("WP-02", ["src/a.py"])
        self.commit_all("overlap")
        self.assertIn("fix the plan first", self.lanes("open")[1])

    def test_done_packages_are_never_built_again(self):
        self.plan()
        f = self.run / "work-packages" / "WP-01-x.md"
        f.write_text(f.read_text(encoding="utf-8").replace("status: planned", "status: done"), encoding="utf-8")
        self.commit_all()
        lanes = self.opened(self.lanes("open")[1])
        self.assertEqual(sorted(lanes), ["WP-02", "WP-03"])
        self.assertIn("waiting WP-04 on WP-02", self.lanes("status")[1])


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

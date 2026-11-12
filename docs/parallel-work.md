# Parallel work: a plan

Status: **built** and trialled; how to use it: [HOW-TO → Parallel work](../HOW-TO.md#parallel-work). Written 2026-11-12. Owner decisions: build all three parts; `build.max_parallel` defaults to 3.

## The ask (owner)
"As part of the work breakdown, identify what can be run in parallel, and how to do that effectively. This will
allow multiple parallel flows to execute and work to get completed faster. If something is series-dependent, we
run that in series."

## What exists today (checked in the code)
- Plan mode (`build-coordinator.agent.md`) orders packages with `depends_on` / `blocks` and forms **waves**: the
  packages that can run before any package that depends on them.
- Execute mode allows a wave's packages to run "in parallel only in separate worktrees whose base already holds
  every package they depend on; while that work is uncommitted, one after another". Nothing creates those
  worktrees, so **in practice every package runs in series**.
- Nothing checks a wave mechanically: two packages in one wave may change the same file, and `depends_on` cycles
  are not caught by a script.
- The Runner's mode locks (`"lock": "local-db"`) live under the checkout (`runs/_adhoc/locks/`), so two worktrees
  would not see each other's locks: parallel lanes could share a database unguarded.
- `run.py new` switches the one working tree to the run's branch, so **only one run can be active per checkout**.

## The design: series where it must be, parallel everywhere else
### 1. Plan: say what runs in parallel, and why the rest doesn't
The Build Coordinator's plan gains a **parallel plan**: per wave, its lanes (one package each), and for every
`depends_on` edge the reason it is series. Allowed reasons:
- **contract**: it consumes what the other produces (an interface, a schema, an API);
- **same file**: both change a file (the plan check refuses two packages in one wave that touch the same file);
- **shared resource**: both need a resource the Runner locks (a local database);
- **risk first**: a risky package (schema, shared contract, security) goes alone in an early wave, as today.

How to plan for parallelism:
- **Contract first.** Put the interface, schema or API shape in a small early package, so its consumers run in
  parallel in the next wave instead of in a chain.
- **Hotspot files last.** Files that every feature touches (route tables, dependency registration, a shared enum)
  go in one small **integration package** at the end, so they don't serialize everything else.
- **Balanced lanes.** A wave is as slow as its biggest package; split a large one along a green line.
- **Tests with their code.** Each lane's Tester works in that lane, so tests don't become a series tail.

`engine/waves.py check --run <run>` makes it mechanical. It computes the waves from `depends_on` (failing on a
cycle), fails when two packages in the same wave share a file in `scope`, warns when lanes of one wave both use a
locked Runner mode, and prints the wave table the plan report carries. It runs in Plan mode's check step, beside
`ac_trace.py`.

### 2. Build: lanes in worktrees
For each wave with more than one package:
1. `engine/lanes.py open --run <run> --wave <n>` creates one git worktree per package, out of the working tree
   (`.git/fyzxsflow-lanes/<run>/<WP>`, in the git common directory), on a branch `fyzxsflow/<run-id>/<WP>` cut from the run
   branch, which already holds every earlier wave.
2. The Orchestrator dispatches every lane at once (one message, several subagents). Each lane runs
   Implementer → Validator → Tester → Validator → done-check, inside its own worktree; reports still go to the
   main run folder. The Runner runs with `--root <lane>`.
3. `lanes.py merge --run <run> --wave <n>` merges the lanes into the run branch in plan order, one commit per
   package. A conflict stops that merge: the package is re-run on top of the merged result, in series, and a
   `replan` finding records why the plan missed it.
4. **No broken window across lanes:** after the merge, Runner `quick` on the run branch. A failure goes back to
   the packages whose files it touches.
5. `lanes.py close` removes the worktrees and lane branches.

Other parts:
- **Locks move** to the git common directory, so every lane, and every parallel run, sees the same Runner locks.
- **Reviews are unchanged:** one pause per wave, all its review files together.
- **Limits:** `config.json` → `build.max_parallel` (default 3), set for cost and machine load. A wave with more
  lanes runs them in batches. `1` turns parallel lanes off.
- Waves with one package run in place, as today.

### 3. Several runs at once
- **`run.py new --worktree`** gives a run its own worktree, so two requests can be in flight at once without
  switching each other's branch. `run.py list` shows where each one lives.
- **At Locate,** when the change map shows that a request is really two independent changes (no shared files,
  contracts or resources), the Code Indicator says so. The Orchestrator then asks the owner whether to split it
  into two runs that go in parallel, each with its own PR. It never splits on its own.
- Runs that share a lock wait for each other through the shared locks. A compaction run still refuses to start
  while any run is active.

## Pieces
- [x] `engine/waves.py` (waves, cycles, same-file and shared-lock checks) + tests
- [x] `engine/lanes.py` (open, status, merge, close) + tests on a real git repo
- [x] Runner: shared lock folder; `--root` per lane (exists)
- [x] `run.py new --worktree`; `run.py list` shows worktrees
- [x] `config.json` → `build.max_parallel` (+ readme)
- [x] Agents:
  - Build Coordinator: plan for parallelism, reasons on every series edge, `waves.py` in the check;
  - Orchestrator: lanes in Running Build, run splitting at Locate;
  - Code Indicator: say when a request splits;
  - `work-package.md` template: a reason per `depends_on` entry.
- [x] HOW-TO, README, design.md
- [x] Trial: a scratch app with three independent packages and one dependent one; lanes run in parallel, merge
      clean, a planted same-file overlap is caught by `waves.py`, and a planted conflict falls back to series.

## Trial (2026-11-12)
A scratch Python app with four packages: three independent (discount, tax, slug) and a checkout package that
depends on two of them. `waves.py check` gave `wave 1: WP-01, WP-02, WP-03 (parallel, 3 at a time) | wave 2:
WP-04`. `lanes.py open` made three worktrees, and three agents were dispatched at once, one per lane, each
running the Runner with `--root <lane>` and writing its report to the run folder. Each lane was committed by path,
`lanes.py merge` merged all three in plan order (one merge commit each), `quick` passed on the merged branch,
wave 2 came back `in place`, and `lanes.py close` removed the worktrees and lane branches. The engine tests also
cover a same-file overlap refused by `waves.py`, a conflict the plan missed falling back to series, uncommitted
lane work never being merged, a run in its own worktree, and Runner locks shared across checkouts.

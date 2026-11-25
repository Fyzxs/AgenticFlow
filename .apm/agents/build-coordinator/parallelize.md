# Build Coordinator: Parallelize mode

<!-- Part of build-coordinator.agent.md, kept in its own file so the agent file stays small enough to load in
     full. Read it before acting on these sections; it is the same authority as the agent file. -->

## Parallelize mode
For a run planned before parallel lanes existed, or planned too serially (`/fyzxsflow-parallelize`). You re-order
the existing plan; you don't re-plan it.
1. **Read** every package in `<run>/work-packages/` and `python -I .fyzxsflow/package/engine/waves.py check --run
   <run>`. Leave every package with `status: done` exactly as it is. If any package is `status: building`, stop:
   say which, and to run this once that package has finished.
2. **Keep only the dependencies that are real.** For each `depends_on` entry of a package not yet done, find its
   reason in the packages themselves, citing `path:line`:
   - `contract`: it uses something the other package creates or changes (a type, function, table, endpoint);
   - `same file`: both packages' `## Scope` change a file;
   - `shared resource`: both done-checks use a Runner mode with the same `lock` in `config.json`;
   - `risk first`: the other is a risky package (schema, shared contract, security) the plan put alone, early.
   Keep the entry and write its line under `## Series reasons`. An entry with no reason is plan order only: remove
   it, and remove the matching `blocks` entry on the other package.
3. **Add what is missing.** Two groups that could now build at the same time but change the same file, or where
   one uses what the other creates, get a dependency with its reason. A real dependency on a package already done is kept
   (it documents the contract) but changes nothing in the done package: no `blocks` entry there.
4. **Change nothing else.** Criteria, scope, context packs, contracts, flag plans and done-checks stay word for
   word, and so does every `pr_group`. Changes that would widen the waves further, or regroup the PRs (splitting a
   large package, a contract-first package, an integration package for hotspot files, splitting or joining PR
   groups), go in your report as proposals for the owner; none touches a package that is done.
5. **Check:** `waves.py check --run <run>` exits 0, and `python -I .fyzxsflow/package/engine/ac_trace.py --run
   <run>` shows no problem it didn't show before you started (run it first; a problem that was already there goes
   in your report's Risks, unfixed: it isn't yours in this mode). `git diff --stat -- <run>/work-packages` shows
   only the packages you meant to change.
6. **Report** in `<run>/reports/build-coordinator.parallelize.md` (report template, no criteria table): the wave
   table before and after, a row per dependency (`| Package | Depends on | Kept: reason, path:line | Removed: why
   |`), and the proposals. Bring the waves and dependencies `reports/build-coordinator.plan.md` lists in line with
   the new plan, in whatever form it has them; add no sections. Log it: `python -I
   .fyzxsflow/package/engine/run.py log <run folder> locate done "plan re-ordered for parallel lanes"`.

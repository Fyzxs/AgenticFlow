# Build Coordinator: Execute mode

<!-- Part of build-coordinator.agent.md, kept in its own file so the agent file stays small enough to load in
     full. Read it before acting on these sections; it is the same authority as the agent file. -->

## Execute mode
The Orchestrator dispatches you for this with the run folder; `continue` means pick up from the packages'
`status:` lines and the ledger. If you have no tool to dispatch agents, start nothing and return `no-dispatch`:
the Orchestrator then runs these steps in its own session. Stamping, review files and owner replies stay with the
Orchestrator; follow its **Models** section (escalation, model compare) on every dispatch.
Some steps may be done by the owner instead of the agent, when the Orchestrator says so; everything after the
step (validator, Runner, contract checks, tracing) is the same either way.
0. **Lanes, one per PR group.** `python -I .fyzxsflow/package/engine/lanes.py open --run <run>` pulls the completed
   group PRs into the run branch, then opens a lane (a worktree beside the run's checkout, `<checkout>-<group>`)
   for every group that may start now, up to `build.max_parallel`; it names the groups `queued` (no free lane) and
   `waiting` (on other groups). Dispatch every open lane's chain below at once (one message, one subagent per agent
   step, each dispatch starting `Worktree: <lane path>`: it works only there, writes its report to the run folder
   in that lane, and runs the Runner with `--root <lane>`). Commit each package in its
   lane, by path, from its reports' changed files, as soon as its done-check passes. Then:
   - **With PRs** (the `pr` step on): after a group's first commit, `lanes.py pr --run <run> --group <g>` opens its
     draft PR into the run branch; after each later commit, the same command pushes it. When the group's last
     package is done and its reviews are finished, `lanes.py sync --run <run> --group <g>` (merges the run branch
     into the lane; rerun the done-check if it says product files changed), then `lanes.py pr --run <run> --group
     <g> --publish --body-file <run>/pr-bodies/<g>.md`, a file the `pr-producer` writes from the group's reports
     (changes and evidence; dispatch it first, and again for every later update to the body): published
     means done and ready for the owner. Publishing refuses while the lane would conflict with the run branch. The
     owner completes it; never complete, merge or auto-complete a PR. Owner comments on it are reworked in the same
     lane and pushed to the same PR. `lanes.py refresh` names open lanes the moving run branch now conflicts with:
     `sync` them.
   - **Without PRs** (the `pr` step off, or no PR host): checkpoint the run folder first (`run.py checkpoint`, with
     no `run.py log` between it and the merge), then `lanes.py merge --run <run>` merges each finished group
     into the run branch in dependency order; then `runner.py quick --run <run>` on the run branch, so what merged
     is green together (a failure goes back to the group whose files it names).
   A `refused` group is not an overlap: commit what the message names and merge again. A `conflict` group starts
   again on top of the merged branch (`lanes.py open`), with a `replan` finding for the
   overlap the plan missed. Run `lanes.py open` again whenever a group completes, to start what it unblocked;
   `lanes.py close --run <run> [--group <g>]` removes finished lanes. When the owner holds a group, `lanes.py park
   --run <run> --group <g> --reason "<their words>"` keeps its work on a parked branch, closes only that lane and
   marks its packages `status: deferred` (their dependents wait; `unpark` brings it back). Findings, the ledger
   and reviews merge between lanes by themselves (merge drivers lanes.py registers), and finding ids never collide:
   never renumber or merge them by hand.
1. **Each package of a group**, in plan order, in the group's lane. **Every dispatch below goes through the
   engine:** `python -I .fyzxsflow/package/engine/run.py dispatch <run> --wp <WP-nn> --role <role> [--target
   <agent>] --worktree <lane>` writes the dispatch file, and the subagent's whole prompt is the line it prints
   ("Read <file> and follow it."). Never write a dispatch prompt by hand, and never hand one role's criteria to
   another: the implementer and the tester are always separate dispatches. A `--note` adds context only.
   1. `python -I .fyzxsflow/package/engine/run.py package-status <run> --wp <WP-nn> --status building`;
      `python -I .fyzxsflow/package/engine/run.py log <run> build started "<stem>: implementer"`;
   2. `implementer` (`iac-implementer`, with the IaC context pack, for pipelines and infrastructure), given the
      package path and told to run its done-check through `runner.py`; then `validator` on it (the
      package, its context pack, the changed files, the report);
   3. `tester`, given the package, the implementer's and its validator's reports and the changed files; then
      `validator` on it;
   4. the Build & Test Runner, for each `Runner:` line of the done-check;
   5. the contract checks: open both sides of each seam and compare them with the package's `## Contract`;
   6. `ac_trace.py --run <run> --require-evidence`: no `FAIL` line may name this package's criteria (other
      packages' lines are expected); a missing or malformed row goes back to the agent that owns the criterion;
   7. `run.py package-status <run> --wp <WP-nn> --status done`; `run.py log <run> build done "<stem>: done-check
      <result>"`. The engine refuses `done` until the maker, the tester (a separate dispatch) and a Validator pass
      on each have reports, stamped, and one of them cites a passing `runner/<id>.json`; it names what's missing.
      Run the missing step. Only the owner may accept a package without it (`--override "<their words>"`).
   Before steps 3 and 4 run `python -I .fyzxsflow/package/engine/review.py needed --run <run> --agent <the agent
   whose output you hand on> --stage build --package <WP-nn> --segment <segment> --paths <changed files>`. On
   `review=pause` with an `always:` or `run-request:` reason, or `- pause: each` in `review-requests.md`, stop that
   group at that hand-off for the owner (its tester waits); other groups go on.
2. **What comes back:**
   - Validator `fail`: re-dispatch the agent with the validator's report. A second fail: `python -I
     .fyzxsflow/package/engine/models.py <agent> --up 1`, re-dispatch on that model, log an `escalation` finding;
     `capped=yes` stops that group.
   - Runner `code` failure: back to the agent owning the file, with the summary path; after 2 rounds stop that
     group. Exit 3 (destructive steps refused) stops it for the owner. Exit 4 (locked): wait, then rerun.
   - `replan` stops the build. `scope-request`: grant it only when the file is in no other package's scope and serves
     this package's criteria (`findings.py amend <F-n> --run <run> --note "granted: <why>"`, then `lanes.py grant
     --run <run> --group <g> --path <the file>` so the hook lets the lane change it); else stop that group.
3. **Each group's end** (and whenever no group can go on): update your report; return each hand-off in order: stem, agent, report path, `review_file`
   (`run.py packages <run> --current <WP-nn> --agent <agent>`), validator verdict, `review.py needed` answer.
4. **Rework** (a redo, review findings, Runner or gate kick-backs): set the package back to `building` and re-run
   it from the agent named, with every step after it. Reports are updated in place.
5. **Close-out** (once every group is completed into the run branch, and again when the Orchestrator asks after ci, Prove or review fixes): for
   every live brief criterion and every package criterion, open the evidence (the cited line, the Runner or gate
   summary, the proof log) and write its row. A criterion only Prove can show stays `partial` until then.

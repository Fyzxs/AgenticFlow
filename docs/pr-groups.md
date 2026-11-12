# PR groups into the run branch, one roll-up PR to the default branch

Status: **built** (0.3.0). Written 2026-11-12, from the owner's suggestion (a prompt written in another session) with
the amendments below.

## The ask (owner, verbatim)
"We can do work earlier; and it can have it's OWN PR. Let's not bundle PRs just cause the work is parallal. If the
work is distinct; it should get it's own PR. Related work can go into the same PR, or we can have them all as their
own PRs into the 'work product branch' and then that final branch does them all into main." Decision: "group PRs go
into the run branch, and that run branch is PRd into main."

## The design
- **Groups.** Each work package names its PR group (`pr_group:` in frontmatter, default: its own id). Packages share
  a group only when one can't be reviewed without the other; the plan report says why. The plan gate shows the
  groups beside the waves.
- **Dependency order is PR order.** A group starts when every group it depends on has its PR **completed** into the
  run branch (merged locally when there are no PRs). It never waits for a wave or an unrelated group. Waves stay as
  a planning view.
- **Lanes are per group.** `lanes.py open` cuts each ready group's lane from the run branch, after pulling the
  completed group PRs from the remote. `lanes.py pr` pushes the lane and opens or updates its draft PR into the run
  branch. `--publish` un-drafts it when the group's done-check is green and its reviews are finished. `lanes.py
  refresh` reads each PR's state from the host. `close` removes only lanes whose PR is completed or abandoned. The
  engine never completes a PR and never sets auto-complete.
- **The owner reviews on the PR.** The always-review areas still pause that group before its tester; everything
  else reaches the owner as its published group PR. Owner comments are handled on that group's lane and pushed to
  the same PR.
- **The roll-up.** When every group PR is completed and the run's checks pass on the run branch, `pr.py` opens one
  PR from the run branch into the default branch, listing the group PRs; it is published by `pr.py ready` after
  ship-check, as before. ship-check gains a `group-prs` row: no group PR still open.

## Amendments to the suggestion
1. **Pull before cutting.** Completed group PRs merge on the remote run branch, while the run folder's checkpoints
   are committed on the local one. `lanes.py open` (and `refresh`) fetch the remote run branch and merge it into the
   local one first, so a new lane sees every dependency.
2. **The run branch is pushed** before the first group PR, since the group PRs target it.
3. **Waiting (owner):** when everything left waits on PRs the owner hasn't completed, the run logs "waiting on PR
   completion" with the links and stops. `/flow resume` refreshes the PR states and continues with whatever is now
   unblocked.
4. **No PRs (owner):** with the `pr` step off, or no PR host, lanes merge locally into the run branch in dependency
   order (`lanes.py merge`), as before.

## Pieces
- [x] `waves.py`: `pr_group`, group dependencies and cycles, ready groups; problems that name only done packages are
      info, not failures
- [x] `lanes.py`: per-group lanes; open (pull first), pr (+ --publish), refresh, status, merge (local mode), close
- [x] `pr.py`: roll-up body lists the group PRs; ship-check `group-prs` row
- [x] Agents and docs: orchestrator (Running Build, review pauses, Commits, The draft PR, Deliver), build
      coordinator (groups in Plan and Parallelize modes, Execute step 0), PR Producer, role-contracts, run-folder,
      work-package template, config readme, HOW-TO, README, design.md; no stale "once per wave", "wave PR",
      "lanes.py merge" (outside local mode) or "one PR per run"
- [x] Version 0.3.0, CHANGELOG.md
- [x] Tests: group PR commands against stubbed gh/az, readiness by completed PR, done-package problems ignored,
      close refusing an open PR, pull-before-cut

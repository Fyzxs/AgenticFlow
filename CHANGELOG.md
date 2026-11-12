# Changelog

## 0.3.0 (2026-11-12)
The installed `INSTALLED.json` said 0.2.0 across every change below; from here each release bumps the version.

- **PR groups and a roll-up PR.** Each distinct piece of work gets its own PR into the run branch (related work may
  share one; building in parallel never bundles). It opens as a draft with its first commit and is published when
  its group is done; the owner completes it. A group starts as soon as the groups it depends on are completed,
  never waiting for a wave. When every group PR is completed, the run branch gets one roll-up PR into the default
  branch, published only when `ship-check` says ready. The engine never completes or auto-completes a PR.
  (`lanes.py open | pr | refresh | status | merge | close`, `pr.py`, ship-check `group-prs`.)
- **The PR is the run's own branch.** Every commit ships, the run's record included.
- **Parallel work.** Lanes in git worktrees (`build.max_parallel`, default 3), `waves.py` (series reasons, file
  overlap between groups that may build together, cycles; done packages count as built and their old problems are
  info), Runner locks shared across checkouts, `run.py new --worktree`, offering to split a request into parallel
  runs, and `/fyzxsflow-parallelize` to re-order an existing plan.
- **Preceptee mode** (off by default; `/flow --preceptee`, or the `precept` step for a project): the engineer
  writes the code and the Preceptor reviews their PRs like a senior engineer, broad to specific (`preceptee.py
  comment | activity`), and coaches in the session; the record stays on their machine. Only the Seeder agent plants
  practice flaws, in preceptee mode, outside the repo; every role is forbidden to plant a mistake. See PRECEPTEE.md.
- **Compactor** (`/fyzxsflow-compact`): shrinks agent files, learned entries and docs without losing a rule
  (`compact.py`, overlays in `.fyzxsflow/compacted/`).
- Slash commands load their agent's Learned entries.

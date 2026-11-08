# Review: <agent> — <WP-04>: <package title, or the stage name>

**Where we are:** Package <n> of <N>: <segment, what this package delivers in plain words>.
Done: <WP-01, WP-02, ... or none yet>. Next: <the next step: this package's tester, or WP-05: its title>.
<!-- Package reviews: copy the where/done/next_package lines from
     `python -I .agentflow/engine/run.py packages <run> --current <WP-n> --agent <agent>`, and name this file
     with the review_file it prints (reviews/<package file stem>.<agent>.md), never the bare id.
     Stage reviews: reviews/<stage>.<agent>.md; say which stage and what comes after it. -->

<!-- Written by the Orchestrator when review.py needed says pause. Committed with the checkpoint, so the
     owner can read it, and the files it lists, in the repo or the PR. -->

**What to look at**
- `<path>` — <one line on what it is>

**Changes since the last checkpoint:** `git diff <checkpoint>..HEAD -- <paths>` (or open the files above)

**Validator verdict:** <pass | corrected | fail>, findings: <F-n ...>

**Acceptance criteria this output is responsible for**
| Criterion | Status | Evidence |
|---|---|---|

**Reply with one of**
- `approve` — continue
- `continue` — after editing any of the files above (your edits are picked up and recorded)
- `redo: <what's wrong>` — the agent re-runs with your note
- `stop` — abandon the run

Add `-less-review` or `-more-review` to any reply to change how closely **<agent>** is reviewed from now on
(current level: **<level>**; levels: on → notify → off).

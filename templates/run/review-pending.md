# Review: <agent> — <WP-04>: <package title, or the stage name>

**Where we are:** Package <n> of <N>: <segment, what this package delivers in plain words>.
Done: <WP-01, WP-02, ... or none yet>. Next: <the next step: this package's tester, or WP-05: its title>.
<!-- Package reviews: copy the where/done/next_package lines from
     `python -I .agentflow/engine/run.py packages <run> --current <WP-n> --agent <agent>`, and name this file
     with the review_file it prints (reviews/<package file stem>.<agent>.md), never the bare id.
     Stage reviews: reviews/<stage>.<agent>.md; say which stage and what comes after it. -->

<!-- Written by the Orchestrator when review.py needed says pause. Committed with the checkpoint, so the
     owner can read it, and the files it lists, in the repo or the PR. -->

**Your feedback, applied** <!-- only when feedback was routed since your last review: each item (review
     feedback F-n, or an inbox file), what was done with it and where (doc path, package, queued run), or why
     not. Approve or redo it with this review. Omit the block when there is none. -->
- <F-n / feedback/<file>> → <docs: `.agentflow/docs/...` (what the rule now says) | agent input: WP-n | rework: WP-n | queued run | this output only: why>

**Done by:** <agent> on <model from the report's frontmatter> (tier <tier>; the agent reported
<model_reported>; escalated: <escalated>). The validator ran on <its model>.

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
- `redo: <what's wrong>` — the agent re-runs with your note (and anything you wrote under Human Feedback)
- `stop` — abandon the run

Add `-less-review` or `-more-review` to any reply to change how closely **<agent>** is reviewed from now on
(current level: **<level>**; levels: on → notify → off).

## Human Feedback
<!-- Write anything here, any length, before you reply: corrections, conventions, context. It is recorded with
     your reply whatever you answer and acted on (docs updated, agents told, rework planned); you approve the
     result in your next review. With approve it applies from the next agent on; with redo it also fixes this
     output. Leave it empty for none. Feedback not about this review goes in .agentflow/feedback/. -->
<write feedback here>

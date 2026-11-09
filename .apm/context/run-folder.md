# The run folder

Every run lives in its own folder. It is the only channel between agents: each agent is handed paths into
it and writes its output back into it. `.fyzxsflow/package/engine/run.py new` creates it.

```
.fyzxsflow/runs/
  active/<run-id>/       work in flight; the only runs the Orchestrator resumes
  completed/<run-id>/    a PR was delivered (run.py close --outcome completed --note "<PR>")
  abandoned/<run-id>/    stopped before a PR, with the reason in the ledger (--outcome abandoned)
```

`.fyzxsflow/` holds only the project's own files (config, profile, docs, feedback, runs, `learned/` agent
entries); `.fyzxsflow/package/` is the installed FyzxsFlow package, replaced by every install: read it, never
write to it. Beside the runs, `.fyzxsflow/feedback/` is the owner's inbox: any file, any time, read by the Orchestrator
at every run start and hand-off (`.fyzxsflow/package/engine/feedback.py`). Handled items move to `feedback/done/`.

```
<run-id>/
  input.md             the raw request: prompt text, or the work item id, with the run's working branch, base commit
                       and base branch in its frontmatter (run.py new); the Work Summarizer appends the fetched
                       items under "## Fetched work items"
  brief.md             Work Summarizer output (.fyzxsflow/package/templates/run/brief.md)
  change-map.md        Code Indicator output (.fyzxsflow/package/templates/run/change-map.md)
  work-packages/       Build Coordinator plan: one file per package (.fyzxsflow/package/templates/run/work-package.md)
    WP-01-<segment>-<what>.md    e.g. WP-04-api-orders-export-contract.md (status: in frontmatter)
  reports/             one report per agent invocation (.fyzxsflow/package/templates/run/report.md); each records
                       its tier, dispatched model and self-reported model (run.py stamp / run.py models)
    work-summarizer.md, code-indicator.md          Intake, Locate
    build-coordinator.plan.md                      the plan: packages with their waves, contract checks
    WP-01.implementer.md, WP-01.tester.md          per package (WP-01.iac-implementer.md for IaC)
    WP-01.validator.implementer.md                 a Validator on <target>: <id>.validator.<target>.md
    build-coordinator.execute.md                   Build's close-out: every criterion traced to evidence
    ci.runner.md, prove.http-generator.md, prove.runner.md, gates.<stage>.md
    review.narrow.md (review.<lens>.md)            one per reviewer
    pr-producer.md, pr-reviewer.md                 Deliver
    feedback-<F-n|item>.docs-gardener.md           Docs Gardener, feedback mode; deliver.docs-gardener.md after-run (in Deliver)
    curator.md                                     Learn
  pr-description.md    the PR Producer's description (the PR body), read by the PR Reviewer and the owner's gate
  runner/              Build & Test Runner summaries (<invocation>.json); raw logs in <invocation>/ stay local
  gates/               Gate Analyst summaries (<invocation>.json); raw tool output in <invocation>/ stays local
  findings.jsonl       every finding from every agent (.fyzxsflow/package/engine/findings.py)
  compare.jsonl        model-compare records, when compare is enabled (.fyzxsflow/package/engine/compare.py)
  review-requests.md   the owner's review requests for this run (editable any time)
  steps.json           this run's step overrides ({"off": [...], "on": [...]}), written only by steps.py set --run;
                       steps.jsonl logs each change with the owner's words
  reviews/             one file per hand-off, whatever the review level (.fyzxsflow/package/templates/run/review-pending.md;
                       "Reply needed: yes" only when the run paused), named <package file stem>.<agent>.md or
                       <stage>.<agent>.md (run.py packages); the owner writes in its ## Human Feedback section,
                       before replying or any time later, recorded as an owner-feedback finding.
                       .feedback-seen.json remembers what was recorded (feedback.py), so edits are picked up again
  reviews.jsonl        every review decision, with -less-review/-more-review level changes (.fyzxsflow/package/engine/review.py)
  reports/shadow/      shadow outputs from model compares; never used by the run
  ledger.md            heartbeat: one line per stage transition (.fyzxsflow/package/engine/run.py log)
  .gitignore           keeps raw logs out of git
```

## Kept in git, and editable by the owner
- By default (`.fyzxsflow/profile.md` → `Runs: commit`) every run is committed. `run.py checkpoint <run>
  <stage>` commits **only** the run folder at the end of each stage, so the brief, plan, reports, findings
  and summaries can be reviewed in history and in the PR. `Runs: local` turns this off.
- The owner may edit any artifact between stages, for example tightening an acceptance criterion or
  reshaping a work package. The next stage reads the edited file.
- `run.py edits <run> --record` at the start of each stage (and on resume) finds every change since the
  last checkpoint, logs it in the ledger, writes a `human-edit` finding per file and checkpoints it. The
  Curator diffs each edit against the agent's version: it is the most direct signal of what an agent got
  wrong.

## Rules
- Files are append-or-replace by their owner only. An agent never edits another agent's report.
- `ledger.md` is the status. Anyone asking "where is this run?" reads its last lines; `run.py list` shows
  every active run.
- A run resumes from the ledger: the Orchestrator finds the last completed stage and continues.
- Only `run.py close` moves a run out of `active/`, so the move is one recorded commit.

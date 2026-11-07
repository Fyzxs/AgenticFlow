# The run folder

Every run lives in its own folder. It is the only channel between agents: each agent is handed paths into
it and writes its output back into it. `.agentflow/engine/run.py new` creates it.

```
.agentflow/runs/
  active/<run-id>/       work in flight; the only runs the Orchestrator resumes
  completed/<run-id>/    a PR was delivered (run.py close --outcome completed --note "<PR>")
  abandoned/<run-id>/    stopped before a PR, with the reason in the ledger (--outcome abandoned)
```

```
<run-id>/
  input.md             the raw request: prompt text, or the work item id and its fetched content
  brief.md             Work Summarizer output (.agentflow/templates/run/brief.md)
  change-map.md        Code Indicator output (.agentflow/templates/run/change-map.md)
  work-packages/       Build Coordinator plan: one file per package (.agentflow/templates/run/work-package.md)
    WP-01-<segment>.md
  reports/             one report per agent invocation (.agentflow/templates/run/report.md)
    WP-01.implementer.md
    WP-01.tester.md
    WP-01.validator.implementer.md
    review.narrow.md
  runner/              Build & Test Runner summaries (<invocation>.json); raw logs in <invocation>/ stay local
  gates/               Gate Analyst summaries (<invocation>.json); raw tool output in <invocation>/ stays local
  findings.jsonl       every finding from every agent (.agentflow/engine/findings.py)
  compare.jsonl        model-compare records, when compare is enabled (.agentflow/engine/compare.py)
  reports/shadow/      shadow outputs from model compares; never used by the run
  ledger.md            heartbeat: one line per stage transition (.agentflow/engine/run.py log)
  .gitignore           keeps raw logs out of git
```

## Kept in git, and editable by the owner
- By default (`.agentflow/profile.md` → `Runs: commit`) every run is committed. `run.py checkpoint <run>
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

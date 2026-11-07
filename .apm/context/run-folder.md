# The run folder

Every run lives in `.agentflow/runs/<run-id>/`. It is the only channel between agents: each agent is
handed paths into it and writes its output back into it. `.agentflow/engine/run.py new` creates it.

```
.agentflow/runs/<run-id>/
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
  runner/              Build & Test Runner logs and summaries, one per invocation
  findings.jsonl       every finding from every agent (.agentflow/engine/findings.py)
  ledger.md            heartbeat: one line per stage transition (.agentflow/engine/run.py log)
```

## Rules
- Files are append-or-replace by their owner only. An agent never edits another agent's report.
- `ledger.md` is the status. Anyone asking "where is this run?" reads its last lines.
- A run resumes from the ledger: the Orchestrator finds the last completed stage and continues.
- Runs are working state. A project decides in `.agentflow/profile.md` whether to keep them in git.

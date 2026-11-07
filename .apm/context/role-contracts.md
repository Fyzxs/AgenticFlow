# Role contracts

Every agent in agentflow is exactly one of these roles. An agent file states its role in its first
section and follows that role's contract.

## Implementor
1. Read the files it was given, and only those (plus what they point to).
2. Do the work.
3. Write a report to the run folder: what changed, what was assumed, what it could not do.

## Validator
1. Read the target agent's file, the target's inputs, and the target's output.
2. Act as that agent: work out what a correct execution would have produced **before** reading the
   output closely, so the output doesn't anchor the judgment.
3. Correct the output where the correction stays inside the target's scope.
4. Log every miss as a finding, classified (see `findings-schema.md`).

## Reviewer
1. Read the diff plus its own rules and docs.
2. Review.
3. **Make no changes.**
4. Write findings, each with `file:line` evidence and a severity.

## Runner
1. Know how to start, build and test the system, from `.agentflow/config.json`.
2. Run the requested mode through `.agentflow/engine/runner.py`.
3. Trust only exit codes and counts, never output text.
4. Classify each failure and route it.
5. It is the only agent that runs builds or tests. (Linters and scanners run through the Gate Analyst
   and `.agentflow/engine/gates.py`; nobody else runs tools directly.)

## Coordinator
- **Orchestrator:** dispatches stages, hands off files, keeps the ledger, enforces caps and gates.
- **Build Coordinator:** plans work packages (Locate) and executes them in dependency order (Build).
- **Curator:** turns findings into agent and doc patches.

## Rules for every role
- **No acceptance criteria, no implementation.** Work is implemented only against numbered acceptance
  criteria (brief `AC-n`, package `WP-xx.n`). They are the checks and the end state. An implementor
  reports every criterion it was responsible for as met / not met / partial, with evidence.
- **Deterministic first.** Anything a tool can decide (build, test, lint, scan, traceability) is decided
  by a script with an exit code: `.agentflow/engine/runner.py`, `.agentflow/engine/gates.py`, `.agentflow/engine/ac_trace.py`,
  `.agentflow/engine/docs_check.py`. Agents interpret results; they never overrule an exit code.
- Never ask the invoker a question mid-task. Record the assumption in the report and continue. Only the
  Orchestrator raises questions to the owner, and only at a gate.
- Never run builds or tests yourself; ask the Build & Test Runner.
- Stay inside your scope. Need something outside it? Report a `scope-request` finding.
- Cite evidence as `path:line`. A claim without a location is not a finding.
- Write your report even when you fail. A failed run with a good report is useful; a silent one is not.

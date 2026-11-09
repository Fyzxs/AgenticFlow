# Role contracts

Every agent in FyzxsFlow is exactly one of these roles. An agent file states its role in its first
section and follows that role's contract.

**Precedence** when sources disagree: the owner's feedback in your inputs first. Between a doc and the
code, follow the code and log a `docs-drift` finding naming both, so the doc gets fixed; the one exception
is a pattern a doc marks legacy, which you never copy, however often it appears in the code.

## Implementor
1. Read the files it was given, and only those (plus what they point to).
2. Do the work.
3. Write a report to the run folder: what changed, what was assumed, what it could not do. Put the model
   you are running as in its `model_reported:` line (`unknown` if you cannot tell); the Orchestrator
   stamps the tier and the model it dispatched.

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
1. Know how to start, build and test the system, from `.fyzxsflow/config.json`.
2. Run the requested mode through `.fyzxsflow/package/engine/runner.py`.
3. Judge by the runner's verdict (exit codes plus the step's declared `fail_if_output` / `expect_output`
   checks), never by reading output yourself. A tool that exits 0 while reporting failures needs a declared
   check: propose one rather than reading around it.
4. Classify each failure and route it.
5. It is the only agent that runs builds or tests. (Linters and scanners run through the Gate Analyst
   and `.fyzxsflow/package/engine/gates.py`; nobody else runs tools directly.)

## Coordinator
- **Orchestrator:** dispatches stages, hands off files, keeps the ledger, enforces caps and gates.
- **Build Coordinator:** plans work packages (Locate) and executes them in dependency order (Build).
- **Curator:** turns findings into agent and doc patches.

## Rules for every role
- **No acceptance criteria, no implementation.** Work is implemented only against numbered acceptance
  criteria (brief `AC-n`, package `WP-xx.n`). They are the checks and the end state. An implementor
  reports every criterion it was responsible for as met / not met / partial, with evidence.
- **Only the owner reduces oversight.** No agent lowers a review level, skips a required review, or
  reduces a gate without the owner's words. Agents may raise oversight on evidence and must say so.
- **Deterministic first.** Anything a tool can decide (build, test, lint, scan, traceability) is decided
  by a script with an exit code: `.fyzxsflow/package/engine/runner.py`, `.fyzxsflow/package/engine/gates.py`, `.fyzxsflow/package/engine/ac_trace.py`,
  `.fyzxsflow/package/engine/docs_check.py`. Agents interpret results; they never overrule an exit code.
- Never ask the invoker a question mid-task. Record the assumption in the report and continue. Only the
  Orchestrator raises questions to the owner, and only at a gate.
- Never run build or test commands directly. Run a Runner mode (`python -I .fyzxsflow/package/engine/runner.py <mode> --run <run>
  [--scope <x>]`) and judge by its exit code and summary; a failure you can't trace to your own change goes
  to the Build & Test Runner to classify.
- Stay inside your scope. Need something outside it? Report a `scope-request` finding.
- Cite evidence as `path:line`, from the file as you read it this session. A claim without a location is not
  a finding. `run.py stamp` and the Validator check every citation (`.fyzxsflow/package/engine/checks.py
  citations`).
- **Every fact in a report comes from something you ran or read this session**: a command's output, a file
  you opened. Counts, "only", "all" and "none" claims are checked with a command, and the command is named.
- **Copy, don't recall.** Code, SQL, error text, orders and positions you quote come from the source, copied.
  Say whether a position is 0- or 1-based.
- **Findings** go only through `.fyzxsflow/package/engine/findings.py`. Read the run's `findings.jsonl` first
  and don't log a duplicate: `findings.py amend <F-n>` updates one. `--fixed` means the target itself was
  corrected, not that a fix is planned.
- **Rework updates the report in place**: its criteria and change tables show the current state, not a
  history to reconcile.
- **Criteria rows start with the bare id** (`AC-3`, `WP-02.1`) in the first cell; `ac_trace.py` reads nothing
  else.
- **Run ids stay in the run.** No finding, criterion or package ids (`F-12`, `AC-3`, `WP-04.2`) and no run-folder
  paths in product code, tests or product docs: they mean nothing once the run folder is gone
  (`checks.py run-ids`).
- Write your report even when you fail. A failed run with a good report is useful; a silent one is not.

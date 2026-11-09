---
name: pr-producer
tier: standard
description: Produces the pull request from the run's reports, in the profile's PR description format. Comments the flow adds to the PR start with 'Agent AI Finding:'.
---

# PR Producer

> **Stub.** Contract only; the full procedure is written when this agent is first exercised.

**Role:** Implementor. Read `.fyzxsflow/package/context/role-contracts.md` first.

## Inputs
- `brief.md`
- all reports
- the Runner's `--extreme` summary
- the PR template from the profile

## Outputs
- the PR (or a ready-to-open PR description, if opening it is gated)
- `reports/pr-producer.md`

## Runs when
Deliver, after `--extreme` is green.

## Rules
- Include the acceptance criteria as a checklist, each with its evidence (from the reports; `.fyzxsflow/package/engine/ac_trace.py --require-evidence` must pass first).
- List every flag added (name, default off, how to flip it, how to retire it). When the run's flags were `not-required`, say so and give the revert path instead.
- Link the work item when the brief's source is ADO.
- Opening the PR is an external write: only when the profile pre-authorises it, otherwise hand the description to the Orchestrator's gate.
- **The PR branch holds the product change.** Cut it from the base branch with the run's product commits, plus
  whatever the profile says belongs in PRs (run records, doc updates). Never the flow's own install or bootstrap
  history: check `git log <base>..<branch>` and list what the PR would contain before writing the description.
- **Revert and deploy steps** are checked against the real pipeline and the real tool: what the pipeline actually
  runs, and what the tool's command actually does (read its help or source). A step you could not check is
  labelled unverified.
- Quote the owner and the reports verbatim; attribute every correction to whoever made it; list every doc the
  run changed.

## Learned
<!-- This project's entries live in `.fyzxsflow/learned/pr-producer.md` (maintained by the Curator; each entry: the
     rule, evidence (run/finding ids), hits, date added). install.py appends them below in the host files. -->

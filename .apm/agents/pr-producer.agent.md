---
name: pr-producer
description: Produces the pull request from the run's reports, in the profile's PR description format. Comments the flow adds to the PR start with 'Agent AI Finding:'.
---

# PR Producer

> **Stub.** Contract only; the full procedure is written when this agent is first exercised.

**Role:** Implementor. Read `.apm/context/role-contracts.md` first.

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
- Include the acceptance criteria as a checklist, each with its evidence (from the reports; `engine/ac_trace.py --require-evidence` must pass first).
- List every flag added (name, default off, how to flip it, how to retire it).
- Link the work item when the brief's source is ADO.
- Opening the PR is an external write: only when the profile pre-authorises it, otherwise hand the description to the Orchestrator's gate.

## Learned
<!-- Maintained by the Curator. Each entry: the rule, evidence (run/finding ids), hits, date added. -->

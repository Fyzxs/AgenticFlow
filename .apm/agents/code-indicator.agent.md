---
name: code-indicator
description: Reads brief.md, the repo and its docs, and writes change-map.md: which files and segments change, the expected change in each, the contracts between segments, the test strategy, and which reviewers apply.
---

# Code Indicator

> **Stub.** Contract only; the full procedure is written when this agent is first exercised.

**Role:** Implementor. Read `.agentflow/context/role-contracts.md` first.

## Inputs
- `brief.md`
- `.agentflow/docs/index.md`, `architecture.md`
- the repo

## Outputs
- `change-map.md` from `.agentflow/templates/run/change-map.md`

## Runs when
Always; Locate stage.

## Rules
- Name segments using the docs index. A change in a kind of code with no segment doc is listed as `segment: unknown` so the Cartographer can write one.
- List every surface touched (API, DB, UI, jobs, auth) so the Orchestrator can choose reviewers and the Prove stage.
- Cite the files you based each expectation on.

## Learned
<!-- Maintained by the Curator. Each entry: the rule, evidence (run/finding ids), hits, date added. -->

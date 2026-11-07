---
name: reviewer-architecture
description: Checks the change against the repo's architecture doc and decision records: layers, boundaries, dependency direction, and anything the change-map says is structural. Makes no changes.
---

# Reviewer Architecture

> **Stub.** Contract only; the full procedure is written when this agent is first exercised.

**Role:** Reviewer. Read `.agentflow/context/role-contracts.md` first.

## Inputs
- the diff
- `.agentflow/docs/architecture.md`
- the decision records it points to

## Outputs
- `reports/review.architecture.md`; findings

## Runs when
When the change-map marks structure or layers as touched.

## Rules
- Cite the architecture rule each finding breaks.

## Learned
<!-- Maintained by the Curator. Each entry: the rule, evidence (run/finding ids), hits, date added. -->

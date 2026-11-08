---
name: reviewer-architecture
tier: deep
description: Checks the change against the repo's architecture doc and decision records: layers, boundaries, dependency direction, and anything the change-map says is structural. Makes no changes.
---

# Reviewer Architecture

> **Stub.** Contract only; the full procedure is written when this agent is first exercised.

**Role:** Reviewer. Read `.fyzxsflow/package/context/role-contracts.md` first.

## Inputs
- the diff
- `.fyzxsflow/docs/architecture.md`
- the decision records it points to

## Outputs
- `reports/review.architecture.md`; findings

## Runs when
When the change-map marks structure or layers as touched.

## Rules
- Cite the architecture rule each finding breaks.

## Learned
<!-- This project's entries live in `.fyzxsflow/learned/reviewer-architecture.md` (maintained by the Curator; each entry: the
     rule, evidence (run/finding ids), hits, date added). install.py appends them below in the host files. -->

---
name: reviewer-narrow
description: Reviews exactly the changed lines for correctness, clarity and adherence to the segment docs. Makes no changes.
---

# Reviewer Narrow

> **Stub.** Contract only; the full procedure is written when this agent is first exercised.

**Role:** Reviewer. Read `.apm/context/role-contracts.md` first.

## Inputs
- the diff
- the context packs of the packages that produced it

## Outputs
- `reports/review.narrow.md`; findings

## Runs when
Always, in Review.

## Rules
- Judge against the repo docs, not general taste.
- Every finding cites `path:line` and a severity.

## Learned
<!-- Maintained by the Curator. Each entry: the rule, evidence (run/finding ids), hits, date added. -->

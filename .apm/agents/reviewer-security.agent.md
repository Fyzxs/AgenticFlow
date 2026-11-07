---
name: reviewer-security
tier: deep
description: Reviews auth, tenancy, input handling, secrets and exposure in the change against the repo's security docs. Makes no changes.
---

# Reviewer Security

> **Stub.** Contract only; the full procedure is written when this agent is first exercised.

**Role:** Reviewer. Read `.agentflow/context/role-contracts.md` first.

## Inputs
- the diff
- the security doc the profile names

## Outputs
- `reports/review.security.md`; findings

## Runs when
When the change-map lists auth, tenant, anonymous or input-handling surfaces.

## Rules
- Settled decisions in the security doc are not re-raised.

## Learned
<!-- Maintained by the Curator. Each entry: the rule, evidence (run/finding ids), hits, date added. -->

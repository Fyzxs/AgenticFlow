---
name: http-generator
tier: standard
description: Writes .http (or the project's equivalent) API proof files for changed endpoints, following the repo's existing proof files and the API segment doc.
---

# .http Generator

> **Stub.** Contract only; the full procedure is written when this agent is first exercised.

**Role:** Implementor. Read `.agentflow/context/role-contracts.md` first.

## Inputs
- the API diff
- existing proof files
- the API segment doc

## Outputs
- proof files
- `reports/http-generator.md`

## Runs when
Prove stage, only when the change-map lists an API surface.

## Rules
- Cover flag on and flag off.
- Assertions must be ones the project's runner actually evaluates (see the API segment doc).

## Learned
<!-- Maintained by the Curator. Each entry: the rule, evidence (run/finding ids), hits, date added. -->

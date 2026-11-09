---
name: http-generator
tier: standard
description: Writes .http (or the project's equivalent) API proof files for changed endpoints, following the repo's existing proof files and the API segment doc.
---

# .http Generator

> **Stub.** Contract only; the full procedure is written when this agent is first exercised.

**Role:** Implementor. Read `.fyzxsflow/package/context/role-contracts.md` first.

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
- When the work is flagged, cover flag on and flag off. When the flag policy is `not-required`, cover the shipped
  behaviour and prove the unchanged default still behaves as before.
- Assertions must be ones the project's runner actually evaluates (see the API segment doc).
- Cover every scope the change reaches, not only the first endpoint; a paged result is walked past page one.
- After a revision, update the file's header and its citations to match; no run ids in proof files.

## Learned
<!-- This project's entries live in `.fyzxsflow/learned/http-generator.md` (maintained by the Curator; each entry: the
     rule, evidence (run/finding ids), hits, date added). install.py appends them below in the host files. -->

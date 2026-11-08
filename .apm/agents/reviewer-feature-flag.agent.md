---
name: reviewer-feature-flag
tier: standard
description: Checks that every behaviour change is behind a feature flag placed at the most responsible seam, per the project's feature-flags.md: coverage, placement, off-path integrity, revert speed, data safety, tests in both states, registry and markers, frontend source. Makes no changes.
---

# Reviewer Feature Flag

> **Stub.** Contract only; the full procedure is written when this agent is first exercised.

**Role:** Reviewer. Read `.fyzxsflow/package/context/role-contracts.md` first.

## Inputs
- the diff
- every work package's flag plan
- `.fyzxsflow/feature-flags.md` and the flag registry

## Outputs
- `reports/review.feature-flag.md`; findings of kind `flag`

## Runs when
When behaviour changes and flags are required (project `Policy: required`, unless the brief's `flags:` says `not-required`). Not dispatched when flags are not required.

## Rules
- Coverage: no changed behaviour runs with the flag off.
- Placement: one read point, at a seam `feature-flags.md` allows; no flag reads in domain logic or loops.
- Off path: the code the flag protects is unchanged from main.
- Revert speed: the flag is read at runtime; nothing bakes or caches it beyond what the file allows.
- Data safety: flag-off still works against data the new path wrote; schema changes only add.
- Judge against `feature-flags.md`. If the file is unclear, log a `context-gap` against it.

## Learned
<!-- This project's entries live in `.fyzxsflow/learned/reviewer-feature-flag.md` (maintained by the Curator; each entry: the
     rule, evidence (run/finding ids), hits, date added). install.py appends them below in the host files. -->

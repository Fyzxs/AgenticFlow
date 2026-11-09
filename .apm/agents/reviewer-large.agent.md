---
name: reviewer-large
tier: deep
description: Reviews the change in its surroundings: callers, consumers, contracts across segments and anything else that depends on what changed. Catches the problems a diff-only review cannot. Makes no changes.
---

# Reviewer Large

> **Stub.** Contract only; the full procedure is written when this agent is first exercised.

**Role:** Reviewer. Read `.fyzxsflow/package/context/role-contracts.md` first.

## Inputs
- the diff
- the change-map's contracts
- the repo

## Outputs
- `reports/review.large.md`; findings

## Runs when
Always, in Review.

## Rules
- Find every consumer of a changed contract and confirm it still holds in the shipped configuration: with the
  flag on and off when the work is flagged; as delivered when the flag policy is `not-required`.
- Registries kept in step: when one concept is registered in several places, check every place for every scope
  the change reaches, and that a scope left out can't be reached by a user.
- Partial deploys: say which states a partial deploy (database, backend or frontend first) leaves running.
  Compatibility across those states is the owner's call per change, not a default requirement: a state that breaks
  without a ruling is an `owner-decision` finding; one the profile or the owner has already ruled on is not a finding.

## Learned
<!-- This project's entries live in `.fyzxsflow/learned/reviewer-large.md` (maintained by the Curator; each entry: the
     rule, evidence (run/finding ids), hits, date added). install.py appends them below in the host files. -->

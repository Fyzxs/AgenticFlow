---
name: pr-reviewer
tier: standard
description: Reviews the produced PR as a whole the way a careful human reviewer would: description accuracy, scope, risk, flags, and test evidence. Makes no changes.
---

# PR Reviewer

> **Stub.** Contract only; the full procedure is written when this agent is first exercised.

**Role:** Reviewer. Read `.fyzxsflow/package/context/role-contracts.md` first.

## Inputs
- the PR
- `brief.md`
- the review reports

## Outputs
- PR review comments starting with 'Agent AI Finding:'; findings

## Runs when
Deliver, after the PR exists.

## Rules
- Check the PR says what the code does, including the flag defaults.

## Learned
<!-- This project's entries live in `.fyzxsflow/learned/pr-reviewer.md` (maintained by the Curator; each entry: the
     rule, evidence (run/finding ids), hits, date added). install.py appends them below in the host files. -->

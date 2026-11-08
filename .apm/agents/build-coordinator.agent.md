---
name: build-coordinator
tier: deep
description: Plan mode (Locate) -- splits change-map.md into work packages, one per segment, each naming its context pack, contract, flag plan, done-check, dependencies and size. Execute mode (Build) -- runs the packages in dependency order through the Implementer, the Tester and validators, and checks the contracts between them.
---

# Build Coordinator

> **Stub.** Contract only; the full procedure is written when this agent is first exercised.

**Role:** Coordinator. Read `.agentflow/context/role-contracts.md` first.

## Inputs
- `change-map.md`, `brief.md`
- `.agentflow/docs/index.md`
- `.agentflow/feature-flags.md`

## Outputs
- plan mode: `work-packages/WP-<nn>-<segment>-<what>.md` from `.agentflow/templates/run/work-package.md`.
  `<nn>` is the build order, two digits; `<what>` is 2 to 5 kebab-case words a person can read without
  opening the file (`WP-04-adapter-postgresql-exi-contract`, not `WP-04-adapter-postgresql`). The file stem
  names the package everywhere a person sees it: reviews, reports, the PR.
- execute mode: a status line per package in the ledger, and its frontmatter `status:` kept current
  (`building` when dispatched, `done` when its done-check passes); contract-check results

## Runs when
Locate (plan), then Build (execute).

## Rules
- Every package's `## Flag plan` states exactly one of: its flag (default off, owner, expiry, the one seam it is read at); `unflaggable` with a reason and a revert path; or `not-required` with a revert path. Use `not-required` only when the project `Policy` or the brief's `flags:` allows it; `ac_trace.py` rejects it otherwise. When flags are required and `feature-flags.md` has no provider, stop the plan with an `owner-decision` finding.
- Every package has an `## Acceptance criteria` section: the brief criteria it serves (`Serves: AC-1, AC-3`) and its own checkable package criteria (`WP-01.1`…). Together the packages serve every brief criterion; `.agentflow/engine/ac_trace.py` checks this before Build.
- Package size: 30 to 120 minutes of work. Split anything larger.
- Done-checks use non-destructive Runner capabilities. A database package proves itself with `db-migrate` then `db-verify` (then the scoped tests), never `db-reset`, so seeded data the proofs need survives. If the capability the plan needs is missing or `UNRESOLVED` in `config.json`, that is a `context-gap` against `config.json`, raised once at Locate, not discovered in Build.
- Packages that change pipelines or infrastructure are dispatched to `iac-implementer` with the IaC context pack; everything else to `implementer`.
- The context pack lists exact files and stays within `docs.pack_budget_kb`. A segment with no doc: ask the Repo Cartographer (segment mode) first.
- Execute mode does not re-plan. A wrong plan becomes a `replan` finding back to Locate.
- Per package: Implementer, Validator on it, Tester, Validator on it. Then the package's done-check via the Runner.
- Independent packages may run in parallel only in separate worktrees, and only the Runner runs builds or tests.

## Learned
<!-- Maintained by the Curator. Each entry: the rule, evidence (run/finding ids), hits, date added. -->

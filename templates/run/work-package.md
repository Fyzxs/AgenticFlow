---
id: WP-01
segment: <segment>
depends_on: []
blocks: []
---

# WP-01 — <segment>: <what this package delivers>

## Acceptance criteria
<!-- REQUIRED. The package is done when every line here passes, and only then. -->
- Serves: AC-1, AC-3            <!-- brief criteria this package satisfies (all or part of) -->
- **WP-01.1**: <package-level checkable criterion, e.g. "the mapper maps every field of X to Y, nulls to the Null Object">
- **WP-01.2**: <...>

## Context pack (load exactly these)
- `.agentflow/docs/tech/<stack>.md`
- `.agentflow/docs/segments/<segment>.md`
- `.agentflow/docs/architecture.md` §<section>
- canonical examples: `path/...`, `path/...`
- brief sections: Problem, AC-1, AC-3

## Scope
- create: `path/...`
- change: `path/...`

## Contract
- produces | consumes: <shape>

## Flag plan
<!-- Exactly one of these three lines, filled in (ac_trace.py checks it). `not-required` only when the
     project Policy or the brief's `flags:` allows it. -->
- flag: `<name>` · default: off · owner: <owner> · expiry: <date> · read at: <the one seam, per feature-flags.md>
- unflaggable — reason: <why>; revert: <how>; goes to the plan gate
- not-required (<project policy | owner, this run>) — revert: <how, e.g. revert the commit and redeploy>

## Done check
- Runner: `--quick --scope <project | test filter>`
- every acceptance criterion above has evidence in the implementer and tester reports

## Size
<estimate, 30–120 minutes; split if larger>

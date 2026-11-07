# agentflow profile — <repo name>

<!-- Written by the Repo Cartographer. The Orchestrator reads this before every run. Machine-readable
     settings live in config.json (runner modes) and gates.json (deterministic gates). -->

## What this repo is
UNRESOLVED: one paragraph.

## Surfaces
| Surface | Present | Docs |
|---|---|---|
| API | UNRESOLVED | `.agentflow/docs/segments/...` |
| Database | | |
| UI | | |
| Background jobs | | |
| IaC / pipelines | | `.agentflow/docs/iac-architecture.md` |

## Reviewers that apply here
- always: reviewer-narrow, reviewer-feature-flag, reviewer-large
- by surface: reviewer-architecture (structure), reviewer-security (auth, tenancy, input), reviewer-iac
  (IaC), plus any domain reviewers: UNRESOLVED

## Work items
- Source: prompt only | Azure DevOps (organisation: UNRESOLVED, project: UNRESOLVED)
- Read-only access for agents: yes

## Pull requests
- Opening a PR: gated | pre-authorised
- Target branch: UNRESOLVED
- Description template:
  ```
  ## What and why
  ## Acceptance criteria (with evidence)
  ## Feature flags (name, default, how to flip, how to retire)
  ## Deploy order
  ## Agent findings
  ```
- Comments the flow adds start with `Agent AI Finding:`.

## Deploy order
UNRESOLVED (e.g. infrastructure → database → backend → frontend)

## Off-limits without the owner
- Hosted data, cloud and account configuration, flag flips outside local, pushes and deploys.
- UNRESOLVED: anything repo-specific.

## Runs
- Runs: commit
<!-- commit (default): every run folder is committed at each stage checkpoint, so the brief, plan, reports and
     findings are reviewable and editable between stages; raw logs stay local.
     local: run folders stay on disk only (set this if run history should not appear in PRs). -->

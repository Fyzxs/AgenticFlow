# FyzxsFlow profile — <repo name>

<!-- Written by the Repo Cartographer. The Orchestrator reads this before every run. Machine-readable
     settings live in config.json (runner modes) and gates.json (deterministic gates). -->

## What this repo is
UNRESOLVED: one paragraph.

## Surfaces
| Surface | Present | Docs |
|---|---|---|
| API | UNRESOLVED | `.fyzxsflow/docs/segments/...` |
| Database | | |
| UI | | |
| Background jobs | | |
| IaC / pipelines | | `.fyzxsflow/docs/iac-architecture.md` |

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

## Models
<!-- Agents declare a tier (deep | standard | fast), never a model. config.json -> models.<host> maps tiers to
     this host's model names; an empty value means "inherit the session's model". After changing the map,
     regenerate host files: python -I .fyzxsflow/package/engine/install.py --sync --target . --host <host>.
     See every agent's tier and model: python -I .fyzxsflow/package/engine/models.py --list --host <host>. -->
- Escalation: when a Validator fails the same agent's output twice in a run, the Orchestrator re-runs that
  agent one tier up (fast -> standard -> deep) and records it.
- Owner overrides per run ("use Fable for the reviews") are honoured for that run only.
- `tier: auto` means "the harness decides" (e.g. Copilot's Auto). Map `models.<host>.auto` to the host's
  keyword where it exists; leave it empty (inherit) where it doesn't.
- **Model compare** (`config.json` → `compare.enabled`, off by default): eligible dispatches also run one
  tier below as a shadow, both outputs are validated independently, and `engine/compare.py summary`
  recommends reducing a tier only after `min_samples` conclusive comparisons at `reduce_when_ok_rate`.
  **It roughly doubles the tokens of every shadowed dispatch**; narrow it with `agents`, `sample_rate`
  and `max_per_run`.

## Reviews
<!-- Every agent's output can pause for your review before the next agent gets it. Levels per agent in
     config.json -> review: on (pause) -> notify (summary only) -> off. Everything starts at review.default
     ("on"). Whatever the level, every hand-off writes a review file you can comment in later. Reply to any review with -less-review or -more-review to move that agent one level; only you can lower
     a level. review.always forces reviews for risky segments or paths. Per run, ask in your request or edit
     the run's review-requests.md. See where every agent stands: python -I .fyzxsflow/package/engine/review.py summary -->
- Always review: UNRESOLVED (e.g. segments db-migration, iac; paths **/Auth/**)

## Steps
<!-- Optional parts of the flow, all on by default. Switch them off for the project in config.json -> steps.off
     (e.g. ["pr"] to end every run with a ready branch instead of a PR), or for one run by saying so in your
     request ("no PR this time"). Steps: http-proofs, gates, reviews (or review-narrow, review-large,
     review-architecture, review-security, review-feature-flag, review-iac), extreme, pr, pr-review,
     docs-upkeep, learn. See them: python -I .fyzxsflow/package/engine/steps.py list -->

## Runs
- Runs: commit
<!-- commit (default): every run folder is committed at each stage checkpoint, so the brief, plan, reports and
     findings are reviewable and editable between stages; raw logs stay local.
     local: run folders stay on disk only (set this if run history should not appear in PRs). -->

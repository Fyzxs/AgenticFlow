# FyzxsFlow

**A self-correcting agentic development flow for Claude Code and GitHub Copilot.**

Give it a prompt, a story or an Azure DevOps work item. It plans the change, implements it behind a
feature flag, proves it with your own build and test commands, reviews it, and opens a pull request.
Every mistake along the way is logged as a finding, and the flow turns findings into better agent
instructions and better repo docs. Each run should need fewer corrections than the one before.

> **Status: early (v0.3.0).** The engine scripts are complete and tested, and all the agents are written in
> full, shaped by a first end-to-end trial on a real application. More trials are under way. Expect
> breaking changes.

## How it works

```
request ──► Intake ──► Locate ──► Build ──► Prove ──► Review ──► Deliver ──► PR
             brief     change map  code +    builds,   reviewers  PR text
             + criteria + packages tests     gates     + fixes
                                        │
                     findings from every stage ──► Curator ──► better agents and docs
```

- **Intake.** The Work Summarizer turns the request into `brief.md` with numbered acceptance criteria.
- **Locate.** The Code Indicator maps what changes and where. The Build Coordinator splits it into work
  packages, one per segment of the codebase, each naming the docs it needs.
- **Build.** Work starts as soon as what it depends on is done, each PR group in its own worktree and with its
  own PR into the run's branch. One Implementer writes each package and a separate Tester writes its tests. A Validator
  checks each output by re-reading the agent's own instructions and acting as that agent.
- **Prove.** The Build & Test Runner runs your build and test commands. The Gate Analyst runs your
  linters and scanners and decides, per result, whether to send it back, correct it, or move on. With the
  opt-in end-to-end step, the whole app also runs on one machine, in airplane mode (nothing external) or
  connected mode (approved non-production services only).
- **Review.** Reviewers chosen by the change check it: narrow (the diff), large (its callers and
  contracts), architecture, security, feature flags, infrastructure.
- **Deliver.** Once you have completed every group PR, the run's branch gets one roll-up PR into the default
  branch: the PR Producer writes it and the PR Reviewer reads it as a human would. Every PR starts as a draft and is
  published only when its work is done, so a draft means work in progress and a published PR means ready for your
  approval. You complete every PR; the flow never does.
  The Curator then routes every finding of the run.

Agents hand off through files in a run folder, never through pasted context, so each one can run on any
host or model. Each run is committed at every stage, so you can read it, edit it, or resume it.

## Principles

1. **Gates are scripts, not prompts.** Anything that must always hold is a script with an exit code or
   a git hook. Prompts carry judgment; scripts carry guarantees.
2. **One Implementer, specialised by context.** There are no per-language agents. Expertise lives in
   your repo's docs, and each work package names the ones that apply. The Repo Cartographer drafts those
   docs from your code; the Docs Gardener keeps them current.
3. **No acceptance criteria, no implementation.** Every brief and work package carries numbered,
   checkable criteria, and `engine/ac_trace.py` checks that each one is served and evidenced before a PR.
4. **Feature-flag everything, unless you say otherwise.** Runtime flags, default off, revert without a
   deploy. Your project's `feature-flags.md` says how flags work in your repo.
5. **Builds and tests run only through one script.** Agents run a mode from your config through
   `runner.py` and read a short summary, which keeps logs out of their context. The Build & Test Runner
   runs the stage checks and decides whether a failure is the change, a flake, the environment, or
   pre-existing.
6. **Every miss is a signal.** Validators, reviewers, the Runner, PR comments and your own corrections
   all become findings. The Curator turns each one into an agent rule, a doc fix, or a proposed hook or
   test.
7. **You review, and you decide when to review less.** Every agent's output pauses for you at first.
   When an agent has earned it, reply `-less-review` to move it from `on` to `notify` to `off`. Only you
   can lower a level; the flow can raise it after a mistake. Every hand-off writes a review file either
   way, so you can comment on it later.
8. **Feedback, not hand edits.** Write in a review file's `## Human Feedback` section, or drop a note in
   `.fyzxsflow/feedback/`, at any time. The flow routes it to the right doc, agent or new piece of work,
   and shows you what it did in your next review.
9. **Models by tier, moved on evidence.** Agents declare `deep`, `standard`, `fast` or `auto`, and each
   project maps tiers to its host's models. An agent that keeps failing moves up a tier for that run.
   An optional model compare shadows a cheaper tier, so a tier is only lowered once the cheaper model
   has proven itself. See [Models](HOW-TO.md#models).
10. **Bounded everything.** Fix loops stop after two rounds, context packs have a size budget, agent files and
    learned entries can be compacted on request without losing a rule, and the Curator's own changes are
    validated before they land.

## Getting started

```
python -I engine/install.py --target <path to your repo> --host claude   # or install with APM
/fyzxsflow-init                                                          # draft .fyzxsflow/ from your code
/flow <request>                                                          # run a request
```

A new project with no code yet starts from its system design instead:
`/fyzxsflow-greenfield <design files> [seed: <rules folder>]`. The flow reads the design, decides what it leaves
open (you approve every decision in one review), writes the project's docs, and builds a reviewed walking
skeleton in the same run.

**Preceptee mode (off by default).** To train an engineer on real work, start a run with
`/flow --preceptee <request>`, or switch it on for a project with
`python -I .fyzxsflow/package/engine/steps.py set precept on --reason "<why>"`. The engineer writes the code, and a
Preceptor agent reviews their pull requests the way a senior engineer would. It asks about the behaviour first,
then points at the file, the method and finally the line, only as far as needed, and eases off as they improve.
Their scores stay on their machine. See [PRECEPTEE.md](PRECEPTEE.md).

When learned entries, docs and agents grow heavy, `/fyzxsflow-compact [targets]` shrinks them without losing a
rule, so every agent dispatch costs fewer tokens.

[HOW-TO.md](HOW-TO.md) has the full steps: installing (from a clone or with APM), setting up, running on each
Claude Code and Copilot surface, turning steps off, and choosing models.

## The agents

| Agent | Does |
|---|---|
| Orchestrator | Drives the run through every stage; the entry point |
| Work Summarizer | Request → `brief.md` with acceptance criteria |
| Code Indicator | Brief → change map: files, segments, contracts, test strategy |
| Build Coordinator | Splits the change map into work packages and runs them in order |
| Implementer | Writes one work package, specialised by its docs |
| IaC Implementer | Pipelines and infrastructure code; validates with previews, never deploys |
| Tester | Writes the tests for one package, separately from the code |
| Validator | Checks any agent's output by acting as that agent; logs every miss |
| Build & Test Runner | Runs the stage checks and classifies failures: code, flake, environment, pre-existing |
| Gate Analyst | Runs linters and scanners; send back, correct, or move on |
| HTTP Generator | API proof files for changed endpoints |
| E2E Investigator | Opt-in: works out how the app can run end to end on one machine, and what each dependency's local substitute is |
| E2E Implementer | Opt-in: builds that setup (containers, emulators, mock servers, local config) in a run you start |
| E2E Tester | Opt-in: end-to-end scenarios for each change, run in airplane or connected mode |
| Reviewers (6) | Narrow, large, architecture, security, feature flag, IaC |
| PR Producer | Writes the pull request |
| PR Reviewer | Reviews the PR as a careful human would |
| Repo Cartographer | Drafts the repo docs from code and CI; confirms a new project's planned docs against its first code |
| Design Reader | New projects: a cited inventory of the system design |
| Greenfield Architect | New projects: decides what the design leaves open, writes the project's docs and the walking-skeleton plan |
| Docs Gardener | Applies your feedback to docs and keeps them in step with the code |
| Preceptor | Preceptee mode, off by default (`/flow --preceptee`): the engineer writes the code; it reviews their PRs like a senior, broad to specific, and eases off as they improve ([PRECEPTEE.md](PRECEPTEE.md)) |
| Seeder | Preceptee mode only: makes a practice copy of an agent's change with one planted flaw, outside the repo, for the preceptee to find. No other agent ever plants a mistake |
| Compactor | On request (`/fyzxsflow-compact`): shrinks agent files, learned entries and docs without losing a rule |
| Curator | Turns findings into agent rules, doc fixes and proposed checks |

## Repository layout

```
.apm/
  agents/            the agents (*.agent.md)
  prompts/           entry points: flow, fyzxsflow-init, fyzxsflow-greenfield, fyzxsflow-compact,
                     fyzxsflow-parallelize
  instructions/      the always-on working agreement
  context/           shared contracts: roles, run folder, findings schema
  skills/            reusable skills (e.g. mining past transcripts for corrections)
engine/              host-neutral Python scripts: runs, findings, reviews, feedback, runner, gates,
                     acceptance-criteria tracing, docs checks, model tiers, install
  hooks/             tool-call guards
  tests/             python -I engine/tests/run_all.py
templates/           shapes of the project files and run artifacts
adapters/            host-specific notes for Claude Code and Copilot
docs/                design summary, decisions, and plans
apm.yml              APM manifest
HOW-TO.md            install, set up, run, and tune
PRECEPTEE.md         preceptee mode: coaching an engineer through real work (off by default)
```

## Roadmap

- Rework the agents around their priorities rather than step-by-step procedure, as trials show where they
  need judgment.
- Verify installation through APM.
- A separate, opt-in `deploy` agent set for pipelines, deployment health and resource optimisation.
  These agents will never change production; prod changes go only through a pipeline with a human
  approval gate. See [`docs/deploy-agents.md`](docs/deploy-agents.md).

## Development

```
python -I engine/tests/run_all.py
```

The design and its decisions are summarised in [`docs/design.md`](docs/design.md).

## License

MIT. See [LICENSE](LICENSE).

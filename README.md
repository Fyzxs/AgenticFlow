# agentflow

A self-correcting agentic development flow that works on more than one agent host. You give it a prompt,
a story or an Azure DevOps work item. An orchestrator splits the work, a single Implementer writes it
behind a feature flag, a Build & Test Runner proves it, reviewers check it, and a PR comes out. Every
miss along the way becomes a finding, and a Curator turns findings into better agent files and better
repo docs, so each run needs fewer corrections than the last.

Design: https://claude.ai/artifact/SzJwCgeAbqtwCeWJLSAGhd (private to the owner) — summarised in
[`docs/design.md`](docs/design.md).

> **Status: scaffold (v0.1.0).** Seven agents are drafted in full (Orchestrator, Implementer, IaC
> Implementer, Validator, Build & Test Runner, Gate Analyst, Repo Cartographer). The rest are contract
> stubs. The engine scripts work and are tested. Nothing has been run end to end yet.

## Principles

1. **Gates are scripts, never prompts.** Anything that must hold on every host is a script with an exit
   code or a git hook. Prompts carry judgment; scripts carry guarantees.
2. **The run folder is the API between agents.** Agents hand off files with fixed shapes, never pasted
   context, so any agent can run on any host or model without the next one noticing.
3. **One Implementer, specialised by context.** Expertise lives in the repo docs, which the Build
   Coordinator names per work package. Agent files hold portable craft.
4. **Only the Build & Test Runner runs builds or tests; only the Gate Analyst runs scanners.** Everyone
   else asks them and gets a compact result.
5. **No acceptance criteria, no implementation.** Every brief and work package carries numbered,
   checkable criteria, and `engine/ac_trace.py` proves each is served and evidenced before a PR.
6. **Deterministic gates are declared, not prompted.** Linters, scanners and custom checks live in
   `.agentflow/gates.json`; `engine/gates.py` runs them and normalises SARIF; baselines keep known results
   from blocking.
7. **Everything is feature-flagged, unless the owner says otherwise.** Runtime flags, default off, revert
   without a deploy. The project's `feature-flags.md` says how, and its `Policy` (`required` or
   `not-required`) or the owner's per-run instruction decides whether. Either way every work package
   records its choice and revert path, and `ac_trace.py` checks it.
8. **Every miss is a signal.** Validators, reviewers, the Runner, PR comments and chat corrections all
   write findings. The Curator routes each to the agent file, a repo doc, or a hook or test.
9. **Runs are kept and editable.** Each run is committed at every stage checkpoint (`runs/active/` →
   `runs/completed/` or `runs/abandoned/`). Edit any artifact between stages and the next stage reads it;
   your edits become the Curator's strongest signal.
10. **Models by tier, moved on evidence.** Agents declare `deep`, `standard`, `fast` or `auto` (the harness
    decides); each project maps tiers to its host's models. Repeated Validator failures move an agent up for
    that run. Optional model compare (off by default; it doubles shadowed tokens) runs a tier below as a
    shadow, so the Curator can propose moving down only when the cheaper tier has proven itself.
11. **Human review between hand-offs, earned down.** Every agent's output pauses for the owner by default.
    Reply `approve`, `continue`, `redo: ...` or `stop`, adding `-reduce` or `-increase` to change that agent's
    level (on → notify → off). Only the owner lowers it; risky segments and per-run requests always pause.
12. **Bounded everything.** Review-fix loops stop after 2 rounds, context packs and agent files have size
   budgets, and the Curator's patches are validated before they land.

## Layout

```
apm.yml                      APM manifest (targets: copilot, claude)
.apm/
  agents/*.agent.md          the agent suite (compiled to .github/agents or .claude/agents)
  instructions/              always-on instructions (working agreement)
  prompts/                   entry points: flow, init
  skills/correction-mining/  mine past transcripts for corrections
  context/                   shared fragments: role contracts, run folder, findings schema
engine/                      host-neutral Python 3 scripts (stdlib only)
  run.py                     create a run folder, append to the ledger, print status
  findings.py                append and validate findings
  runner.py                  execute a Build & Test Runner mode from .agentflow/config.json
  gates.py                   run declared linters/scanners, normalise SARIF, apply baselines
  ac_trace.py                acceptance-criteria traceability (plan check; evidence check before PR)
  docs_check.py              cited paths exist, segment globs match, packs within budget
  pointers.py                write/check host-native pointers (.claude/rules, .github/instructions) per segment
  install.py                 install into a repo (.agentflow/ + host files), or --sync host files after edits
  models.py                  agent tier -> model per host (config.json models), escalation (--up), shadow (--down)
  compare.py                 model compare: whether to shadow a dispatch, record and score it, summarise
  review.py                  human review between hand-offs: needed?, reply parsing (-reduce/-increase), levels
  hooks/                     tool-call guards (Claude Code adapter today)
  tests/                     python -I engine/tests/run_all.py
templates/
  project/.agentflow/        what the Cartographer writes into a repo
  run/                       the shapes of brief, change-map, work package, report
adapters/claude, adapters/copilot   host-specific wiring and the open questions per host
docs/design.md               design summary and decisions
```

## Using it in a repo

Everything installs under `.agentflow/` in the target repo (engine, context, agents, templates, skills),
and host files are generated from it. Agent files refer to those installed paths.

1. Until the APM route is verified: `python -I engine/install.py --target <repo> --host claude [--host copilot]`.
   Later: `apm install <you>/agentflow`.
2. Run the `agentflow-init` prompt. The Repo Cartographer drafts `.agentflow/` from the repo and asks only
   what it can't find (usually the feature-flag provider).
3. Run the `flow` prompt with a request or a work item id.

## Development

```
python -I engine/tests/run_all.py
```

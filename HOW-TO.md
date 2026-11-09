# FyzxsFlow how-to

How to install FyzxsFlow into a repo, set it up, run it, and tune it. For what FyzxsFlow is and how it
works, see the [README](README.md).

- [Requirements](#requirements)
- [Install](#install)
- [Set up your repo](#set-up-your-repo)
- [Run the flow](#run-the-flow)
- [Turn steps off](#turn-steps-off)
- [Models](#models)
- [What lands in your repo](#what-lands-in-your-repo)
- [Upgrade](#upgrade)

## Requirements

Python 3 (the engine uses the standard library only), git, and Claude Code and/or GitHub Copilot.

## Install

Install for the host you use: `--host claude`, `--host copilot`, or both.

### From a clone of this repo

```
python -I engine/install.py --target <path to your repo> --host claude --host copilot
```

### With APM

> **Not yet verified end to end.** These steps follow [APM's documentation](https://microsoft.github.io/apm/);
> if one doesn't behave as described, please open an issue.

[APM](https://github.com/microsoft/apm) (Agent Package Manager) installs agent packages from GitHub and pins
them in `apm.yml` and `apm.lock.yaml`. Install the CLI (for example `pip install apm-cli`, `brew install apm`,
or `winget install --id Microsoft.APM --exact --source winget`), then, in your repo:

```
apm install Fyzxs/AgenticFlow --target claude,copilot
python -I apm_modules/Fyzxs/AgenticFlow/engine/install.py --target . --host claude --host copilot
```

The first command downloads FyzxsFlow into `apm_modules/` (keep that gitignored) and deploys its agents,
prompts, instructions and skills into `.claude/` and `.github/`. The second sets up `.fyzxsflow/`: the engine
the agents call, the templates, the kill-by-name hook, and host files that include what the Curator has learned
for your project. APM can't run a package's installer itself, so the second command is needed, after every
`apm install` or `apm update` of FyzxsFlow. Pin a version with `apm install Fyzxs/AgenticFlow#<tag or commit>`.

To have APM run the installer for you, add this to **your** repo's `apm.yml` and trust it once with
`apm lifecycle trust` (APM never runs a project's lifecycle scripts until you do, and re-asks after any change
to them):

```yaml
lifecycle:
  post-install:
    - type: command
      description: "Set up FyzxsFlow (.fyzxsflow/ and host files)"
      command: "python -I apm_modules/Fyzxs/AgenticFlow/engine/install.py --target . --host claude --host copilot"
      timeoutSec: 120
  post-update:
    - type: command
      description: "Set up FyzxsFlow (.fyzxsflow/ and host files)"
      command: "python -I apm_modules/Fyzxs/AgenticFlow/engine/install.py --target . --host claude --host copilot"
      timeoutSec: 120
```

The installer rewrites some files APM deployed (each agent file gets your project's Learned entries), so
`apm audit` reports those files as changed. That is expected.

## Set up your repo

Run `/fyzxsflow-init` (see [Run the flow](#run-the-flow) for your tool). The Repo Cartographer drafts
`.fyzxsflow/` (profile, build and test commands, gates, feature-flag rules and per-segment docs) from your
code and CI, and asks only for what it cannot find. Review what it wrote before the first run.

## Run the flow

The flow is two entry points: **`flow`** (run a request through the Orchestrator) and **`fyzxsflow-init`**
(bootstrap the repo with the Repo Cartographer). Open your repo and start them like this:

| Where | Bootstrap | Run a request |
|---|---|---|
| **Claude Code** (CLI, VS Code or JetBrains extension, desktop app) | `/fyzxsflow-init` | `/flow <request>` |
| **VS Code, GitHub Copilot Chat** | `/fyzxsflow-init` in the Chat view | `/flow <request>`, or pick **orchestrator** in the agents dropdown and type the request |
| **GitHub Copilot CLI** | `copilot --agent=repo-cartographer --prompt "Bootstrap FyzxsFlow in this repo (bootstrap mode)"` | `copilot --agent=orchestrator --prompt "<request>"`, or `/agent` → **orchestrator** in an interactive session |
| **GitHub Copilot app** (desktop) | start a local session on the repo: `Act as the FyzxsFlow repo-cartographer in bootstrap mode (.fyzxsflow/package/agents/repo-cartographer.agent.md).` | `Act as the FyzxsFlow orchestrator (.fyzxsflow/package/agents/orchestrator.agent.md) and run the flow on: <request>` |

- **Claude Code** reads the commands from `.claude/commands/` and dispatches each agent as a subagent.
- **VS Code** runs `.github/prompts/*.prompt.md` as slash commands. The prompts open in the right custom agent
  (`.github/agents/`), and the Orchestrator dispatches the others as subagents (the `agent` tool). Use agent
  mode with the Local harness.
- **Copilot CLI** has no prompt files; start the custom agent directly. Restart the CLI after installing so it
  loads the agents from `.github/agents/`.
- **Copilot app** documents no support for a repository's custom agents yet, so ask the session to act as the
  agent by its file, which works in any agent that can read files and run commands. Use a local session: the
  flow runs `python` and your build and test commands.

Where a host can't dispatch one agent from another, the Orchestrator runs that agent's step itself from its
file and says so in the ledger. The run is the same, but the Validator's check is less independent.

Reply to reviews in the same conversation. If a session ends mid-run, start a new one and say `/flow resume`
(or ask the Orchestrator to resume): it picks the run up from `.fyzxsflow/runs/active/`.

> **Copilot surfaces are not yet verified end to end.** The steps follow the
> [VS Code prompt files](https://code.visualstudio.com/docs/copilot/customization/prompt-files),
> [subagents](https://code.visualstudio.com/docs/copilot/agents/subagents),
> [Copilot CLI custom agents](https://docs.github.com/en/copilot/how-tos/copilot-cli/use-copilot-cli/invoke-custom-agents)
> and [Copilot app](https://docs.github.com/en/copilot/concepts/agents/github-copilot-app) docs. Claude Code is
> the host the flow has been trialled on.

Requests can be plain text or an Azure DevOps work item:

```
/flow Add sorting by release date to the collection page
/flow 12345        (an Azure DevOps work item id)
```

Answer each review with `approve`, `redo: <what to change>` or `stop`.

## Turn steps off

Everything outside the core (intake, planning, build, validation, build and test checks) can be switched
off. For the whole project, list the steps in `.fyzxsflow/config.json`:

```json
"steps": { "off": ["pr", "learn"] }
```

For one run, say it in your request ("no PR this time", "skip the security review"). See where every step
stands with `python -I .fyzxsflow/package/engine/steps.py list`.

| Step | While it is off |
|---|---|
| `pr` | no pull request; the run ends with its branch committed and ready |
| `pr-review` | the PR opens without the agent's whole-PR review |
| `reviews` | no reviewers (or one at a time: `review-narrow`, `review-large`, `review-architecture`, `review-security`, `review-feature-flag`, `review-iac`) |
| `http-proofs` | API changes are proven by tests only |
| `gates` | the flow doesn't run your linters and scanners (CI still does) |
| `extreme` | no strict sign-off build; the CI-equivalent run is the last check |
| `docs-upkeep` | docs aren't refreshed after the run (your feedback still updates them) |
| `learn` | findings are kept but not turned into agent or doc changes |

## Models

Each agent declares a tier, never a model name. Out of the box:

| Tier | Agents | Claude Code | Copilot |
|---|---|---|---|
| `deep` | orchestrator, build-coordinator, validator, curator, repo-cartographer, code-indicator, reviewer-architecture, reviewer-large, reviewer-security, reviewer-iac | `opus` | inherit |
| `standard` | work-summarizer, implementer, tester, http-generator, iac-implementer, gate-analyst, docs-gardener, pr-producer, pr-reviewer, reviewer-narrow, reviewer-feature-flag | `sonnet` | inherit |
| `fast` | build-test-runner | `haiku` | inherit |
| `auto` | none | inherit | inherit |

*Inherit* means the agent runs on whatever model the session uses. On Copilot that is the model you pick in
its model picker; it applies to every agent because Copilot's model names and its Auto keyword aren't
verified yet. `auto` is for hosts whose harness chooses the model itself. Claude Code has no such mode, so
it inherits there as well.

Map tiers to models in `.fyzxsflow/config.json`. A host's map replaces the defaults for that host entirely,
so give all four keys:

```json
"models": {
  "claude":  { "deep": "opus", "standard": "sonnet", "fast": "haiku", "auto": "" },
  "copilot": { "deep": "", "standard": "", "fast": "", "auto": "" }
}
```

Then regenerate the host agent files: `python -I .fyzxsflow/package/engine/install.py --sync --target . --host claude`.
`python -I .fyzxsflow/package/engine/models.py --list --host claude` shows what each agent resolves to.

During a run, an agent whose output fails validation twice moves up one tier for the rest of that run. A
`deep` agent can't move up, so the flow asks you instead. You can also override a model for one run ("use
opus for the reviews"). Every report records the model it ran on; `run.py models <run>` lists them.

**Model compare** is off by default because it can double the tokens of each agent it shadows. To turn it on:

```json
"compare": {
  "enabled": true,
  "agents": ["implementer", "reviewer-narrow"],
  "sample_rate": 1.0,
  "max_per_run": 3,
  "min_samples": 5,
  "reduce_when_ok_rate": 0.9
}
```

While it is on, the flow runs a chosen agent twice for the same task, once on its own tier and once a tier
lower (the shadow). Only the main output counts; the shadow's goes under `reports/shadow/`, and agents that
write code run their shadow in a throwaway worktree. A separate Validator checks each output.

- `agents`: the agents to shadow; `[]` shadows every eligible one. `fast` and `auto` agents have no lower
  tier, so they are never shadowed.
- `sample_rate`: the share of eligible dispatches that get a shadow.
- `max_per_run`: the most shadows in one run.

`python -I .fyzxsflow/package/engine/compare.py summary` shows each agent's verdict:
- `reduce` once there are at least `min_samples` usable comparisons and the shadow passed at least
  `reduce_when_ok_rate` of them;
- `keep` when it didn't pass often enough;
- `insufficient` until there are enough samples.

Nothing lowers a tier automatically. The Curator proposes it, and only where the summary says `reduce`.

## What lands in your repo

```
.fyzxsflow/
  config.json, profile.md, gates.json, feature-flags.md   your project's settings (yours to edit)
  docs/              the repo docs agents are specialised by
  feedback/          drop notes for the flow here, any time
  learned/           rules the Curator has learned for this project, per agent
  runs/              every run: brief, plans, reports, reviews, findings
  package/           the installed engine and agents; replaced on every install, never edited
.claude/  .github/   host files generated from package/ + learned/
```

## Upgrade

Install again at any time, the same way you installed. `package/` and the host files are rewritten; your
project's files (settings, docs, feedback, learned rules, runs) are never overwritten.

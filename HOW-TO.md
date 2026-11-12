# FyzxsFlow how-to

How to install FyzxsFlow into a repo, set it up, run it, and tune it. For what FyzxsFlow is and how it
works, see the [README](README.md).

- [Requirements](#requirements)
- [Install](#install)
- [Set up your repo](#set-up-your-repo)
- [Start a new project](#start-a-new-project)
- [Run the flow](#run-the-flow)
- [Turn steps off](#turn-steps-off)
- [Test end to end (opt-in)](#test-end-to-end-opt-in)
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

## Start a new project

`/fyzxsflow-init` learns your conventions from code, so it can't start an empty repo. A new project starts from
its logical and physical system design instead. Install FyzxsFlow into the empty repo, put the design files in
it (markdown, diagrams, PDFs), and run:

```
/fyzxsflow-greenfield docs/design/ seed: ../other-project/.claude/rules
```

`seed:` is optional: a folder of rules from your other projects to start from. One run then does all of this, on
its own branch:

1. **Read the design.** The **Design Reader** writes a cited inventory: components, deployables, data, flows,
   cross-cutting concerns, environments, the technology the design names, and every gap or contradiction.
2. **Decide.** The **Greenfield Architect** decides everything the design leaves open: language and framework
   versions, project layout, tests, linters, the local dev stack, CI, infrastructure code, feature flags. Each
   decision becomes a record in `docs/decisions/`, saying whether the design, your seed rules or the architect
   made it. It writes the whole of `.fyzxsflow/` from them, marked `status: planned` because no code exists yet.
3. **You approve, once.** One review lists every decision the design didn't make and every gap, numbered, each
   with a recommendation, and asks whether to switch end-to-end testing on from day one. Answer "1 - yes,
   2 - xUnit, ..." in the review. Nothing is built before this.
4. **The walking skeleton.** The run continues as a normal run: every deployable exists, builds and starts
   locally, and one key flow from the design works through every layer against a local database, with tests,
   linters, a CI pipeline file and a getting-started README. No business features. Pipelines and infrastructure
   code are written and validated offline, never run or applied.
5. **Confirm.** The **Repo Cartographer** checks every planned doc against the skeleton: each segment gets its
   canonical examples, and each rule is borne out by the code or kept as "intended". Ship-check blocks until
   nothing is still planned.

After that, `/flow` works as it does on any repo, and the skeleton's files are the examples it copies.

## Run the flow

The flow has four entry points: **`flow`** (run a request through the Orchestrator), **`fyzxsflow-init`**
(bootstrap the repo with the Repo Cartographer), **`fyzxsflow-greenfield`** (start a new project from its
design; see [Start a new project](#start-a-new-project)) and **`fyzxsflow-compact`** (shrink the agent files; see
[Compact the agent files](#compact-the-agent-files)). Open your repo and start them like this:

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

Each run works on its own branch, `fyzxsflow/<run-id>`, cut from whatever you had checked out; nothing lands on
your base branch. Reply to reviews in the same conversation. If a session ends mid-run, start a new one and say `/flow resume`
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

`e2e` is the one step that starts **off**; see the next section.

## Test end to end (opt-in)

End-to-end testing runs your whole app on one machine and drives it the way a user would. It is opt-in, because
setting it up is real work for most repos. Turn it on for the project, or say "test this end to end" in a request
for one run:

```
python -I .fyzxsflow/package/engine/steps.py set e2e on --reason "we want end-to-end proofs"
```

What happens next depends on `.fyzxsflow/e2e.md`:

1. **No setup yet.** On the next run, the **E2E Investigator** works out how your app can run end to end
   locally. It lists every external dependency (database, cache, queue, storage, identity, third-party APIs)
   and picks a local substitute for each: an emulator, the real software in a container, a mock server built
   from the API's contract, or a fake. It writes the plan to `.fyzxsflow/e2e.md` and asks its questions in one
   review file, ending with "Start the setup run?". The run you asked for carries on; its PR says it wasn't proven
   end to end.
2. **Setup.** When you say "set up end to end testing", a separate run has the **E2E Implementer** build it. That
   means the compose file and pinned images, the mock servers, a local config profile, seed data and one smoke
   scenario. It also adds the Runner modes below, which it proves by running them, and sets `e2e.md` to `Status: ready`.
3. **Every run after that.** The **E2E Tester** adds scenarios for the change. The end-to-end modes run in
   Prove, and ship-check blocks until they pass on the current commit.

Two modes, either or both:

| Mode | Means |
|---|---|
| `e2e-airplane` | everything the tests need lives on this machine. Nothing calls an external service |
| `e2e-connected` | the app runs on this machine but may call external services you approved in `e2e.md`, never production |
| `e2e-prefetch` | downloads what airplane needs (images, packages, browsers), once, while online |

**Airplane is checked, not switched on.** Your network stays on. While an airplane mode runs, the Runner points
every process's proxy settings at a closed local port and refuses container starts that could pull an image. It
watches the connections of every process the mode started. A connection to anything that isn't this machine (or
an address range you allowed for containers) fails the mode and names the process and the address. One limit:
processes inside containers aren't watched; `--pull never` proves their images are local.

## Models

Each agent declares a tier, never a model name. Out of the box:

| Tier | Agents | Claude Code | Copilot |
|---|---|---|---|
| `deep` | orchestrator, build-coordinator, validator, curator, repo-cartographer, design-reader, greenfield-architect, code-indicator, e2e-investigator, reviewer-architecture, reviewer-large, reviewer-security, reviewer-iac | `opus` | inherit |
| `standard` | work-summarizer, build-test-runner, implementer, tester, http-generator, e2e-implementer, e2e-tester, iac-implementer, gate-analyst, docs-gardener, pr-producer, pr-reviewer, reviewer-narrow, reviewer-feature-flag | `sonnet` | inherit |
| `fast` | none | `haiku` | inherit |
| `auto` | none | inherit | inherit |

*Inherit* means the agent runs on whatever model the session uses. On Copilot that is the model you pick in
its model picker; it applies to every agent because Copilot's model names and its Auto keyword aren't
verified yet. `auto` is for hosts whose harness chooses the model itself. Claude Code has no such mode, so
it inherits there as well.

Map tiers to models in `.fyzxsflow/config.json` (every setting is described in
`.fyzxsflow/config.json.readme.md`). A host's map replaces the defaults for that host entirely,
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

## Compact the agent files

Learned entries, docs and the agents themselves only grow, and every agent dispatch pays for what it loads. When
they feel heavy, run **`/fyzxsflow-compact`** (Claude Code, or Copilot Chat; on the Copilot CLI,
`copilot --agent=orchestrator --prompt "compaction run: <targets>"`). It never runs on its own.

```
/fyzxsflow-compact                  # everything
/fyzxsflow-compact learned docs     # only the learned entries and the project docs
/fyzxsflow-compact orchestrator     # one agent
```

It is a short run of its own (refused while another run is active): the Compactor shrinks the files, a Validator
checks each one against its original, and you review a table of sizes before and after. Nothing is lost silently:
`compact.py check` lists any heading, command, path, id or number that disappeared, and the Compactor must restore
it or name it in **Accepted drops** with a reason.

- **Learned entries and docs** are your files and are changed in place. `profile.md` and `feature-flags.md` are
  only ever proposed.
- **The package's agents** are replaced by every install, so a compacted one is kept in
  `.fyzxsflow/compacted/`, and the installer copies it back over the package after each install. When an upgrade
  changes that agent upstream, the installer keeps the new upstream file and warns that the compaction is stale:
  run `/fyzxsflow-compact <that agent>` again. `python -I .fyzxsflow/package/engine/compact.py status` lists
  them all; `compact.py drop <path>` and a reinstall undo one.

## What lands in your repo

```
.fyzxsflow/
  config.json, profile.md, gates.json, feature-flags.md   your project's settings (yours to edit)
  config.json.readme.md   what every config.json setting means; refreshed by each install
  e2e.md             how the app is tested end to end (only once you opt in)
  docs/              the repo docs agents are specialised by
  feedback/          drop notes for the flow here, any time
  learned/           rules the Curator has learned for this project, per agent
  compacted/         smaller copies of package files, from /fyzxsflow-compact; re-applied by each install
  runs/              every run: brief, plans, reports, reviews, findings
  package/           the installed engine and agents; replaced on every install, never edited
.claude/  .github/   host files generated from package/ + learned/
```

## Upgrade

Upgrading is the install command again, run against the newer FyzxsFlow.

**From a clone:** update the clone, then re-run the installer for each repo you installed into, with the same
`--host` flags as before:

```
cd <your FyzxsFlow clone>
git pull
python -I engine/install.py --target <path to repo A> --host claude --host copilot
python -I engine/install.py --target <path to repo B> --host claude
```

**With APM:** in your repo, `apm update`, then the second command from [With APM](#with-apm) (or let the
`post-update` lifecycle hook run it).

The installer replaces `.fyzxsflow/package/` and regenerates the host files (`.claude/`, `.github/`) from it,
adding your project's Learned entries and compacted files back in. It never overwrites your project's files: settings, docs,
feedback, learned rules and runs. New settings take their defaults until you add them to `config.json`;
`.fyzxsflow/config.json.readme.md` is refreshed by the same install and lists every one.

Then, in the upgraded repo:

1. **Upgrade between runs.** The installer doesn't stop you mid-run, but a paused run in
   `.fyzxsflow/runs/active/` would continue on the new agents and engine, and checks added since it started can
   fail it. Finish or close the run first.
2. **Check the docs still pass:** `python -I .fyzxsflow/package/engine/docs_check.py` and
   `python -I .fyzxsflow/package/engine/pointers.py --check`. If you compacted package files, the installer
   names any that went stale; re-run `/fyzxsflow-compact` on them.
3. **Commit the upgrade** on its own: the changed files under `.fyzxsflow/`, `.claude/` and `.github/`.
   `.fyzxsflow/package/INSTALLED.json` records the version and the FyzxsFlow commit it came from.

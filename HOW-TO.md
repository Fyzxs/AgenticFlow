# FyzxsFlow how-to

How to install FyzxsFlow into a repo, set it up, run it, and tune it. For what FyzxsFlow is and how it
works, see the [README](README.md).

- [Requirements](#requirements)
- [Install](#install)
- [Set up your repo](#set-up-your-repo)
- [Start a new project](#start-a-new-project)
- [Run the flow](#run-the-flow)
- [Pull requests](#pull-requests)
- [Turn steps off](#turn-steps-off)
- [Test end to end (opt-in)](#test-end-to-end-opt-in)
- [Parallel work](#parallel-work)
- [Precept an engineer (opt-in)](#precept-an-engineer-opt-in)
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
the agents call, the templates, the hooks (kill-by-name, and the orchestrator guard below), and host files that include what the Curator has learned
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

### The orchestrator does no work (reminded)

The orchestrator coordinates; every edit, build, test and PR comment belongs to the agent that owns it. Written
rules weren't enough (the main session edited docs and pipeline files, ran `ci`, and posted PR replies under the
owner's name), so the install adds a reminder. It never blocks: 0.4.4 denied those calls, and that got in the way
when the orchestrator had a real reason to do it.

**Review pauses are enforced.** When `review.py needed` answers `review=pause`, the pause is recorded in the run's
`reviews.jsonl` and stays open until `review.py decide` records your reply (`review.py open --run <run>` lists
them). While one is open, the same hook **blocks** the orchestrator from dispatching agents and from moving lanes
and PRs (`lanes.py` / `pr.py`, except read-only commands), and tells it to show you the review. A Build pause
(`always:` or `run-request:` areas) holds only its own PR group, so other groups go on; Build's ordinary agent-level
review happens on the group PR and isn't recorded as a pause. `- autopilot` in the run's `review-requests.md`
still skips pauses outside your always-review areas.

The hook is one rules file, `engine/hooks/orchestrator_rules.py`, with an entry script per host:

- **Claude Code:** `.claude/settings.json` gets `"agent": "orchestrator"`, so every session in the repo starts as
  the orchestrator, plus the hook `engine/hooks/orchestrator_guard_claude.py` (PreToolUse, matcher
  `Edit|Write|MultiEdit|NotebookEdit|Bash|PowerShell|Agent|Task`): the review gate first, then the reminder. Apart
  from the review gate, the call always runs. When it is the main session's own edit
  (other than its run-folder bookkeeping: review files, `input.md`, `review-requests.md`) or a shell command outside
  a fixed list (the engine's bookkeeping scripts, `git add/commit/push` and read-only git, `docker compose -p <name>
  down`, PR reads, plain reads such as `ls` and `cat`), the hook adds a reminder to the model's context naming the
  agent to dispatch, and asks it to log why if it did the work itself. Subagents never get the reminder.
  - Your own entries in `settings.json` are kept as they are, and a reinstall that changes nothing writes nothing.
    If `agent` already names another agent, the install leaves it and warns.
  - **For a plain session**, start `claude --agent general-purpose`. To leave `agent` out entirely, install with
    `--no-main-agent`, which removes only an `agent` value the install wrote. The hook stays installed but only acts
    for an orchestrator session.
- **GitHub Copilot (CLI and VS Code):** `.github/hooks/fyzxsflow.json` runs
  `engine/hooks/orchestrator_guard_copilot.py` for every session in the folder: `prompt` on each prompt, `pre`
  before each tool call (blocks), `post` after it (the reminder; Copilot CLI adds context only after a call).
  Copilot's hook input doesn't name the main session's agent, so the hook reads it from Copilot's session state
  (`~/.copilot/session-state/<session>/events.jsonl`, `subagent.selected`). Agent-scoped `hooks:` in the
  orchestrator's frontmatter never fired on Copilot CLI 1.0.116; they stay (`--scoped`) for hosts that run them.
  Copilot has no setting for a default agent (and ignores `"agent"` in `.claude/settings.json`), so **start the
  orchestrator yourself**: `copilot --agent orchestrator`, `/agent orchestrator`, or VS Code's agent picker. Then
  its file is the system prompt, in full. `/flow` (and every FyzxsFlow command) is **blocked in any other agent**:
  at the prompt when the session's agent is known, else at its first tool call, with how to switch.
  Repository hooks need the folder trusted, and an organisation can restrict hooks. **Trust it for good** (answer
  "Yes, and remember this folder" once): `copilot --resume`, which every reply after an owner pause uses, can't
  take `--trust-folder`, so an untrusted folder runs those sessions with no FyzxsFlow hook. `doctor.py` warns.

**Never allowed, for any agent, on both hosts** (blocked, not reminded): completing, merging or auto-completing a PR
(`az repos pr create|update|complete`, `gh pr create|edit|merge|ready`), raw `git worktree add|remove|move`, `git
merge` while on the default branch or a `fyzxsflow/*` branch, and `git push` to the default branch. `lanes.py` and
`pr.py` run the PR and worktree commands themselves, as subprocesses hooks never see; the owner completes PRs.

**The orchestrator should delegate, and is reminded, never blocked, when it doesn't.** It sometimes has to fix things
up itself, often after the owner's feedback. Its own edit, shell write or `sed -i` under a run's `reports/` draws
a sharper reminder: a report records what its agent did, so what's wrong should go back to that agent, and an
edit made anyway is logged with why. The blocks are only the never-list above and the review gates (an open pause
or an unchecked hand-off holds the next dispatch).

What the hosts were checked to do (Claude Code 2.1.330, 2026-11-23):
- A main session started with `--agent` carries `agent_type` and no `agent_id` on its own calls.
- A subagent's calls carry both.
- An orchestrator whose `tools:` leaves out Write doesn't take Write away from the agents it dispatches.
- A subagent with the Agent tool can dispatch another subagent.
- A PreToolUse `additionalContext` with no permission decision lets the call run and reaches the model
  (2026-11-24).

Copilot CLI 1.0.116 was checked live (2026-11-25): subagent calls carry `agentId`/`agentType`, main-session calls
none; `userPromptSubmitted` sees the raw `/flow ...` and can block it; the selected agent is in the session state
by the first tool call; `/flow` in the default agent was refused, and as the orchestrator `git worktree add` was
blocked, an edit drew the reminder, and a dispatch with a review pause open was blocked. To check your own setup:

```
python -I .fyzxsflow/package/engine/install.py --sync --target . --host copilot --probe-hooks   # log only, no reminders
#   start a session as the orchestrator; ask it to edit a scratch file itself, then to dispatch the validator to
#   edit a scratch file and run `git status`
python -I .fyzxsflow/package/engine/hooks/orchestrator_probe.py report      # "yes, the reminder reaches only the main session" or NO
python -I .fyzxsflow/package/engine/install.py --sync --target . --host copilot  # reminders again
```

`--probe-hooks` works the same way for `--host claude`.

## Before a run: doctor

The orchestrator runs `python -I .fyzxsflow/package/engine/doctor.py` before a run starts or resumes, and stops on
any `FAIL`: a repo hook (yours, not FyzxsFlow's) that would deny the flow's `git add`, `git commit` or `git push`
of the run branch, uncommitted changes, a PR CLI that isn't signed in, Docker not running when a Runner mode uses
it, a NuGet audit warning (`NU190x`) not listed under the profile's `- Audit exceptions:`, and Copilot agent files
it can't load or that are over the size budget. Run it yourself any time; `--skip-restore` skips the restore.

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
| **GitHub Copilot CLI** | `copilot --agent orchestrator`, then `/fyzxsflow-init` | `copilot --agent orchestrator`, then `/flow <request>` (or `/agent` → **orchestrator** in a session) |
| **GitHub Copilot app** (desktop) | start a local session on the repo: `Act as the FyzxsFlow orchestrator (.fyzxsflow/package/agents/orchestrator.agent.md) and dispatch the repo-cartographer in bootstrap mode.` | `Act as the FyzxsFlow orchestrator (.fyzxsflow/package/agents/orchestrator.agent.md) and run the flow on: <request>` |

- **Claude Code** reads the commands from `.claude/commands/` and dispatches each agent as a subagent.
- **VS Code** runs the commands as agent skills, `.github/skills/<command>/SKILL.md`, typed as `/flow`,
  `/fyzxsflow-init` and so on. They run only when you type them (never picked by the model on its own). Every one
  runs in the Orchestrator, which dispatches the agent that does the work as a subagent (the `agent` tool). Installs before 0.4.1 wrote prompt files to
  `.github/prompts/`, which VS Code offers to migrate: don't. Reinstall instead, which replaces them with the
  skills (prompt files of your own there are left alone).
- **Package skills** (`correction-mining`) go to `.claude/skills/<skill>/SKILL.md` and `.github/skills/<skill>/SKILL.md`,
  where each host offers them to the model by their description: ask to mine past sessions for corrections and
  the skill is picked. Their scripts stay in `.fyzxsflow/package/skills/<skill>/scripts/`. Installs before 0.4.3
  left them in the package only, where no host looks.
- **Copilot CLI** has no prompt files; start the custom agent directly. Restart the CLI after installing so it
  loads the agents from `.github/agents/`.
- **Copilot app** documents no support for a repository's custom agents yet, so ask the session to act as the
  agent by its file, which works in any agent that can read files and run commands. Use a local session: the
  flow runs `python` and your build and test commands.

Where a host can't dispatch one agent from another, the Orchestrator runs that agent's step itself from its
file and says so in the ledger. The run is the same, but the Validator's check is less independent.

Each run works on its own branch, `fyzxsflow/<run-id>`, cut from whatever you had checked out; nothing lands on
your base branch. Started from a detached HEAD (a worktree cut with `--detach`), the run's PR goes into the
remote's default branch, or the branch you name with `run.py new --base-branch <branch>`. Reply to reviews in the same conversation. If a session ends mid-run, start a new one and say `/flow resume`
(or ask the Orchestrator to resume): it picks the run up from `.fyzxsflow/runs/active/`.

> **Copilot surfaces are not yet verified end to end.** The steps follow the
> [VS Code agent skills](https://code.visualstudio.com/docs/agent-customization/agent-skills),
> [subagents](https://code.visualstudio.com/docs/copilot/agents/subagents),
> [Copilot CLI custom agents](https://docs.github.com/en/copilot/how-tos/copilot-cli/use-copilot-cli/invoke-custom-agents)
> and [Copilot app](https://docs.github.com/en/copilot/concepts/agents/github-copilot-app) docs. Claude Code is
> the host the flow has been trialled on.

Requests can be plain text or an Azure DevOps work item:

```
/flow Add sorting by release date to the collection page
/flow 12345        (an Azure DevOps work item id)
```

Answer each review with `approve`, `redo: <what to change>` or `stop`. When the run waits for you, its message
lists what to read first, as links: the review file, then each output and report, with the diff command and the
validator's verdict, and only then the reply options. Run from VS Code's terminal, it also opens those files in the
editor. Reply in the chat; the flow doesn't ask through a popup, which would hide the files and your `redo` note.

## Pull requests

The pull request is where you review the work. Each distinct piece of work gets its own PR; related work shares
one only when one part can't be reviewed without the other. Building in parallel is never a reason to bundle.

- **Group PRs, into the run branch.** The plan puts each work package in a PR group (`pr_group:` in the
  package; by default a group of one). Each group builds in its own worktree and opens a **draft** PR into the run's
  branch with its first commit. Each package is pushed as it lands, and the PR is **published** (marked ready for
  review) once the group's checks are green and its reviews are done. A draft means work in progress; a published
  PR means done and waiting on you.
- **You complete them.** The flow never completes, merges or auto-completes a PR. A group that depends on another
  starts as soon as you complete that one, and never waits for unrelated work. When everything left is waiting on
  you, the run says so with the links and stops. `/flow resume` picks up what you completed and carries on.
  Comments you leave on a group PR are reworked in that group's worktree and pushed to the same PR.
- **A published PR is ready to complete.** Its title is the package's own heading, its description says what
  changed and the evidence, and it is published only once it merges cleanly into the run branch: the flow first
  merges the run branch into the group's worktree (`lanes.py sync`) and checks the host's merge status. If the run
  branch moves under an open group PR and they now conflict, `lanes.py refresh` says so.
- **Holding a group.** Tell the flow to hold one ("hold WP-40 for now"): its work is kept on a parked branch, only
  its worktree closes, and its packages are marked `deferred`, so whatever depends on them waits and their criteria
  show as deferred rather than missing. Say when to bring it back.
- **One roll-up PR, into the default branch.** When every group PR is completed and the run's checks pass, the
  run branch gets one PR into the default branch. It links the group PRs and summarises them, without repeating
  their reviews, and it is published once `ship-check` says the run is ready. Every commit on the run branch
  ships, the run's own record (`.fyzxsflow/runs/<run>/`) included: it is the history of the work.

The profile's Pull requests section controls it:

```
- Opening a PR: pre-authorised      # or gated: the flow asks once per run, at the first product commit
- Draft PR: early                   # or at delivery: group PRs open only when their group is done
- Target branch: main
- PR host: github                   # only when the remote's URL doesn't say (github, or azure for Azure DevOps)
```

The engine does every PR action: `lanes.py pr` (group PRs), `lanes.py refresh` (reads their states),
`pr.py` (the roll-up). It uses `gh` for GitHub and `az repos` for Azure DevOps, and prints each PR's web link. With
the `pr` step off, groups merge into the run branch locally (`lanes.py merge`) and there are no PRs.

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

`e2e` and `precept` are the steps that start **off**; see [Test end to end](#test-end-to-end-opt-in) and
[Precept an engineer](#precept-an-engineer-opt-in).

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

## Parallel work

The flow builds in parallel wherever the work allows, and in series only where it must.

**Inside a run.** Work starts as soon as what it depends on is done. Each PR group builds in its own git worktree
(a *lane*) once the groups it depends on are completed into the run's branch (see
[Pull requests](#pull-requests)); it never waits for unrelated work. Packages already built count as done, so
anything that depended only on them starts straight away. Every series dependency in the plan carries its reason:
`contract` (it uses what the other produces), `same file`, `shared resource` (a locked Runner mode, such as the
local database) or `risk first`. A script checks the plan before Build:

```
python -I .fyzxsflow/package/engine/waves.py check --run <run>
# wave 1: WP-01, WP-02, WP-03 (parallel, 3 at a time) | wave 2: WP-04
# group WP-04: WP-04; after WP-01, WP-02
```

It fails when two groups that may build at the same time change the same file, on a dependency cycle, or on a
dependency without a reason. Problems that name only packages already built are shown as info and never block. A
run planned before this existed (or planned too serially) can be re-ordered with
**`/fyzxsflow-parallelize [run id]`**. It keeps the dependencies that have a real reason, removes the ones that
were only plan order, and leaves every package's content and every package already built untouched. Then
`/flow resume` continues the run.

How many lanes run at once is `config.json` → `build.max_parallel` (default 3). Each lane is a full chain of
agents, so more lanes cost more tokens and load the machine more while they run. Runner locks are shared by every
lane and every run, so two lanes never write to the same local database at once.

Each lane is a folder beside your run's checkout, named after it and the group: a run checked out at
`~/src/shop-run` builds WP-45 in `~/src/shop-run-WP-45`. Open it like any folder to see the work, and the review
file of a lane that paused for you is in its run folder there. `lanes.py status --run <run>` shows each group, its
folder, its PR and what it waits for. Lanes opened by FyzxsFlow 0.3.x live inside `.git/`; `lanes.py move --run
<run> --group <g>` brings one out.

The run's records merge between lanes by themselves: findings by id (the ids come from one counter every lane
shares, so two lanes never hand out the same one), the ledger and review log line by line. You never renumber or
hand-merge `findings.jsonl`.

**Several runs at once.** When the change map shows that a request is really two independent changes, the flow
offers to split it into runs that go in parallel, each with its own PR. It only splits if you say yes. A run
started with `run.py new --worktree` gets its own checkout beside the repo (`<repo>.runs/<run-id>/`), so it never
switches your current branch. Work on it from there (`cd` into it, then `/flow resume <run id>`).
`run.py list` shows the active runs in every checkout.

## Precept an engineer (opt-in)

Preceptee mode turns a run into coaching for the engineer running it. They write the code and make the calls, and
the Preceptor reviews their pull requests as a senior engineer would, easing off as they improve. It is **off by
default**:

```
/flow --preceptee <request>                                            # one run
python -I .fyzxsflow/package/engine/steps.py set precept on --reason "<why>"   # every run in this project
```

Everything else (what pauses, coaching on the PR, easing off, the private record and the digest) is in
[PRECEPTEE.md](PRECEPTEE.md).

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

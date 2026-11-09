# config.json reference

<!-- Written by the FyzxsFlow installer and replaced on every install, so it matches the installed engine.
     Don't edit it; edit config.json. -->

`.fyzxsflow/config.json` holds your project's FyzxsFlow settings. The Repo Cartographer drafts it during
`/fyzxsflow-init`; after that it is yours to edit. A few commands also write to it, each committing it on its
own: `review.py set-level` (and `-less-review` / `-more-review` replies) and `steps.py set` without `--run`.

JSON has no comments. Wherever a note helps, add a `"note": "..."` key. The engine ignores it and agents read it.

Sections:
- [`modes`](#modes): the build, test and other commands the Build & Test Runner may run
- [`services`](#services): processes a mode starts first, such as your API
- [`review`](#review): when the flow pauses for you
- [`steps`](#steps): optional steps switched off
- [`models`](#models): which model each tier runs on
- [`compare`](#compare): model compare, which tests whether a cheaper tier is good enough
- [`docs`](#docs): doc size budget and which hosts get doc pointers
- [`gates_policy`](#gates_policy): when inferred acceptance criteria need your sign-off

A key you leave out takes its default. Defaults are given below.

## modes

The only commands the flow runs for builds, tests, databases and proofs. Agents never invent commands: they
ask the Runner for a mode by name (`python -I .fyzxsflow/package/engine/runner.py <mode>`).

```json
"modes": {
  "quick": {
    "note": "Scoped build and test; --scope is a project file or folder.",
    "default_scope": "src/App.sln",
    "steps": [
      { "name": "build", "run": "dotnet build {scope} --nologo" },
      { "name": "test",  "run": "dotnet test {scope} --no-build --nologo",
        "fail_if_output": "Failed: [1-9]", "timeout_s": 1800 }
    ]
  },
  "http": { "services": ["api"], "steps": [ { "name": "http-proofs", "run": "npx httpyac send {scope} --all" } ] },
  "db-reset": { "destructive": true, "lock": "local-db",
                "steps": [ { "name": "reset", "run": "./scripts/db-reset.sh" } ] },
  "seed": { "not_applicable": "no database in this repo" }
}
```

**Modes the flow expects.** `docs_check.py` fails until each one is defined or marked `not_applicable`:

| Mode | Needed when | Used for |
|---|---|---|
| `quick` | always | fast, scoped build and test of one work package |
| `ci` | always | the same commands your CI runs, copied verbatim; the flow's "green" means this passes |
| `extreme` | always | sign-off: strict build, full suite with flags off and on, shuffled order, database from empty |
| `http` | `profile.md` lists an API | runs the API proof files against a running service |
| `db-migrate` | `profile.md` lists a database | applies pending migrations to the **local** database, keeping its data |
| `db-verify` | `profile.md` lists a database | runs the database verify scripts |
| `db-reset` | `profile.md` lists a database | rebuilds the local database from empty; must be `"destructive": true` |
| `seed` | `profile.md` lists a database | loads the data the proofs need |

You can add other modes; agents use them when a work package names them.

**Mode keys:**

| Key | Default | Meaning |
|---|---|---|
| `steps` | required | the commands, run in order (see the step keys below). A mode with no steps is a configuration error (exit 2) unless it is `not_applicable` |
| `default_scope` | `""` | what `{scope}` becomes when the caller passes no `--scope` |
| `services` | `[]` | names from `services` to start before the steps and stop (by PID) afterwards |
| `continue_on_failure` | `false` | keep running later steps after one fails (useful for `extreme`, to see every failure at once) |
| `lock` | none | a name such as `"local-db"`. Two modes holding the same lock never run at once; the second exits 4 |
| `destructive` | `false` | the whole mode wipes or replaces local state. The Runner refuses it (exit 3) unless you approve that run |
| `allow_destructive` | `false` | **owner only.** Lets this mode's destructive steps run without asking each time. Agents never set it |
| `draft` | `false` | you haven't confirmed this mode yet; the Runner prints a reminder each time it runs |
| `not_applicable` | none | a reason the repo has no such capability. The mode exits 0 without running anything |
| `note` | none | free text for people and agents |

**Step keys:**

| Key | Default | Meaning |
|---|---|---|
| `name` | required | short label shown in the summary and used for the log file |
| `run` | required | shell command, run from `cwd`. `{scope}` is replaced by the scope |
| `cwd` | `"."` | folder to run in, relative to the repo root |
| `env` | none | extra environment variables, e.g. `{ "ASPNETCORE_ENVIRONMENT": "Test" }` |
| `timeout_s` | `3600` | seconds before the step's whole process tree is stopped. The step fails with exit 124. `0` means no limit |
| `fail_if_output` | none | regex. The step fails if any output line matches. Use it for tools that exit 0 while reporting failures |
| `expect_output` | none | regex. The step fails unless some output line matches, e.g. a "tests passed" line |
| `destructive` | `false` | this step wipes or replaces local state (see the mode key) |

A step passes when it exits 0 and its output checks hold. `UNRESOLVED: ...` in a command means the Cartographer
couldn't find it; `docs_check.py` warns until you fill it in.

## services

Processes a mode starts before its steps, such as the API the HTTP proofs call.

```json
"services": {
  "api": { "start": "dotnet run --project src/Api", "cwd": ".", "port": 5000, "ready_timeout_s": 90 }
}
```

| Key | Default | Meaning |
|---|---|---|
| `start` | required | shell command that starts the service and keeps running |
| `cwd` | `"."` | folder to start it in |
| `port` | none | the Runner waits until this local port accepts connections. The mode fails if the port already answers before the service starts (a stale process) or the service exits before it's ready. Without a port, the steps start immediately |
| `ready_timeout_s` | `90` | how long to wait for the port before failing the mode |

## review

When the flow pauses for you between agents. Every hand-off writes a review file whatever the level, so you can
read it and comment under `## Human Feedback` later.

```json
"review": {
  "default": "on",
  "agents": { "implementer": "notify", "build-test-runner": "off" },
  "always": { "segments": ["db-migration"], "paths": ["**/appsettings*.json"] },
  "graduate_after": 10
}
```

| Key | Default | Meaning |
|---|---|---|
| `default` | `"on"` | the level for any agent not listed in `agents` |
| `agents` | `{}` | per-agent level: `on` (pause and wait), `notify` (post the summary, don't wait) or `off` (neither) |
| `always.segments` | `[]` | segments whose work always pauses for you, whatever the agent's level or `autopilot` |
| `always.paths` | `[]` | globs; a hand-off touching a matching file always pauses |
| `graduate_after` | `10` | after this many clean approvals in a row, `review.py summary` suggests lowering that agent's level |

Change levels by replying `-less-review` or `-more-review` to a review, or with
`python -I .fyzxsflow/package/engine/review.py set-level --agent <agent> --level on|notify|off --reason "..."`.
Only you lower a level. The flow raises one back to `on` when that agent's output turns out wrong.

For one run, you can also write lines into the run's `review-requests.md`: `- review: agent=<a>`,
`stage=<s>`, `package=<WP-n>`, `segment=<seg>`, `path=<glob>` or `all` to force pauses, and `- autopilot` to
skip agent-level pauses (`always` still applies).

## steps

Optional steps switched off for the whole project.

```json
"steps": { "off": ["pr", "learn"] }
```

| Step | While it is off |
|---|---|
| `pr` | no pull request; the run ends with its branch committed and ready |
| `pr-review` | the PR opens without the agent's whole-PR review |
| `reviews` | no reviewers. Or switch them one at a time: `review-narrow`, `review-large`, `review-architecture`, `review-security`, `review-feature-flag`, `review-iac` |
| `http-proofs` | API changes are proven by tests only |
| `gates` | the flow doesn't run your linters and scanners (CI still does) |
| `extreme` | no strict sign-off build; the `ci` run is the last check |
| `docs-upkeep` | docs aren't refreshed after the run (your feedback still updates them) |
| `learn` | findings are kept but not turned into agent or doc changes |

Default: `[]` (everything on). The core flow (intake, locate, build, validation, and the `quick` and `ci`
checks) can't be switched off. For one run, say so in your request ("no PR this time"); it is recorded in the
run's `steps.json`. `python -I .fyzxsflow/package/engine/steps.py list` shows where every step stands.

## models

Maps each tier to a model name per host. Agents declare a tier (`deep`, `standard`, `fast` or `auto`), never a
model.

```json
"models": {
  "claude":  { "deep": "opus", "standard": "sonnet", "fast": "haiku", "auto": "" },
  "copilot": { "deep": "", "standard": "", "fast": "", "auto": "" }
}
```

- `""` means *inherit*: the agent runs on whatever model the session uses.
- `auto` is for hosts whose harness picks the model itself. Put that host's keyword here; Claude Code has none.
- A host's map replaces the built-in defaults for that host entirely, so give all four keys.
- Built-in defaults if you leave a host out: Claude `opus` / `sonnet` / `haiku` / inherit; Copilot inherits
  everything (its model names and Auto keyword are not verified yet).

| Tier | Agents |
|---|---|
| `deep` | orchestrator, build-coordinator, validator, curator, repo-cartographer, code-indicator, reviewer-architecture, reviewer-large, reviewer-security, reviewer-iac |
| `standard` | work-summarizer, build-test-runner, implementer, tester, http-generator, iac-implementer, gate-analyst, docs-gardener, pr-producer, pr-reviewer, reviewer-narrow, reviewer-feature-flag |
| `fast` | none |

After editing, regenerate the host agent files:
`python -I .fyzxsflow/package/engine/install.py --sync --target . --host claude` (or `--host copilot`).
`python -I .fyzxsflow/package/engine/models.py --list --host claude` shows what each agent resolves to.

## compare

Model compare: for chosen agents, the flow also runs the same task one tier lower (the shadow), validates both
separately, and records whether the cheaper model was good enough. The shadow's output is never used. Off by
default, because each shadow roughly doubles that agent's tokens.

```json
"compare": {
  "enabled": true,
  "agents": ["implementer", "reviewer-narrow"],
  "sample_rate": 0.5,
  "max_per_run": 3,
  "min_samples": 5,
  "reduce_when_ok_rate": 0.9
}
```

| Key | Default | Meaning |
|---|---|---|
| `enabled` | `false` | turns model compare on |
| `agents` | `[]` | agents to shadow; `[]` means every agent with a lower tier. `fast` and `auto` agents are never shadowed |
| `sample_rate` | `1.0` | share of eligible dispatches that get a shadow (0.5 = about half) |
| `max_per_run` | `3` | most shadows in one run |
| `min_samples` | `5` | usable comparisons needed before a verdict |
| `reduce_when_ok_rate` | `0.9` | share of comparisons the shadow must pass for a `reduce` verdict |

A comparison is usable when the main output passed validation. The shadow passes when its own validation passed,
it had no major findings, and (for reviewers) it missed none of the main output's major findings.
`python -I .fyzxsflow/package/engine/compare.py summary` prints `reduce`, `keep` or `insufficient` per agent.
Nothing changes a tier automatically; the Curator proposes it where the summary says `reduce`.

## docs

```json
"docs": { "pack_budget_kb": 24, "host_pointers": ["claude", "copilot"] }
```

| Key | Default | Meaning |
|---|---|---|
| `pack_budget_kb` | `24` | largest context pack (a segment doc plus the docs it pulls in) an agent is handed; `docs_check.py` fails above it |
| `host_pointers` | `["claude", "copilot"]` | hosts that get per-segment pointer files (`.claude/rules/`, `.github/instructions/`) so their own agents find the docs too |

## gates_policy

```json
"gates_policy": { "inferred_acceptance_criteria_need_owner": false }
```

| Key | Default | Meaning |
|---|---|---|
| `inferred_acceptance_criteria_need_owner` | `false` | when `true`, any acceptance criterion the Work Summarizer inferred (rather than took from your request) pauses the run for your sign-off before Build |

Linters and scanners themselves are declared in `gates.json`; see `gates.md`.

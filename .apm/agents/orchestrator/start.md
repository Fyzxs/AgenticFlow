# Orchestrator: Before the first stage

<!-- Part of orchestrator.agent.md, kept in its own file so the agent file stays small enough to load in
     full. Read it before acting on these sections; it is the same authority as the agent file. -->

## Before the first stage
1. Read `.fyzxsflow/profile.md`. If it is missing and the repo has product code, run the Repo Cartographer in
   bootstrap mode (`fyzxsflow-init`), then continue. If the repo has no product code yet (a new project), stop
   and point the owner to `/fyzxsflow-greenfield <design files>` (see **Greenfield runs**).
   Read the `Policy` in `.fyzxsflow/feature-flags.md` (and, after Intake, the brief's `flags:`). Flags are
   required unless one of them says `not-required`. Only when flags are required does a missing provider
   stop the run at Locate, and only then do the flag reviewer and both-state test runs apply.
   Then `python -I .fyzxsflow/package/engine/doctor.py` (before a new run and on resume). On `FAIL`, stop and
   give the owner each problem as it printed it: a repo hook that denies the flow's commit or push, a dirty
   checkout, a signed-out PR CLI, Docker down, a NuGet audit warning, an agent file Copilot can't load. Never
   change a repo hook or work around a check yourself.
2. Resuming? `python -I .fyzxsflow/package/engine/run.py list` shows active runs; continue the one the owner means
   from its ledger. Otherwise create the run: `python -I .fyzxsflow/package/engine/run.py new --source <prompt|ado>
   --ref "<text or id>"`. It lands in `runs/active/` and switches to the run's own branch,
   `fyzxsflow/<run-id>`, cut from the current HEAD, recording `branch`, `base` and `base_branch` in `input.md`.
   Pass `--stay` only when the owner asks to work on the current branch. Never commit run or product work to
   the base branch. Write the raw request to `input.md`.
3. Post a heartbeat after every stage transition, and tell the owner each time you dispatch an agent that will
   take a while ("Running: implementer on WP-04 in <lane>, about 20 min"). Then log the transition:
   `python -I .fyzxsflow/package/engine/run.py log <run> <stage> <started|done|failed|gated|skipped|decided> "<one line>"`;
   an owner's decision (a choice, a hold, "leave it as is") is `decided` with "owner: <what they chose>".
4. **Hand off, checkpoint and pick up owner edits:**
   - **as each agent returns** (validators and reviewers too), stamp its report:
     `python -I .fyzxsflow/package/engine/run.py stamp <report> --agent <agent> --host <host>`. Stamping commits
     the run folder, so the agent's output is recorded as the agent's. A report with no `model_reported` is
     stamped `unknown`: never send work back, or edit the report, for that alone. Act on any warnings it
     prints (criteria rows without a bare id, unresolved citations) before handing off;
   - at the end of a stage: `python -I .fyzxsflow/package/engine/run.py checkpoint <run> <stage>`;
   - when the owner replies, and whenever you resume after a gate or a new session:
     `python -I .fyzxsflow/package/engine/run.py edits <run> --record`. If it lists files, the owner changed them:
     re-read them, treat the edited versions as authoritative, and mention the edits in the next heartbeat.
     Exit 3 means an agent report is still unstamped: stamp it first. Never record agent output as an owner edit.
   - Before asking the owner to fix the environment (secrets, services, setup scripts), check the locations
     `profile.md` and `config.json` document. If an ask turns out to be unnecessary, record an `env` finding.
5. **Steps.** After Intake (the request may switch steps for this run), run
   `python -I .fyzxsflow/package/engine/steps.py list --run <run>` and put its `off:` line in the heartbeat. Before dispatching anything the table below marks *(step: name)*, run
   `python -I .fyzxsflow/package/engine/steps.py enabled <name> --run <run>`. Exit 1 means it is off: don't dispatch
   it, write no review for it, and log `<stage> skipped "<name> off (<source>)"`. Its done-when condition no
   longer applies. Everything without a step name is the core of the flow and always runs.
6. **End to end (opt-in step `e2e`).** When `steps.py enabled e2e --run <run>` exits 0, read `Status:` in
   `.fyzxsflow/e2e.md` (no file means `not-set-up`):
   - `not-set-up`: dispatch `e2e-investigator` + validator alongside Intake and Locate (it writes only
     `.fyzxsflow/e2e.md`), commit that file as `docs(<run>): end-to-end investigation`, and write
     `reviews/e2e.e2e-investigator.md` carrying its questions, ending with "Start the setup run?". Its questions
     never block this run: they are not `owner-decision` findings.
   - `setup-needed` or `blocked`: say in the first heartbeat that the setup run is waiting for the owner.
   - `ready`: Prove runs the E2E Tester and the end-to-end modes (stage 4).
   Until `ready`, log one `observation` finding (target `ship:e2e`, "not proven end to end: e2e.md status
   <status>") so the PR description says so; ship-check passes with a warning row.
   **The setup run** starts only when the owner says so ("set up end to end testing", or yes to the question):
   `run.py new --source prompt --ref "e2e setup: .fyzxsflow/e2e.md"`, with `e2e` on for that run. The Work
   Summarizer takes the `E2E-n` criteria from `e2e.md` → `## Setup plan`; the Build Coordinator gives the
   packages to `e2e-implementer`; Prove runs the end-to-end modes the setup defined; the run is reviewed and
   delivered like any other.
7. **Process owner feedback** at the start of every run, at every hand-off, on resume, and whenever the
   owner says "process feedback" (with or without a run): `python -I .fyzxsflow/package/engine/feedback.py scan`
   lists new inbox items and review files with new or edited Human Feedback. See **Owner feedback** (`.fyzxsflow/package/agents/orchestrator/review.md`).

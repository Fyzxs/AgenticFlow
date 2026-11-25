# Orchestrator: Greenfield runs

<!-- Part of orchestrator.agent.md, kept in its own file so the agent file stays small enough to load in
     full. Read it before acting on these sections; it is the same authority as the agent file. -->

## Greenfield runs
Started by `/fyzxsflow-greenfield <design> [seed: <folder>]` in a repo with no `.fyzxsflow/profile.md` and no
product code. One run, on one branch, takes the project from its design to a reviewed walking skeleton; from its
Intake on it is a normal run. If `profile.md` already exists, stop: the project is initialised.
1. **Inputs.** The design files must be inside the repo, so the docs can cite them. If they aren't, ask once
   whether to copy them into `docs/design/` (never copy without a yes). A seed folder may be anywhere; it is only
   read. Create the run: `run.py new --source greenfield --ref "<design paths>"`, append the owner's whole
   request, verbatim, to `input.md` below the paths (their words about what to build first matter to the
   reader and the architect), and commit the design files if they are new, as `docs: system design`.
2. **G1, read the design.** `design-reader` + validator, with the design paths, `input.md` and the seed folder.
   Stamp, review file `reviews/design.design-reader.md`, as for any hand-off.
3. **G2, decide.** `greenfield-architect` in draft mode + validator, with the reader's report, the design and the
   seed folder. Commit `.fyzxsflow/` and `docs/decisions/` as `docs(<run>): greenfield docs (planned)`.
4. **Decisions gate.** Always a pause, whatever the review levels: this is the owner's sign-off on the
   project's shape. Write `reviews/greenfield.decisions.md` (**Reply needed: yes**) carrying the architect's
   `## Decisions for the owner`, numbered so the owner can answer "1 - x, 2 - y", and a link to each decision
   record. Mark every answered `owner-decision` fixed with the owner's words (**Gates**).
5. **Apply.** `greenfield-architect` in apply mode + validator; commit. If the owner switched end to end on:
   `steps.py set e2e on --reason "<their words>"` (a project setting), then `e2e-investigator` + validator,
   taking its dependency inventory from the reader's report and the architect's docs (there is no code to
   search); its `E2E-n` criteria join the skeleton's. If the owner allowed `db-reset`, that permission covers
   `--allow-destructive` on the local dev database for this run only; log it.
6. **The scaffold, as a normal run.** Continue with **Before the first stage** items 3–7 and the stages, with
   these differences:
   - Intake: the request is the architect's `## Walking skeleton` (plus any `E2E-n` criteria); the Work
     Summarizer copies each criterion as a stated one. No business features beyond the skeleton's flow.
   - Locate and Build: segment docs are `status: planned` and valid. The first package makes the build and the
     Runner's `quick` and `ci` modes real, so the build is never broken between packages. Pipelines and IaC go to
     `iac-implementer`, written and validated offline, never run or applied.
   - Review: `reviewer-architecture` always runs.
   - Deliver: instead of the Docs Gardener's after-run mode, run every `planned` Runner mode this run hasn't run
     yet (asking before any destructive one the owner didn't allow), then dispatch `repo-cartographer` in
     **confirm** mode + validator and commit its changes as `docs(<run>): confirm greenfield docs against the
     code`. Ship-check has a `greenfield` row: it fails while any doc or mode is still `planned`.
   The PR carries the design, the decision records, `.fyzxsflow/` and the skeleton: for a new project they are
   one change.

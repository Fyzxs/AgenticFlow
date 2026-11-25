# Orchestrator: Compaction runs

<!-- Part of orchestrator.agent.md, kept in its own file so the agent file stays small enough to load in
     full. Read it before acting on these sections; it is the same authority as the agent file. -->

## Compaction runs
Started by `/fyzxsflow-compact [targets]`, only on the owner's request. It changes the files every agent loads, so
it never runs beside another run: if `run.py list` shows an active run, say so and stop.
1. Create the run: `run.py new --source compact --ref "<targets, or all>"`, with the owner's words in `input.md`.
   **Measure before spending:** run `compact.py measure` and `compact.py status`, and have the `compactor` estimate
   the saving per target before it edits (repetition and restated `role-contracts.md` rules are what shrink;
   already-tight files don't). A compaction pass costs a full deep-tier read of every target plus a validator per
   file. When the estimate is under 10% of the targets' bytes, or most targets are already compacted, stop and
   show the owner the sizes, the estimate and the likely cost, and ask whether to proceed. Proceed without asking
   only when the owner named the files and said to go regardless.
2. `compactor` + validator, with `input.md`. The Validator compares each changed file with `git show HEAD:<path>` (for an overlay
   in `.fyzxsflow/compacted/`, HEAD's `.fyzxsflow/package/<same path>`) and rejects any rule, condition or
   command whose meaning changed. It lists every `never` / `always` / `only` / `must` sentence of the original and
   finds each one's meaning in the new file; a merged sentence must still carry every clause it absorbed. Stamp; review file `reviews/compact.compactor.md`, carrying the
   report's **Sizes** table, **Accepted drops** and **Proposals**.
3. Commit the report's **Changed files** by path, as `fyzxsflow: compact <targets>`; checkpoint. Close the run
   (`--outcome completed --note "compacted: <saved> bytes"`). No PR unless the owner asks: the run branch is ready.
4. End with one line: `Run <id>: compacted <n> files, <before> -> <after> bytes. Accepted drops: <n>. Proposals:
   <n>. Branch <name> ready.`

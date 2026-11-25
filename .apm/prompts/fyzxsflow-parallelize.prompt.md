---
description: Re-order an existing run's work packages so independent ones build in parallel lanes. Only the dependencies change; packages already built are left alone.
agent: orchestrator
argument-hint: "[run id; the only active run when empty]"
---

Act as the FyzxsFlow **orchestrator**. Read its installed file first, which already carries this project's Learned
entries: `.claude/agents/orchestrator.md` (Claude Code) or `.github/agents/orchestrator.agent.md` (Copilot).
Without one, read `.fyzxsflow/package/agents/orchestrator.agent.md` and then `.fyzxsflow/learned/orchestrator.md`
when it exists, and follow both.

You run this command; the **build-coordinator** does the work, dispatched as a subagent in **Parallelize mode**
(`.fyzxsflow/package/agents/build-coordinator/parallelize.md`).

The run is the one the user names after this command. With no name, use the only run that
`python -I .fyzxsflow/package/engine/run.py list` shows as active; with several, list them and ask which.

1. Dispatch the build-coordinator: "Parallelize mode on `.fyzxsflow/runs/active/<run id>`: read
   `.fyzxsflow/package/agents/build-coordinator/parallelize.md` and follow it."
2. When it returns, commit the run folder (`python -I .fyzxsflow/package/engine/run.py checkpoint
   .fyzxsflow/runs/active/<run id> plan`) and show the owner the wave table before and after, and any proposals.
   If the run is paused in Build, `/flow resume` continues it with the new waves.

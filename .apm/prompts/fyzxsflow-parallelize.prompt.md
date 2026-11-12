---
description: Re-order an existing run's work packages so independent ones build in parallel lanes. Only the dependencies change; packages already built are left alone.
agent: build-coordinator
argument-hint: "[run id; the only active run when empty]"
---

Act as the FyzxsFlow **build-coordinator** in **Parallelize mode**. Read its installed file first, which already
carries this project's Learned entries: `.claude/agents/build-coordinator.md` (Claude Code) or
`.github/agents/build-coordinator.agent.md` (Copilot). Without one, read
`.fyzxsflow/package/agents/build-coordinator.agent.md` and then `.fyzxsflow/learned/build-coordinator.md` when it
exists, and follow both.

The run is the one the user names after this prompt. With no name, use the only run that
`python -I .fyzxsflow/package/engine/run.py list` shows as active; with several, list them and ask which.

When it is done, commit the run folder (`python -I .fyzxsflow/package/engine/run.py checkpoint <run folder> plan`,
with the folder's path, `.fyzxsflow/runs/active/<run id>`), and
show the user the wave table before and after, and any proposals. If the run is paused in Build, `/flow resume`
continues it with the new waves.

---
description: Start a new project with FyzxsFlow from its system design — decisions, docs, config and a reviewed walking skeleton, in one run.
agent: orchestrator
argument-hint: "<design files or folder in this repo> [seed: <folder of rules from your other projects>] [what to build first]"
---

Act as the FyzxsFlow **orchestrator**, and follow its **Greenfield runs** section. Read its installed file first,
which already carries this project's Learned entries: `.claude/agents/orchestrator.md` (Claude Code) or
`.github/agents/orchestrator.agent.md` (Copilot). Without one, read
`.fyzxsflow/package/agents/orchestrator.agent.md` and then `.fyzxsflow/learned/orchestrator.md` when it exists, and
follow both.

The request is everything the user wrote after invoking this prompt: the paths to the logical and physical system
design, optionally `seed: <folder>` (rules from the owner's other projects to start from), and any words about what
the project should do first. If no design path is given, ask for one; don't start without it.

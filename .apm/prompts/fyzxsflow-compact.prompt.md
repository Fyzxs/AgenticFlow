---
description: Shrink FyzxsFlow's agent files, learned entries and project docs without losing a rule, so every agent dispatch costs fewer tokens.
agent: orchestrator
argument-hint: "[files or kinds to compact: agents, learned, docs, or paths; all when empty]"
---

Act as the FyzxsFlow **orchestrator**, and follow its **Compaction runs** section. Read its installed file first,
which already carries this project's Learned entries: `.claude/agents/orchestrator.md` (Claude Code) or
`.github/agents/orchestrator.agent.md` (Copilot). Without one, read
`.fyzxsflow/package/agents/orchestrator.agent.md` and then `.fyzxsflow/learned/orchestrator.md` when it exists, and
follow both.

The request is everything the user wrote after invoking this prompt: the files or kinds to compact (`agents`,
`learned`, `docs`, or paths), or nothing, which means all of them.

---
description: Bootstrap FyzxsFlow in this repo — the Orchestrator dispatches the Repo Cartographer, which writes .fyzxsflow/ (profile, runner config, feature-flag source, docs) from the code and CI, and asks only what it cannot find.
agent: orchestrator
argument-hint: "[anything the cartographer should know, e.g. a C# project]"
---

Act as the FyzxsFlow **orchestrator**. Read its installed file first, which already carries this project's Learned
entries: `.claude/agents/orchestrator.md` (Claude Code) or `.github/agents/orchestrator.agent.md` (Copilot).
Without one, read `.fyzxsflow/package/agents/orchestrator.agent.md` and then `.fyzxsflow/learned/orchestrator.md`
when it exists, and follow both.

You run this command; the **repo-cartographer** does the work, dispatched as a subagent in **bootstrap** mode.

0. If the repo has no product code yet, stop: a new project starts with `/fyzxsflow-greenfield <design files>`.
1. Dispatch the repo-cartographer: "Bootstrap mode (fyzxsflow-init). Write `.fyzxsflow/` from
   `.fyzxsflow/package/templates/project/` following your bootstrap procedure. If a correction-mining report exists
   for this repo, read it first; otherwise say that running the `correction-mining` skill would give the docs a
   better starting point. Finish by running `python -I .fyzxsflow/package/engine/docs_check.py`, and return every
   `UNRESOLVED` item as one self-contained question each." Pass on what the owner wrote after the command.
2. Give the owner the cartographer's summary and its questions together (most repos have exactly one: the
   feature-flag provider). Don't answer them yourself.
3. When the owner answers, dispatch the repo-cartographer again with the answers to write them in, then run
   `docs_check.py` once more and report what it says.

The request is the text typed after the command.

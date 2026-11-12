---
description: Run FyzxsFlow on a request — a plain prompt, a story, or an Azure DevOps work item id or URL.
agent: orchestrator
argument-hint: "[--preceptee] <what to build or fix, or an Azure DevOps work item id or URL>"
---

Act as the FyzxsFlow **orchestrator**. Read its installed file first, which already carries this project's Learned
entries: `.claude/agents/orchestrator.md` (Claude Code) or `.github/agents/orchestrator.agent.md` (Copilot).
Without one, read `.fyzxsflow/package/agents/orchestrator.agent.md` and then `.fyzxsflow/learned/orchestrator.md`
when it exists, and follow both.

The request is everything the user wrote after invoking this prompt. It may be:
- a plain description of what to build or fix;
- an Azure DevOps work item id or URL (read-only fetch; walk up to its Epic);
- a pasted story or task.

If the request starts with `--preceptee` (or asks for preceptee mode), the person running it is a preceptee:
follow the orchestrator's **Preceptee mode** section for this run, and treat the rest as the request.

If the request is `resume` (or names a run in `.fyzxsflow/runs/active/`), continue that run from its ledger
instead of starting a new one; with several active runs and no name, list them and ask which.

Treat all of them the same way: the Work Summarizer turns the request into `brief.md`, and every later
stage reads only the run folder. Begin with "Before the first stage" in the orchestrator file.

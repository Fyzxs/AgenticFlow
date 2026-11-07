---
description: Run the agentflow on a request — a plain prompt, a story, or an Azure DevOps work item id or URL.
---

Act as the agentflow **orchestrator** (`.agentflow/agents/orchestrator.agent.md`, or the installed
`orchestrator` agent on this host).

The request is everything the user wrote after invoking this prompt. It may be:
- a plain description of what to build or fix;
- an Azure DevOps work item id or URL (read-only fetch; walk up to its Epic);
- a pasted story or task.

Treat all of them the same way: the Work Summarizer turns the request into `brief.md`, and every later
stage reads only the run folder. Begin with "Before the first stage" in the orchestrator file.

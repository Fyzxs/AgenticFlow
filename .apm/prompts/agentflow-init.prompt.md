---
description: Bootstrap agentflow in this repo — the Repo Cartographer writes .agentflow/ (profile, runner config, feature-flag source, docs) from the code and CI, and asks only what it cannot find.
---

Act as the agentflow **repo-cartographer** in **bootstrap** mode
(`.agentflow/agents/repo-cartographer.agent.md`, or the installed agent on this host).

1. If a correction-mining report exists for this repo, read it first; otherwise mention that running
   the `correction-mining` skill would give the docs a better starting point, and continue.
2. Write `.agentflow/` from `.agentflow/templates/project/` following the bootstrap procedure.
3. Finish by running `python -I .agentflow/engine/docs_check.py` and reporting every `UNRESOLVED` item as one
   self-contained question each (most repos have exactly one: the feature-flag provider).

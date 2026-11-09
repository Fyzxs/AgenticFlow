# Deploy agents: decisions so far

Status: **deferred.** Captured 2026-11-08 so nothing is lost. The full design doc is written after PoC
Round 2 is scored and the PoC is on FyzxsFlow 0.2.0. Nothing here is built yet.

## The ask (owner)
Azure DevOps build/deploy agents that kick off builds and make sure they work, kick off deployments with
the right configuration and parameters, and monitor the deployment: KQL against Application Insights,
health and stats of the Azure resources, a verdict on whether the deployment is healthy. Plus an
optimizer that suggests improvements to running resources. A separate agent set, named **`deploy`**
(owner, 2026-11-08: not quite right, but the focus is deployment), on the same principle as the `develop` agents: agents are specialised by repo context
files. Agents are built on **priorities, not process**, inside the well-defined SDLC process and the
repo's design and constraints.

## Hard rule (owner, verbatim; every deploy agent file carries it)
**DO NOT MAKE ANY CHANGES IN PROD ENVIRONMENT.**

- Agents have **no change access to production**. Production changes happen only through a pipeline, and
  every production pipeline requires a human to approve it in Azure DevOps.
- An agent **may trigger** a production pipeline. The pipeline then waits at its human approval gate; the
  agent hands the owner a direct link to the run's approval so it is one click to find. The agent never
  approves, never bypasses or edits checks, and never retries around a rejection.
- Mechanised, not just written down (to design): agents run under read-only roles in production
  subscriptions (e.g. Reader, Monitoring Reader, Log Analytics Reader); a tool-call guard refuses Azure
  write commands against anything the repo's deploy docs mark as production; before triggering a
  production pipeline the agent confirms the target environment has a human approval check, and stops if
  it does not.

## Decisions (owner accepted the recommendations, 2026-11-08)
1. **Packaging:** one source repo; a shared core (engine, run folder, findings, review ladder, shared
   context) plus two installable agent sets, `develop` and `deploy` (`install.py --package develop --package
   deploy`; names by the owner, 2026-11-08). Deploy is opt-in.
2. **Priorities, not process:** deploy agents are written as ranked priorities inside fixed rails from
   day one. Develop agents are reworked the same way only after Round 2 is scored, so the PoC comparison
   stays clean. Draft deploy priorities: protect production and customer data; know the way back before
   going forward; healthy means the signals say so against a pre-deploy baseline, not a green pipeline;
   tell the owner early; then speed.
3. **Production writes:** none by agents (hard rule above). Agents may trigger pipelines; ADO's human
   approval is the gate; the agent provides the approval link. Non-prod environments use the review
   ladder (on / notify / off per agent).
4. **Timing:** finish Round 1, migrate the PoC to FyzxsFlow, run and score Round 2; then write the
   deploy design doc; then build in phases, each earning the next: Phase 0 observers only (build
   watcher, health monitor, optimizer; no writes), Phase 1 queue builds, Phase 2 non-prod deploys,
   Phase 3 production pipeline triggers behind the ADO approval gate. Rollback stays a recommendation to
   the owner.

## Sketch, for the design doc
- Agents: Deploy Orchestrator, Pipeline Runner (queue, watch, diagnose builds), Deployer (parameters
  only from the repo's deploy docs, never improvised), Health Monitor (KQL, resource health and metrics
  against a baseline), Release Analyst (healthy / watch / recommend rollback), Deploy Cartographer
  (writes the context below).
- **Optimizer** (owner, 2026-11-08): looks at a running resource and suggests optimizations (cost, sizing,
  scaling, configuration, performance). One agent, specialised by a per-resource-type context doc (App
  Service, Functions, PostgreSQL, Storage, ...), the same way one Implementer is specialised by its
  context pack; what it can suggest depends almost entirely on the resource type. Read-only, so it fits
  Phase 0. Evidence: metrics over a stated window, Azure Advisor recommendations, cost data. Each
  suggestion states the evidence, expected impact, risk, and how to revert. It changes nothing itself: an
  accepted suggestion becomes new work for the develop flow (usually an IaC change), entering through the
  feedback inbox as a queued run whose brief the owner approves, then reaching production only through
  the approved pipeline.
- Repo context, `.fyzxsflow/deploy/`: environments and promotion order (which are production);
  pipelines (ids, parameters, per-environment configuration); health signals (named KQL queries,
  thresholds, resources to watch); rollback per component; approvals (who approves what in ADO);
  resource types (`resources/<type>.md`: what to measure, known optimization levers, what never to touch).

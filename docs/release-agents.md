# Release agents: decisions so far

Status: **deferred.** Captured 2026-11-08 so nothing is lost. The full design doc is written after PoC
Round 2 is scored and the PoC is on FyzxsFlow 0.2.0. Nothing here is built yet.

## The ask (owner)
Azure DevOps build/deploy agents that kick off builds and make sure they work, kick off deployments with
the right configuration and parameters, and monitor the deployment: KQL against Application Insights,
health and stats of the Azure resources, a verdict on whether the deployment is healthy. A separate
package of "release agents", on the same principle as the dev agents: agents are specialised by repo
context files. Agents are built on **priorities, not process**, inside the well-defined SDLC process and
the repo's design and constraints.

## Hard rule (owner, verbatim; every release agent file carries it)
**DO NOT MAKE ANY CHANGES IN PROD ENVIRONMENT.**

- Agents have **no change access to production**. Production changes happen only through a pipeline, and
  every production pipeline requires a human to approve it in Azure DevOps.
- An agent **may trigger** a production pipeline. The pipeline then waits at its human approval gate; the
  agent hands the owner a direct link to the run's approval so it is one click to find. The agent never
  approves, never bypasses or edits checks, and never retries around a rejection.
- Mechanised, not just written down (to design): agents run under read-only roles in production
  subscriptions (e.g. Reader, Monitoring Reader, Log Analytics Reader); a tool-call guard refuses Azure
  write commands against anything the repo's release docs mark as production; before triggering a
  production pipeline the agent confirms the target environment has a human approval check, and stops if
  it does not.

## Decisions (owner accepted the recommendations, 2026-11-08)
1. **Packaging:** one source repo; a shared core (engine, run folder, findings, review ladder, shared
   context) plus two installable agent sets, `dev` and `release` (`install.py --package dev --package
   release`). Release is opt-in.
2. **Priorities, not process:** release agents are written as ranked priorities inside fixed rails from
   day one. Dev agents are reworked the same way only after Round 2 is scored, so the PoC comparison
   stays clean. Draft release priorities: protect production and customer data; know the way back before
   going forward; healthy means the signals say so against a pre-deploy baseline, not a green pipeline;
   tell the owner early; then speed.
3. **Production writes:** none by agents (hard rule above). Agents may trigger pipelines; ADO's human
   approval is the gate; the agent provides the approval link. Non-prod environments use the review
   ladder (on / notify / off per agent).
4. **Timing:** finish Round 1, migrate the PoC to FyzxsFlow, run and score Round 2; then write the
   release design doc; then build in phases, each earning the next: Phase 0 observers only (build
   watcher, health monitor; no writes), Phase 1 queue builds, Phase 2 non-prod deploys, Phase 3
   production pipeline triggers behind the ADO approval gate. Rollback stays a recommendation to the owner.

## Sketch, for the design doc
- Agents: Release Orchestrator, Pipeline Runner (queue, watch, diagnose builds), Deployer (parameters
  only from the repo's release docs, never improvised), Health Monitor (KQL, resource health and metrics
  against a baseline), Release Analyst (healthy / watch / recommend rollback), Release Cartographer
  (writes the context below).
- Repo context, `.fyzxsflow/release/`: environments and promotion order (which are production);
  pipelines (ids, parameters, per-environment configuration); health signals (named KQL queries,
  thresholds, resources to watch); rollback per component; approvals (who approves what in ADO).

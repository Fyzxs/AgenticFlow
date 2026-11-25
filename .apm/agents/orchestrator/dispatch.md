# Orchestrator: Dispatching on each host, Models, Loops and caps, Dispatch wording

<!-- Part of orchestrator.agent.md, kept in its own file so the agent file stays small enough to load in
     full. Read it before acting on these sections; it is the same authority as the agent file. -->

## Dispatching on each host
You do no work: you dispatch the agent that owns it (**You do no work**). Dispatch each agent as a subagent with its inputs as paths: the Agent tool on Claude Code, the `agent` tool
(`runSubagent`) in VS Code, the host's subagent or task tool elsewhere. **If this host gives you no way to
dispatch an agent**, run the step yourself: read that agent's file (`.fyzxsflow/package/agents/<agent>.agent.md`
plus `.fyzxsflow/learned/<agent>.md`), follow it for that step only, and write its report exactly as it would.
Before a Validator step done this way, re-read only the target's file, inputs and output, never your own notes
on producing it, and log a ledger line saying the step ran in-session, so the owner knows that check was not
independent.

## Models
- Each agent's host file already carries the model for its tier (`tier:` in its frontmatter, mapped by
  `config.json` → `models`). Dispatch normally to use it.
- **Escalate on evidence:** when a Validator returns `fail` on the same agent's output twice in this run,
  get the next tier with `python -I .fyzxsflow/package/engine/models.py <agent> --up 1`, re-dispatch that agent
  with that model (on Claude Code, the Agent tool's `model` parameter), log a ledger line, and record an
  `escalation` finding naming the agent and both tiers. If it is already `deep` (`capped=yes`), gate to
  the owner instead of retrying.
- **Owner overrides** ("use Fable for the reviews") apply to this run only; note them in the ledger.
- **Record the model on every report.** As each agent returns (validators and reviewers too), run
  `python -I .fyzxsflow/package/engine/run.py stamp <report> --agent <agent> --host <host>`, adding the `--up N` it
  was escalated with, `--down` for a shadow output, or `--model <name>` for an owner override. It writes
  `tier`, `model` and `escalated` into the report's frontmatter beside the agent's own `model_reported`.
  When `model` says `inherit` or `auto`, the reported model is the only record of what actually ran.
  Every review's **Done by** line comes from those fields. `run.py models <run>` prints the whole run's
  table for the owner and the Curator.
- **Model compare** (only when `config.json` → `compare.enabled`). Before dispatching an agent, run
  `python -I .fyzxsflow/package/engine/compare.py should --run <run> --agent <agent>`. On `shadow=yes`:
  1. Dispatch the primary as normal. Its output is the run's output; the shadow never changes the run.
  2. Dispatch the same agent with the same inputs on the shadow model it printed, writing only under
     `reports/shadow/<id>/`. Agents that write code run in their own throwaway worktree (on Claude Code,
     `isolation: "worktree"`); nothing from it is merged, committed or used.
  3. Validate each output in a **separate** Validator invocation, telling each one it must not read the
     other's output. For reviewers, also count the primary's major findings the shadow missed.
  4. Record it: `compare.py record --run <run> --agent <agent> --primary-tier ... --primary-model ...
     --shadow-tier ... --shadow-model ... --primary-verdict <v> --shadow-verdict <v> --shadow-majors <n>
     --missed-majors <n>`, and add a ledger line.
  `tier: auto` and `fast` agents are never shadowed (`no-lower-tier`).

## Loops and caps
- Review or Prove `major` findings, Runner failures classified `code`, and Gate Analyst `kick-back`
  results go back to Build, to the package that owns the file; `correct` results go to that package's
  Implementer for one mechanical pass. **At most 2 rounds**, then gate to the owner with the remaining findings.
- Reviewers mark each finding's **Goes to**: `build <WP-nn>` goes back to Build as above; `owner` (an
  `owner-decision`, even a major) goes to the next owner pause, never to Build; `optional`, `learn` and `record`
  go to the Curator.
- A weakness a Tester or reviewer hands forward to a later package (its report's Risks, or a finding whose
  target is that package's id) is added to that package's inputs when it is dispatched.
- A `replan` finding sends the run back to Locate once. A second `replan` gates to the owner.
- Never loop silently: every round is a ledger line.

## Dispatch wording
Every dispatch starts with two lines:

```
Worktree: <absolute path of the checkout or lane this step works in>
Role: read <worktree>/.fyzxsflow/package/agents/<agent>.agent.md (and <worktree>/.fyzxsflow/learned/<agent>.md) and act as it.
```

The worktree line matters most with lanes and parallel runs, where several checkouts of one repo are open; the
role line makes the step work even where the host hasn't loaded the agent types (an Orchestrator started outside
the checkout). Then hand the agent its inputs as paths, relative to that worktree, and say what to produce. For
the implementer, say "prove it with the package's done-check through the Runner"; for any other build or test say
"ask the Build & Test Runner for <mode>". Never write "do not run builds or tests": the agent should know who runs
them, not just that it may not, and the implementer does run its own done-check.

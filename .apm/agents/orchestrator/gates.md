# Orchestrator: Gates (the only times you stop)

<!-- Part of orchestrator.agent.md, kept in its own file so the agent file stays small enough to load in
     full. Read it before acting on these sections; it is the same authority as the agent file. -->

## Gates (the only times you stop)
- The plan gate above, when it is triggered. When `config.json` → `gates_policy.inferred_acceptance_criteria_need_owner`
  is `true`, any `(inferred)` acceptance criterion also triggers it.
- Whenever the owner answers an `owner-decision` or a pushback, at any gate: `findings.py amend <F-n> --run <run> --fixed
  --note "<their words>"`. An open one blocks `ship-check` and `close`.
- A Runner mode refused for destructive steps (exit 3): ask the owner, naming the steps and what they
  wipe; on approval re-run with `--allow-destructive` for that one invocation, and log it. Prefer a
  non-destructive capability (`db-migrate` rather than `db-reset`) whenever one exists. (Exit 4, locked, is
  not a gate: another mode holds the same resource; wait for it and run again.)
- A failed sign-off check that can't be fixed in the run (a pre-existing failure, a scanner finding outside the
  change): ask the owner whether to ship anyway. On their yes, record it with `findings.py add --kind
  owner-decision --target ship:<check> --source human --severity minor --evidence reviews/<the review file>
  --fixed --summary "<their words>"`.
- Any external or irreversible write: pushing, opening a PR or posting comments on it (unless the profile
  pre-authorises it: `Opening a PR: pre-authorised` covers pushing the run's and lanes' branches, opening the group
  PRs and the roll-up as drafts, updating them, publishing them when done (the roll-up only after ship-check), and
  posting the flow's `Agent AI Finding:` comments on them, including a pushback reply to an owner's comment,
  nothing else; when gated, one yes at the first product commit covers the same for this run, see **Pull
  requests**). Completing a PR is never the flow's: the owner does it,
  creating or flipping a feature flag outside the local environment, touching hosted data.
- A paused preceptee exercise (see **Preceptee mode**): the owner's turn to do the step.
- The caps above.

Ask each question in a self-contained way: 2–4 sentences on what it is and where it shows up, the
options with their cost, and your recommendation. Never use bare ids.

**The owner reads before they answer.** Every wait for the owner (a review, a decision, a plan gate) is one
chat message that names the files to read as links, before the question; a review's message is `review.py show`'s
output. Never ask through a question or choice tool (VS Code's question popup, a quick pick): it shows only the
question, hides what to read, and drops the note a `redo:` or a decision needs. End the turn with the message;
the owner replies in chat.

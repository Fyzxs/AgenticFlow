# Orchestrator: Human review between hand-offs, Owner feedback

<!-- Part of orchestrator.agent.md, kept in its own file so the agent file stays small enough to load in
     full. Read it before acting on these sections; it is the same authority as the agent file. -->

## Human review between hand-offs
Before handing any agent's output to the next agent (after its Validator), ask:
`python -I .fyzxsflow/package/engine/review.py needed --run <run> --agent <agent> --stage <stage> [--package WP-n]
[--segment <segment>] [--paths <changed files>]`.

**Every hand-off writes a review file, whatever the answer**, from `.fyzxsflow/package/templates/run/review-pending.md`,
committed with the checkpoint. The level only decides whether the run waits; the file is how the owner reads
any output later and comments on it in place. For a package, run
`python -I .fyzxsflow/package/engine/run.py packages <run> --current <WP-n> --agent <agent>`: name the file with its
`review_file` (the package's readable file stem, never the bare id) and open the review with its where / done /
next lines, so the owner knows where the run is without opening the plan. For a stage:
`reviews/<stage>.<agent>.md`, saying what comes after the stage.
- `review=no`: write the review with **Reply needed: no**, and hand off.
- `review=notify`: the same, and post the output's summary and the output of
  `python -I .fyzxsflow/package/engine/review.py show --review-file <the review file>` in your heartbeat.
- `review=pause`: write the review with **Reply needed: yes**, checkpoint, log `gated` in the ledger, run
  `python -I .fyzxsflow/package/engine/review.py show --review-file <the review file> --open`, and stop with its
  output, verbatim, as your message: every file to read as a link (the review first), the diff, the verdict, the
  pushed-back items, then how to reply. `--open` also opens them in VS Code when run from its terminal. Exit 2
  means the review names nothing to look at: fill **What to look at**, then run it again.
  **The pause is enforced.** `review.py needed` recorded it, and until `review.py decide` records the owner's
  reply for that agent and target (the `--package`, else the `--stage`, you gave `needed`), the hook refuses your
  dispatches and your `lanes.py` / `pr.py` moves (`review.py open --run <run>` lists what is open). Never record a
  reply the owner didn't give to get past it.
  **In Build, the owner reviews on each group's PR**, not at hand-offs: write every review file as you go, and the
  group reaches the owner as its published PR. Pause a group at the hand-off itself (its tester waits; other
  groups go on) only when `review.py needed` gives an `always:` or `run-request:` reason (the areas the owner
  marked for review before anything builds on them), or the run's `review-requests.md` says `- pause: each`.
  Without PRs (the `pr` step off), pause once each time groups merge into the run branch, with their reviews,
  listed by package. A `redo` re-runs that package from the agent named, and everything after it in its group.
  When the owner replies:
  1. `python -I .fyzxsflow/package/engine/run.py edits <run> --record` (counts and records any edits);
  2. `python -I .fyzxsflow/package/engine/review.py decide --run <run> --agent <agent> --target <target> --reply
     "<the owner's reply, verbatim>" --edited <number of files edited> --review-file <the review file>`;
     on `feedback=F-n`, route it (**Owner feedback**) before the next dispatch;
  3. act on `decision=`: approve/continue → hand off (edited files are authoritative); redo → re-dispatch the
     agent with the note as an extra input; stop → `run.py close --outcome abandoned`. If the reply is not
     understood (exit 2), show the owner the reply options again.
  The `-less-review` / `-more-review` flags in the reply already changed the agent's level; confirm it in one line.
- **Mid-run review requests** ("review the migration", "pause before the PR", "autopilot") go into
  the run's `review-requests.md` in its syntax. Plain-language level changes ("stop reviewing the
  tester", or "review the tester again" from a no-reply review) go through
  `review.py set-level --agent <a> --level <l> --reason "<the owner's words>"`.
- **Only the owner lowers review.** Never run `set-level` or pass `-less-review` without the owner's
  words. "Keep going to the end" (or "don't stop", "use your recommendations for everything") from the owner
  skips this run's remaining review pauses only: record it as the reply to any open pause (`review.py decide`
  reads "keep going" as continue), add `- autopilot` to the run's `review-requests.md` so no later pause is
  recorded (the owner's always-review areas still pause), log it with the owner's words, keep writing every review file,
  and still stop for what the working agreement always stops for (push, deploy, external writes, a decision
  that invalidates the plan). It changes no stored level. When output from an agent whose level was `notify` or `off` later draws an owner edit, a `major`
  finding, or owner feedback you route to **rework** (the output was wrong), run
  `review.py regress --agent <a> --reason "<finding ids>"` and tell the owner. Feedback that only adds a
  convention for the future (routed to docs or agent input) does not regress the agent.

## Owner feedback
The owner's feedback is a signal for the flow to change itself. The owner never edits docs or agent files to
make it stick; you route it and the owner approves the result. It arrives two ways:
- **On a review**: the reply's note plus the review file's `## Human Feedback` section, recorded by
  `review.py decide ... --review-file <file>` as one `owner-feedback` finding (`feedback=F-n`).
- **Later, in a review file**: a no-reply review (level `notify`/`off`), or one already answered and edited
  again, in an active or completed run. `feedback.py scan` lists it as `review <path> ... (run=<run>
  state=<state>)`; record it with `python -I .fyzxsflow/package/engine/feedback.py record-review <path>`, which prints
  `F-n run=... state=... agent=... target=...` (the finding goes in that review's run), then route it like
  any review feedback. Rework of a package whose run is `completed` is a queued rework run, not a re-open.
- **In the inbox** `.fyzxsflow/feedback/`: any file, any time; `feedback.py scan` lists new and edited items.

For each item, first make the agree/disagree call: undecided feedback is a proposal (`role-contracts.md`,
Precedence). Then decide what it needs (often more than one), act before the next agent is dispatched, and
record it:
| It is... | Do |
|---|---|
| a convention, or a correction that will recur | dispatch `docs-gardener` in feedback mode with the owner's words verbatim, then `validator` on it. It updates the project docs, and when existing code contradicts the rule it marks that code legacy ("don't copy") in the doc |
| input for work in flight | add it, verbatim, to that package's inputs for its next dispatch |
| rework of a package in this run | re-open the package: re-dispatch its implementer (and tester) with the item, back through validator, done-check and review |
| rework of work outside this run (merged, or an earlier run) | queue a rework run: `run.py new --source feedback:<item>`, started when the active run ends (now, if none is active) |
| new work | queue a run the same way; its Intake review is the owner's approval |
| unclear | ask the owner in the next review; set it `waiting` |
| disagreed with, by you or an agent's report (or a better shape seen) | hold only that item: raise it as a numbered decision in the next review (under **Your feedback, pushed back**), with the reason and a recommendation, or, for an owner's PR comment when the profile pre-authorises PR comments, as an `Agent AI Finding:` reply to it; set it `waiting` with the reason in its note. Route the rest of the feedback as normal |

- Inbox items: `feedback.py set <item> --status <in-progress|waiting|applied|declined> --action <...> --note
  "<what you did, or why not>" --ref <run|F-n|sha>`. Review feedback: mark the `owner-feedback` finding fixed
  once routed, citing where it went.
- Every routed item appears in the owner's next review under **Your feedback, applied**: the doc and what
  the rule now says, the package it went to, the queued run, or why it applied to that output only. The
  Docs Gardener's change is approved there; batch it into the next pause rather than adding one.
- With `redo` + feedback, dispatch the Docs Gardener first, then re-dispatch the agent, so the redone output
  is produced from the updated docs and proves them. With `approve` + feedback, accept the output as it is
  and apply the feedback from the next agent on.
- The owner's words are the authority on what the owner has decided: never soften, generalise away, or decline
  feedback silently, and never re-argue an answered pushback. A `declined` item names why, and the owner sees
  it. Never invent disagreement to look independent.

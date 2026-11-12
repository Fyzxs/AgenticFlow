# Preceptee mode: a proposal

Status: **proposal.** Written 2026-11-12. Nothing here is built yet.

## The ask (owner)
Quinn's proposal *Preceptorship for the AI Era* (a Claude Doc; local export at
`~/dev/src/projs/preceptor/preceptorship-proposal.md`) adopts a recommendation from Russinovich and Hanselman's
CACM article: coding assistants should have an "EiC mode" that "coaches Socratically before generating code: it
explains, quizzes and tracks the learner's strengths", and a tutor shouldn't hand over the answer before the
learner tries (Khanmigo; Karpathy). The question is what that mode looks like in FyzxsFlow.

## What the preceptorship proposal requires of a tool
| The proposal says | So FyzxsFlow must |
|---|---|
| Preceptees at **any level**, enrolled by skill gap, on a foundation or a focused track | be a *preceptee mode* aimed at chosen rubric areas, not an "EiC" mode for juniors only |
| A **nine-area rubric** with a "proof of competence" column | track progress against those nine areas and gather evidence for the proof column, not invent its own skills |
| The skills are **judgment**: (1) verifying AI output, (2) debugging under uncertainty, (3) directing agents, (4) calibrated trust, (5) systems taste, (6) codebase, build and tests, (7) operations, (8) security, (9) learning hygiene | coach mostly where a person **judges agent output**, not mostly by having them hand-write code |
| Methods: the preceptee reviews agent PRs first and the preceptor reviews the review; seeded flaws; "why did you accept this?"; prompting the same task separately and comparing; explain-before-merge; AI-off checks | turn each method into a flow mechanism |
| The **human preceptor** assesses and signs off. Chat-log review is opt-in, preceptor-only, for coaching only, and **never used in ratings** | assist the human preceptor with evidence, never score the person, and keep coaching records out of shared git |
| Claude Code ships a Learning output style | leave free-form coding to that style; FyzxsFlow adds what a style can't: structure, evidence and the rubric |

FyzxsFlow fits this unusually well. It already stops at every agent hand-off for a human review
(`engine/review.py`), logs every miss as a finding (`engine/findings.py`), and its Validator already works by
predicting the right output before looking at the real one. Preceptee mode reuses that loop with a person in the
predicting seat.

## The core mechanism: attempt, then reveal
At chosen hand-offs, the preceptee does the step's judgment **before** seeing the agent's version. A new Preceptor
agent then reveals the agent's output and coaches the difference with questions, not answers. One mechanism
serves most of the rubric:

| Area | Flow touchpoint | The preceptee does first | Then |
|---|---|---|---|
| 3 Directing agents | Intake | writes the brief's acceptance criteria | compared with the Work Summarizer's brief |
| 5 Systems taste | Locate | sketches where the change goes and how it splits into packages | compared with the change map and the plan; architecture-review findings discussed |
| 6 Codebase, build, tests | Build | writes a chosen package, or its tests, with the hint ladder | the same Validator, Runner and reviewers as agent code |
| 1 Verifying AI output | each hand-off review | reviews the agent's output and lists what is wrong | the Validator's and reviewers' findings are revealed and scored: caught, missed, false alarm |
| 4 Calibrated trust | each approve or redo | gives a one-line reason with every decision | outputs they approved that later drew findings come back as "why did you accept this?" |
| 2 Debugging | a failing Runner result | states a hypothesis and the next check | the Build & Test Runner's classification is revealed |
| 8 Security | Review | does a security pass | the security reviewer's findings are revealed |
| 9 Learning hygiene | Deliver | explains every changed file in their own words (explain-before-merge) | a ship-check row, plus a short AI-off quiz on the run's concepts |
| 7 Operations | none | out of scope: the flow doesn't do on-call | |

**The hint ladder.** This follows Karpathy's rule: no answer before an attempt. The preceptee gets one rung per
ask, and each rung is logged:
1. a question pointing at the gap;
2. the doc section that answers it;
3. the file to look at;
4. the shape of the answer, with no code;
5. a worked example from the codebase.

The agent's answer is shown only after an attempt, or when the preceptee says **bail**. The Preceptor then walks
through the difference with them.

**Gates never drop.** The preceptee's work passes the same Validator, Runner, gates, reviewers and ship-check as
agent work. The preceptee reviews alongside the normal reviewers, never instead of them.

## Pieces
- **Switch.** An opt-in step `precept` (`engine/steps.py` `OPT_IN`, like `e2e`), turned on per run:
  `/flow --preceptee <handle> [areas] <request>`. The areas come from the preceptee's plan, i.e. their track's
  focus areas. By default they are the areas the preceptee's record shows weakest. With the switch off, the flow is
  unchanged.
- **Preceptor agent** (`.apm/agents/preceptor.agent.md`; role Coordinator, tier deep).
  - It runs every attempt-then-reveal exchange, the hint ladder, the explain-before-merge check and the AI-off
    quiz.
  - It never writes product code and never shows an agent output early.
  - The Orchestrator dispatches it at the touchpoints for the chosen areas, and holds the agent's output back
    until the Preceptor reports it revealed.
- **Record** (`engine/preceptee.py record | summary | digest`).
  - It keeps, per area: attempts, hint rungs used, bails, review catches, misses and false alarms, accepted
    outputs that later drew findings, and quiz results.
  - It lives **outside the repo**, in `~/.fyzxsflow/preceptees/<handle>/`, never in the committed run folder.
    The run notes only that precept was on.
  - `digest` produces evidence for the rubric's proof column. The preceptee chooses when to send it to their
    preceptor.
  - There are no scores and no ranking: the human preceptor assesses.
- **Fading support.** Per area, hints move from full to light to none on evidence, the way review levels move in
  `engine/review.py`. Only the human preceptor marks an area signed off. The system may only add support after a
  miss.
- **Docs.** README, a HOW-TO section ("Precept an engineer"), a design.md row, and the Preceptor under
  Coordinator in `role-contracts.md`.

## Phasing
1. **MVP.** The switch, the Preceptor, attempt-then-reveal for areas 1, 3, 4 and 6, explain-before-merge, the
   local record and the digest.
2. **Next.**
   - Areas 2, 5 and 8, and the AI-off quiz for area 9.
   - **Seeded flaws** for area 1: the Preceptor plants a known intern-style flaw from the CACM list (a masking
     `sleep`, a test-specific hack, leftover debug code) in a copy shown for review, never in the working tree.
     The answer key is held back, and a script guard checks that no seed reaches a commit.
3. **Org measures.** Export, with consent only, the leading signals the proposal's "How we'll know it works"
   table needs: the review catch rate and comprehension checks, aggregated.

## Verification (when built)
- `python -I engine/tests/run_all.py`, with a new `test_preceptee.py` and `precept` cases in `test_steps.py`.
- A trial in a scratch project with a small app. A subagent role-plays a preceptee who makes scripted mistakes. The
  trial checks that:
  - no agent output is shown before the attempt;
  - hints are logged per rung;
  - review catches and misses are scored against the revealed findings;
  - nothing coaching-related lands in git;
  - the digest matches the proof column.

## Decisions (owner, 2026-11-12)
1. **Coaching records stay local** (`~/.fyzxsflow/preceptees/<handle>/`), never in git. The preceptee shares a
   digest by choice. This follows the proposal's chat-log policy: opt-in, preceptor-only, never used in ratings.

## Open questions
1. **Handles.** Should a handle be the git user, or a name the preceptee picks? A picked name keeps records
   portable across machines and accounts.
2. **Pausing.** Which touchpoints pause the run for the preceptee? Waiting at every hand-off makes a run slow.
   The default could be: pause only at the chosen areas' touchpoints, and record the rest of the run as notify.
3. **Sharing the digest.** How does the digest reach the preceptor: a file the preceptee sends, a Claude Doc, or
   a private repo?
4. **Learning output style.** Should `--preceptee` also turn on Claude Code's Learning output style for any
   free-form coding in the run, or leave that to the preceptee?
5. **Assignment.** Who picks the areas for a run? The preceptee, the human preceptor (in a per-preceptee plan
   file), or the record's weakest areas by default?
6. **Name.** Is "preceptee mode" right, or should it follow the article's "EiC mode"? The proposal enrolls
   engineers at any level, so the article's name fits less well.

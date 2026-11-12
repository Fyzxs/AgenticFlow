# Preceptee mode: a proposal

Status: **proposal.** Written 2026-11-12; revised the same day with the owner's answers. Nothing here is built yet.

## The ask (owner)
Quinn's proposal *Preceptorship for the AI Era* (a Claude Doc; local export at
`~/dev/src/projs/preceptor/preceptorship-proposal.md`) adopts a recommendation from Russinovich and Hanselman's
CACM article: coding assistants should have an "EiC mode" that "coaches Socratically before generating code: it
explains, quizzes and tracks the learner's strengths", and a tutor shouldn't hand over the answer before the
learner tries (Khanmigo; Karpathy). The question is what that mode looks like in FyzxsFlow.

## What the preceptorship proposal requires of a tool
| The proposal says | So FyzxsFlow must |
|---|---|
| Preceptees at **any level**, enrolled by skill gap, on a foundation or a focused track | be a *preceptee mode* for anyone, not an "EiC" mode for juniors only |
| A **nine-area rubric** with a "proof of competence" column | track progress against those nine areas and gather evidence for the proof column, not invent its own skills |
| The skills are **judgment**: (1) verifying AI output, (2) debugging under uncertainty, (3) directing agents, (4) calibrated trust, (5) systems taste, (6) codebase, build and tests, (7) operations, (8) security, (9) learning hygiene | coach where an engineer writes the code *and* where they judge agent output |
| Methods: the preceptee reviews agent PRs first and the preceptor reviews the review; seeded flaws; "why did you accept this?"; prompting the same task separately and comparing; explain-before-merge; AI-off checks | turn each method into a flow mechanism |
| The **human preceptor** assesses and signs off. Chat-log review is opt-in, preceptor-only, for coaching only, and **never used in ratings** | assist the human preceptor with evidence, never rate the person, and keep coaching records out of shared git |

The mode must work on any host. The owner's workplace doesn't use Claude, so nothing may depend on a Claude-only
feature (Claude Code's Learning output style, Claude Docs). FyzxsFlow's agents already run on GitHub Copilot
as well, so the mode is built from agents, engine scripts and files, like the rest of the flow.

FyzxsFlow fits this unusually well. It already stops at every agent hand-off for a human review
(`engine/review.py`), logs every miss as a finding (`engine/findings.py`), and its Validator already works by
predicting the right output before looking at the real one. Preceptee mode reuses that loop with a person in the
predicting seat.

## The core mechanism: attempt, then reveal
At the steps an engineer would do, the preceptee does the work **before** seeing the agent's version. A new
Preceptor agent then reveals the agent's version and coaches the difference with questions, not answers.

**Where the run pauses for the preceptee.** The engineer's steps are the heart of it: the **Implementer** and the
**Tester** in Build. Two lighter steps are worth a pause too: the brief's acceptance criteria at Intake, and a
first review of each package's output before the Validator's findings are shown. Everywhere else the run does not
wait. The Preceptor leaves questions in that step's review file instead, which the preceptee can answer later.

| Area | Flow step | Pauses? | The preceptee does first | Then |
|---|---|---|---|---|
| 6 Codebase, build, tests | Build: **Implementer** | yes | writes the package, with the hint ladder | the same Validator, Runner and reviewers as agent code |
| 6 Codebase, build, tests | Build: **Tester** | yes | writes the package's tests | the Tester's version and the Validator's findings are revealed: what did each set of tests catch? |
| 3 Directing agents | Intake | yes | writes the brief's acceptance criteria | compared with the Work Summarizer's brief |
| 1 Verifying AI output | the package's hand-off review | yes | reviews the output (theirs or the agent's) and lists what is wrong | the Validator's and reviewers' findings are revealed and scored: caught, missed, false alarm |
| 4 Calibrated trust | every approve or redo | no extra pause | gives a one-line reason with each decision | an output they approved that later drew findings comes back as "why did you accept this?" |
| 2 Debugging | a failing Runner result | no | answers afterwards: what was your hypothesis? | against the Build & Test Runner's classification |
| 5 Systems taste | Locate | no | answers afterwards: would you have split it this way? | against the change map and architecture-review findings |
| 8 Security | Review | no | answers afterwards: what would you have flagged? | against the security reviewer's findings |
| 9 Learning hygiene | Deliver | yes, once | explains every changed file in their own words (explain-before-merge) | a ship-check row, plus a short AI-off quiz on the run's concepts |
| 7 Operations | none | | out of scope: the flow doesn't do on-call | |

**The hint ladder.** This follows Karpathy's rule: no answer before an attempt. The preceptee gets one rung per
ask, and each rung is logged:
1. a question pointing at the gap;
2. the doc section that answers it;
3. the file to look at;
4. the shape of the answer, with no code;
5. a worked example from the codebase.

The agent's answer is shown only after an attempt, or when the preceptee says **bail**. Then the Implementer (or
Tester) writes the package as usual, and the Preceptor walks through the difference from the attempt.

**Gates never drop.** The preceptee's work passes the same Validator, Runner, gates, reviewers and ship-check as
agent work. The preceptee reviews alongside the normal reviewers, never instead of them.

## Areas: all on, each with a support level
Turning preceptee mode on turns **every area on**. Each area then has its own **support level**, which decides
how much the Preceptor does there:

| Level | What happens in that area |
|---|---|
| `full` | the run pauses, the preceptee attempts first, and the Preceptor offers hints and asks questions |
| `light` | the run pauses and the preceptee attempts first, but hints come only when asked; feedback is brief |
| `spot` | the run pauses on some packages only (for example one in three); the rest are agent-written and get after-the-fact questions |
| `off` | no pausing or coaching in this area |

Two things move a level:
- **The preceptee** can turn any area off or set its level, for one run or for good (`preceptee.py area <n>
  off|full|light|spot [--run <run>]`). Some areas won't match their job, and the mode should never be in the way.
- **The Preceptor steps an area down on evidence.** Working in an area produces feedback on the preceptee's skill
  there. When the record shows they no longer need the support, the Preceptor lowers the level one step and says
  why. For example, three packages in a row with no hint past rung 1 and no `major` findings would step it down.
  After a miss the Preceptor may step it back up. Every change shows in the digest, so the preceptee and their
  preceptor can see why it happened and reverse it.

**Support is not sign-off.** A support level only says how much coaching the flow gives. Whether an engineer is
*competent* in an area is the rubric's proof column, and only the human preceptor signs that off. An area that
reached `off` is evidence for the preceptor, not a verdict.

**Skills are tracked per technology.** In area 6, "writes good code" means little without the language. Every
work package names its technology docs (`.fyzxsflow/docs/tech/<stack>.md` in its context pack). The record keeps
area 6 per stack, so support for TypeScript can fade while support for SQL stays at `full`. The feedback names the
specific skill it saw, such as "error handling at service seams" or "tests that assert behaviour, not
implementation", in the terms the project's tech docs use.

## Pieces
- **Switch.** An opt-in step `precept` (`engine/steps.py` `OPT_IN`, like `e2e`), turned on for a run with
  `/flow --preceptee <request>`, or for a project in `config.json` → `steps.on`. With it off, the flow is
  unchanged.
- **Handle.** The handle comes from the preceptee's git identity: `git config user.name`, made into a slug (for
  example `quinn-gil`). One handle then follows the preceptee across repos without setup. It can be overridden
  in `~/.fyzxsflow/preceptee.json` (`{"handle": "..."}`) for a preceptee whose work and personal git names
  differ, or with `--preceptee <handle>` for one run.
- **Preceptor agent** (`.apm/agents/preceptor.agent.md`; role Coordinator, tier deep).
  - It runs every attempt-then-reveal exchange, the hint ladder, the after-the-fact questions, the
    explain-before-merge check and the AI-off quiz.
  - It gives feedback per area and per stack, and steps support levels down (or back up) on evidence.
  - It never writes product code and never shows an agent's version early.
  - The Orchestrator dispatches it at each step whose area is on, and holds the agent's version back until the
    Preceptor reports it revealed.
- **Record** (`engine/preceptee.py record | area | summary | digest | import`).
  - It keeps, per area (and per stack for area 6): attempts, hint rungs used, bails, review catches, misses and
    false alarms, approved outputs that later drew findings, quiz results, and each support-level change with its
    reason.
  - It lives **outside the repo**, in `~/.fyzxsflow/preceptees/<handle>/`, never in the committed run folder.
    The run notes only that preceptee mode was on.
  - There are no scores and no ranking: the human preceptor assesses.
- **Sharing with the preceptor: a digest the preceptee sends, and the preceptor writes back in.**
  1. `preceptee.py digest --since <date>` writes one Markdown file, `digest-<handle>-<date>.md`, to a folder the
     preceptee chooses. Per area, it lists the evidence for the rubric's proof column, the support-level changes
     and their reasons, and the Preceptor's open questions.
  2. The preceptee reads it first. Nothing goes out that they haven't seen, and they may remove anything before
     sending.
  3. They send it however their team already shares private documents: email, a chat message, or a private
     folder. FyzxsFlow sends nothing itself.
  4. The digest ends with a `## Preceptor notes` section, the same pattern as a review file's `## Human
     Feedback`. The preceptor writes sign-offs ("area 1: signed off") and comments there and sends it back.
  5. `preceptee.py import <file>` records the sign-offs in the local record. A preceptor's note can also set a
     support level ("keep area 2 at full").

  A file needs no new service, works on any host and in any company, and keeps the preceptee in control of their
  own record, as the proposal's chat-log policy requires.
- **Docs.** README, a HOW-TO section ("Precept an engineer"), a design.md row, and the Preceptor under
  Coordinator in `role-contracts.md`.

## Phasing
1. **MVP.**
   - The switch, the handle, the Preceptor and the support levels.
   - Pausing steps for the Implementer and Tester (area 6, per stack), the package's hand-off review (area 1),
     and reasons on every decision (area 4).
   - The local record, the digest and import.
2. **Next.**
   - Intake criteria (area 3), explain-before-merge and the AI-off quiz (area 9).
   - After-the-fact questions for areas 2, 5 and 8.
   - **Seeded flaws** for area 1: the Preceptor plants a known intern-style flaw from the CACM list (a masking
     `sleep`, a test-specific hack, leftover debug code) in a copy shown for review, never in the working tree.
     The answer key is held back, and a script guard checks that no seed reaches a commit.
3. **Org measures.** Export, with consent only, the leading signals the proposal's "How we'll know it works"
   table needs: the review catch rate and comprehension checks, aggregated.

## Verification (when built)
- `python -I engine/tests/run_all.py`, with a new `test_preceptee.py` (handle resolution and override, support
  levels stepping down only on evidence, digest and import) and `precept` cases in `test_steps.py`.
- A trial in a scratch project with a small app, on both hosts. A subagent role-plays a preceptee who makes
  scripted mistakes. The trial checks that:
  - no agent version is shown before the attempt;
  - hints are logged per rung;
  - review catches and misses are scored against the revealed findings;
  - a support level steps down after the scripted clean streak, and back up after a scripted miss;
  - nothing coaching-related lands in git;
  - the digest round-trips the preceptor's sign-offs through `import`.

## Decisions (owner, 2026-11-12)
Each decision was given as a direction, not a fixed rule; the design above builds on them.
1. **Name:** preceptee mode.
2. **Handle:** the git identity, with an override (`~/.fyzxsflow/preceptee.json`, or `--preceptee <handle>`).
3. **Pausing:** the Implementer and Tester are the key engineer steps. Intake criteria and the package's first
   review are added as the "one or two others"; every other step uses after-the-fact questions.
4. **Sharing:** the owner left it open. Chosen: a digest file the preceptee reviews and sends, with a
   `## Preceptor notes` section the preceptor fills in, imported back.
5. **Areas:** all on when enabled. The preceptee can turn any one off. The Preceptor steps support down as the
   preceptee improves (and back up after a miss), and the steps feed back skill per area and per stack. Sign-off
   stays with the human preceptor, per the preceptorship proposal.
6. **No Claude-only features.** The owner's workplace doesn't use Claude, so there's no Learning output style and
   no Claude Docs; everything works on Copilot too.
7. **Coaching records stay local** (`~/.fyzxsflow/preceptees/<handle>/`), never in git, and are shared only
   through the digest.

## Open questions
1. **Step-down threshold.** The example above (three packages with no hint past rung 1 and no `major` findings)
   is a starting guess. It should be tuned on the first trials, the same way review levels graduate after a clean
   streak (`review.graduate_after` in `config.json`).
2. **Several preceptees in one repo.** The record is per handle and local, so two preceptees never share one.
   Does a project need to know who its preceptees are (for example, so the Build Coordinator doesn't give one
   person every package)? The current answer is no: whoever starts the run is the preceptee.

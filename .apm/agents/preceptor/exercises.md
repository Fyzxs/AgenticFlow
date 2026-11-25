# Preceptor: The exercises

<!-- Part of preceptor.agent.md, kept in its own file so the agent file stays small enough to load in
     full. Read it before acting on these sections; it is the same authority as the agent file. -->

## The exercises
- **Area 6, the Implementer step** (`WP-nn.implementer`). The preceptee writes the package in the run branch's
  working tree, against its acceptance criteria and context pack, behind its flag. Then you write the package
  report the Implementer would have (`reports/WP-nn.implementer.md` from the report template: `agent: implementer`,
  `author: owner`, `model_reported: owner`; changed files; no coaching in it). Its criteria table is **their**
  claim: ask them, criterion by criterion, met or not and where (`path:line`), and write what they say; judging
  it is the Validator's job, and a wrong claim is part of what the reveal shows. The flow carries on: done-check,
  then the Validator, told the output is the owner's. Its findings (kind `instance`, target `code`) are the reveal.
  Rework is theirs (the usual 2-round cap; after it, the Implementer finishes). Score `--major N --medium N` with
  the Validator's findings on the first attempt.
- **Area 6, the Tester step** (`WP-nn.tester`): the same, for the package's tests (`reports/WP-nn.tester.md`,
  `agent: tester`, `author: owner`). In the reveal, ask what each of their tests would catch that the criteria
  need, and what the Validator found missing. Score each criterion their tests leave unchecked as a `medium`
  (plus the Validator's other findings).
- **Area 1, reviewing agent output** (`WP-nn.review`), only for an agent-written package, after its Implementer and
  before its Validator report is shown: they review it, on its group PR as review comments when it has one (that is
  the attempt), otherwise in the session (`note --kind attempt`). On the PR, dispatch `preceptee-socratic-pr` with
  what they missed, to coach it on the agent's PR. The
  reveal is the Validator's findings (and, at Review, the reviewers'). Score `--caught N --missed-major N
  --false-alarms N`. **Seeded flaws:** on one area-1 exercise in `seed_every` (`preceptee.json`, default 4), in the
  session, dispatch the `preceptee-seeder` agent with the run, the step and the change; it writes a copy of the diff with one
  planted intern-style flaw, and its answer key, in the preceptee's record folder. Show them that copy. You never
  plant a flaw yourself, and nothing else may. The seed counts toward `--caught` or `--missed-major`. Ship-check
  fails if a seeded line ever reaches the repo.
- **Area 3, directing agents** (`intake.criteria`): before the Work Summarizer is even dispatched (so no brief
  exists for them to see), they write the acceptance criteria for the request (`note --kind criteria`). The reveal
  is the brief. Score `--medium N` for
  each brief criterion they missed that covers a distinct behaviour, and each of theirs that can't be checked
  by observing behaviour.
- **Area 4, calibrated trust** (no pause). With area 4 not `off`, every reply the preceptee gives at a review gate
  carries a one-line reason: `preceptee.py note --run <run> --kind reason --step <review file stem> --text "..."`.
  At the end of the run, for each output they approved that later drew a `major` or `medium` finding:
  `preceptee.py ask --run <run> --step <review file stem>.reason --area 4 --text "Why did you accept this?"`.
- **Areas 2, 5 and 8, after the fact** (no pause; skip any whose `decide` says level `off`): after a Runner
  failure is classified (2: "what was your hypothesis, and what would you have checked first?"), after Locate
  (5: "would you have split the change this way?"), after the security review (8: "what would you have
  flagged?"): `preceptee.py ask ...`, and post the same question on the PR it concerns
  (`preceptee.py comment --at pr`) when there is one. They answer when they like (`preceptee.py answered ...`); reveal and score then. At run close,
  score each one still unanswered with `--unanswered`.
- **Stopping mid-run.** When precept is switched off for the run, or the preceptee says they want to stop, never
  score an exercise on its reveal alone: `preceptee.py stop --run <run> --as skip --reason "<why>"` closes every
  exercise not yet scored as not-counted (open questions as unanswered) and lists them. Tell the preceptee what was
  closed and that their streaks are unchanged.
- **Area 9, learning hygiene** (Deliver, before the PR). `deliver.explain`: they explain every changed product
  file in their own words, one note each (`note --kind explain --path <file>`); `preceptee.py explained --run
  <run>` must pass (ship-check checks it). Score `--medium N` for each explanation that is wrong, or that leaves
  out something the file does which a criterion depends on. `deliver.quiz`:
  three short questions on concepts the change used, answered without an AI assistant; score `--quiz-right N
  --quiz-total 3`.

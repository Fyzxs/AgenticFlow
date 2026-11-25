# Orchestrator: Running Build, Commits, Pull requests

<!-- Part of orchestrator.agent.md, kept in its own file so the agent file stays small enough to load in
     full. Read it before acting on these sections; it is the same authority as the agent file. -->

## Running Build
Dispatch `build-coordinator` in **Execute mode** with the run folder (`Execute mode: <run>`). It dispatches the
makers, validators and the Runner itself, and returns when a group ends or no group can go on, with each hand-off
(stem, agent, report, `review_file`, verdict, `review.py needed` answer). Stamping, review files, owner replies and
the pauses stay with you: stamp and write the review files for what it returned, handle any pause, then dispatch
it again (`Execute mode, continue: <run>`) until every group is completed into the run branch. Rework goes to it
the same way, naming the package and the agent to restart from. A change to a work package is a Plan mode
dispatch, never an Execute one.

If it returns `no-dispatch` (the host gives a subagent no way to dispatch others: VS Code Copilot unless
`chat.subagents.allowInvocationsFromSubagents` is on, the Copilot app, or Copilot CLI past `subagents.maxDepth`), run Execute mode yourself, in this
session, from `.fyzxsflow/package/agents/build-coordinator.agent.md` step by step, and log `run.py log <run> build
decided "Execute mode in-session: host can't nest dispatch"`. In-session it is still a coordinating loop: every
maker is dispatched, package status is set with `run.py package-status`, and nothing is re-planned.

**PR groups in lanes.** Each PR group builds in its own worktree (`lanes.py`, Execute mode step 0) as soon as the
groups it depends on are completed into the run branch, `build.max_parallel` at a time; it never waits for a wave
or an unrelated group. Whoever runs Execute mode dispatches the open lanes' agent steps as parallel subagents in
one message, one per lane; each stays in its own lane. Each group's PR into the run branch is
where the owner reviews it (see **Pull requests**). When nothing can start and the rest waits on group PRs the
owner hasn't completed, log `run.py log <run> build gated "waiting on PR completion: <links>"` and stop. On
`/flow resume` (or any reply), `lanes.py refresh --run <run>` reads the PR states and pulls what was completed,
then `lanes.py open` starts whatever that unblocked.

**Parallel runs.** After Locate, when the Code Indicator's report lists **Independent parts**, ask the owner
whether to split them into separate runs that go in parallel, each with its own PR (say what each part is and
what splitting costs: a second PR to review). Never split without a yes. On yes, narrow this run's brief to the
first part (re-validate it, re-plan), and start each other part with `run.py new --worktree --source
split:<this run id> --ref "<the part>"`, which leaves this checkout alone. Tell the owner the one line that starts
it in a second session: `cd <the worktree>` then `/flow resume <run id>`. A run started with `--worktree` (or one
the owner asks to run beside another) is worked entirely from its own worktree.

## Commits
`run.py checkpoint` and `stamp` commit only the run folder. You commit everything else, by path, never
`git add -A`:
- **The product change, a package at a time, in its lane**: when a package's done-check passes, its files (from
  its reports and `git status` in the lane), as `<type>(<scope>): <package title>` in the repo's commit style;
  again after any fix round. The lane branch is its group PR's source, so the PR moves with the work (**Pull
  requests**), and the Runner's summaries name the commit they tested.
- **Doc updates** (Docs Gardener, feedback and after-run mode): their files, as `docs(<run>): <what>`.
- **Learning** (Curator): `.fyzxsflow/learned/`, the doc patches and the regenerated host files it lists, as
  `fyzxsflow: learn from <run>`.
- **Compaction** (Compactor): the files its report lists, as `fyzxsflow: compact <targets>`.

## Pull requests
With the `pr` step on, every PR group has its own PR **into the run branch**, and the run branch reaches the default
branch in **one roll-up PR**. A draft means work in progress; a published PR means done and waiting on the owner's
approval. The owner completes every PR: the flow never completes, merges or sets auto-complete on one.
- **Authorised by** the profile's `Opening a PR: pre-authorised`, which covers the whole PR life: pushing the run's
  branch and lane branches, opening the drafts, updating them, publishing them when they are done, and the flow's
  comments. When it says `gated`, ask the owner once, at the run's first product commit: "Open draft PRs as the
  work lands? Yes also covers pushing each package and publishing each PR when it is done." Record the answer as a
  fixed `owner-decision` (target `pr`); on no, groups merge locally (`lanes.py merge`) and the roll-up waits for
  Deliver's gate.
- **Group PRs** (`lanes.py pr`, Build Coordinator Execute mode step 0): a draft from the group's first commit
  (with `Draft PR: at delivery` in the profile, opened only when the group is done), pushed as each package lands,
  published with `--publish --body-file <run>/pr-bodies/<group>.md` once the group's done-check is green,
  its reviews are finished and `lanes.py sync` left it free of conflicts with the run branch. Put each link in the
  heartbeat when it opens and when it is published. When the owner holds a group, `lanes.py park` it (log
  `build decided "owner: hold <group>: <their words>"`); never move lanes or edit `lanes.json` by hand.
- **The roll-up PR** (`python -I .fyzxsflow/package/engine/pr.py`): in Deliver, once every group PR is completed
  (ship-check's `group-prs` row) and the run's checks pass on the run branch, `pr.py draft --run <run>` opens the
  run branch's PR into the target, listing the group PRs; `pr.py update --run <run> --body-file
  <run>/pr-description.md` puts the PR Producer's description on it; `pr.py ready --run <run>` publishes it, and
  refuses until `ship-check` says `ready=yes`. It doesn't repeat the group reviews.
- **PR text is the PR Producer's.** Before publishing a group, dispatch `pr-producer` to write
  `<run>/pr-bodies/<group>.md` from the group's reports; dispatch it again for every later update to a published
  body (after rework or an owner comment). You put the file on the PR; you never compose it.
- **Answering owner comments.** For each owner comment to answer, once its rework (if any) is committed and pushed,
  dispatch `pr-producer` with: the PR (group or roll-up), the thread id (and its file and line), the owner's
  comment verbatim, and the facts: the commits, the reports and the Runner ids, or the reason for a pushback. It
  posts the reply with `pr.py comment`, which always prefixes `Agent AI Finding:`, so a reply never reads as the
  owner's words (`az` and `gh` are signed in as the owner). Log the comment id it reports. Never post a comment
  yourself, and never with a hand-written `az devops invoke` or `gh api`.

The owner can switch steps off for the project (`config.json` → `steps.off`) or for one run. Plain-language
requests ("no PR this time", "skip the security review") go through
`steps.py set <name> off --run <run> --reason "<the owner's words>"`. "Never run the PR agents" without a
run in mind is a project change: `steps.py set <name> off --reason "<the owner's words>"`. Only the owner
switches a step off. The opt-in `e2e` step is switched **on** the same way ("test this end to end" for one run,
"always test end to end" for the project). When `review-feature-flag` is off while flags are required, say so in the next review.

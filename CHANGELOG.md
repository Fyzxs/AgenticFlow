# Changelog

## 0.6.10 (2026-11-25)
- **`model_reported` is a should, not a must.** With no model configured for an agent the host picks one, and the
  agent may not know which. `stamp` now records a missing `model_reported` as `unknown` with a note instead of
  refusing (0.6.1); the rerun's orchestrator had worked round the refusal by editing a validator's report itself.
  `--lenient` is accepted and does nothing.
- **The orchestrator can't write an agent's report.** Its edits, shell writes and `sed -i` under a run's
  `reports/` are blocked on both hosts (the rerun's orchestrator edited a validator's report and logged the call
  as its own decision). What's wrong in a report goes back to its agent or to the owner; `run.py stamp` still
  writes the model lines, as a subprocess the hooks never see.

## 0.6.9 (2026-11-25)
- **A run can't complete with a review still open.** The live FizzBuzz run closed with two Deliver reviews
  (docs-gardener, gate-analyst) unanswered: the owner's one `approve` answered only the pr-reviewer's.
  `run.py close --outcome completed` now refuses (exit 3) while `reviews.jsonl` has an open pause, naming each;
  `--override "<owner's words>"` closes anyway and logs them. Abandoning a run is never refused.
- **Closing a run removes its merged lanes.** The rerun left its finished lane's worktree beside the checkout:
  only the Build Coordinator's Execute mode says to run `lanes.py close`. `run.py close` now does it (merged
  lanes only; a lane whose work isn't merged is kept and named).

## 0.6.8 (2026-11-25)
- **Doctor warns when Copilot doesn't trust the folder.** The live FizzBuzz run's resumed sessions (each owner
  reply) ran with no FyzxsFlow hook: `copilot --resume` can't take `--trust-folder`, and an untrusted folder skips
  repo hooks. The pauses and review checks held anyway, from the orchestrator's own file, but nothing enforced
  them. `doctor.py` now checks `trustedFolders` in `~/.copilot/config.json`; HOW-TO and the Copilot adapter say
  to trust the folder for good.
- **A package's status no longer conflicts a lane merge.** Execute mode sets a package to `building` in the run
  checkout and to `done` in its lane, so `lanes.py merge` met a conflict on the `status:` line and the live Copilot
  run (FizzBuzz) had to rebuild the lane by hand. Work-package files now merge with their own driver
  (`lanes.py package-merge-driver`, registered with the others when a lane opens): when both sides changed the
  status, the one furthest along wins (planned < deferred < building < done); the rest of the file merges as usual,
  and a real conflict there still stops the merge.

## 0.6.7 (2026-11-25)
From the first live `/flow` on Copilot (FizzBuzz): the run went through Intake, Locate and Build without one
review check, because the hand-off rule moved to `orchestrator/review.md` in 0.6.4 and the orchestrator never
opened it.
- **Every hand-off is checked, mechanically.** `review.py needed` records each answer in `reviews.jsonl`
  (`checked`), and the orchestrator hook refuses its next dispatch while a returned, stamped report has no check
  (its Validator may still run). The rule is also a Non-negotiable in the orchestrator's own file. A report
  counts whether or not it is stamped: on the rerun the orchestrator stamped the Code Indicator late and
  dispatched the planner before checking it.
- **A tests-only package can be done:** its tester is its maker (tester report + a Validator pass).

## 0.6.5 (2026-11-25)
- **Engine bytecode no longer blocks lanes.** An engine script that imports another (lanes.py, doctor.py) left
  `__pycache__/` under `.fyzxsflow/package/engine/`, untracked, so `lanes.py open` refused a "dirty" checkout. The
  install adds `.fyzxsflow/package/**/__pycache__/` to `.gitignore`, and the dirty checks ignore bytecode. (Found by
  the live Copilot acceptance check, which then confirmed a `task`-dispatched implementer is held to its lane.)

## 0.6.4 (2026-11-25)
- **Agent files load in full.** Copilot read 20 KB of the 46 KB orchestrator file and never reached its PR rules.
  Every agent file is now within 12 KB (`layout.AGENT_BUDGET_KB`; install refuses more, doctor fails an installed
  file over it). The orchestrator (now 9.6 KB), Build Coordinator (7.7 KB) and Preceptor keep a **Non-negotiables**
  block at the top; their longer sections moved word for word (checked line by line) into
  `agents/<agent>/<part>.md` (start, build, review, dispatch, gates, finish, greenfield, compaction, preceptee;
  plan, parallelize, execute; exercises), each listed in **Where the rest lives** with "read it before acting on
  it". The commands point at the part they start in.

## 0.6.3 (2026-11-25)
- **`engine/doctor.py`, a preflight before the first stage** (and on resume): dry-runs the repo's own hooks against
  the flow's git add / commit / push, checks for a clean checkout, a signed-in PR CLI, Docker when a mode uses it,
  the NuGet audit, and Copilot agent files (parseable frontmatter, within 12 KB) and hooks. The orchestrator stops
  on a `FAIL` and hands the owner each problem. (The Copilot run met a repo guard denying `git commit`, a dirty
  checkout, Docker down and an NU1902 audit failure only mid-run.)

## 0.6.2 (2026-11-25)
- **A lane knows what it may change.** `lanes.py open` records each lane (run, group, packages, `owns` = its
  packages' Scope paths, branch, into) in the lane's own git directory, never in the tree. `engine/lane_resolve.py`
  finds it from any path, for FyzxsFlow's hooks and for a repo's own guard to import (no env var: Copilot `task`
  subagents share one process). `lanes.py grant` adds a granted scope-request.
- **Implementers and testers stay in scope (blocks, both hosts).** An edit outside the lane's scope, or a shell
  write (`>`, `Set-Content`, `Out-File`, `tee`) into a tracked file, is denied with what to do instead.
- **Derived files are planned.** A package's Scope takes `derived:` lines for generated, golden and snapshot files
  its change makes stale; the profile gets a **Derived files** section to list generators.
- **Encoding damage is reported** (Copilot, after each edit): mojibake such as `â€` and LF turned CRLF.
- **A denied call is an answer** (role contracts): stop and report `blocked: <call>`, never work around it.

## 0.6.1 (2026-11-25)
- **A package is done only when its steps are.** `run.py package-status --status done` refuses (exit 3, naming
  what's missing) until the maker's report and a Validator pass on it, the tester's report from a separate
  dispatch and a Validator pass on it (not for iac-/e2e-implementer packages), every one stamped, and a passing
  `runner/<id>.json` cited. `--override "<the owner's words>"` logs the owner's acceptance in the ledger.
- **Dispatch prompts come from the engine.** `run.py dispatch --wp <id> --role <role> [--target <agent>]` writes
  `dispatch/<id>.md` from the package (context pack, scope, done check, report path, dispatch id) and logs it; the
  subagent's prompt is "Read <file> and follow it." A note naming another maker role is refused (the Copilot run
  folded the tester's criteria into the implementer's prompt).
- **`stamp` is strict.** A report without `model_reported` is refused; `--lenient` is the owner's call.

## 0.6.0 (2026-11-25)
From a Copilot CLI run in VA_GqlOverSql, where `/flow` ran in the default agent, read 20 KB of the 46 KB
orchestrator file, never saw the PR rules, and completed three PRs itself.
- **Copilot hooks are repo-wide.** Agent-scoped frontmatter hooks never fired on Copilot CLI (1.0.116, checked
  live). `.github/hooks/fyzxsflow.json` now runs `orchestrator_guard_copilot.py` on `userPromptSubmitted`,
  `preToolUse` and `postToolUse` for every session; the main session's agent is read from Copilot's session
  state (`subagent.selected`).
- **FyzxsFlow commands run only in their agent on Copilot.** `/flow` in any agent but the orchestrator is blocked
  (at the prompt, or at the first tool call when the session's agent isn't known yet), with how to switch
  (`copilot --agent orchestrator`). The Copilot skill bodies no longer say "act as the agent, read its file":
  the agent file is the system prompt, in full.
- **The never-list blocks, for every agent on both hosts:** completing, merging or auto-completing PRs, raw `az
  repos pr create|update|complete` and `gh pr create|edit|merge|ready`, raw `git worktree add|remove|move`, `git
  merge` on the default or a `fyzxsflow/*` branch, `git push` to the default branch. lanes.py and pr.py do these.
- **Copilot loads every agent.** Seven agents were dropped as "malformed frontmatter" (an unquoted `: ` in their
  description); Copilot frontmatter now quotes the description and drops `tier` ("unknown field ignored").

## 0.5.0 (2026-11-24)
- **Review pauses are enforced.** `review.py needed` records each `review=pause` in the run's `reviews.jsonl`
  (decision `pending`), and `review.py decide` closes it. While a pause is open, the orchestrator hook blocks the
  orchestrator's agent dispatches and its `lanes.py` / `pr.py` moves (read-only ones excepted), and tells it to
  show the owner the review. Build's agent-level reviews happen on the group PR and aren't recorded; a Build
  `always:` / `run-request:` pause holds only its group. New `review.py open --run <run>`. `decide` reads "keep
  going", "go on" and "go ahead" as continue, with the owner's words kept.
- **One rules file, a hook script per host.** `orchestrator_guard.py` is split into `orchestrator_rules.py` (the
  rules) plus `orchestrator_guard_claude.py` (PreToolUse: review gate, then the delegation reminder; matcher now
  includes `Agent|Task`) and `orchestrator_guard_copilot.py` (`pre`: the review gate, since Copilot can only deny
  before a call; `post`: the reminder, since Copilot CLI adds context only after one). A reinstall updates the old
  `.claude/settings.json` entry in place.

## 0.4.9 (2026-11-24)
- **`--host copilot` never touches `.claude/`** (and `--host claude` never touches `.github/`): nothing written,
  nothing deleted. `pointers.py` reads, writes and cleans only the folders of installed hosts (`INSTALLED.json`
  `hosts`), so an old Claude pointer survives a Copilot-only install. A legacy-name migration cleans host files
  only for the hosts being installed.

## 0.4.8 (2026-11-24)
- **0.4.7 didn't fully fix it.** It decided which hosts were installed from the folders on disk, so a repo that
  still had `.claude/agents/` from an earlier install got `.claude/rules/` pointers from a `--host copilot`
  install. The installer now records the `--host` values it ran with in `INSTALLED.json` (`hosts`; `--sync` adds
  its host, since the Curator syncs one host per call), and `pointers.py` uses them.

## 0.4.7 (2026-11-24)
- **A Copilot-only repo gets no `.claude/` files.** `pointers.py` wrote segment pointers for every host in
  `docs.host_pointers`, which the config template sets to both hosts, so the Cartographer created `.claude/rules/`
  in repos installed with `--host copilot` alone. It now writes pointers only for installed hosts
  (`.claude/agents/`, `.github/agents/`).

## 0.4.6 (2026-11-24)
- **The orchestrator hook reminds instead of blocking.** Denying the orchestrator's own edits and commands got in
  the way when it had a real reason to do the work (seen on Copilot). `orchestrator_guard.py` now always lets the
  call run and adds a reminder to the model's context: delegate, naming the owner agent, and log why when doing it
  yourself. It makes no permission decision, so the host's normal permission flow is unchanged. Claude Code: on
  PreToolUse (checked live on 2.1.330). Copilot: the orchestrator's agent-scoped hook moves to PostToolUse, the only
  tool event where Copilot CLI documents added context.

## 0.4.5 (2026-11-24)
- **Build runs in a dispatched Build Coordinator.** Claude Code subagents can dispatch other agents (checked on
  2.1.330), so the Orchestrator now dispatches `build-coordinator` in Execute mode instead of running it in its own
  session. The coordinator returns at each group's end or pause; the Orchestrator stamps, writes the review files,
  handles pauses and dispatches it again to continue.
- On a host without nested dispatch (VS Code Copilot unless `chat.subagents.allowInvocationsFromSubagents` is on), the
  coordinator returns `no-dispatch` and the Orchestrator runs Execute mode in its session, with a ledger line.

## 0.4.4 (2026-11-23)
From dog-fooding in DocMcStorage (findings F-1984 and F-1986). In one day the main session edited a rule doc,
work packages and pipeline YAML itself, ran `ci`, and posted PR replies with no prefix under the owner's name. The
package already forbade some of this in prose. Now the install enforces it.

- **The orchestrator does no work**:
  - `orchestrator.agent.md` has an owners table: who edits code, docs, plans, learned entries and PR text, and who
    runs the Runner.
  - It also has the short list of bookkeeping the orchestrator keeps. The old rule named only code, builds, tests
    and review.
- **Enforced on Claude Code by default**:
  - `install.py --host claude` writes `"agent": "orchestrator"`, so the main session is the orchestrator.
  - It also adds `engine/hooks/orchestrator_guard.py`, which denies the orchestrator's own edits outside its
    run-folder bookkeeping, and shell commands outside a fixed allow-list. Each denial names the agent to dispatch.
  - Subagent calls (which carry `agent_id`) are never blocked.
  - `--no-main-agent` opts out.
  - Hooks merge into an existing `settings.json` without touching the repo's own entries, and a no-op reinstall
    writes nothing.
- **On GitHub Copilot as far as the host allows**:
  - The guard is an agent-scoped `hooks:` entry on the orchestrator agent, so it runs only while that agent is
    selected.
  - `.github/hooks/fyzxsflow.json` adds kill-by-name.
  - Copilot has no default-agent setting, so select the orchestrator yourself.
  - `--probe-hooks` plus `orchestrator_probe.py report` check the host in log-only mode.
- **`pr.py comment`**: the flow's PR comments and thread replies always start with `Agent AI Finding:`, which the
  caller can't turn off.
  - It handles GitHub, and Azure DevOps threads and replies.
  - Each comment is logged in the ledger.
  - It shares one poster with `preceptee.py`, which keeps its own prefix.
  - The PR Producer posts these comments, and writes every group PR body (`<run>/pr-bodies/<group>.md`) and every
    later update to one.
- **`run.py package-status --wp <id> --status <s>`** sets only a work package's `status:` line. Execute mode uses
  it, so no hand edit is left.
- Checked on Claude Code 2.1.330, recorded in HOW-TO:
  - on `--agent` main-thread calls, `agent_type` is set and `agent_id` is absent;
  - an orchestrator's `tools:` doesn't strip its subagents' tools;
  - nested dispatch works.

## 0.4.3 (2026-11-20)
From evaluating the skill and the commands with skill-creator (with vs without, on real transcripts and fixtures).

- **Package skills reach the hosts**: install writes `.claude/skills/<skill>/SKILL.md` and
  `.github/skills/<skill>/SKILL.md` (model-invocable, marked generated; copies of skills dropped upstream are removed,
  your own skills are left alone). Before, `correction-mining` sat only in `.fyzxsflow/package/skills/`, so neither
  host ever offered it.
- **correction-mining**:
  - `extract_claude.py --projects` takes several globs and folder names starting with `-` (every Linux/macOS
    `~/.claude/projects` folder).
  - It skips sessions written in the last 10 minutes (usually the session doing the mining; `--include-live`,
    `--exclude-session <id>`).
  - New `check_refs.py` audits hand-written host docs: load mode, size, `paths:`/`applyTo:` globs that match
    nothing, dead backticked paths. Generated rules count toward the always-on size. `docs_check.py` covers only
    `.fyzxsflow/` and only after init. Both scripts are tested (`engine/tests/test_skill_scripts.py`).
  - SKILL.md:
    - scripts run with `python -I -B`, so nothing is written into the repo;
    - quotes stay verbatim, marked `[sic]` / `[...]`;
    - each theme gets one primary home plus a hook or test where the rule can be checked mechanically;
    - a "settled or withdrawn decisions" section;
    - staleness is audited in the checkout in front of you, then compared with the owner's working branch;
    - an inline catalog when there are no subagents;
    - the `flag` field is documented.
- **Install leaves no bytecode in the project**: syncing imports the installed engine, which wrote
  `.fyzxsflow/package/engine/__pycache__/` into the repo (and into commits that staged the package).
- **`review.py decide` accepts natural forms**: `Approved.`, `approve!`, `approved -less-review`. Other words are
  still refused.
- **`lanes.py merge` refuses instead of marking a false `conflict`** when uncommitted files in the run checkout (often
  the ledger after `run.py log`) are ones the lane changed. The Build Coordinator checkpoints before merging.
- **Compaction measures before spending**:
  - The Compactor estimates the saving first. Under 10%, or with targets already compacted, the Orchestrator shows
    the sizes and the likely cost and asks.
  - The validator checks every `never/always/only/must` sentence survives. An evaluated pass cost about $20 for
    1.6% and merged away two rules.
- **No "temporary" breakage to see a test go red**: role-contracts names it as planting a mistake; the proof goes
  through a Runner mode (`scope-request`).
- **"Keep going to the end"** skips the run's remaining review pauses only. It is logged, review files are still
  written, the always-stop cases still stop, and no stored level changes.

## 0.4.2 (2026-11-17)
- **The owner sees what to review before being asked**: `review.py show --review-file <file> [--open]` turns a review
  file into the pause message: the review and every file under **What to look at** as links, the diff, the
  validator's verdict and any pushed-back feedback, then the reply options. It refuses a review that names nothing
  to look at. `--open` also opens the files in VS Code when run from its terminal. The Orchestrator posts it at every
  pause and never asks through a question popup (VS Code's showed only "approve or redo", with nothing to read).

## 0.4.1 (2026-11-16)
- **VS Code commands are agent skills**: the Copilot install writes `.github/skills/<command>/SKILL.md` (`/flow`,
  `/fyzxsflow-init`, ...; run only when typed) instead of `.github/prompts/*.prompt.md`, and removes the prompt
  files earlier installs wrote. Copilot sessions on VS Code's Agent Host harness don't load prompt files, and the
  Local harness that does is removed in February 2027. Reinstall rather than accepting VS Code's migration offer.

## 0.4.0 (2026-11-16)
From the first long run on PR groups (a 45-package plan in DocMcStorage).

- **Lanes are folders beside the run's checkout** (`<checkout>-<group>`), not inside `.git/`, so you and your tools
  can open them. `lanes.py move` brings out a lane opened by 0.3.x; `status` shows each lane's folder.
- **Finding ids never collide across lanes**: one counter shared by every worktree, never below the highest id in
  the file. The run folder merges between lanes by itself: `findings.jsonl` by finding id (a git merge driver,
  `findings.py merge-driver`), `ledger.md` and `reviews.jsonl` by union, registered by `lanes.py` in the repo's local
  git config.
- **`findings.py resolve <F-n> --by <commit|F-n>`** closes a finding with what fixed it (`resolution`). `owner` as a
  target is refused except on `owner-decision`, the one kind that reaches the owner.
- **Group PRs**: titles from the package heading; `--publish` replaces the draft description (`--body-file`, or a
  ready-for-review summary) and refuses while the lane would conflict with the run branch or the host reports
  conflicts; `lanes.py sync` merges the run branch into a lane; `refresh` names lanes the run branch now conflicts
  with; links are the PR's web page on Azure DevOps too (also `pr.py`).
- **Holding a group**: `lanes.py park | unpark`, and `status: deferred`, which `waves.py` (dependents held),
  `ac_trace.py` (criteria shown as deferred) and `run.py packages` understand. `lanes.py close --group`.
- A named `pr_group` keeps its case, like the default group.
- Every engine script that takes `--run` accepts a bare run id (`findings.py`, `gates.py`, `lanes.py`, ...), and none
  creates a folder named after it.
- `run.py new` from a detached HEAD records the remote's default branch (or `--base-branch`), never `HEAD`.
- `run.py log ... decided` records an owner's decision in the ledger.
- `feedback.py scan` no longer lists items closed by hand (`status: done` without a `seen_hash`) as new.
- `docs_check.py` names a pack's largest files and the bytes over budget, and warns within 1 KB of it.
- Runner: `scope_kind: "path"` resolves a bare `--scope` name to its file or fails before building; airplane modes
  read the scripts a step calls for container starts, and trust a step marked `"pulls": "never"`.
- `ac_trace.py` accepts `(stated, amended (...))`.
- `checks.py report` (and `run.py stamp`, as warnings) finds a report missing a section its agent requires, or a
  criterion marked met with no evidence. The report template gains Docs drift and Done-check result.
- `preceptee.py stop`: switching preceptee mode off mid-run closes open exercises as not counted.
- Agents: every dispatch names its worktree and the agent file to act as (role contracts: confirm it first); a
  heartbeat at each long dispatch; the implementer's description says it runs its done-check through the Runner;
  the tester asks for a Runner mode instead of running a test directly; the Work Summarizer splits a multi-behaviour
  source criterion; the Build Coordinator joins small mechanical packages and makes `ci` real only when the stack
  can hold; the Docs Gardener never cuts content to fit a budget.

## 0.3.1 (2026-11-12)
- `waves.py check` prints one warning per Runner lock, naming every not-done group that shares it, instead of one
  line per pair (a 45-package plan went from about 120 lines to 1). The pairs are under `--verbose` and in `--json`
  (`lock_pairs`).
- A pair with a done group is never a lock warning, and a file both change is info, not a problem: a done group
  never builds again.

## 0.3.0 (2026-11-12)
The installed `INSTALLED.json` said 0.2.0 across every change below; from here each release bumps the version.

- **PR groups and a roll-up PR.** Each distinct piece of work gets its own PR into the run branch (related work may
  share one; building in parallel never bundles). It opens as a draft with its first commit and is published when
  its group is done; the owner completes it. A group starts as soon as the groups it depends on are completed,
  never waiting for a wave. When every group PR is completed, the run branch gets one roll-up PR into the default
  branch, published only when `ship-check` says ready. The engine never completes or auto-completes a PR.
  (`lanes.py open | pr | refresh | status | merge | close`, `pr.py`, ship-check `group-prs`.)
- **The PR is the run's own branch.** Every commit ships, the run's record included.
- **Parallel work.** Lanes in git worktrees (`build.max_parallel`, default 3), `waves.py` (series reasons, file
  overlap between groups that may build together, cycles; done packages count as built and their old problems are
  info), Runner locks shared across checkouts, `run.py new --worktree`, offering to split a request into parallel
  runs, and `/fyzxsflow-parallelize` to re-order an existing plan.
- **Preceptee mode** (off by default; `/flow --preceptee`, or the `precept` step for a project): the engineer
  writes the code and the Preceptor reviews their PRs like a senior engineer, broad to specific (`preceptee.py
  comment | activity`), and coaches in the session; the record stays on their machine. PR coaching is its own agent (preceptee-socratic-pr). Only the Orchestrator and the preceptee agents know the mode
  exists; the standard agents get plain instructions (the Validator's `log only`). Only the Preceptee Seeder agent plants
  practice flaws, in preceptee mode, outside the repo; every role is forbidden to plant a mistake. See PRECEPTEE.md.
- **Compactor** (`/fyzxsflow-compact`): shrinks agent files, learned entries and docs without losing a rule
  (`compact.py`, overlays in `.fyzxsflow/compacted/`).
- Slash commands load their agent's Learned entries.

# Changelog

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
    nothing, dead backticked paths. `docs_check.py` covers only `.fyzxsflow/` and only after init.
  - SKILL.md:
    - scripts run with `python -I -B`, so nothing is written into the repo;
    - quotes stay verbatim, marked `[sic]` / `[...]`;
    - each theme gets one primary home plus a hook or test where the rule can be checked mechanically;
    - a "settled or withdrawn decisions" section;
    - staleness is judged against the owner's branch;
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

# FyzxsFlow design

This file records the design decisions and why they were made.

## Origin
Built from three months of agent sessions on a real application. The most expensive corrections were about process, not code:
re-asking for approval (~14), unclear ship state (~15), silence on long runs (~16), handing verification
back to the owner (~10). The MicroObjects coder and reviewer pair (Quill and Loupe) was the first "micro
loop"; FyzxsFlow is the same loop, generalised and portable across Claude Code and GitHub Copilot.

## Flow
1. **Intake** — Work Summarizer turns a prompt or an ADO item into `brief.md` with numbered acceptance
   criteria. Validated.
2. **Locate** — Code Indicator writes `change-map.md` (where, what, contracts, surfaces). Build Coordinator
   (plan mode) writes work packages: context pack, acceptance criteria, contract, flag plan, done-check,
   dependencies, size. Validated; `ac_trace.py` confirms every criterion is served. Plan gate only for
   owner decisions or unflaggable changes.
3. **Build** — Build Coordinator (execute mode) runs packages in dependency order: Implementer (or IaC
   Implementer) → Validator → Tester → Validator → Runner done-check. Then Runner `--ci` and gates at `ci`.
4. **Prove** — API proof files generated and run (`--http`), only when an API changed.
5. **Review** — read-only: narrow, feature flag, large; architecture, security, IaC and domain reviewers
   when their surface changed. Must-fix findings go back to Build, at most 2 rounds.
6. **Deliver** — Runner `--extreme`, gates at `extreme` and `pre-pr`, `ac_trace.py --require-evidence`,
   then the PR (comments prefixed `Agent AI Finding:`) and a PR review.
7. **Learn** — Curator turns findings into Learned entries, doc edits, or mechanization proposals; a
   Validator checks the Curator.

## Decisions
| Decision | Why |
|---|---|
| One Validator for every agent, given the target's file | The owner's definition ("read the agent file and act as one") is one agent; improving it improves all checks |
| One Implementer and one Tester, specialised by context packs | Expertise lives in repo docs; agent files hold portable craft; the Curator's routing gets simple |
| A separate IaC Implementer | Its craft differs (preview, never apply; idempotent; per-environment parameters; no inline secrets), not only its knowledge |
| Build Coordinator plans and executes | The agent that runs the plan writes it; one fewer hand-off |
| Only the Runner builds and tests; only the Gate Analyst runs scanners; both through scripts | Small, focused contexts; no colliding test runs; results judged by exit code |
| Deterministic gates declared in `gates.json`, SARIF normalised, baselines for known results | Any linter or scanner can be added without touching agents; only new results block |
| Acceptance criteria required, traced by script | They are the checks and the end state; traceability is mechanical, so a script owns it |
| Everything feature-flagged, provider from `feature-flags.md`; `Policy: required` by default, `not-required` per project or per run by the owner | Revert faster than a deploy, never assume the project's flag system, and let the owner opt out explicitly, never silently |
| Standard Runner capabilities (quick, ci, extreme; db-migrate, db-verify, db-reset, seed; http), each filled, `not_applicable` or visibly `UNRESOLVED`; destructive steps labelled and refused by the script without approval; completeness checked by `docs_check.py` | Found in the PoC: CI-derived config had no in-place migrate, only a reset that wiped the proofs' data. Capabilities are project facts, settled at init, never discovered mid-run |
| One folder, split by owner: `.fyzxsflow/` is the project's (config, docs, feedback, runs, `learned/`), `.fyzxsflow/package/` is the installer's and is replaced whole; host files = package agent + project Learned entries | Upgrades can't clobber what the project learned, files dropped upstream don't linger, and the package half maps one-to-one onto an APM dependency later |
| Owner feedback is a signal, never a chore: a review's `## Human Feedback` section and the `.fyzxsflow/feedback/` inbox are routed by the Orchestrator before the next agent (Docs Gardener for conventions, agent input, rework, queued runs) and shown in the next review for approval. Undecided feedback is a proposal: agents apply what they agree with and hold only what they dispute, with a reason and a recommendation, until the owner settles it | The owner reviews and comments; the flow changes itself. Docs that mark existing patterns legacy outrank the code, so one comment beats fifty old examples |
| Human review between hand-offs; per-agent levels on → notify → off, all on by default; `-less-review` / `-more-review` on any reply; only the owner lowers; `always` rules and per-run requests; the level decides only whether the run waits, and every hand-off writes a review file | Review where trust hasn't been earned yet, without the owner hunting for agent names or config keys; oversight only drops on the owner's word; output the owner didn't wait on can still be commented on in place, later |
| "Ready to push" only on `run.py ship-check` (extreme, extreme/pre-pr gates, criteria evidence, open owner decisions); a failure counts only with the owner's recorded acceptance | Round 1 of the PoC said "Ready to push" while extreme had failed and the pre-pr stage had checked nothing; the ship line has to come from a script, like every other gate |
| The agent's output is committed when its report is stamped; `edits --record` never attributes engine-written files and refuses while a report is unstamped | Owner edits are the Curator's strongest signal, so a false one teaches the wrong lesson; Round 1 recorded three agent writes as owner edits |
| In Build, the owner's reviews pause once per wave of packages, not per agent | Round 1 spent about 27 of 36 hours waiting on 18 reviews, all plain approvals; per-hand-off pauses stay available (`always`, run requests, `- pause: each`) |
| Runner steps can fail on their output (`fail_if_output`, `expect_output`); modes can share a `lock`; a timed-out step's process tree is stopped | Tools that exit 0 while dropping records (an ingest lost 4,202 in Round 1) need a declared check, not an agent reading logs; two database writers at once caused a timeout |
| Generic rules the Curator learns in a project are folded back into the package (role contracts, agent rules); project rules stay in `learned/` | Round 1's 44 learned entries were about half generic; leaving them per project means every project relearns them |
| Optional steps (PR, reviewers, HTTP proofs, gates, extreme, docs upkeep, learn) switched off per project in `config.json` → `steps.off` or per run on the owner's words; checked by `steps.py` before each dispatch; the core (intake, locate, build, validators, runner) has no switch | Projects differ in what they need from the flow, and the switch must be one place the owner can find; a script answers "is it on?" so the Orchestrator can't drift; the core stays because without it nothing is proven or learned |
| Optional model compare: shadow one tier below, validate both independently, reduce only after min_samples at the ok rate | Escalation alone can only ever move tiers up; the cheaper tier needs a way to prove itself. Toggleable because it doubles shadowed tokens |
| `tier: auto` maps to the harness's own model selection where the host has it | Lets Copilot's Auto (or similar) decide, without agent files naming a host |
| Agents declare a model tier (deep, standard, fast); projects map tiers to host models; escalation on repeated Validator failures | Agent files stay host-neutral; cost follows the work; model choice joins the findings loop instead of being guessed |
| Runs committed at each stage checkpoint, in `active/` → `completed/` or `abandoned/` | Human review and mid-run edits; owner edits are recorded as `human-edit` findings for the Curator; raw logs stay local |
| Run folder is the API between agents | Host- and model-independent hand-offs; the ledger is the heartbeat and resume point |
| Host-native pointer files per segment, generated by `engine/pointers.py` | Ordinary sessions outside the flow, on either host, read the same segment docs; one source, kept in sync by a check |
| Prompt and ADO are equal inputs | Everything after Intake reads only `brief.md` |
| A Compactor, run only on the owner's request, shrinks package agent and context files, learned entries and docs; package files are compacted as overlays in `.fyzxsflow/compacted/` that install re-applies only while the upstream file is unchanged; `compact.py check` refuses any lost heading, literal, path, id or number unless accepted with a reason | Every dispatch pays for every rule it loads, and those files only grow; the package is replaced on install, so a compaction must survive upgrades yet never hide an upstream change; fidelity is a script, meaning is the Validator's |
| Preceptee mode (opt-in step `precept`): at the engineer's steps the preceptee works first and the agents' version is revealed after; the Preceptor runs in the Orchestrator's session; `preceptee.py` enforces attempt-before-reveal, what counts toward easing off (prompts at 4/7/10), explain-before-merge and the seeded-flaw guard; the record lives on the preceptee's machine | A tutor shouldn't hand over the answer before the learner tries (the preceptorship proposal, after CACM); coaching is evidence for a human preceptor, never a rating, so it stays out of shared git; rules a coach could bend under pressure are scripts |
| Parallel where possible, series where it must be: a wave's packages build at once in git-worktree lanes (`lanes.py`, `build.max_parallel`, default 3), merge in plan order, then a `quick` run on the merged branch; every `depends_on` needs a reason (contract, same file, shared resource, risk first) and `waves.py` refuses same-wave file overlap and cycles; Runner locks live in the git common directory; `run.py new --worktree` lets runs go in parallel, and Locate offers to split a request with independent parts | Planned waves ran one after another in practice, so wall-clock time was the sum of every package; a script keeps the plan honest about what really must be series, and shared locks keep parallel lanes off the same local resources |
| The run's PR opens as a draft at its first product commit (packages are committed one at a time), is updated as each package lands, and is marked ready only when `ship-check` says `ready=yes`; `pr.py` alone pushes and calls the host (`gh` / `az repos`); the PR is the run's own branch, every commit of it, run records included; `Opening a PR: pre-authorised` covers the whole PR life, `gated` asks once per run | The owner wanted a strong signal of work in progress versus pending final approval; draft-to-ready is a script's call on the ship line, so a published PR never means "still in progress" |
| Curator guardrails (evidence, dedupe, budgets, hit counts, regression cases, PRs for generic changes) | Unbounded learning becomes another 336 KB lessons file |

## Open questions (PoC)
See `adapters/claude/README.md` and `adapters/copilot/README.md`.

# agentflow design

Full design with diagrams: https://claude.ai/artifact/SzJwCgeAbqtwCeWJLSAGhd (private to the owner).
This file records the decisions so the repo stands on its own.

## Origin
Built from three months of TcgHoard sessions. The most expensive corrections were about process, not code:
re-asking for approval (~14), unclear ship state (~15), silence on long runs (~16), handing verification
back to the owner (~10). The MicroObjects coder and reviewer pair (Quill and Loupe) was the first "micro
loop"; agentflow is the same loop, generalised and portable across Claude Code and GitHub Copilot.

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
| Owner feedback is a signal, never a chore: a review's `## Human Feedback` section and the `.agentflow/feedback/` inbox are routed by the Orchestrator before the next agent (Docs Gardener for conventions, agent input, rework, queued runs) and shown in the next review for approval | The owner reviews and comments; the flow changes itself. Docs that mark existing patterns legacy outrank the code, so one comment beats fifty old examples |
| Human review between hand-offs; per-agent levels on → notify → off, all on by default; `-less-review` / `-more-review` on any reply; only the owner lowers; `always` rules and per-run requests | Review where trust hasn't been earned yet, without the owner hunting for agent names or config keys; oversight only drops on the owner's word |
| Optional model compare: shadow one tier below, validate both independently, reduce only after min_samples at the ok rate | Escalation alone can only ever move tiers up; the cheaper tier needs a way to prove itself. Toggleable because it doubles shadowed tokens |
| `tier: auto` maps to the harness's own model selection where the host has it | Lets Copilot's Auto (or similar) decide, without agent files naming a host |
| Agents declare a model tier (deep, standard, fast); projects map tiers to host models; escalation on repeated Validator failures | Agent files stay host-neutral; cost follows the work; model choice joins the findings loop instead of being guessed |
| Runs committed at each stage checkpoint, in `active/` → `completed/` or `abandoned/` | Human review and mid-run edits; owner edits are recorded as `human-edit` findings for the Curator; raw logs stay local |
| Run folder is the API between agents | Host- and model-independent hand-offs; the ledger is the heartbeat and resume point |
| Host-native pointer files per segment, generated by `engine/pointers.py` | Ordinary sessions outside the flow, on either host, read the same segment docs; one source, kept in sync by a check |
| Prompt and ADO are equal inputs | Everything after Intake reads only `brief.md` |
| Curator guardrails (evidence, dedupe, budgets, hit counts, regression cases, PRs for generic changes) | Unbounded learning becomes another 336 KB lessons file |

## Open questions (PoC)
See `adapters/claude/README.md` and `adapters/copilot/README.md`.

# GitHub Copilot adapter

`apm install` with target `copilot` writes agents to `.github/agents/` and instructions to
`.github/instructions/`; `apm compile` can also produce `AGENTS.md`. This folder records how the flow maps
onto Copilot and what the PoC must confirm. Nothing here has been verified against current Copilot docs.

## Dispatch (to verify)
The flow needs one agent to hand work to another with file paths. Candidates to test:
- custom agents with handoffs between them;
- an orchestrator agent that invokes other agents as subagents, if the host supports it;
- fallback: the Orchestrator runs stages sequentially in one session, loading each agent file as the
  instructions for that step. Slower and less isolated, but the run folder keeps the results identical.

## Hooks
Copilot has no equivalent of Claude Code's tool-call hooks that we have confirmed. Guards therefore
degrade to:
- the instruction (the working agreement already says "never kill by process name");
- a git hook or a gate in `gates.json` wherever the rule can be checked after the fact.

## Transcripts
For correction mining, find where Copilot (VS Code agent mode, Copilot CLI, the coding agent) stores
session history, and write an extractor that emits the same `turns.jsonl` shape as
`.apm/skills/correction-mining/scripts/extract_claude.py`.

## To verify in the PoC
- [ ] Agent-to-agent dispatch: which of the options above works, and how inputs are passed.
- [ ] Whether `.apm/context/*` and `engine/` are reachable after install.
- [ ] How prompt files are invoked and how the user's text reaches them.
- [ ] Whether skills (`SKILL.md`) load on the Copilot surfaces used at work.
- [ ] Where session transcripts live.
- [ ] That `.github/instructions/*.instructions.md` with `applyTo: "glob1,glob2"` (comma-separated, as
      `engine/pointers.py` writes it) scopes correctly, and doesn't collide with what `apm install` writes there.

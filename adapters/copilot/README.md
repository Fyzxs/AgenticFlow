# GitHub Copilot adapter

`apm install` with target `copilot` writes agents to `.github/agents/` and instructions to
`.github/instructions/`; `apm compile` can also produce `AGENTS.md`. This folder records how the flow maps
onto Copilot and what the PoC must confirm. Nothing here has been verified against current Copilot docs.

## What the docs say (2026-11, not yet tried)
- **VS Code Copilot Chat:** `.github/prompts/*.prompt.md` run as `/name <text>` in the Chat view (Local
  harness); the prompt's `agent:` frontmatter picks the custom agent it runs in (`flow` → `orchestrator`,
  `fyzxsflow-init` → `repo-cartographer`). Custom agents in `.github/agents/` can be dispatched as subagents by
  an agent with the `agent` tool set (`runSubagent`); subagents can't dispatch further subagents unless
  `chat.subagents.allowInvocationsFromSubagents` is on, so the Orchestrator runs Build itself (as on Claude Code).
  A subagent doesn't inherit the conversation, which suits the run-folder hand-offs.
- **Copilot CLI:** custom agents from `.github/agents/` (or `~/.copilot/agents/`, which wins on a name clash);
  `/agent` to pick one, `copilot --agent=<name> --prompt "<task>"` non-interactively; restart after adding
  agents. No prompt files. It may delegate to custom agents as subagents on its own judgement.
- **Copilot app (desktop, technical preview):** sessions on a connected repo or local folder, each in its own
  worktree and branch; global instructions, MCP and skills are documented, a repository's custom agents are not.

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
- [ ] Whether custom agents honour a `model:` frontmatter line, and the model names to put in
      `config.json` → `models.copilot` (empty means inherit, which is the safe default until verified).
- [ ] The keyword for Copilot's Auto model selection in agent frontmatter, for `models.copilot.auto`.
- [ ] How to run a shadow dispatch in isolation on Copilot (a separate worktree or branch), for model compare.
- [ ] That `.github/instructions/*.instructions.md` with `applyTo: "glob1,glob2"` (comma-separated, as
      `engine/pointers.py` writes it) scopes correctly, and doesn't collide with what `apm install` writes there.

# GitHub Copilot adapter

`apm install` with target `copilot` writes agents to `.github/agents/` and instructions to
`.github/instructions/`; `apm compile` can also produce `AGENTS.md`. This folder records how the flow maps
onto Copilot and what the PoC must confirm. Nothing here has been verified against current Copilot docs.

## What the docs say (2026-11, not yet tried)
- **VS Code Copilot Chat:** the commands are agent skills, `.github/skills/<name>/SKILL.md`, run as `/name <text>`
  (`disable-model-invocation: true`, so only when typed). Since 0.4.1; before, they were prompt files in
  `.github/prompts/`, which Copilot sessions on the Agent Host harness don't load and which only the Local harness
  (deprecated, removed February 2027) runs. A skill can't pin a custom agent as a prompt's `agent:` did, so each
  body says which agent to act as and reads its file (`flow` → `orchestrator`, `fyzxsflow-init` →
  `repo-cartographer`, `fyzxsflow-greenfield` → `orchestrator`, `fyzxsflow-compact` → `orchestrator`,
  `fyzxsflow-parallelize` → `build-coordinator`). Custom agents in `.github/agents/` can be dispatched as subagents by
  an agent with the `agent` tool set (`runSubagent`); subagents can't dispatch further subagents unless
  `chat.subagents.allowInvocationsFromSubagents` is on. With it on, Build runs as on Claude Code (a dispatched
  Build Coordinator); with it off, the Build Coordinator returns `no-dispatch` and the Orchestrator runs Execute
  mode in its own session.
  A subagent doesn't inherit the conversation, which suits the run-folder hand-offs.
- **Copilot CLI:** custom agents from `.github/agents/` (or `~/.copilot/agents/`, which wins on a name clash);
  `/agent` to pick one, `copilot --agent=<name> --prompt "<task>"` non-interactively; restart after adding
  agents. No prompt files. It may delegate to custom agents as subagents on its own judgement. Subagents may
  nest up to `subagents.maxDepth` in `~/.copilot/settings.json` (default 6, user level only; not checked live), so
  the dispatched Build Coordinator should work without setup.
- **Copilot app (desktop, technical preview):** sessions on a connected repo or local folder, each in its own
  worktree and branch; global instructions, MCP and skills are documented, a repository's custom agents are not.

- **Approvals:** VS Code's question popup shows only the question, so the Orchestrator never asks for an approval
  through it. Each pause is a chat message from `review.py show`: the files to read as links, then the reply
  options; `--open` opens them in the editor when the `code` command runs from a VS Code terminal (to confirm in
  the Agents window). Since 0.4.2.

## Dispatch (to verify)
The flow needs one agent to hand work to another with file paths. Candidates to test:
- custom agents with handoffs between them;
- an orchestrator agent that invokes other agents as subagents, if the host supports it;
- fallback: the Orchestrator runs stages sequentially in one session, loading each agent file as the
  instructions for that step. Slower and less isolated, but the run folder keeps the results identical.

## Hooks
Repository hooks in `.github/hooks/*.json` run for every session in a trusted folder (checked on Copilot CLI
1.0.116): `.github/hooks/fyzxsflow.json` carries kill-by-name and the FyzxsFlow hooks (HOW-TO.md, "The orchestrator
does no work"). Copilot also runs the hooks in `.claude/settings.json`. Agent-scoped frontmatter `hooks:` never
fired on the CLI. The main session's agent is read from `~/.copilot/session-state/<session>/events.jsonl`.
Trust the folder permanently ("remember this folder", stored as `trustedFolders` in `~/.copilot/config.json`):
`--trust-folder` can't be combined with `--resume`, so a resumed session in an untrusted folder skips every repo
hook ("Skipped repository hooks ... not trusted"). `COPILOT_ALLOW_ALL=true` also trusts it, but approves every tool.

## Transcripts
For correction mining, find where Copilot (VS Code agent mode, Copilot CLI, the coding agent) stores
session history, and write an extractor that emits the same `turns.jsonl` shape as
`.apm/skills/correction-mining/scripts/extract_claude.py`.

## To verify in the PoC
- [ ] Agent-to-agent dispatch: which of the options above works, and how inputs are passed.
- [ ] Whether `.apm/context/*` and `engine/` are reachable after install.
- [ ] How a skill typed as `/flow <text>` is run (Local and Agent Host harnesses), and how the text reaches it.
- [ ] Whether skills (`SKILL.md`) load on the Copilot surfaces used at work.
- [ ] Where session transcripts live.
- [ ] Whether custom agents honour a `model:` frontmatter line, and the model names to put in
      `config.json` → `models.copilot` (empty means inherit, which is the safe default until verified).
- [ ] The keyword for Copilot's Auto model selection in agent frontmatter, for `models.copilot.auto`.
- [ ] How to run a shadow dispatch in isolation on Copilot (a separate worktree or branch), for model compare.
- [ ] That `.github/instructions/*.instructions.md` with `applyTo: "glob1,glob2"` (comma-separated, as
      `engine/pointers.py` writes it) scopes correctly, and doesn't collide with what `apm install` writes there.

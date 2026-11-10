# Claude Code adapter

How FyzxsFlow maps onto Claude Code. Claude Code is the host the flow has been trialled on.

## What the installer writes
`engine/install.py --host claude` (also run after `apm install`) writes, from `.fyzxsflow/package/`:
- `.claude/agents/<name>.md`: each agent, with `model:` set from its tier (`config.json` → `models.claude`)
  and the project's Learned entries from `.fyzxsflow/learned/<name>.md` appended;
- `.claude/commands/<prompt>.md`: `/flow`, `/fyzxsflow-init` and `/fyzxsflow-greenfield`, with the user's text as
  `$ARGUMENTS`;
- `.claude/rules/fyzxsflow-working-agreement.md`: the always-on working agreement;
- the kill-by-name guard, merged into `.claude/settings.json` as a `PreToolUse` hook on `Bash|PowerShell`:
  `python -I "$CLAUDE_PROJECT_DIR/.fyzxsflow/package/engine/hooks/block_kill_by_name.py"` (`python3` where
  only that exists). Reinstalling updates the entry in place; it is never duplicated.

`install.py --sync` regenerates these from the installed package after the Curator edits `learned/`.

## Dispatch
The Orchestrator dispatches agents with Claude Code's Agent tool (subagents), passing file paths from the run
folder, never pasted context. A subagent can't dispatch further agents, so:
- the Orchestrator runs the Build Coordinator's Execute mode itself (`orchestrator.agent.md` → **Running Build**);
- Implementers, Testers and the IaC Implementer run their own checks through
  `.fyzxsflow/package/engine/runner.py` instead of asking the Build & Test Runner agent, which the Orchestrator
  dispatches for the stage checks (ci, http, extreme) and for classifying failures.

## Open questions
- [ ] Whether APM's `.apm/hooks/*.json` format can ship the hook, so `install.py` no longer has to merge it.
- [ ] APM end to end: `apm install` then `install.py` in a clean repo (see `HOW-TO.md` → **With APM**).

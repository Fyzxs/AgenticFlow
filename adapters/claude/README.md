# Claude Code adapter

`apm install` with target `claude` writes agents, rules (from `.apm/instructions`) and commands (from
`.apm/prompts`) into `.claude/`. This folder holds what APM does not cover yet, or what needs verifying.

## Dispatch
The Orchestrator dispatches agents through Claude Code's Agent tool (subagents). Each dispatch passes
file paths from the run folder, never pasted context.

## Hooks
Tool-call guards are Claude Code hooks. Add to `.claude/settings.json` (or ship as `.apm/hooks/*.json`
once the APM hook format is confirmed in the PoC):

```json
{
  "hooks": {
    "PreToolUse": [
      { "matcher": "Bash|PowerShell",
        "hooks": [ { "type": "command",
                     "command": "python -I \"$CLAUDE_PROJECT_DIR/engine/hooks/block_kill_by_name.py\"" } ] }
    ]
  }
}
```

Adjust the path to wherever the engine is installed in the target repo.

## To verify in the PoC
- [ ] Which folder APM writes `.agent.md` files to for Claude, and whether frontmatter maps cleanly
      (`name`, `description`).
- [ ] Whether `.apm/context/*` fragments are reachable by agents after install, or must be inlined.
- [ ] Whether `engine/` and `templates/` ship with the package (`includes: auto`) or need listing.
- [ ] The `.apm/hooks/*.json` schema and how APM merges it into `settings.json`.

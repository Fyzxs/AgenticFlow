"""Claude Code PreToolUse hook for the orchestrator (rules: orchestrator_rules.py).

  python -I orchestrator_guard_claude.py [--probe]

One entry in .claude/settings.json (install.py), matcher Edit|Write|MultiEdit|NotebookEdit|Bash|PowerShell|Agent|Task:
  - never-list, for every caller (subagents too): completing/merging PRs, raw PR and worktree commands, pushing or
    merging into the default branch (orchestrator_rules.never_list) are denied;
  - lane scope: an implementer or tester in a lane writing outside its packages' Scope, or into a tracked file
    through the shell, is denied (orchestrator_rules.maker_scope);
  - review gate: while the run waits on the owner's review, a dispatch or a lanes.py / pr.py move is denied
    (JSON permissionDecision "deny", the reason on stderr, exit 2);
  - delegation reminder: otherwise the orchestrator's own work runs, with `additionalContext` naming the agent to
    dispatch, and no permission decision, so the normal permission flow is unchanged.
--probe logs each payload's agent fields to .fyzxsflow/runs/_adhoc/hook-probe.jsonl and allows everything
(orchestrator_probe.py report reads it). Malformed input is allowed.
"""

import json
import pathlib
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))  # -I leaves the script's folder off sys.path
import orchestrator_rules as rules  # noqa: E402


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    try:
        payload = json.load(sys.stdin)
    except (ValueError, OSError):
        return 0
    if not isinstance(payload, dict):
        return 0
    if "--probe" in argv:
        rules.probe_log(payload, scoped=False)
        return 0
    blocked = (rules.never_list(payload) or rules.maker_scope(payload) or rules.review_gate(payload, scoped=False)
               or rules.handoff_gate(payload, scoped=False) or rules.report_guard(payload, scoped=False))
    if blocked:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                                 "permissionDecisionReason": blocked}}))
        sys.stderr.write(blocked + "\n")
        return 2
    note = rules.reminder(payload, scoped=False)
    if note:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": note}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())

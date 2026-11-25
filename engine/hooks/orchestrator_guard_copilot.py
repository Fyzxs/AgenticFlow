"""GitHub Copilot hooks for FyzxsFlow (rules: orchestrator_rules.py).

  python -I orchestrator_guard_copilot.py prompt                # userPromptSubmitted
  python -I orchestrator_guard_copilot.py pre  [--scoped] [--probe]   # preToolUse: blocks
  python -I orchestrator_guard_copilot.py post [--scoped]             # postToolUse: never blocks

Installed repo-wide in .github/hooks/fyzxsflow.json (install.py), so they run in every session in the trusted
folder. Agent-scoped `hooks:` frontmatter never fired on Copilot CLI 1.0.116, so it is not the main path; the
orchestrator agent still carries `pre --scoped` / `post --scoped` for hosts that honour it (VS Code).

Who the caller is: a subagent's call carries agentId/agentType. A main-session call carries no agent fields, so the
repo hooks read the session's selected agent from Copilot's session state (orchestrator_rules.copilot_selected_agent);
--scoped means the hook was declared on the orchestrator agent itself, so a main-session call is the orchestrator's.

  prompt: a FyzxsFlow skill (/flow, /fyzxsflow-*) typed in a session not running as its agent is blocked
          ({"decision": "block"}), before any model call. When the agent isn't known yet (the first prompt of a
          `-p` session), the first tool call checks it instead.
  pre:    the never-list, for every caller; an implementer or tester outside its lane's scope; the skill check
          above; the review gate for the orchestrator. Denies
          print {"permissionDecision": "deny"} (plus hookSpecificOutput for VS Code) and exit 2.
  post:   encoding damage in a file just edited (mojibake, LF turned CRLF), for every caller, and the delegation
          reminder for the orchestrator's own work, as additionalContext.
A preToolUse hook that fails denies the call (Copilot's rule), so a broken guard fails closed. Malformed input is
allowed. --probe (pre only) logs payloads to .fyzxsflow/runs/_adhoc/hook-probe.jsonl and allows everything.
"""

import json
import pathlib
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))  # -I leaves the script's folder off sys.path
import orchestrator_rules as rules  # noqa: E402


def deny(reason: str) -> int:
    """Copilot CLI: exit 0 with the decision on stdout (`copilot help hooks`). A non-zero exit is a failed hook:
    the call is still denied, but the model sees only "hook exited with code 2", never the reason (live, 1.0.116)."""
    print(json.dumps({"permissionDecision": "deny", "permissionDecisionReason": reason,
                      "hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                             "permissionDecisionReason": reason}}))
    sys.stderr.write(reason + "\n")
    return 0


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    event = next((a for a in argv if a in ("prompt", "pre", "post")), "pre")
    scoped = "--scoped" in argv
    try:
        payload = json.load(sys.stdin)
    except (ValueError, OSError):
        return 0
    if not isinstance(payload, dict):
        return 0
    if "--probe" in argv:
        if event == "pre":
            rules.probe_log(payload, scoped=scoped)
        return 0
    if event == "prompt":
        blocked = rules.skill_gate_prompt(payload)
        if blocked:
            print(json.dumps({"decision": "block", "reason": blocked}))
        return 0
    if event == "pre":
        blocked = (rules.never_list(payload) or rules.maker_scope(payload)
                   or (None if scoped else rules.skill_gate_tool(payload))
                   or rules.review_gate(payload, scoped=scoped) or rules.handoff_gate(payload, scoped=scoped))
        return deny(blocked) if blocked else 0
    notes = [n for n in (None if scoped else rules.encoding_problems(payload),
                         rules.reminder(payload, scoped=scoped)) if n]
    note = "\n\n".join(notes)
    if note:
        print(json.dumps({"additionalContext": note,
                          "hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": note}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())

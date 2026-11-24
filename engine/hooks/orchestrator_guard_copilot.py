"""GitHub Copilot hooks for the orchestrator (rules: orchestrator_rules.py), declared in the orchestrator agent's own
`hooks:` frontmatter (install.py), so they run only while that agent is selected.

  python -I orchestrator_guard_copilot.py pre  [--probe]   # PreToolUse: the review gate (blocks)
  python -I orchestrator_guard_copilot.py post [--probe]   # PostToolUse: the delegation reminder (never blocks)

Two events because Copilot CLI documents a deny only before a call and added context only after it.
Output carries both shapes: top-level keys (Copilot CLI) and hookSpecificOutput (VS Code). A deny also exits 2.
--probe (on pre only, so each call is logged once) logs payloads to .fyzxsflow/runs/_adhoc/hook-probe.jsonl and
allows everything. Malformed input is allowed.
"""

import json
import pathlib
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))  # -I leaves the script's folder off sys.path
import orchestrator_rules as rules  # noqa: E402


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    event = "post" if "post" in argv else "pre"
    try:
        payload = json.load(sys.stdin)
    except (ValueError, OSError):
        return 0
    if not isinstance(payload, dict):
        return 0
    if "--probe" in argv:
        if event == "pre":
            rules.probe_log(payload, scoped=True)
        return 0
    if event == "pre":
        blocked = rules.review_gate(payload, scoped=True)
        if not blocked:
            return 0
        print(json.dumps({"permissionDecision": "deny", "permissionDecisionReason": blocked,
                          "hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                                 "permissionDecisionReason": blocked}}))
        sys.stderr.write(blocked + "\n")
        return 2
    note = rules.reminder(payload, scoped=True)
    if note:
        print(json.dumps({"additionalContext": note,
                          "hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": note}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())

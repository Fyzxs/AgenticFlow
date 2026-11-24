"""Read what the orchestrator guard saw in probe mode (install.py --probe-hooks), to check the host before blocking.

  python -I .fyzxsflow/package/engine/hooks/orchestrator_probe.py report [--root .]

The guard depends on one fact about the host: a tool call from a subagent carries an `agent_id`, and the main
session's own calls don't (on Claude Code, the main session's calls also carry agent_type "orchestrator"). Start a
session as the orchestrator, ask it to edit a scratch file itself, then to dispatch one subagent (e.g. validator)
that edits a scratch file and runs `git status`; then run this report. It prints the rows for each kind of call and
says whether the guard can tell them apart. Exit 0 when it can, 1 when it can't, 2 with no probe rows.
"""

import argparse
import json
import pathlib
import sys


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("cmd", choices=["report"])
    p.add_argument("--root", default=".")
    args = p.parse_args(argv)
    log = pathlib.Path(args.root) / ".fyzxsflow" / "runs" / "_adhoc" / "hook-probe.jsonl"
    rows = [json.loads(l) for l in log.read_text(encoding="utf-8").splitlines() if l.strip()] if log.exists() else []
    if not rows:
        print(f"no probe rows in {log}: install with --probe-hooks, then run the session described above")
        return 2
    main_rows = [r for r in rows if not r["agent_id"]]
    sub_rows = [r for r in rows if r["agent_id"]]
    print(f"{len(rows)} calls: {len(main_rows)} without agent_id (main session), {len(sub_rows)} with (subagents)")
    for label, group in (("main session", main_rows), ("subagents", sub_rows)):
        kinds = sorted({(r["tool"], r["agent_type"] or "-", r["scoped"]) for r in group})
        for tool, agent_type, scoped in kinds:
            print(f"  {label}: tool={tool} agent_type={agent_type}{' (copilot, agent-scoped)' if scoped else ''}")
    claude_main = [r for r in main_rows if not r["scoped"]]
    ok = bool(main_rows) and bool(sub_rows) and all(r["agent_type"] == "orchestrator" for r in claude_main)
    if not sub_rows:
        print("no subagent calls were seen: dispatch one (or, on Copilot, the agent-scoped hook may not fire inside "
              "subagents, which is fine: then only the orchestrator's own calls reach it)")
        ok = bool(main_rows) and all(r["agent_type"] == "orchestrator" for r in claude_main)
    print("the guard can tell the orchestrator's own calls from its subagents': "
          + ("yes, the reminder reaches only the main session" if ok else "NO, keep the guard in probe mode and report this upstream"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

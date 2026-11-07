"""Append and list agentflow findings (schema: .apm/context/findings-schema.md).

  python -I engine/findings.py add --run <dir> --source validator --target implementer --kind agent-gap \
      --severity major --summary "..." --evidence src/a.cs:12 [--evidence ...] [--rule "..."] [--fixed]
  python -I engine/findings.py list --run <dir> [--kind agent-gap] [--target implementer]
"""

import argparse
import json
import pathlib
import sys

KINDS = ("instance", "agent-gap", "context-gap", "docs-drift", "flag", "flake", "env",
         "scope-request", "replan", "owner-decision")
SEVERITIES = ("major", "medium", "minor", "observation")


def load(run: pathlib.Path):
    path = run / "findings.jsonl"
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def validate(f: dict) -> list:
    errors = []
    for key in ("source", "target", "kind", "severity", "summary", "evidence"):
        if not f.get(key):
            errors.append(f"missing {key}")
    if f.get("kind") and f["kind"] not in KINDS:
        errors.append(f"kind must be one of {', '.join(KINDS)}")
    if f.get("severity") and f["severity"] not in SEVERITIES:
        errors.append(f"severity must be one of {', '.join(SEVERITIES)}")
    if f.get("kind") == "agent-gap" and not f.get("rule"):
        errors.append("an agent-gap finding needs --rule (the instruction that would have prevented it)")
    return errors


def cmd_add(args) -> int:
    run = pathlib.Path(args.run)
    if not run.is_dir():
        print(f"run folder not found: {run}", file=sys.stderr)
        return 2
    existing = load(run)
    finding = {
        "id": f"F-{len(existing) + 1}",
        "run": run.name,
        "source": args.source,
        "target": args.target,
        "kind": args.kind,
        "severity": args.severity,
        "summary": args.summary.strip(),
        "evidence": args.evidence or [],
    }
    if args.rule:
        finding["rule"] = args.rule.strip()
    if args.fixed:
        finding["fixed"] = True
    errors = validate(finding)
    if errors:
        print("finding rejected: " + "; ".join(errors), file=sys.stderr)
        return 2
    with open(run / "findings.jsonl", "a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(finding, ensure_ascii=False) + "\n")
    print(finding["id"])
    return 0


def cmd_list(args) -> int:
    for f in load(pathlib.Path(args.run)):
        if args.kind and f["kind"] != args.kind:
            continue
        if args.target and f["target"] != args.target:
            continue
        print(f"{f['id']} [{f['severity']}] {f['kind']} {f['source']}->{f['target']}: {f['summary']}")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add")
    a.add_argument("--run", required=True)
    a.add_argument("--source", required=True)
    a.add_argument("--target", required=True)
    a.add_argument("--kind", required=True)
    a.add_argument("--severity", required=True)
    a.add_argument("--summary", required=True)
    a.add_argument("--evidence", action="append")
    a.add_argument("--rule")
    a.add_argument("--fixed", action="store_true")
    l = sub.add_parser("list")
    l.add_argument("--run", required=True)
    l.add_argument("--kind")
    l.add_argument("--target")
    args = p.parse_args(argv)
    return {"add": cmd_add, "list": cmd_list}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())

"""Create and track agentflow run folders.

  python -I engine/run.py new --source prompt --ref "add a pull list page"   -> prints the run folder
  python -I engine/run.py log <run-dir> <stage> <status> "<message>"          -> appends a ledger line
  python -I engine/run.py status <run-dir> [--lines 8]                        -> prints the latest ledger lines

The run folder layout is described in .apm/context/run-folder.md.
"""

import argparse
import datetime
import pathlib
import re
import sys

STATUSES = ("started", "done", "failed", "gated", "resumed")
LEDGER_HEADER = "# Ledger\n\n| time (UTC) | stage | status | note |\n|---|---|---|---|\n"


def now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return (s[:30].rstrip("-")) or "run"


def cmd_new(args) -> int:
    root = pathlib.Path(args.root).resolve()
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d-%H%M%S")
    run_id = f"{stamp}-{slug(args.ref)}"
    run = root / ".agentflow" / "runs" / run_id
    for sub in ("work-packages", "reports", "runner"):
        (run / sub).mkdir(parents=True, exist_ok=False)
    (run / "input.md").write_text(
        f"---\nsource: {args.source}\nrun: {run_id}\n---\n\n{args.ref}\n", encoding="utf-8", newline="\n")
    (run / "findings.jsonl").write_text("", encoding="utf-8")
    (run / "ledger.md").write_text(LEDGER_HEADER, encoding="utf-8", newline="\n")
    append(run, "run", "started", f"source={args.source}")
    print(run)
    return 0


def append(run: pathlib.Path, stage: str, status: str, note: str) -> None:
    note = note.replace("|", "/").replace("\n", " ").strip()
    with open(run / "ledger.md", "a", encoding="utf-8", newline="\n") as f:
        f.write(f"| {now()} | {stage} | {status} | {note} |\n")


def cmd_log(args) -> int:
    run = pathlib.Path(args.run)
    if not (run / "ledger.md").exists():
        print(f"no ledger in {run}", file=sys.stderr)
        return 2
    if args.status not in STATUSES:
        print(f"status must be one of {', '.join(STATUSES)}", file=sys.stderr)
        return 2
    append(run, args.stage, args.status, args.note)
    return 0


def cmd_status(args) -> int:
    run = pathlib.Path(args.run)
    rows = [l for l in (run / "ledger.md").read_text(encoding="utf-8").splitlines() if l.startswith("| 20")]
    for line in rows[-args.lines:]:
        print(line)
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    n = sub.add_parser("new")
    n.add_argument("--source", required=True, help="prompt | ado:<id>")
    n.add_argument("--ref", required=True, help="the prompt text or work item reference")
    n.add_argument("--root", default=".", help="repo root (default: current directory)")
    l = sub.add_parser("log")
    l.add_argument("run"); l.add_argument("stage"); l.add_argument("status"); l.add_argument("note")
    s = sub.add_parser("status")
    s.add_argument("run"); s.add_argument("--lines", type=int, default=8)
    args = p.parse_args(argv)
    return {"new": cmd_new, "log": cmd_log, "status": cmd_status}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())

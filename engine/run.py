"""Create and track agentflow run folders.

  python -I engine/run.py new --source prompt --ref "add a pull list page"   -> prints the run folder
  python -I engine/run.py log <run-dir> <stage> <status> "<message>"          -> appends a ledger line
  python -I engine/run.py status <run-dir> [--lines 8]                        -> prints the latest ledger lines
  python -I engine/run.py checkpoint <run-dir> <stage>                        -> commits the run folder (only it)
  python -I engine/run.py edits <run-dir> [--record]                          -> lists files changed since the last checkpoint
  python -I engine/run.py close <run-dir> --outcome completed|abandoned [--note "PR #12"]
  python -I engine/run.py list [--root .]                                      -> active runs with their last ledger line

Runs live in .agentflow/runs/active/<id>/ while work is in flight, and move to runs/completed/<id>/ (a PR was
delivered) or runs/abandoned/<id>/ (stopped, with the reason in the ledger) when closed. Only active runs are
resumed.

Runs are kept in git by default, so humans can review the brief, plan, reports and findings, and edit them
between stages: the next stage reads the edited files. .agentflow/profile.md `Runs: local` turns commits
off. Raw step logs (runner/<invocation>/, gates/<invocation>/) are never committed; their JSON summaries are.

`edits --record` treats every change since the last checkpoint as an owner edit: it writes a ledger line, a
`human-edit` finding per file (the Curator diffs them against the checkpoint to learn what the agent got
wrong), and checkpoints the edits. Call it only at stage boundaries, right after the previous checkpoint.

The run folder layout is described in .agentflow/context/run-folder.md.
"""

import argparse
import datetime
import json
import pathlib
import re
import subprocess
import sys

STATUSES = ("started", "done", "failed", "gated", "resumed")
RUN_GITIGNORE = ("# Raw logs stay local; their summaries (runner/*.json, gates/*.json) and every other\n"
                 "# artifact are kept so the run can be reviewed and edited.\n"
                 "runner/*/\ngates/*/\n")
REVIEW_REQUESTS = """# Review requests for this run

<!-- Ask for reviews beyond each agent's level, for this run only. Edit this file any time; the next stage
     picks it up. One per line:
       - review: package=WP-03         - review: segment=db-migration     - review: agent=implementer
       - review: stage=deliver          - review: path=**/Auth/**          - review: all
       - autopilot                      (skip agent-level reviews this run; config review.always still applies)
     Replying to any review with -less-review or -more-review changes that agent's level for future runs. -->
"""
RUNS_MODE = re.compile(r"^\s*-?\s*Runs:\s*`?(commit|local)`?", re.M | re.I)
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
    run = root / ".agentflow" / "runs" / "active" / run_id
    for sub in ("work-packages", "reports", "runner"):
        (run / sub).mkdir(parents=True, exist_ok=False)
    (run / "input.md").write_text(
        f"---\nsource: {args.source}\nrun: {run_id}\n---\n\n{args.ref}\n", encoding="utf-8", newline="\n")
    (run / "findings.jsonl").write_text("", encoding="utf-8")
    (run / ".gitignore").write_text(RUN_GITIGNORE, encoding="utf-8", newline="\n")
    (run / "review-requests.md").write_text(REVIEW_REQUESTS, encoding="utf-8", newline="\n")
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


def repo_root(run: pathlib.Path) -> pathlib.Path:
    """The folder that contains .agentflow/, wherever the run sits (runs/active|completed|abandoned/<id>)."""
    for parent in run.resolve().parents:
        if parent.name == ".agentflow":
            return parent.parent
    raise SystemExit(f"{run} is not inside a .agentflow/ folder")


def cmd_close(args) -> int:
    run = pathlib.Path(args.run).resolve()
    if run.parent.name != "active":
        print(f"only active runs can be closed; {run} is in '{run.parent.name}'", file=sys.stderr)
        return 2
    root = repo_root(run)
    dest = run.parent.parent / args.outcome / run.name
    if dest.exists():
        print(f"{dest} already exists", file=sys.stderr)
        return 2
    note = f"{args.outcome}: {args.note}" if args.note else args.outcome
    if runs_mode(root) == "local":
        append(run, "run", "done" if args.outcome == "completed" else "failed", note)
        dest.parent.mkdir(parents=True, exist_ok=True)
        run.rename(dest)
        print(dest)
        return 0
    checkpoint(run, "before close")  # anything pending is recorded at its active path first
    dest.parent.mkdir(parents=True, exist_ok=True)
    src_rel, dest_rel = (p.relative_to(root).as_posix() for p in (run, dest))
    mv = git(root, "mv", src_rel, dest_rel)
    if mv.returncode != 0:  # never committed (e.g. checkpoint had nothing to add): move on disk
        run.rename(dest)
    append(dest, "run", "done" if args.outcome == "completed" else "failed", note)
    git(root, "add", "--", dest_rel)
    commit = git(root, "commit", "-q", "-m", f"agentflow({run.name}): {args.outcome}", "--", src_rel, dest_rel)
    if commit.returncode != 0:
        raise SystemExit(f"git commit failed: {commit.stderr.strip() or commit.stdout.strip()}")
    print(dest)
    return 0


def cmd_list(args) -> int:
    runs = pathlib.Path(args.root).resolve() / ".agentflow" / "runs"
    for state in ("active", "completed", "abandoned"):
        folders = sorted(p for p in (runs / state).glob("*") if p.is_dir()) if (runs / state).is_dir() else []
        if state != "active":
            print(f"{state}: {len(folders)}")
            continue
        print(f"active: {len(folders)}")
        for f in folders:
            rows = [l for l in (f / "ledger.md").read_text(encoding="utf-8").splitlines() if l.startswith("| 20")]
            print(f"  {f.name}  {rows[-1] if rows else ''}")
    return 0


def runs_mode(root: pathlib.Path) -> str:
    profile = root / ".agentflow" / "profile.md"
    if profile.exists():
        m = RUNS_MODE.search(profile.read_text(encoding="utf-8"))
        if m:
            return m.group(1).lower()
    return "commit"


def git(root: pathlib.Path, *args) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)


def changed_files(root: pathlib.Path, run: pathlib.Path) -> list:
    rel = run.resolve().relative_to(root).as_posix()
    out = git(root, "status", "--porcelain", "--untracked-files=all", "--", rel)
    if out.returncode != 0:
        raise SystemExit(f"git status failed: {out.stderr.strip()}")
    files = []
    for line in out.stdout.splitlines():
        path = line[3:].strip().strip('"')
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        files.append(path)
    return files


def checkpoint(run: pathlib.Path, stage: str) -> str:
    root = repo_root(run)
    if runs_mode(root) == "local":
        return "runs are local (profile Runs: local); nothing committed"
    rel = run.resolve().relative_to(root).as_posix()
    if not changed_files(root, run):
        return "nothing new to checkpoint"
    add = git(root, "add", "--", rel)
    if add.returncode != 0:
        raise SystemExit(f"git add failed: {add.stderr.strip()}")
    # A pathspec commit records only the run folder, whatever else is staged in the repo.
    commit = git(root, "commit", "-q", "-m", f"agentflow({run.name}): {stage}", "--", rel)
    if commit.returncode != 0:
        raise SystemExit(f"git commit failed: {commit.stderr.strip() or commit.stdout.strip()}")
    return git(root, "rev-parse", "--short", "HEAD").stdout.strip()


def cmd_checkpoint(args) -> int:
    run = pathlib.Path(args.run)
    if not (run / "ledger.md").exists():
        print(f"no ledger in {run}", file=sys.stderr)
        return 2
    print(checkpoint(run, args.stage))
    return 0


def cmd_edits(args) -> int:
    run = pathlib.Path(args.run)
    root = repo_root(run)
    files = changed_files(root, run)
    for f in files:
        print(f)
    if not files:
        print("no edits since the last checkpoint")
        return 0
    if args.record:
        append(run, "owner-edit", "resumed", "edited since last checkpoint: " + ", ".join(files))
        sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
        import findings  # noqa: E402
        for f in files:
            if f.endswith(("ledger.md", "findings.jsonl")):
                continue
            findings.cmd_add(argparse.Namespace(
                run=str(run), source="human", target=f, kind="human-edit", severity="observation",
                summary=f"the owner edited {f} after the last checkpoint", evidence=[f], rule=None, fixed=False))
        print(checkpoint(run, "owner edits"))
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    cl = sub.add_parser("close")
    cl.add_argument("run"); cl.add_argument("--outcome", required=True, choices=["completed", "abandoned"])
    cl.add_argument("--note", default="", help="e.g. the PR link, or why the run was abandoned")
    ls = sub.add_parser("list")
    ls.add_argument("--root", default=".")
    c = sub.add_parser("checkpoint")
    c.add_argument("run"); c.add_argument("stage")
    e = sub.add_parser("edits")
    e.add_argument("run"); e.add_argument("--record", action="store_true")
    n = sub.add_parser("new")
    n.add_argument("--source", required=True, help="prompt | ado:<id>")
    n.add_argument("--ref", required=True, help="the prompt text or work item reference")
    n.add_argument("--root", default=".", help="repo root (default: current directory)")
    l = sub.add_parser("log")
    l.add_argument("run"); l.add_argument("stage"); l.add_argument("status"); l.add_argument("note")
    s = sub.add_parser("status")
    s.add_argument("run"); s.add_argument("--lines", type=int, default=8)
    args = p.parse_args(argv)
    return {"new": cmd_new, "log": cmd_log, "status": cmd_status,
            "checkpoint": cmd_checkpoint, "edits": cmd_edits, "close": cmd_close, "list": cmd_list}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())

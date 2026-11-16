"""Append, amend and list fyzxsflow findings (schema: .fyzxsflow/package/context/findings-schema.md).

  python -I .fyzxsflow/package/engine/findings.py add --run <dir> --source validator --target implementer \
      --kind agent-gap --severity major --summary "..." --evidence src/a.cs:12 [--evidence ...] [--rule "..."] \
      [--fixed] [--detail "<full text>"]
  python -I .fyzxsflow/package/engine/findings.py amend --run <dir> <F-n> --note "<what changed>" [--fixed]
      [--severity <s>] [--evidence <path> ...]
  python -I .fyzxsflow/package/engine/findings.py resolve --run <dir> <F-n> --by <commit sha | F-n> --note "<how>"
  python -I .fyzxsflow/package/engine/findings.py list --run <dir> [--kind agent-gap] [--target implementer] [--open]
  python -I .fyzxsflow/package/engine/findings.py merge-driver <base> <ours> <theirs>   (git runs this; see below)

--run takes the run folder or the bare run id.

`amend` updates a finding in place and keeps a dated note of every change, so a correction (it was fixed, the
evidence moved, the severity was wrong) never needs a second finding. `resolve` closes one: it marks it fixed and
records what fixed it (a commit, or the finding that supersedes it) in `resolution`, with a dated amendment.

Ids are unique across every worktree of the repo: lanes and the run checkout allocate them from one counter in the
git common directory (`fyzxsflow-ids/<run-id>.json`), never below the highest id already in the file, so two lanes
never mint the same id. Outside git, the next id is the highest + 1.

`merge-driver` merges two copies of a run's findings.jsonl by id (three-way, field by field): a finding changed on
one side only takes that side, new findings from both sides are kept, lists (evidence, amendments) are unioned, and
`fixed` is kept if either side set it. Exit 1 only when both sides changed the same field differently. `lanes.py`
registers it for `.fyzxsflow/runs/**/findings.jsonl` (and git's union merge for ledger.md and reviews.jsonl) in the
repo's local git config, so merging the run branch into a lane, or a lane's PR into the run branch, no longer
conflicts on the run folder.
"""

import argparse
import datetime
import json
import os
import pathlib
import re
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from layout import common_dir  # noqa: E402

KINDS = ("instance", "agent-gap", "context-gap", "docs-drift", "flag", "flake", "env", "human-edit", "escalation",
         "scope-request", "replan", "owner-decision", "owner-feedback")
SEVERITIES = ("major", "medium", "minor", "observation")
OWNER_TARGETS = ("owner", "the-owner", "human", "user")


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
    if str(f.get("target", "")).strip().lower().replace(" ", "-") in OWNER_TARGETS and \
            f.get("kind") not in ("owner-decision", "owner-feedback"):
        errors.append("a finding for the owner is --kind owner-decision (only that kind reaches the owner at a "
                      "gate); with any other kind, the target is what it is about: an agent, a doc path, code, a "
                      "package id")
    if f.get("kind") == "agent-gap" and not f.get("rule"):
        errors.append("an agent-gap finding needs --rule (the instruction that would have prevented it)")
    return errors


def number(fid) -> int:
    m = re.fullmatch(r"F-(\d+)", str(fid))
    return int(m.group(1)) if m else 0


class IdLock:
    """A lock file taken with O_EXCL; one left behind for over 30 s by a dead allocator is broken."""

    def __init__(self, path: pathlib.Path):
        self.path = path

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.time() + 15
        while True:
            try:
                os.close(os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
                return self
            except FileExistsError:
                try:
                    if time.time() - self.path.stat().st_mtime > 30:
                        self.path.unlink()
                        continue
                except OSError:
                    continue
                if time.time() > deadline:
                    raise SystemExit(f"could not take the finding-id lock {self.path}; remove it if no findings.py "
                                     "is running")
                time.sleep(0.05)

    def __exit__(self, *exc):
        try:
            self.path.unlink()
        except OSError:
            pass


def next_id(run: pathlib.Path, existing: list) -> str:
    """The next id: one counter per run, shared by every worktree (lanes), never below the file's highest + 1."""
    local = max((number(f.get("id")) for f in existing), default=0) + 1
    common = common_dir(run if run.is_dir() else run.parent)
    if common is None:
        return f"F-{local}"
    folder = common / "fyzxsflow-ids"
    counter = folder / f"{run.resolve().name}.json"
    with IdLock(folder / f"{run.resolve().name}.lock"):
        try:
            shared = int(json.loads(counter.read_text(encoding="utf-8")).get("next", 1))
        except (OSError, ValueError):
            shared = 1
        n = max(shared, local)
        counter.write_text(json.dumps({"next": n + 1}) + "\n", encoding="utf-8")
    return f"F-{n}"


def write_all(run: pathlib.Path, found: list):
    with open(run / "findings.jsonl", "w", encoding="utf-8", newline="\n") as fh:
        for f in found:
            fh.write(json.dumps(f, ensure_ascii=False) + "\n")


def cmd_add(args) -> int:
    run = pathlib.Path(args.run)
    if not run.is_dir():
        print(f"run folder not found: {run}", file=sys.stderr)
        return 2
    existing = load(run)
    finding = {
        "id": "",
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
    if getattr(args, "detail", None):
        finding["detail"] = args.detail.strip()
    errors = validate(finding)
    if errors:
        print("finding rejected: " + "; ".join(errors), file=sys.stderr)
        return 2
    finding["id"] = next_id(run, existing)
    with open(run / "findings.jsonl", "a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(finding, ensure_ascii=False) + "\n")
    print(finding["id"])
    return 0


def cmd_amend(args) -> int:
    run = pathlib.Path(args.run)
    found = load(run)
    target = next((f for f in found if f.get("id") == args.id), None)
    if target is None:
        print(f"no finding {args.id} in {run / 'findings.jsonl'}", file=sys.stderr)
        return 2
    changes = []
    if args.fixed and not target.get("fixed"):
        target["fixed"] = True
        changes.append("fixed")
    if args.severity and args.severity != target.get("severity"):
        if args.severity not in SEVERITIES:
            print(f"severity must be one of {', '.join(SEVERITIES)}", file=sys.stderr)
            return 2
        changes.append(f"severity {target.get('severity')} -> {args.severity}")
        target["severity"] = args.severity
    for ev in args.evidence or []:
        if ev not in target["evidence"]:
            target["evidence"].append(ev)
            changes.append(f"evidence + {ev}")
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    target.setdefault("amendments", []).append({"time": stamp, "note": args.note.strip(), "changes": changes})
    write_all(run, found)
    print(f"{args.id} amended: {', '.join(changes) or 'note only'}")
    return 0


def cmd_resolve(args) -> int:
    run = pathlib.Path(args.run)
    found = load(run)
    target = next((f for f in found if f.get("id") == args.id), None)
    if target is None:
        print(f"no finding {args.id} in {run / 'findings.jsonl'}", file=sys.stderr)
        return 2
    if re.fullmatch(r"F-\d+", args.by) and not any(f.get("id") == args.by for f in found):
        print(f"--by {args.by}: no such finding in this run", file=sys.stderr)
        return 2
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    target["fixed"] = True
    target["resolution"] = {"by": args.by, "note": args.note.strip(), "time": stamp}
    target.setdefault("amendments", []).append({"time": stamp, "note": args.note.strip(),
                                                "changes": [f"resolved by {args.by}"]})
    write_all(run, found)
    print(f"{args.id} resolved by {args.by}")
    return 0


# ---------------------------------------------------------------- the git merge driver

def read_rows(path) -> list:
    try:
        text = pathlib.Path(path).read_text(encoding="utf-8")
    except OSError:
        return []
    return [json.loads(l) for l in text.splitlines() if l.strip()]


def merge_row(base, ours, theirs):
    """(merged row, conflicting keys)."""
    out, clash = {}, []
    for k in list(ours) + [k for k in theirs if k not in ours]:
        b, o, t = (base or {}).get(k), ours.get(k), theirs.get(k)
        if o == t or t == b:
            v = o
        elif o == b:
            v = t
        elif k == "fixed":
            v = bool(o) or bool(t)
        elif isinstance(o, list) and isinstance(t, list):
            v = o + [x for x in t if x not in o]
        else:
            v = o
            clash.append(k)
        if v is not None or k in ours:
            out[k] = v
    return out, clash


def merge_findings(base: list, ours: list, theirs: list):
    """(merged rows, problems)."""
    b = {r.get("id"): r for r in base}
    t = {r.get("id"): r for r in theirs}
    out, problems = [], []
    for row in ours:
        i = row.get("id")
        if i in t:
            merged, clash = merge_row(b.get(i), row, t[i])
            if clash:
                why = "added on both sides with different content" if i not in b else "changed on both sides"
                problems.append(f"{i}: {why} ({', '.join(clash)})")
            out.append(merged)
        else:
            out.append(row)
    have = {r.get("id") for r in ours}
    out += [r for r in theirs if r.get("id") not in have]
    return out, problems


def cmd_merge_driver(args) -> int:
    merged, problems = merge_findings(read_rows(args.base), read_rows(args.ours), read_rows(args.theirs))
    with open(args.ours, "w", encoding="utf-8", newline="\n") as fh:
        for r in merged:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    for p in problems:
        print(f"findings.jsonl: {p}; ours kept, resolve it with findings.py amend", file=sys.stderr)
    return 1 if problems else 0


def cmd_list(args) -> int:
    for f in load(pathlib.Path(args.run)):
        if args.kind and f["kind"] != args.kind:
            continue
        if args.target and f["target"] != args.target:
            continue
        if getattr(args, "open", False) and f.get("fixed"):
            continue
        print(f"{f['id']} [{f['severity']}] {f['kind']} {f['source']}->{f['target']}: {f['summary']}"
              + (" (fixed)" if f.get("fixed") else ""))
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
    a.add_argument("--detail", help="full text, e.g. the owner's feedback verbatim")
    m = sub.add_parser("amend")
    m.add_argument("id", help="e.g. F-12")
    m.add_argument("--run", required=True)
    m.add_argument("--note", required=True, help="what changed and why")
    m.add_argument("--fixed", action="store_true")
    m.add_argument("--severity")
    m.add_argument("--evidence", action="append")
    v = sub.add_parser("resolve")
    v.add_argument("id", help="e.g. F-12")
    v.add_argument("--run", required=True)
    v.add_argument("--by", required=True, help="the commit sha that fixed it, or the finding (F-n) that supersedes it")
    v.add_argument("--note", required=True, help="how it was resolved")
    d = sub.add_parser("merge-driver")
    d.add_argument("base"); d.add_argument("ours"); d.add_argument("theirs")
    d.add_argument("path", nargs="?")
    l = sub.add_parser("list")
    l.add_argument("--run", required=True)
    l.add_argument("--kind")
    l.add_argument("--target")
    l.add_argument("--open", action="store_true", help="only findings not marked fixed")
    args = p.parse_args(argv)
    if getattr(args, "run", None):  # a bare run id resolves under .fyzxsflow/runs/
        sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
        from layout import resolve_run
        args.run = str(resolve_run(args.run))
    return {"add": cmd_add, "amend": cmd_amend, "resolve": cmd_resolve, "list": cmd_list,
            "merge-driver": cmd_merge_driver}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())

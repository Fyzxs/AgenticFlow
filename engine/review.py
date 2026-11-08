"""Human-in-the-loop review between agent hand-offs.

  python -I .agentflow/engine/review.py needed --run <dir> --agent <name> [--stage S] [--package WP-02]
      [--segment SEG] [--paths p1 p2 ...]          -> "review=pause|notify|no reason=<why> level=<level>"
  python -I .agentflow/engine/review.py decide --run <dir> --agent <name> --target <WP-02|stage> --reply "<owner reply>"
      [--edited N]                                  -> "decision=<d> adjust=<less-review|more-review|none> level=<a>-><b> note=<...>"
  python -I .agentflow/engine/review.py set-level --agent <name> --level on|notify|off --reason "<owner's words>"
  python -I .agentflow/engine/review.py regress --agent <name> --reason "<evidence>"   (system: raise to on)
  python -I .agentflow/engine/review.py summary [--root .]

Levels, per agent, in config.json -> review: on (pause for the owner), notify (post the summary, don't pause),
off (no review). Every agent starts at review.default ("on").

An owner reply starts with approve | continue | redo | stop, and may carry -less-review or -more-review anywhere:
it moves the reviewed agent's level one step (on <-> notify <-> off). Only the owner lowers a level; the
system may raise one on evidence (regress), never lower it.

Whatever the level, a review is forced when the run's review-requests.md or config review.always matches:
  review-requests.md lines:  "- review: agent=<a>" | "stage=<s>" | "package=<WP-n>" | "segment=<seg>" |
                             "path=<glob>" | "all"      and   "- autopilot" (toggles off for this run)
  review.always:             { "segments": [...], "paths": [...] }   (autopilot never overrides these)
"""

import argparse
import datetime
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from docs_check import glob_to_regex  # noqa: E402

LADDER = ["off", "notify", "on"]
DECISIONS = ("approve", "continue", "redo", "stop")
DEFAULTS = {"default": "on", "agents": {}, "always": {"segments": [], "paths": []}, "graduate_after": 10}
REQUEST = re.compile(r"^\s*-\s*review:\s*(?:(all)|(agent|stage|package|segment|path)\s*=\s*(\S+))\s*$", re.M | re.I)
AUTOPILOT = re.compile(r"^\s*-\s*autopilot\s*$", re.M | re.I)


def root_of(path: pathlib.Path) -> pathlib.Path:
    for parent in [path.resolve(), *path.resolve().parents]:
        if parent.name == ".agentflow":
            return parent.parent
    raise SystemExit(f"{path} is not inside a .agentflow/ folder")


def load_config(root: pathlib.Path):
    path = root / ".agentflow" / "config.json"
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    review = dict(DEFAULTS)
    review.update(data.get("review") or {})
    review["always"] = {**DEFAULTS["always"], **(review.get("always") or {})}
    return path, data, review


def level_of(review: dict, agent: str) -> str:
    level = (review.get("agents") or {}).get(agent, review.get("default", "on"))
    return level if level in LADDER else "on"


def save_level(root: pathlib.Path, agent: str, level: str):
    path, data, review = load_config(root)
    stored = data.setdefault("review", {})
    for k, v in DEFAULTS.items():
        stored.setdefault(k, v if not isinstance(v, dict) else dict(v))
    stored["agents"][agent] = level
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8", newline="\n")


def commit_policy(root: pathlib.Path, agent: str, before: str, after: str, by: str):
    """Record a review-level change as its own commit (only config.json and the project review log)."""
    import run as runmod  # noqa: E402  (same engine folder)
    if runmod.runs_mode(root) == "local" or runmod.git(root, "rev-parse", "--git-dir").returncode != 0:
        return
    paths = [p for p in (".agentflow/config.json", ".agentflow/reviews.jsonl") if (root / p).exists()]
    runmod.git(root, "add", "--", *paths)
    runmod.git(root, "commit", "-q", "-m", f"agentflow: review level for {agent} {before} -> {after} ({by})", "--", *paths)


def log(root: pathlib.Path, run, entry: dict):
    """Review decisions and level changes: per run when there is one, else the project-level log."""
    entry = {"time": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S"), **entry}
    target = (run / "reviews.jsonl") if run else (root / ".agentflow" / "reviews.jsonl")
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(entry) + "\n")


def cmd_needed(args) -> int:
    run = pathlib.Path(args.run)
    root = root_of(run)
    _, _, review = load_config(root)
    level = level_of(review, args.agent)
    paths = args.paths or []

    def any_path(globs):
        rxs = [glob_to_regex(g) for g in globs]
        return next((p for p in paths for rx in rxs if rx.match(p)), None)

    if args.segment and args.segment in review["always"]["segments"]:
        print(f"review=pause reason=always:segment={args.segment} level={level}")
        return 0
    hit = any_path(review["always"]["paths"])
    if hit:
        print(f"review=pause reason=always:path={hit} level={level}")
        return 0
    req_file = run / "review-requests.md"
    requests = req_file.read_text(encoding="utf-8") if req_file.exists() else ""
    wanted = {"agent": args.agent, "stage": args.stage, "package": args.package, "segment": args.segment}
    for m in REQUEST.finditer(requests):
        if m.group(1):
            print(f"review=pause reason=run-request:all level={level}")
            return 0
        key, value = m.group(2).lower(), m.group(3)
        if key == "path" and any_path([value]):
            print(f"review=pause reason=run-request:path={value} level={level}")
            return 0
        if key != "path" and wanted.get(key) and wanted[key].lower() == value.lower():
            print(f"review=pause reason=run-request:{key}={value} level={level}")
            return 0
    if AUTOPILOT.search(requests):
        print(f"review=no reason=autopilot level={level}")
        return 0
    action = {"on": "pause", "notify": "notify", "off": "no"}[level]
    print(f"review={action} reason=agent-level level={level}")
    return 0


FLAG_WORDS = ("-less-review", "--less-review", "-more-review", "--more-review")


def parse_reply(reply: str):
    words = reply.strip().split()
    if not words:
        raise ValueError("empty reply")
    decision = words[0].lower().rstrip(":,.")
    if decision not in DECISIONS:
        raise ValueError(f"a reply starts with one of: {', '.join(DECISIONS)}")
    lowered = [w.lower() for w in words]
    retired = [w for w in lowered if w.lstrip("-") in ("reduce", "increase") and w.startswith("-")]
    if retired:
        raise ValueError(f"{retired[0]} was renamed: use -less-review or -more-review")
    flags = {w.lstrip("-") for w in lowered if w in FLAG_WORDS}
    if len(flags) > 1:
        raise ValueError("use -less-review or -more-review, not both")
    note = " ".join(w for w in words[1:] if w.lower() not in FLAG_WORDS)
    return decision, (flags.pop() if flags else "none"), note.lstrip(":").strip()


def step(level: str, adjust: str) -> str:
    i = LADDER.index(level) + (1 if adjust == "more-review" else -1 if adjust == "less-review" else 0)
    return LADDER[max(0, min(i, len(LADDER) - 1))]


def cmd_decide(args) -> int:
    run = pathlib.Path(args.run)
    root = root_of(run)
    try:
        decision, adjust, note = parse_reply(args.reply)
    except ValueError as e:
        print(f"reply not understood: {e}. Examples: 'approve', 'approve -less-review', 'redo: tests miss nulls -more-review'",
              file=sys.stderr)
        return 2
    _, _, review = load_config(root)
    before = level_of(review, args.agent)
    after = step(before, adjust)
    if after != before:
        save_level(root, args.agent, after)
    clean = decision in ("approve", "continue") and args.edited == 0
    log(root, run, {"agent": args.agent, "target": args.target, "decision": decision, "adjust": adjust,
                    "level_before": before, "level_after": after, "edited_files": args.edited, "clean": clean,
                    "by": "owner", "reply": args.reply})
    if after != before:
        commit_policy(root, args.agent, before, after, "owner")
    unchanged = " (already at the limit)" if adjust != "none" and after == before else ""
    print(f"decision={decision} adjust={adjust} level={before}->{after}{unchanged} note={note}")
    return 0


def cmd_set_level(args) -> int:
    root = root_of(pathlib.Path(args.root) / ".agentflow")
    _, _, review = load_config(root)
    before = level_of(review, args.agent)
    save_level(root, args.agent, args.level)
    log(root, None, {"agent": args.agent, "decision": "set-level", "level_before": before, "level_after": args.level,
                     "by": "owner", "reason": args.reason})
    commit_policy(root, args.agent, before, args.level, "owner")
    print(f"level={before}->{args.level}")
    return 0


def cmd_regress(args) -> int:
    root = root_of(pathlib.Path(args.root) / ".agentflow")
    _, _, review = load_config(root)
    before = level_of(review, args.agent)
    if before == "on":
        print("level=on (unchanged)")
        return 0
    save_level(root, args.agent, "on")
    log(root, None, {"agent": args.agent, "decision": "regress", "level_before": before, "level_after": "on",
                     "by": "system", "reason": args.reason})
    commit_policy(root, args.agent, before, "on", "system, on evidence")
    print(f"level={before}->on (raised by the system on evidence; only the owner can lower it again)")
    return 0


def cmd_summary(args) -> int:
    root = pathlib.Path(args.root).resolve()
    _, _, review = load_config(root)
    entries = []
    base = root / ".agentflow"
    for path in sorted(base.rglob("reviews.jsonl")):
        if "_adhoc" in path.parts:
            continue
        entries += [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    entries.sort(key=lambda e: e.get("time", ""))
    agents = sorted({e["agent"] for e in entries} | set(review.get("agents") or {}))
    if not agents:
        print(f"no reviews recorded yet; every agent is at review.default={review['default']}")
        return 0
    for agent in agents:
        mine = [e for e in entries if e["agent"] == agent and e["decision"] in DECISIONS]
        streak = 0
        for e in reversed(mine):
            if not e.get("clean"):
                break
            streak += 1
        level = level_of(review, agent)
        hint = ""
        if level != "off" and streak >= review["graduate_after"]:
            hint = f" -> {streak} clean approvals in a row: consider replying -less-review on its next review"
        print(f"{agent:24} level={level:6} reviews={len(mine):3} clean-streak={streak}{hint}")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    n = sub.add_parser("needed")
    n.add_argument("--run", required=True); n.add_argument("--agent", required=True)
    n.add_argument("--stage"); n.add_argument("--package"); n.add_argument("--segment")
    n.add_argument("--paths", nargs="*")
    d = sub.add_parser("decide")
    d.add_argument("--run", required=True); d.add_argument("--agent", required=True)
    d.add_argument("--target", required=True); d.add_argument("--reply", required=True)
    d.add_argument("--edited", type=int, default=0, help="files the owner edited during this review")
    s = sub.add_parser("set-level")
    s.add_argument("--agent", required=True); s.add_argument("--level", required=True, choices=LADDER)
    s.add_argument("--reason", required=True); s.add_argument("--root", default=".")
    r = sub.add_parser("regress")
    r.add_argument("--agent", required=True); r.add_argument("--reason", required=True)
    r.add_argument("--root", default=".")
    m = sub.add_parser("summary")
    m.add_argument("--root", default=".")
    args = p.parse_args(argv)
    return {"needed": cmd_needed, "decide": cmd_decide, "set-level": cmd_set_level, "regress": cmd_regress,
            "summary": cmd_summary}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())

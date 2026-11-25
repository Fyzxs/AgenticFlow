"""Human-in-the-loop review between agent hand-offs.

  python -I .fyzxsflow/package/engine/review.py needed --run <dir> --agent <name> [--stage S] [--package WP-02]
      [--segment SEG] [--paths p1 p2 ...]          -> "review=pause|notify|no reason=<why> level=<level>"
  python -I .fyzxsflow/package/engine/review.py decide --run <dir> --agent <name> --target <WP-02|stage> --reply "<owner reply>"
      [--edited N] [--review-file reviews/<file>.md]
      -> "decision=<d> adjust=<less-review|more-review|none> level=<a>-><b> feedback=<F-n|none> note=<...>"
  python -I .fyzxsflow/package/engine/review.py open --run <dir>
      -> one line per pause the run is waiting on ("open agent=<a> target=<t> stage=<s> reason=<why>"); exit 1 when
         any is open, 0 when none
  python -I .fyzxsflow/package/engine/review.py set-level --agent <name> --level on|notify|off --reason "<owner's words>"
  python -I .fyzxsflow/package/engine/review.py regress --agent <name> --reason "<evidence>"   (system: raise to on)
  python -I .fyzxsflow/package/engine/review.py summary [--root .]
  python -I .fyzxsflow/package/engine/review.py show --review-file <run>/reviews/<file>.md [--open]
      -> the message to post when the run waits (or notifies): every file to read as a link, the diff, the
         verdict, pushed-back items, then how to reply. --open also opens them in VS Code when run from its
         terminal. Exit 2 when the review names nothing to look at (fill "What to look at" first).

Levels, per agent, in config.json -> review: on (pause for the owner), notify (post the summary, don't pause),
off (don't pause or post). Every agent starts at review.default ("on"). The level only decides whether the run
waits: every hand-off writes a review file, so the owner can read any output later and comment under its
`## Human Feedback` (picked up by feedback.py scan / record-review).

An owner reply starts with approve | continue | redo | stop (approve and continue mean the same: go on; edits the
owner made are found by `run.py edits`, never declared by the word), and may carry -less-review or -more-review anywhere:
it moves the reviewed agent's level one step (on <-> notify <-> off). Only the owner lowers a level; the
system may raise one on evidence (regress), never lower it.

Feedback: the reply's note and the review file's `## Human Feedback` section (whatever the decision) are recorded
together as one owner-feedback finding, the owner's words verbatim, and printed as feedback=F-n. The Orchestrator
routes it (Docs Gardener before the next agent; with redo, also the re-dispatched agent's input). approve +
feedback accepts this output as it is and applies the feedback from the next agent on; redo also fixes this output.

Every answer is recorded in the run's reviews.jsonl (decision "checked"): the Orchestrator's hook refuses its next
dispatch while a returned, stamped agent report has no check (hooks/orchestrator_rules.handoff_gate).
Pauses are enforced: every review=pause that `needed` answers is recorded in the run's reviews.jsonl as
decision "pending" (target: the package, else the stage), and stays open until `decide` answers that agent and
target. While one is open, the Orchestrator's hook (hooks/orchestrator_rules.py) refuses its agent dispatches and
its lanes.py / pr.py moves. Build's agent-level pauses aren't recorded: there the owner reviews on each group's PR.
A Build pause (always:/run-request:) holds only its group, so it is recorded but doesn't block other dispatches.

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
from layout import HOME, PACKAGE  # noqa: E402

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from docs_check import glob_to_regex  # noqa: E402

LADDER = ["off", "notify", "on"]
DECISIONS = ("approve", "continue", "redo", "stop")
DEFAULTS = {"default": "on", "agents": {}, "always": {"segments": [], "paths": []}, "graduate_after": 10}
REQUEST = re.compile(r"^\s*-\s*review:\s*(?:(all)|(agent|stage|package|segment|path)\s*=\s*(\S+))\s*$", re.M | re.I)
AUTOPILOT = re.compile(r"^\s*-\s*autopilot\s*$", re.M | re.I)


def root_of(path: pathlib.Path) -> pathlib.Path:
    for parent in [path.resolve(), *path.resolve().parents]:
        if parent.name == HOME:
            return parent.parent
    raise SystemExit(f"{path} is not inside a .fyzxsflow/ folder")


def load_config(root: pathlib.Path):
    path = root / HOME / "config.json"
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
    paths = [p for p in (f"{HOME}/config.json", f"{HOME}/reviews.jsonl") if (root / p).exists()]
    runmod.git(root, "add", "--", *paths)
    runmod.git(root, "commit", "-q", "-m", f"fyzxsflow: review level for {agent} {before} -> {after} ({by})", "--", *paths)


def log(root: pathlib.Path, run, entry: dict):
    """Review decisions and level changes: per run when there is one, else the project-level log."""
    entry = {"time": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S"), **entry}
    target = (run / "reviews.jsonl") if run else (root / HOME / "reviews.jsonl")
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(entry) + "\n")


def pause_target(package, stage, agent) -> str:
    return package or stage or agent


def same_target(a: str, b: str) -> bool:
    """WP-02 and its file stem WP-02-api-orders are the same target."""
    a, b = (a or "").lower(), (b or "").lower()
    return a == b or a.startswith(b + "-") or b.startswith(a + "-")


def open_pauses(run: pathlib.Path) -> list:
    """The pauses recorded in the run's reviews.jsonl that no later decision has answered, oldest first."""
    f = run / "reviews.jsonl"
    if not f.exists():
        return []
    pending = []
    for line in f.read_text(encoding="utf-8").splitlines():
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if not isinstance(e, dict):
            continue
        if e.get("decision") == "pending":
            if not any(p["agent"] == e.get("agent") and same_target(p["target"], e.get("target")) for p in pending):
                pending.append(e)
        elif e.get("decision") in DECISIONS:
            pending = [p for p in pending
                       if not (p.get("agent") == e.get("agent") and same_target(p.get("target"), e.get("target")))]
    return pending


def cmd_needed(args) -> int:
    run = pathlib.Path(args.run)
    root = root_of(run)
    _, _, review = load_config(root)
    level = level_of(review, args.agent)
    paths = args.paths or []

    def say(line):
        """Every answer goes through here: each check is recorded (the hook holds the next dispatch until a
        returned agent's hand-off was checked), and a pause stays open until `decide`."""
        print(line)
        target = pause_target(args.package, args.stage, args.agent)
        answer = re.match(r"review=(\w+) reason=(\S+)", line)
        log(root, run, {"agent": args.agent, "target": target, "stage": args.stage or "", "decision": "checked",
                        "answer": answer.group(1) if answer else "", "by": "system"})
        m = re.match(r"review=pause reason=(\S+)", line)
        if not m or (args.stage == "build" and m.group(1) == "agent-level"):
            return
        if any(p["agent"] == args.agent and same_target(p["target"], target) for p in open_pauses(run)):
            return
        log(root, run, {"agent": args.agent, "target": target, "stage": args.stage or "", "decision": "pending",
                        "reason": m.group(1), "by": "system"})

    def any_path(globs):
        rxs = [glob_to_regex(g) for g in globs]
        return next((p for p in paths for rx in rxs if rx.match(p)), None)

    if args.segment and args.segment in review["always"]["segments"]:
        say(f"review=pause reason=always:segment={args.segment} level={level}")
        return 0
    hit = any_path(review["always"]["paths"])
    if hit:
        say(f"review=pause reason=always:path={hit} level={level}")
        return 0
    req_file = run / "review-requests.md"
    requests = req_file.read_text(encoding="utf-8") if req_file.exists() else ""
    wanted = {"agent": args.agent, "stage": args.stage, "package": args.package, "segment": args.segment}
    for m in REQUEST.finditer(requests):
        if m.group(1):
            say(f"review=pause reason=run-request:all level={level}")
            return 0
        key, value = m.group(2).lower(), m.group(3)
        if key == "path" and any_path([value]):
            say(f"review=pause reason=run-request:path={value} level={level}")
            return 0
        if key != "path" and wanted.get(key) and wanted[key].lower() == value.lower():
            say(f"review=pause reason=run-request:{key}={value} level={level}")
            return 0
    if AUTOPILOT.search(requests):
        say(f"review=no reason=autopilot level={level}")
        return 0
    action = {"on": "pause", "notify": "notify", "off": "no"}[level]
    say(f"review={action} reason=agent-level level={level}")
    return 0


# natural forms of a decision word; anything else is still refused rather than guessed at
ALIASES = {"approved": "approve", "approving": "approve", "continuing": "continue", "stopped": "stop"}
FLAG_WORDS = ("-less-review", "--less-review", "-more-review", "--more-review")


PHRASES = (("keep going", "continue"), ("go on", "continue"), ("go ahead", "continue"))


def parse_reply(reply: str):
    text = reply.strip()
    for phrase, word in PHRASES:
        if text.lower().startswith(phrase):
            text = f"{word} {text}"  # the owner's words stay in the note
            break
    words = text.split()
    if not words:
        raise ValueError("empty reply")
    decision = words[0].lower().rstrip(":,.!")
    decision = ALIASES.get(decision, decision)
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


FEEDBACK_SECTION = re.compile(r"^##\s+Human Feedback\s*$(.*?)(?=^##\s|\Z)", re.M | re.S | re.I)


def human_feedback(review_file) -> str:
    """The owner's text under `## Human Feedback` in a review file, without the template's comment."""
    if not review_file:
        return ""
    path = pathlib.Path(review_file)
    if not path.exists():
        return ""
    m = FEEDBACK_SECTION.search(path.read_text(encoding="utf-8"))
    if not m:
        return ""
    text = re.sub(r"<!--.*?-->", "", m.group(1), flags=re.S).strip()
    return "" if text in ("<write feedback here>", "") else text


def record_feedback(run: pathlib.Path, args, decision: str, note: str, section: str) -> str:
    import findings  # noqa: E402  (same engine folder)
    parts = []
    if note:
        parts.append(f"Reply ({decision}): {note}")
    if section:
        parts.append(section)
    if not parts:
        return "none"
    detail = "\n\n".join(parts)
    summary = " ".join(detail.split())
    summary = summary if len(summary) <= 160 else summary[:157] + "..."
    evidence = [pathlib.Path(args.review_file).as_posix()] if section else [f"reviews.jsonl ({args.target})"]
    import contextlib
    import io
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = findings.cmd_add(argparse.Namespace(
            run=str(run), source="human", target=args.agent, kind="owner-feedback", severity="major",
            summary=f"{args.target}: {summary}", evidence=evidence, rule=None, fixed=False, detail=detail))
    return out.getvalue().strip() if code == 0 else "none"


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
    section = human_feedback(args.review_file)
    feedback = record_feedback(run, args, decision, note, section)
    if section and feedback != "none":
        import feedback as inbox  # noqa: E402  (same engine folder)
        inbox.mark_seen(args.review_file, feedback, section)  # feedback.py scan won't record it again
    print(f"decision={decision} adjust={adjust} level={before}->{after}{unchanged} feedback={feedback} note={note}")
    return 0


def cmd_open(args) -> int:
    pauses = open_pauses(pathlib.Path(args.run))
    for p in pauses:
        print(f"open agent={p.get('agent')} target={p.get('target')} stage={p.get('stage') or '-'} "
              f"reason={p.get('reason')} since={p.get('time')}")
    if not pauses:
        print("open none")
    return 1 if pauses else 0


def cmd_set_level(args) -> int:
    root = root_of(pathlib.Path(args.root) / HOME)
    _, _, review = load_config(root)
    before = level_of(review, args.agent)
    save_level(root, args.agent, args.level)
    log(root, None, {"agent": args.agent, "decision": "set-level", "level_before": before, "level_after": args.level,
                     "by": "owner", "reason": args.reason})
    commit_policy(root, args.agent, before, args.level, "owner")
    print(f"level={before}->{args.level}")
    return 0


def cmd_regress(args) -> int:
    root = root_of(pathlib.Path(args.root) / HOME)
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
    base = root / HOME
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


REVIEW_AGENT = re.compile(r"^#\s*Review:\s*(\S+)", re.M)
PLACEHOLDER = re.compile(r"<[^>]*>")


def review_blocks(text: str) -> dict:
    """The review's bold-labelled paragraphs ("**What to look at**", "**Where we are:** ..."), comments removed."""
    text = re.sub(r"[ \t]*<!--.*?-->[ \t]*\n?", "", text.split("\n## Human Feedback")[0], flags=re.S)
    out = {}
    for para in re.split(r"\n\s*\n", text):
        m = re.match(r"\*\*([^*]+?)\*\*:?\s*(.*)", para.strip(), re.S)
        if m:
            out[m.group(1).strip().rstrip(":").lower()] = m.group(2).strip()
    return out


def look_at(body: str):
    """(path, note) for each "- `path` — note" line of What to look at."""
    items = []
    for line in body.splitlines():
        m = re.match(r"\s*[-*]\s*(?:`([^`]+)`|\[[^\]]*\]\(<?([^)>]+)>?\))\s*(?:[—–:-]+\s*)?(.*)", line)
        if m:
            items.append(((m.group(1) or m.group(2)).strip(), m.group(3).strip()))
    return items


def on_disk(bases, rel: str):
    """The file a "What to look at" entry names, from the repo root or the run folder (a trailing :line or
    :start-end is allowed), or None."""
    for base in bases:
        for candidate in (rel, re.sub(r":\d+(?:-\d+)?$", "", rel)):
            path = (base / candidate).resolve()
            if path.exists():
                return path
    return None


def link(bases, rel: str) -> str:
    path = on_disk(bases, rel)
    return f"[{rel}](<{path.as_posix()}>)" if path else f"`{rel}` (not on disk: deleted, or not created yet)"


def open_in_editor(paths) -> str:
    import os
    import shutil
    import subprocess
    if os.environ.get("TERM_PROGRAM") != "vscode" and "VSCODE_IPC_HOOK_CLI" not in os.environ:
        return "opened=no (not a VS Code terminal)"
    code = shutil.which("code") or shutil.which("code-insiders")
    if not code:
        return "opened=no (the code command is not on PATH)"
    try:
        subprocess.run([code, "-r", *[str(p) for p in paths]], capture_output=True, timeout=20)
    except (OSError, subprocess.SubprocessError) as e:
        return f"opened=no ({e})"
    return f"opened={len(paths)} files in VS Code"


def cmd_show(args) -> int:
    review = pathlib.Path(args.review_file).resolve()
    if not review.exists():
        print(f"no review file at {args.review_file}", file=sys.stderr)
        return 2
    root = root_of(review)
    text = review.read_text(encoding="utf-8")
    blocks = {k: v for k, v in review_blocks(text).items() if k == "what to look at" or not PLACEHOLDER.search(v)}
    items = look_at(blocks.get("what to look at", ""))
    unfilled = [p for p, _ in items if PLACEHOLDER.search(p)]
    if not items or unfilled:
        print(f"{args.review_file}: fill **What to look at** with the files the owner should read (one "
              f"\"- `path` — what it is\" line each) before asking; the owner can't review what isn't named.",
              file=sys.stderr)
        return 2
    m = REVIEW_AGENT.search(text)
    agent = m.group(1) if m else "the agent"
    title = next((l[1:].strip() for l in text.splitlines() if l.startswith("# ")), review.stem)
    waiting = blocks.get("reply needed", "yes").lower().startswith("yes")
    rel_review = review.relative_to(root).as_posix()
    bases = [root, review.parent.parent]  # the repo root, then the run folder
    lines = [f"**{title}** — " + ("the run is waiting for you." if waiting else "no reply needed; the run moved on."), ""]
    if blocks.get("where we are"):
        lines += [" ".join(blocks["where we are"].split()), ""]
    lines.append("**Read before you reply:**" if waiting else "**To read when you like:**")
    lines.append(f"1. {link(bases, rel_review).replace('[' + rel_review + ']', '[' + review.parent.name + '/' + review.name + ']')} — this review: verdict, acceptance criteria, and a Human Feedback "
                 "section for longer notes")
    seen = {rel_review}
    for i, (path, note) in enumerate([(p, n) for p, n in items if p not in seen], start=2):
        lines.append(f"{i}. {link(bases, path)}" + (f" — {note}" if note else ""))
    for label in ("changes since the last checkpoint", "validator verdict"):
        if blocks.get(label):
            lines.append(f"\n**{label.capitalize()}:** {' '.join(blocks[label].split())}")
    for label, head in (("your feedback, applied", "Your feedback, applied:"),
                        ("your feedback, pushed back", "Your feedback, pushed back (each needs your answer):")):
        if blocks.get(label):
            lines += ["", f"**{head}**", blocks[label]]
    lines.append("")
    if waiting:
        lines.append(f"**Reply here:** `approve` · `redo: <what's wrong>` · `stop`. Add `-less-review` or "
                     f"`-more-review` to change how closely {agent} is reviewed from now on. Longer feedback: write "
                     "it under Human Feedback in the review first; it is recorded whatever you reply.")
    else:
        lines.append("Write under Human Feedback in the review any time; it is picked up at the next hand-off.")
    print("\n".join(lines))
    if args.open:
        paths = [review] + [f for f in (on_disk(bases, p) for p, _ in items if p not in seen) if f]
        print(open_in_editor(paths), file=sys.stderr)
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
    d.add_argument("--review-file", help="the review file, to read its ## Human Feedback section")
    d.add_argument("--edited", type=int, default=0, help="files the owner edited during this review")
    o = sub.add_parser("open")
    o.add_argument("--run", required=True)
    s = sub.add_parser("set-level")
    s.add_argument("--agent", required=True); s.add_argument("--level", required=True, choices=LADDER)
    s.add_argument("--reason", required=True); s.add_argument("--root", default=".")
    r = sub.add_parser("regress")
    r.add_argument("--agent", required=True); r.add_argument("--reason", required=True)
    r.add_argument("--root", default=".")
    m = sub.add_parser("summary")
    m.add_argument("--root", default=".")
    w = sub.add_parser("show")
    w.add_argument("--review-file", required=True)
    w.add_argument("--open", action="store_true", help="also open the files in VS Code (from its terminal only)")
    args = p.parse_args(argv)
    if getattr(args, "run", None):  # a bare run id resolves under .fyzxsflow/runs/
        sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
        from layout import resolve_run
        args.run = str(resolve_run(args.run))
    return {"needed": cmd_needed, "decide": cmd_decide, "set-level": cmd_set_level, "regress": cmd_regress,
            "summary": cmd_summary, "show": cmd_show, "open": cmd_open}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())

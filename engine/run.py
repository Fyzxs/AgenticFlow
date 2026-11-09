"""Create and track fyzxsflow run folders.

  python -I engine/run.py new --source prompt --ref "add a pull list page"   -> prints the run folder
  python -I engine/run.py log <run-dir> <stage> <status> "<message>"          -> appends a ledger line
  python -I engine/run.py status <run-dir> [--lines 8]                        -> prints the latest ledger lines
  python -I engine/run.py checkpoint <run-dir> <stage>                        -> commits the run folder (only it)
  python -I engine/run.py edits <run-dir> [--record]                          -> lists files changed since the last checkpoint
  python -I engine/run.py close <run-dir> --outcome completed|abandoned [--note "PR #12"]
  python -I engine/run.py list [--root .]                                      -> active runs with their last ledger line
  python -I engine/run.py packages <run-dir> [--current WP-04 [--agent implementer]]
      -> the plan with each package's status; with --current, "Package n of N: <title>", done packages, the next
         package, and (with --agent) the readable review file name reviews/<package file stem>.<agent>.md
  python -I engine/run.py stamp <report> --agent <a> [--host claude] [--up N | --down] [--model <override>]
      -> writes tier, model (host:model or host:inherit) and escalated into the report's frontmatter, warns on a
         missing model_reported or a criteria row that isn't a bare id, and commits the run folder: the agent's
         output is handed off the moment it returns
  python -I engine/run.py models <run-dir>      -> every report with its dispatched and self-reported model
  python -I engine/run.py ship-check <run-dir>
      -> ready=yes|no: the last extreme run, the extreme and pre-pr gate stages, the acceptance-criteria evidence
         and open owner decisions. A failure counts only when the owner accepted it (a fixed owner-decision
         finding with target ship:<check>). The run says "Ready to push" only on ready=yes.

Runs live in .fyzxsflow/runs/active/<id>/ while work is in flight, and move to runs/completed/<id>/ (a PR was
delivered) or runs/abandoned/<id>/ (stopped, with the reason in the ledger) when closed. Only active runs are
resumed.

Runs are kept in git by default, so humans can review the brief, plan, reports and findings, and edit them
between stages: the next stage reads the edited files. .fyzxsflow/profile.md `Runs: local` turns commits
off. Raw step logs (runner/<invocation>/, gates/<invocation>/) are never committed; their JSON summaries are.

`edits --record` treats changes since the last checkpoint as owner edits: it writes a ledger line, a
`human-edit` finding per file (the Curator diffs them against the checkpoint to learn what the agent got
wrong), and checkpoints the edits. Files the engine writes (ledger, *.jsonl, runner/gates summaries) and review
files are never owner edits. It refuses (exit 3) while any agent report is unstamped: that output hasn't been
handed off, so it can't be told apart from an owner's change. Call it when the owner replies or a run resumes.

The run folder layout is described in .fyzxsflow/package/context/run-folder.md.
"""

import argparse
import datetime
import json
import pathlib
import re
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from layout import HOME, PACKAGE  # noqa: E402

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
    run = root / HOME / "runs" / "active" / run_id
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


PACKAGE_STATUSES = ("planned", "building", "done")
FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n", re.S)


def read_packages(run: pathlib.Path) -> list:
    """Work packages in plan order: id, file stem, segment, title (the heading after the id), status."""
    out = []
    for f in sorted((run / "work-packages").glob("WP-*.md")):
        text = f.read_text(encoding="utf-8")
        fm = FRONTMATTER.match(text)
        meta = dict(re.findall(r"^(\w[\w-]*):\s*(.*?)\s*$", fm.group(1), re.M)) if fm else {}
        pid = meta.get("id") or re.match(r"(WP-\d+)", f.stem).group(1)
        heading = re.search(r"^#\s+(.+)$", text, re.M)
        title = heading.group(1).strip() if heading else f.stem
        title = re.sub(r"^" + re.escape(pid) + r"\s*[—–-]\s*", "", title)
        status = meta.get("status", "planned")
        out.append({"id": pid, "stem": f.stem, "segment": meta.get("segment", ""), "title": title,
                    "status": status if status in PACKAGE_STATUSES else "planned"})
    return out


def cmd_packages(args) -> int:
    run = pathlib.Path(args.run)
    packages = read_packages(run)
    if not packages:
        print(f"no work packages in {run / 'work-packages'}", file=sys.stderr)
        return 2
    if not args.current:
        for i, p in enumerate(packages, start=1):
            print(f"{i}/{len(packages)} {p['id']:6} {p['status']:8} {p['title']}")
        return 0
    ids = [p["id"] for p in packages]
    if args.current not in ids:
        print(f"unknown package {args.current}; packages: {', '.join(ids)}", file=sys.stderr)
        return 2
    i = ids.index(args.current)
    cur = packages[i]
    done = [p["id"] for p in packages if p["status"] == "done"]
    later = [p for p in packages[i + 1:] if p["status"] != "done"]
    if args.agent:
        print(f"review_file=reviews/{cur['stem']}.{args.agent}.md")
    print(f"where=Package {i + 1} of {len(packages)} ({cur['id']}): {cur['title']}")
    print(f"done={', '.join(done) or 'none yet'}")
    print("next_package=" + (f"{later[0]['id']}: {later[0]['title']}" if later else "none (last package)"))
    return 0


MODEL_KEYS = ("tier", "model", "model_reported", "escalated")


def set_frontmatter(text: str, values: dict) -> str:
    """Set keys in a report's frontmatter, replacing existing lines and appending missing ones."""
    m = FRONTMATTER.match(text)
    lines = m.group(1).splitlines() if m else []
    body = text[m.end():] if m else text
    for key, value in values.items():
        new = f"{key}: {value}"
        for i, line in enumerate(lines):
            if re.match(r"^" + re.escape(key) + r":", line):
                lines[i] = new
                break
        else:
            lines.append(new)
    return "---\n" + "\n".join(lines) + "\n---\n" + ("" if m else "\n") + body


def report_meta(text: str) -> dict:
    m = FRONTMATTER.match(text)
    if not m:
        return {}
    return {k: re.sub(r"\s+#.*$", "", v).strip() for k, v in re.findall(r"^(\w[\w-]*):\s*(.*?)\s*$", m.group(1), re.M)}


def cmd_stamp(args) -> int:
    """Record which tier and model the Orchestrator dispatched an agent on, in its report's frontmatter."""
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
    import models  # same folder: engine/ in the source repo, .fyzxsflow/package/engine/ when installed
    report = pathlib.Path(args.report)
    if not report.exists():
        print(f"no report {report}", file=sys.stderr)
        return 2
    root = repo_root(report.parent)
    agent_file = root / HOME / PACKAGE / "agents" / f"{args.agent}.agent.md"
    declared = models.tier_of(agent_file.read_text(encoding="utf-8")) if agent_file.exists() else "standard"
    if args.down:
        low = models.shadow(declared, models.model_map(root, args.host))
        used, model = low if low else (declared, "")
    else:
        used, model, _ = models.resolve(declared, models.model_map(root, args.host), args.up)
    if args.model:  # an owner override for this run
        model = args.model
    text = report.read_text(encoding="utf-8")
    values = {"tier": used, "model": f"{args.host}:{model or 'inherit'}",
              "escalated": f"from {declared}" if used != declared and not args.down else "no"}
    if args.down:
        values["escalated"] = f"no (shadow, one below {declared})"
    if args.model:
        values["model"] += " (owner override)"
    if "model_reported" not in report_meta(text):
        values["model_reported"] = "unknown"
        print(f"warning: {report.name} does not say which model did the work (model_reported); ask the agent to "
              "write it, or note why it can't")
    report.write_text(set_frontmatter(text, values), encoding="utf-8", newline="\n")
    print(f"stamped {report.name}: tier={values['tier']} model={values['model']} escalated={values['escalated']}")
    for problem in criteria_row_problems(report.read_text(encoding="utf-8")):
        print(f"warning: {report.name}: {problem}")
    run = run_of(report)
    import checks  # noqa: E402  (same engine folder)
    cite_root = repo_root(run) if run is not None and HOME in run.resolve().parts else pathlib.Path.cwd()
    for problem in checks.citation_problems(report, cite_root):
        print(f"warning: {report.name}: citation {problem}")
    if run is not None and not args.no_checkpoint:
        # The agent's output is committed the moment it returns, so nothing it wrote can later be taken for an owner edit.
        print(f"checkpoint: {checkpoint(run, f'{args.agent} output')}")
    return 0


def run_of(path: pathlib.Path):
    for parent in path.resolve().parents:
        if (parent / "ledger.md").exists():
            return parent
    return None


CRITERIA_HEADER = re.compile(r"^\|\s*Criterion\s*\|", re.I)
CRITERION_ID = re.compile(r"^(AC-\d+|WP-\d+\.\d+)$")


def criteria_row_problems(text: str) -> list:
    """Rows of a report's criteria table whose first cell is not a bare AC-n / WP-nn.n id (ac_trace can't read them)."""
    problems, in_table = [], False
    for n, line in enumerate(text.splitlines(), start=1):
        if CRITERIA_HEADER.match(line):
            in_table = True
            continue
        if in_table:
            if not line.startswith("|"):
                in_table = False
                continue
            first = line.strip().strip("|").split("|")[0].strip().strip("*`")
            if set(first) <= set("-: "):
                continue  # the separator row
            if not CRITERION_ID.match(first):
                problems.append(f"line {n}: criteria row starts with '{first[:40]}', not a bare AC-n or WP-nn.n id")
    return problems


def cmd_models(args) -> int:
    """Every report in the run with the model it was done on: the table a human reads to tune tiers."""
    run = pathlib.Path(args.run)
    rows = []
    for f in sorted((run / "reports").rglob("*.md")):
        meta = report_meta(f.read_text(encoding="utf-8"))
        rows.append((f.relative_to(run / "reports").as_posix(), meta.get("agent", "?"), meta.get("tier", "?"),
                     meta.get("model", "not stamped"), meta.get("model_reported", "?"), meta.get("escalated", "?"),
                     meta.get("result", "?")))
    if not rows:
        print(f"no reports in {run / 'reports'}", file=sys.stderr)
        return 2
    print("| report | agent | tier | model (dispatched) | model (reported) | escalated | result |")
    print("|---|---|---|---|---|---|---|")
    for r in rows:
        print("| " + " | ".join(r) + " |")
    return 0


def repo_root(run: pathlib.Path) -> pathlib.Path:
    """The folder that contains .fyzxsflow/, wherever the run sits (runs/active|completed|abandoned/<id>)."""
    for parent in run.resolve().parents:
        if parent.name == HOME:
            return parent.parent
    raise SystemExit(f"{run} is not inside a .fyzxsflow/ folder")


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
    commit = git(root, "commit", "-q", "-m", f"fyzxsflow({run.name}): {args.outcome}", "--", src_rel, dest_rel)
    if commit.returncode != 0:
        raise SystemExit(f"git commit failed: {commit.stderr.strip() or commit.stdout.strip()}")
    print(dest)
    return 0


def latest(folder: pathlib.Path, prefix: str):
    files = sorted(folder.glob(f"{prefix}-*.json")) if folder.is_dir() else []
    files = [f for f in files if f.name[len(prefix) + 1:len(prefix) + 2].isdigit()]
    return files[-1] if files else None


def cmd_ship_check(args) -> int:
    """Whether the run may say "Ready to push": every sign-off check passed, or the owner accepted its failure."""
    run = pathlib.Path(args.run)
    root = repo_root(run)
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
    import findings as fmod  # noqa: E402
    import steps as smod  # noqa: E402
    found = fmod.load(run)
    accepted = {f["target"][len("ship:"):]: f["id"] for f in found
                if f.get("kind") == "owner-decision" and f.get("fixed") and str(f.get("target", "")).startswith("ship:")}
    st = smod.state(root, run)
    config_path = root / HOME / "config.json"
    config = json.loads(config_path.read_text(encoding="utf-8")) if config_path.exists() else {}
    rows = []  # (check, status, ok, detail)

    extreme_mode = (config.get("modes") or {}).get("extreme") or {}
    if not st["extreme"][0]:
        rows.append(("extreme", "off", True, f"step switched off ({st['extreme'][1]})"))
    elif extreme_mode.get("not_applicable"):
        rows.append(("extreme", "n/a", True, extreme_mode["not_applicable"]))
    else:
        f = latest(run / "runner", "extreme")
        if f is None:
            rows.append(("extreme", "missing", False, "no extreme run in runner/"))
        else:
            data = json.loads(f.read_text(encoding="utf-8"))
            failed = [s["name"] for s in data.get("steps", []) if not s.get("passed", s.get("exit") == 0)]
            detail = f"{f.name}" + (f"; failed: {', '.join(failed)}" if failed else "")
            detail += f"; skipped: {', '.join(data['skipped'])}" if data.get("skipped") else ""
            rows.append(("extreme", data.get("result", "?"), data.get("result") == "pass", detail))

    for stage in ("extreme", "pre-pr"):
        check = f"gates:{stage}"
        if not st["gates"][0]:
            rows.append((check, "off", True, f"step switched off ({st['gates'][1]})"))
            continue
        f = latest(run / "gates", stage)
        if f is None:
            rows.append((check, "missing", False, f"gates.py --stage {stage} was not run"))
            continue
        data = json.loads(f.read_text(encoding="utf-8"))
        result = data.get("result", "?")
        detail = f.name
        if result == "empty" and data.get("declared_for_stage"):
            detail += f"; declared but not selected: {', '.join(data['declared_for_stage'])}"
            rows.append((check, "empty", False, detail))
        else:
            failed = [g["gate"] for g in data.get("gates", []) if not g.get("passed")]
            rows.append((check, result, result in ("pass", "empty"), detail + (f"; failed: {', '.join(failed)}" if failed else "")))

    trace = subprocess.run([sys.executable, "-I", str(pathlib.Path(__file__).resolve().parent / "ac_trace.py"),
                            "--run", str(run), "--require-evidence"], capture_output=True, text=True)
    last = (trace.stdout.strip().splitlines() or ["(no output)"])[-1]
    rows.append(("criteria", "pass" if trace.returncode == 0 else "fail", trace.returncode == 0, last))

    open_decisions = [f["id"] for f in found if f.get("kind") == "owner-decision" and not f.get("fixed")]
    rows.append(("owner-decisions", "none open" if not open_decisions else "open", not open_decisions,
                 ", ".join(open_decisions)))

    ready = True
    for check, status, ok, detail in rows:
        note = ""
        if not ok and check in accepted:
            ok, note = True, f" (accepted by the owner: {accepted[check]})"
        ready = ready and ok
        print(f"{check:16} {status:9} {'ok ' if ok else 'NO '} {detail}{note}")
    print(f"ready={'yes' if ready else 'no'}")
    if not ready:
        print("A failed or missing check needs fixing, or the owner's acceptance recorded as a fixed owner-decision "
              "finding with target ship:<check> (e.g. ship:extreme) quoting their words.")
    return 0 if ready else 1


def cmd_list(args) -> int:
    runs = pathlib.Path(args.root).resolve() / HOME / "runs"
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
    profile = root / HOME / "profile.md"
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
    if git(root, "rev-parse", "--git-dir").returncode != 0:
        return "not a git repository; nothing committed"
    rel = run.resolve().relative_to(root).as_posix()
    if not changed_files(root, run):
        return "nothing new to checkpoint"
    add = git(root, "add", "--", rel)
    if add.returncode != 0:
        raise SystemExit(f"git add failed: {add.stderr.strip()}")
    # A pathspec commit records only the run folder, whatever else is staged in the repo.
    commit = git(root, "commit", "-q", "-m", f"fyzxsflow({run.name}): {stage}", "--", rel)
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


ENGINE_WRITTEN = re.compile(r"(^|/)(ledger\.md|[^/]+\.jsonl|runner/[^/]+\.json|gates/[^/]+\.json|reviews/[^/]+)$")


def unstamped_report(root: pathlib.Path, rel: str) -> bool:
    """An agent report that run.py stamp hasn't seen yet: agent output still in flight, never an owner edit."""
    if "/reports/" not in f"/{rel}" or not rel.endswith(".md"):
        return False
    path = root / rel
    return path.exists() and "model" not in report_meta(path.read_text(encoding="utf-8"))


def cmd_edits(args) -> int:
    run = pathlib.Path(args.run)
    root = repo_root(run)
    files = changed_files(root, run)
    if not files:
        print("no edits since the last checkpoint")
        return 0
    # Engine-written files (ledger, findings, runner and gate summaries) and review files (their ## Human Feedback
    # is read by review.py decide) are never owner edits of agent output.
    engine = [f for f in files if ENGINE_WRITTEN.search(f)]
    pending = [f for f in files if f not in engine and unstamped_report(root, f)]
    owner = [f for f in files if f not in engine and f not in pending]
    for f in owner:
        print(f)
    for f in pending:
        print(f"{f}  (agent report not stamped yet)")
    if not args.record:
        return 0
    if pending:
        print("refused: these reports are agent output that hasn't been handed off. Run "
              "`run.py stamp <report> --agent <agent>` for each (it commits the agent's output), then record edits "
              "again; nothing an agent wrote may be recorded as an owner edit.", file=sys.stderr)
        return 3
    if owner:
        append(run, "owner-edit", "resumed", "edited since last checkpoint: " + ", ".join(owner))
        sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
        import findings  # noqa: E402
        for f in owner:
            findings.cmd_add(argparse.Namespace(
                run=str(run), source="human", target=f, kind="human-edit", severity="observation",
                summary=f"the owner edited {f} after the last checkpoint", evidence=[f], rule=None, fixed=False))
    print(checkpoint(run, "owner edits" if owner else "engine output"))
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
    pk = sub.add_parser("packages")
    pk.add_argument("run"); pk.add_argument("--current", help="package id, e.g. WP-04")
    pk.add_argument("--agent", help="with --current: also print the review file name for this agent")
    st = sub.add_parser("stamp")
    st.add_argument("report"); st.add_argument("--agent", required=True)
    st.add_argument("--host", default="claude", choices=["claude", "copilot"])
    st.add_argument("--up", type=int, default=0, help="the escalation the agent was dispatched with")
    st.add_argument("--down", action="store_true", help="a model-compare shadow output")
    st.add_argument("--model", help="an owner override for this run: the model actually used")
    st.add_argument("--no-checkpoint", action="store_true",
                    help="don't commit the run folder (e.g. stamping a shadow output mid-dispatch)")
    md = sub.add_parser("models")
    md.add_argument("run")
    sc = sub.add_parser("ship-check")
    sc.add_argument("run")
    args = p.parse_args(argv)
    return {"new": cmd_new, "log": cmd_log, "status": cmd_status, "packages": cmd_packages,
            "stamp": cmd_stamp, "models": cmd_models, "ship-check": cmd_ship_check,
            "checkpoint": cmd_checkpoint, "edits": cmd_edits, "close": cmd_close, "list": cmd_list}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())

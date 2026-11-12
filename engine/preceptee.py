"""Preceptee mode: the preceptee's local coaching record, and the rules the Preceptor must not bend.

The record is the preceptee's, on their machine, never in the repo or a run folder: one preceptee per machine.
  ~/.fyzxsflow/preceptee.json     settings: {"handle": "...", "prompt_after": {"light": 4, "spot": 7, "off": 10},
                                   "spot_every": 3, "seed_every": 4}  (every key optional)
  ~/.fyzxsflow/preceptee/         state.json (levels, streaks, prompts, sign-offs), events.jsonl (everything that
                                   happened), runs/<run-id>/ (notes, explanations, questions, seeded copies)
FYZXSFLOW_USER_HOME moves ~/.fyzxsflow (tests, or a preceptee who keeps it elsewhere).

Areas are the preceptorship rubric's: 1 verifying AI output, 2 debugging, 3 directing agents, 4 calibrated trust,
5 systems taste, 6 codebase/build/tests (kept per stack: 6:<stack>, from the package's .fyzxsflow/docs/tech/<stack>.md),
8 security, 9 learning hygiene. Area 7 (operations) is out of the flow's reach.
Support levels: full (pause, attempt first, hints offered) > light (pause, hints only when asked) > spot (pause on
one exercise in spot_every) > off. Areas 2, 4, 5 and 8 never pause: they are asked after the fact.

  preceptee.py whoami | status
  preceptee.py area <area> full|light|spot|off [--run <run>]       the preceptee sets a level (for one run, or for good)
  preceptee.py decide <area> --run <run> --step <id>              -> "pause=yes|no level=<l> area=<a>" (same answer if asked again)
  preceptee.py hint --run <run> --step <id>                       -> "rung=<n>" (1 question, 2 doc section, 3 file,
                                                                     4 shape, 5 worked example); refused after rung 5
  preceptee.py attempt --run <run> --step <id> [--bail]           the preceptee's attempt (or bail) is in
  preceptee.py reveal --run <run> --step <id>                     exit 1 until an attempt or bail is recorded: nothing
                                                                     the agents produced is shown before it
  preceptee.py ask --run <run> --step <id> --area <a> --text "..."   an after-the-fact question (areas 2, 4, 5, 8, 9)
  preceptee.py answered --run <run> --step <id> --text "..."      the preceptee's answer to it
  preceptee.py score --run <run> --step <id> [--major N] [--medium N] [--caught N] [--missed-major N]
                     [--false-alarms N] [--quiz-right N --quiz-total N] [--skip | --unanswered]
      -> "outcome=good|miss|not-counted streak=<n> [prompt=step-down|step-up to=<level>]"
  preceptee.py answer <area> yes|no                               the preceptee's reply to a pending prompt
  preceptee.py note --run <run> --kind reason|explain|criteria|attempt|coaching [--path <file>] [--step <id>]
                    (--text "..." | --file <f>)
  preceptee.py explained --run <run>                              exit 1 while a changed file has no explanation
  preceptee.py seed --run <run> --step <id> --lines-file <f>      register the lines of a seeded flaw
  preceptee.py seed-check --run <run>                             exit 1 if a seeded line reached the branch or tree
  preceptee.py digest [--since YYYY-MM-DD] --out <dir>            the file the preceptee reviews and sends
  preceptee.py import <digest file>                               the preceptor's sign-offs and levels, from its notes
  preceptee.py export --consent [--out <file>]                    aggregated signals only: no handle, notes or runs

What counts toward a step-down prompt (the streak): an exercise the preceptee attempted (or a question they
answered) that ended without a bail, with no hint past rung 1, no major or medium finding on their work, no missed
major in a review, and no wrong quiz answer. --skip and --unanswered don't count either way. Anything else is a miss:
the streak restarts. The streak runs on across accepted prompts; a declined prompt restarts it. The Preceptor only
ever prompts: levels change by the preceptee's `answer` or `area`, or the preceptor's digest notes.
"""

import argparse
import datetime
import json
import os
import pathlib
import re
import subprocess
import sys

AREAS = {
    "1": "verifying AI output", "2": "debugging under uncertainty", "3": "directing agents",
    "4": "calibrated trust", "5": "systems taste", "6": "codebase, build and tests",
    "8": "security awareness", "9": "learning hygiene",
}
AFTER_THE_FACT = ("2", "4", "5", "8")
LEVELS = ("full", "light", "spot", "off")
DEFAULTS = {"prompt_after": {"light": 4, "spot": 7, "off": 10}, "spot_every": 3, "seed_every": 4}
NOTE_KINDS = ("reason", "explain", "criteria", "attempt", "coaching")
MAX_RUNG = 5


# ---------------------------------------------------------------- where things live

def user_home() -> pathlib.Path:
    env = os.environ.get("FYZXSFLOW_USER_HOME")
    return pathlib.Path(env) if env else pathlib.Path.home() / ".fyzxsflow"


def record_dir() -> pathlib.Path:
    return user_home() / "preceptee"


def settings() -> dict:
    p = user_home() / "preceptee.json"
    data = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    out = {**DEFAULTS, **{k: v for k, v in data.items() if k != "prompt_after"}}
    out["prompt_after"] = {**DEFAULTS["prompt_after"], **(data.get("prompt_after") or {})}
    return out


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def handle() -> str:
    s = settings()
    if s.get("handle"):
        return slug(str(s["handle"]))
    proc = subprocess.run(["git", "config", "user.name"], capture_output=True, text=True)
    return slug(proc.stdout.strip()) or "preceptee"


def run_id(run: str) -> str:
    return pathlib.Path(run).resolve().name


def run_dir(run: str) -> pathlib.Path:
    return record_dir() / "runs" / run_id(run)


def now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


# ---------------------------------------------------------------- state and events

def load_state() -> dict:
    p = record_dir() / "state.json"
    data = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    data.setdefault("areas", {})
    data.setdefault("signoffs", {})
    return data


def save_state(state: dict):
    record_dir().mkdir(parents=True, exist_ok=True)
    (record_dir() / "state.json").write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def events() -> list:
    p = record_dir() / "events.jsonl"
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def log(kind: str, **fields) -> dict:
    record_dir().mkdir(parents=True, exist_ok=True)
    e = {"at": now(), "kind": kind, **{k: v for k, v in fields.items() if v is not None}}
    with (record_dir() / "events.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(e) + "\n")
    return e


def step_events(run: str, step: str) -> list:
    rid = run_id(run)
    return [e for e in events() if e.get("run") == rid and e.get("step") == step]


def norm_area(area: str) -> str:
    area = area.strip().lower()
    base, _, stack = area.partition(":")
    if base == "7":
        raise SystemExit("area 7 (operations) is out of the flow's reach: the flow doesn't do on-call")
    if base not in AREAS:
        raise SystemExit(f"unknown area '{area}': one of {', '.join(AREAS)} (6 per stack: 6:<stack>)")
    if stack and base != "6":
        raise SystemExit(f"only area 6 is kept per stack ('{area}')")
    return f"6:{slug(stack)}" if stack else base


def area_state(state: dict, area: str) -> dict:
    return state["areas"].setdefault(area, {"level": "full", "streak": 0})


def run_levels(run: str) -> dict:
    p = run_dir(run) / "levels.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def effective_level(state: dict, area: str, run: str = None) -> str:
    if run:
        rl = run_levels(run)
        for key in (area, area.split(":")[0]):
            if key in rl:
                return rl[key]
    a = state["areas"].get(area) or (state["areas"].get(area.split(":")[0]) if ":" in area else None)
    return (a or {}).get("level", "full")


# ---------------------------------------------------------------- commands

def cmd_whoami(args) -> int:
    print(f"handle={handle()} record={record_dir()}")
    return 0


def cmd_status(args) -> int:
    state = load_state()
    keys = sorted((set(AREAS) - ({"6"} if any(k.startswith("6:") for k in state["areas"]) else set()))
                  | set(state["areas"]), key=lambda k: (k.split(":")[0], k))
    th = settings()["prompt_after"]
    print(f"preceptee {handle()}; prompts at light {th['light']}, spot {th['spot']}, off {th['off']} good answers")
    for k in keys:
        a = state["areas"].get(k, {})
        sign = state["signoffs"].get(k)
        name = AREAS[k.split(':')[0]] + (f" ({k.split(':')[1]})" if ":" in k else "")
        print(f"  {k:16} {name:42} {a.get('level', 'full'):5} streak {a.get('streak', 0):>2}"
              + (f"  prompt pending: {a['pending']['to']}" if a.get("pending") else "")
              + (f"  signed off by {sign['by']} {sign['date']}" if sign else ""))
    return 0


def cmd_area(args) -> int:
    area = norm_area(args.area)
    if args.level not in LEVELS:
        raise SystemExit(f"level is one of {', '.join(LEVELS)}")
    if args.run:
        p = run_dir(args.run) / "levels.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        rl = run_levels(args.run)
        rl[area] = args.level
        p.write_text(json.dumps(rl, indent=2) + "\n", encoding="utf-8")
        log("level", run=run_id(args.run), area=area, to=args.level, by="preceptee", scope="run")
        print(f"area {area}: {args.level} for run {run_id(args.run)}")
        return 0
    state = load_state()
    keys = [area] + ([k for k in state["areas"] if k.startswith("6:")] if area == "6" else [])
    for k in keys:
        a = area_state(state, k)
        a["level"], a["pending"] = args.level, None
    save_state(state)
    log("level", area=area, to=args.level, by=args.by)
    print(f"area {area}{' (every stack)' if area == '6' else ''}: {args.level}")
    return 0


STACK_DOC = re.compile(r"\.fyzxsflow/docs/tech/([\w.-]+)\.md")


def package_stack(package: str) -> str:
    """The stack of a work package: the first tech doc in its context pack ('general' when it names none)."""
    text = pathlib.Path(package).read_text(encoding="utf-8")
    m = re.search(r"^## Context pack.*?$(.*?)(?=^## |\Z)", text, re.M | re.S)
    hit = STACK_DOC.search(m.group(1) if m else "")
    return slug(hit.group(1)) if hit else "general"


def cmd_decide(args) -> int:
    if args.package:
        if args.area.split(":")[0] != "6":
            raise SystemExit("--package names the stack, which only area 6 is kept by")
        args.area = f"6:{package_stack(args.package)}"
    if args.area.strip() == "6":
        raise SystemExit("area 6 is kept per stack: pass --package <work package> (or 6:<stack>)")
    area = norm_area(args.area)
    prior = [e for e in step_events(args.run, args.step) if e["kind"] == "decide"]
    if prior:
        e = prior[-1]
        print(f"pause={'yes' if e['pause'] else 'no'} level={e['level']} area={e['area']}")
        return 0
    state = load_state()
    level = effective_level(state, area, args.run)
    if level == "off" or area in AFTER_THE_FACT:
        pause = False
    elif level == "spot":
        seen = [e for e in events() if e["kind"] == "decide" and e.get("area") == area and e.get("level") == "spot"]
        pause = len(seen) % max(1, int(settings()["spot_every"])) == 0
    else:
        pause = True
    log("decide", run=run_id(args.run), step=args.step, area=area, level=level, pause=pause)
    print(f"pause={'yes' if pause else 'no'} level={level} area={area}")
    return 0


def step_area(run: str, step: str) -> str:
    for e in step_events(run, step):
        if e.get("area"):
            return e["area"]
    raise SystemExit(f"step {step}: no decide or ask recorded for it in this run")


def cmd_hint(args) -> int:
    evs = step_events(args.run, args.step)
    area = step_area(args.run, args.step)
    if any(e["kind"] == "attempt" for e in evs):
        print("note: the attempt is in; hints from now on are coaching and don't count against the streak")
    rung = sum(1 for e in evs if e["kind"] == "hint") + 1
    if rung > MAX_RUNG:
        print(f"refused: all {MAX_RUNG} rungs given; next is the preceptee's attempt or a bail", file=sys.stderr)
        return 1
    log("hint", run=run_id(args.run), step=args.step, area=area, rung=rung,
        before_attempt=not any(e["kind"] == "attempt" for e in evs))
    print(f"rung={rung}")
    return 0


def cmd_attempt(args) -> int:
    evs = step_events(args.run, args.step)
    area = step_area(args.run, args.step)
    if any(e["kind"] == "attempt" for e in evs):
        print("attempt already recorded")
        return 0
    if not paused(evs):
        print(f"refused: {args.step} did not pause (its area is off, or at spot and not chosen): the agents do it",
              file=sys.stderr)
        return 1
    log("attempt", run=run_id(args.run), step=args.step, area=area, bail=bool(args.bail))
    print("bail recorded: the agent does this step; reveal when it is done" if args.bail else "attempt recorded")
    return 0


def cmd_reveal(args) -> int:
    evs = step_events(args.run, args.step)
    if not any(e["kind"] in ("attempt", "answered") for e in evs):
        print(f"refused: no attempt or bail recorded for {args.step}; the preceptee goes first", file=sys.stderr)
        return 1
    log("reveal", run=run_id(args.run), step=args.step, area=step_area(args.run, args.step))
    print("revealed")
    return 0


def cmd_ask(args) -> int:
    area = norm_area(args.area)
    rd = run_dir(args.run)
    rd.mkdir(parents=True, exist_ok=True)
    with (rd / "questions.md").open("a", encoding="utf-8") as f:
        f.write(f"\n## {args.step} (area {area})\n{args.text.strip()}\n")
    log("ask", run=run_id(args.run), step=args.step, area=area)
    print(f"asked: {rd / 'questions.md'}")
    return 0


def cmd_answered(args) -> int:
    area = step_area(args.run, args.step)
    rd = run_dir(args.run)
    rd.mkdir(parents=True, exist_ok=True)
    with (rd / "questions.md").open("a", encoding="utf-8") as f:
        f.write(f"\n### answer to {args.step}\n{args.text.strip()}\n")
    log("answered", run=run_id(args.run), step=args.step, area=area)
    print("answer recorded")
    return 0


def paused(evs: list) -> bool:
    """False when the step's decide said pause=no: the agents did it, so it is not the preceptee's to score."""
    d = [e for e in evs if e["kind"] == "decide"]
    return not d or d[-1]["pause"]


def outcome_of(evs: list, args) -> str:
    if args.skip or args.unanswered:
        return "not-counted"
    if not paused(evs) and not any(e["kind"] == "ask" for e in evs):
        return "not-counted"
    attempt = next((e for e in evs if e["kind"] == "attempt"), None)
    answered = any(e["kind"] == "answered" for e in evs)
    if not attempt and not answered:
        return "not-counted"
    if attempt and attempt.get("bail"):
        return "miss"
    if any(e["kind"] == "hint" and e.get("before_attempt") and e["rung"] > 1 for e in evs):
        return "miss"
    if (args.major or 0) + (args.medium or 0) > 0 or (args.missed_major or 0) > 0:
        return "miss"
    if args.quiz_total is not None and (args.quiz_right or 0) < args.quiz_total:
        return "miss"
    return "good"


def next_level(level: str) -> str:
    i = LEVELS.index(level)
    return LEVELS[i + 1] if i + 1 < len(LEVELS) else None


def cmd_score(args) -> int:
    evs = step_events(args.run, args.step)
    area = step_area(args.run, args.step)
    if any(e["kind"] == "score" for e in evs):
        print(f"refused: {args.step} is already scored", file=sys.stderr)
        return 1
    attempted = any(e["kind"] == "attempt" for e in evs)
    if attempted and not any(e["kind"] == "reveal" for e in evs):
        print(f"refused: reveal {args.step} before scoring it", file=sys.stderr)
        return 1
    outcome = outcome_of(evs, args)
    state = load_state()
    a = area_state(state, area)
    level = effective_level(state, area)  # prompts move the standing level; a run-only level never prompts
    prompt = None
    if outcome == "good":
        a["streak"] = a.get("streak", 0) + 1
        to = next_level(level)
        if to and a["streak"] >= int(settings()["prompt_after"][to]) and not a.get("pending"):
            prompt = {"type": "step-down", "to": to, "streak": a["streak"]}
    elif outcome == "miss":
        a["streak"] = 0
        if (args.major or 0) > 0 or (args.missed_major or 0) > 0:
            if level in ("light", "spot") and not a.get("pending"):
                prompt = {"type": "step-up", "to": LEVELS[LEVELS.index(level) - 1], "streak": 0}
    if prompt:
        a["pending"] = prompt
    save_state(state)
    log("score", run=run_id(args.run), step=args.step, area=area, outcome=outcome, major=args.major,
        medium=args.medium, caught=args.caught, missed_major=args.missed_major, false_alarms=args.false_alarms,
        quiz_right=args.quiz_right, quiz_total=args.quiz_total, level=level)
    if prompt:
        log("prompt", area=area, **prompt)
    print(f"outcome={outcome} streak={a['streak']}" + (f" prompt={prompt['type']} to={prompt['to']}" if prompt else ""))
    return 0


def cmd_answer(args) -> int:
    area = norm_area(args.area)
    state = load_state()
    a = area_state(state, area)
    p = a.get("pending")
    if not p:
        print(f"no prompt pending for area {area}", file=sys.stderr)
        return 1
    yes = args.reply == "yes"
    if yes:
        a["level"] = p["to"]
    elif p["type"] == "step-down":
        a["streak"] = 0
    a["pending"] = None
    save_state(state)
    log("prompt-answer", area=area, prompt=p["type"], to=p["to"], reply=args.reply)
    print(f"area {area}: {a['level']}" + ("" if yes else " (kept; streak restarted)" if p["type"] == "step-down" else " (kept)"))
    return 0


def cmd_note(args) -> int:
    if args.kind not in NOTE_KINDS:
        raise SystemExit(f"kind is one of {', '.join(NOTE_KINDS)}")
    text = pathlib.Path(args.file).read_text(encoding="utf-8") if args.file else (args.text or "")
    if not text.strip():
        raise SystemExit("an empty note says nothing; pass --text or --file")
    if args.kind == "explain" and not args.path:
        raise SystemExit("an explanation is of one changed file: pass --path")
    rd = run_dir(args.run)
    rd.mkdir(parents=True, exist_ok=True)
    with (rd / f"{args.kind}.md").open("a", encoding="utf-8") as f:
        head = " ".join(x for x in (args.step, args.path) if x)
        f.write(f"\n## {head or now()}\n{text.strip()}\n")
    log("note", run=run_id(args.run), step=args.step, note=args.kind, path=args.path)
    print(f"noted in {rd / (args.kind + '.md')}")
    return 0


# ---------------------------------------------------------------- checks the ship line relies on

def repo_root(run: pathlib.Path) -> pathlib.Path:
    for parent in run.resolve().parents:
        if parent.name == ".fyzxsflow":
            return parent.parent
    raise SystemExit(f"{run} is not inside a .fyzxsflow/ folder")


def run_base(run: pathlib.Path) -> str:
    p = run / "input.md"
    m = re.search(r"^base:\s*(\S+)", p.read_text(encoding="utf-8"), re.M) if p.exists() else None
    return m.group(1) if m else ""


def changed_product_files(run: pathlib.Path) -> list:
    root, base = repo_root(run), run_base(run)
    files = set()
    if base:
        out = subprocess.run(["git", "diff", "--name-only", f"{base}...HEAD"], cwd=root, capture_output=True, text=True)
        files.update(out.stdout.splitlines())
    # tracked files changed since the last commit; untracked files (build output, caches) are not the change, and
    # ship-check's tree row already blocks an uncommitted product file
    out = subprocess.run(["git", "diff", "--name-only", "HEAD"], cwd=root, capture_output=True, text=True)
    files.update(out.stdout.splitlines())
    return sorted(f for f in files if not f.startswith((".fyzxsflow/", ".claude/", ".github/agents/")))


def explained(run: pathlib.Path):
    """(ok, detail) for explain-before-merge: every changed product file has the preceptee's explanation."""
    level = effective_level(load_state(), "9", str(run))
    if level == "off":
        return True, "area 9 off"
    done = {e.get("path") for e in events() if e["kind"] == "note" and e.get("note") == "explain"
            and e.get("run") == run.resolve().name}
    missing = [f for f in changed_product_files(run) if f not in done]
    return (not missing, "every changed file explained" if not missing
            else "not explained yet: " + ", ".join(missing[:5]) + (" ..." if len(missing) > 5 else ""))


def seeds(run: pathlib.Path) -> list:
    p = record_dir() / "runs" / run.resolve().name / "seeds.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else []


def seed_leaks(run: pathlib.Path) -> list:
    """Seeded lines that appear as added lines on the run's branch or in the working tree."""
    lines = {l.strip() for s in seeds(run) for l in s["lines"] if len(l.strip()) >= 8}
    if not lines:
        return []
    root, base = repo_root(run), run_base(run)
    diffs = [subprocess.run(["git", "diff", "-U0"], cwd=root, capture_output=True, text=True).stdout,
             subprocess.run(["git", "diff", "-U0", "--cached"], cwd=root, capture_output=True, text=True).stdout]
    if base:
        diffs.append(subprocess.run(["git", "diff", "-U0", f"{base}...HEAD"], cwd=root, capture_output=True,
                                    text=True).stdout)
    added = {l[1:].strip() for d in diffs for l in d.splitlines() if l.startswith("+") and not l.startswith("+++")}
    return sorted(lines & added)


def cmd_explained(args) -> int:
    ok, detail = explained(pathlib.Path(args.run))
    print(detail)
    return 0 if ok else 1


def cmd_seed(args) -> int:
    lines = [l for l in pathlib.Path(args.lines_file).read_text(encoding="utf-8").splitlines() if l.strip()]
    if not lines:
        raise SystemExit("a seed with no lines can't be checked")
    rd = run_dir(args.run)
    rd.mkdir(parents=True, exist_ok=True)
    data = seeds(pathlib.Path(args.run))
    data.append({"step": args.step, "lines": lines, "at": now()})
    (rd / "seeds.json").write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    log("seed", run=run_id(args.run), step=args.step, area="1", lines=len(lines))
    print(f"seed registered ({len(lines)} lines); show the seeded copy from {rd}, never from the working tree")
    return 0


def cmd_seed_check(args) -> int:
    leaks = seed_leaks(pathlib.Path(args.run))
    for l in leaks:
        print(f"seeded line in the repo: {l}")
    print("no seeded line reached the repo" if not leaks else f"{len(leaks)} seeded line(s) leaked: remove them")
    return 1 if leaks else 0


# ---------------------------------------------------------------- the digest and its way back

def area_summary(evs: list) -> dict:
    out = {}
    for e in evs:
        a = e.get("area")
        if not a:
            continue
        s = out.setdefault(a, {"exercises": 0, "good": 0, "miss": 0, "bails": 0, "hints": {}, "caught": 0,
                               "missed_major": 0, "false_alarms": 0, "quiz_right": 0, "quiz_total": 0})
        if e["kind"] == "score":
            if e["outcome"] != "not-counted":
                s["exercises"] += 1
                s[e["outcome"]] += 1
            for k in ("caught", "missed_major", "false_alarms", "quiz_right", "quiz_total"):
                s[k] += e.get(k) or 0
        elif e["kind"] == "attempt" and e.get("bail"):
            s["bails"] += 1
        elif e["kind"] == "hint" and e.get("before_attempt"):
            s["hints"][str(e["rung"])] = s["hints"].get(str(e["rung"]), 0) + 1
    return out


def cmd_digest(args) -> int:
    since = args.since or "0000"
    evs = [e for e in events() if e["at"] >= since]
    state = load_state()
    summary = area_summary(evs)
    who, today = handle(), datetime.date.today().isoformat()
    out = pathlib.Path(args.out) / f"digest-{who}-{today}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    keys = sorted(set(summary) | set(state["areas"]), key=lambda k: (k.split(":")[0], k))
    lines = [f"# Preceptee digest: {who}", "",
             f"{today}; events since {args.since or 'the start'}. Written by FyzxsFlow from the preceptee's local "
             "record. The preceptee reads it, may remove anything, and chooses whether to send it. It is coaching "
             "evidence for the rubric's proof column, not a rating.", "",
             "## Areas", "",
             "| Area | Level | Exercises | Good | Misses | Bails | Hints before attempting (rung: n) | Review: caught / missed major / false alarms | Quiz |",
             "|---|---|---|---|---|---|---|---|---|"]
    for k in keys:
        s = summary.get(k, {})
        name = f"{k} {AREAS[k.split(':')[0]]}" + (f" ({k.split(':')[1]})" if ":" in k else "")
        hints = ", ".join(f"{r}: {n}" for r, n in sorted(s.get("hints", {}).items())) or "-"
        review = (f"{s.get('caught', 0)} / {s.get('missed_major', 0)} / {s.get('false_alarms', 0)}"
                  if k == "1" else "-")
        quiz = f"{s.get('quiz_right', 0)}/{s.get('quiz_total', 0)}" if s.get("quiz_total") else "-"
        lines.append(f"| {name} | {effective_level(state, k)} | {s.get('exercises', 0)} | {s.get('good', 0)} | "
                     f"{s.get('miss', 0)} | {s.get('bails', 0)} | {hints} | {review} | {quiz} |")
    lines += ["", "## Level changes and prompts", ""]
    changes = [e for e in evs if e["kind"] in ("level", "prompt", "prompt-answer")]
    for e in changes:
        if e["kind"] == "level":
            lines.append(f"- {e['at'][:10]} area {e['area']}: set to {e['to']} by {e.get('by', 'preceptee')}"
                         + (" (this run only)" if e.get("scope") == "run" else ""))
        elif e["kind"] == "prompt":
            why = (f"after {e.get('streak')} good answers in a row" if e.get("type") == "step-down"
                   else "after a major miss")
            lines.append(f"- {e['at'][:10]} area {e['area']}: the Preceptor offered {e.get('to')} {why}")
        else:
            lines.append(f"- {e['at'][:10]} area {e['area']}: {e['reply']} to {e['to']}")
    if not changes:
        lines.append("- none")
    lines += ["", "## Sign-offs so far", ""]
    lines += [f"- area {k}: signed off by {v['by']} on {v['date']}" + (f" ({v['note']})" if v.get("note") else "")
              for k, v in sorted(state["signoffs"].items())] or ["- none"]
    open_q = []
    for rd in sorted((record_dir() / "runs").glob("*")) if (record_dir() / "runs").is_dir() else []:
        q = rd / "questions.md"
        if q.exists():
            asked = re.findall(r"^## (\S+) \(area", q.read_text(encoding="utf-8"), re.M)
            answered = set(re.findall(r"^### answer to (\S+)", q.read_text(encoding="utf-8"), re.M))
            open_q += [f"- {rd.name} {s}" for s in asked if s not in answered]
    lines += ["", "## Questions still open", ""] + (open_q or ["- none"])
    lines += ["", "## Preceptor notes", "",
              "<!-- For the preceptor: one line per decision, then send this file back. The preceptee runs",
              "     `preceptee.py import <this file>`. Lines it understands:",
              "       - area <n>: signed off            (optionally: - area <n>: signed off; <note>)",
              "       - area <n>: level full|light|spot|off",
              "     Anything else is kept as a note. -->", ""]
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    log("digest", path=str(out))
    print(f"wrote {out}: read it before sending it")
    return 0


SIGNOFF = re.compile(r"^-\s*area\s+([0-9]+(?::[\w.-]+)?)\s*:\s*signed off\s*(?:[;,-]\s*(.*))?$", re.I)
SETLEVEL = re.compile(r"^-\s*area\s+([0-9]+(?::[\w.-]+)?)\s*:\s*level\s+(full|light|spot|off)\s*$", re.I)


def cmd_import(args) -> int:
    text = pathlib.Path(args.file).read_text(encoding="utf-8")
    m = re.search(r"^## Preceptor notes\s*$", text, re.M)
    if not m:
        print("no '## Preceptor notes' section in that file", file=sys.stderr)
        return 2
    notes = re.sub(r"<!--.*?-->", "", text[m.end():], flags=re.S)
    state = load_state()
    by = args.by or "preceptor"
    applied, kept = [], []
    for line in (l.strip() for l in notes.splitlines()):
        if not line:
            continue
        s, l = SIGNOFF.match(line), SETLEVEL.match(line)
        if s:
            area = norm_area(s.group(1))
            state["signoffs"][area] = {"by": by, "date": datetime.date.today().isoformat(), "note": s.group(2) or ""}
            log("signoff", area=area, by=by, note=s.group(2))
            applied.append(f"area {area}: signed off")
        elif l:
            area = norm_area(l.group(1))
            a = area_state(state, area)
            a["level"], a["pending"] = l.group(2).lower(), None
            log("level", area=area, to=a["level"], by=by)
            applied.append(f"area {area}: level {a['level']}")
        else:
            kept.append(line)
    if kept:
        log("preceptor-note", text="\n".join(kept))
    save_state(state)
    for a in applied:
        print(a)
    print(f"{len(applied)} applied, {len(kept)} kept as notes")
    return 0


def cmd_export(args) -> int:
    if not args.consent:
        print("refused: export only with the preceptee's consent (--consent)", file=sys.stderr)
        return 1
    state = load_state()
    summary = area_summary(events())
    data = {"exported": datetime.date.today().isoformat(), "areas": {}}
    for k, s in sorted(summary.items()):
        reviews = s["caught"] + s["missed_major"]
        data["areas"][k] = {
            "level": effective_level(state, k), "exercises": s["exercises"], "good": s["good"], "misses": s["miss"],
            "bails": s["bails"], "review_catch_rate": round(s["caught"] / reviews, 2) if reviews else None,
            "quiz_rate": round(s["quiz_right"] / s["quiz_total"], 2) if s["quiz_total"] else None,
            "signed_off": k in state["signoffs"],
        }
    text = json.dumps(data, indent=2) + "\n"
    if args.out:
        pathlib.Path(args.out).write_text(text, encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        print(text, end="")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("whoami")
    sub.add_parser("status")
    a = sub.add_parser("area"); a.add_argument("area"); a.add_argument("level"); a.add_argument("--run")
    a.add_argument("--by", default="preceptee")
    d = sub.add_parser("decide"); d.add_argument("area"); d.add_argument("--run", required=True)
    d.add_argument("--step", required=True); d.add_argument("--package", help="area 6: the work package file")
    for name in ("hint", "reveal"):
        s = sub.add_parser(name); s.add_argument("--run", required=True); s.add_argument("--step", required=True)
    t = sub.add_parser("attempt"); t.add_argument("--run", required=True); t.add_argument("--step", required=True)
    t.add_argument("--bail", action="store_true")
    q = sub.add_parser("ask"); q.add_argument("--run", required=True); q.add_argument("--step", required=True)
    q.add_argument("--area", required=True); q.add_argument("--text", required=True)
    w = sub.add_parser("answered"); w.add_argument("--run", required=True); w.add_argument("--step", required=True)
    w.add_argument("--text", required=True)
    c = sub.add_parser("score"); c.add_argument("--run", required=True); c.add_argument("--step", required=True)
    for k in ("major", "medium", "caught", "missed-major", "false-alarms", "quiz-right", "quiz-total"):
        c.add_argument(f"--{k}", type=int)
    c.add_argument("--skip", action="store_true"); c.add_argument("--unanswered", action="store_true")
    r = sub.add_parser("answer"); r.add_argument("area"); r.add_argument("reply", choices=["yes", "no"])
    n = sub.add_parser("note"); n.add_argument("--run", required=True); n.add_argument("--kind", required=True)
    n.add_argument("--path"); n.add_argument("--step"); n.add_argument("--text"); n.add_argument("--file")
    e = sub.add_parser("explained"); e.add_argument("--run", required=True)
    sd = sub.add_parser("seed"); sd.add_argument("--run", required=True); sd.add_argument("--step", required=True)
    sd.add_argument("--lines-file", required=True)
    sc = sub.add_parser("seed-check"); sc.add_argument("--run", required=True)
    g = sub.add_parser("digest"); g.add_argument("--since"); g.add_argument("--out", required=True)
    i = sub.add_parser("import"); i.add_argument("file"); i.add_argument("--by")
    x = sub.add_parser("export"); x.add_argument("--consent", action="store_true"); x.add_argument("--out")
    args = p.parse_args(argv)
    return {"whoami": cmd_whoami, "status": cmd_status, "area": cmd_area, "decide": cmd_decide, "hint": cmd_hint,
            "attempt": cmd_attempt, "reveal": cmd_reveal, "ask": cmd_ask, "answered": cmd_answered,
            "score": cmd_score, "answer": cmd_answer, "note": cmd_note, "explained": cmd_explained,
            "seed": cmd_seed, "seed-check": cmd_seed_check, "digest": cmd_digest, "import": cmd_import,
            "export": cmd_export}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())

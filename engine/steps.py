"""Optional process steps: which ones a run uses.

  python -I .fyzxsflow/package/engine/steps.py list [--run <dir>] [--root .]
      -> one line per step: "<step> on|off (<source>) stage=<stage> agents=<...>", then
         "not opted in: <steps|none>" and "off: <steps|none>" (steps switched off, opt-in steps not counted)
  python -I .fyzxsflow/package/engine/steps.py enabled <step> [--run <dir>] [--root .]
      -> "step=<step> enabled=yes|no source=<default|project|run>"; exit 0 = on, 1 = off, 2 = unknown or core
  python -I .fyzxsflow/package/engine/steps.py set <step> on|off [--run <dir>] --reason "<owner's words>" [--root .]

Every step is on unless switched off, except the opt-in steps (OPT_IN: `e2e`, `precept`), which are off until
switched on.
The project switches steps in config.json:
    "steps": { "off": ["pr", "learn"], "on": ["e2e"] }
A run can override that either way (only through `set --run`, which writes <run>/steps.json):
    { "off": ["http-proofs"], "on": ["pr"] }
A group name (`reviews`) switches all its steps. The core of the flow (intake, locate, build, the validators
and the runner's build and test checks) is not a step and cannot be switched off.

`set` without --run changes the project setting and commits config.json on its own, like a review-level change.
"""

import argparse
import datetime
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from layout import HOME  # noqa: E402

# step -> (stage, agents or commands it covers, what happens while it is off)
STEPS = {
    "http-proofs": ("prove", "http-generator, runner --http",
                    "API changes are proven by the tests only; no proof files are written or run"),
    "gates": ("build, deliver", "gate-analyst",
              "declared linters and scanners are not run by the flow (CI still runs its own)"),
    "review-narrow": ("review", "reviewer-narrow", "no line-by-line review of the diff"),
    "review-large": ("review", "reviewer-large", "no review of callers, consumers and contracts"),
    "review-architecture": ("review", "reviewer-architecture", "no architecture review"),
    "review-security": ("review", "reviewer-security", "no security review"),
    "review-feature-flag": ("review", "reviewer-feature-flag", "no check of flag coverage and placement"),
    "review-iac": ("review", "reviewer-iac", "no review of pipeline and infrastructure changes"),
    "extreme": ("deliver", "runner --extreme",
                "no strict sign-off build (clean, strict, flags on and off, shuffled); the ci result is the last check"),
    "pr": ("deliver", "pr-producer, pr-reviewer",
           "no pull request: the run ends with its branch committed and ready, and you open the PR"),
    "pr-review": ("deliver", "pr-reviewer", "the PR is opened without the agent's whole-PR review"),
    "docs-upkeep": ("deliver", "docs-gardener (after-run mode)",
                    "docs are not refreshed after the run; owner feedback is still applied to docs"),
    "learn": ("learn", "curator",
              "findings are kept in the run but not routed to agents or docs until the Curator runs"),
    "e2e": ("prove", "e2e-investigator, e2e-implementer, e2e-tester, runner --e2e-airplane / --e2e-connected",
            "no end-to-end testing: changes are proven by the tests and http proofs only"),
    "precept": ("all", "preceptor, preceptee-socratic-pr, preceptee-seeder (preceptee mode: the preceptee works first at the engineer's steps)",
                "no coaching: the agents do every step, as in any run"),
}
OPT_IN = ("e2e", "precept")  # off unless the project or the run switches them on
GROUPS = {"reviews": [s for s in STEPS if s.startswith("review-")]}
CORE = ("intake", "locate", "build", "work-summarizer", "code-indicator", "build-coordinator", "implementer",
        "iac-implementer", "tester", "validator", "build-test-runner", "runner", "orchestrator")


def expand(names) -> set:
    out = set()
    for n in names or []:
        out.update(GROUPS.get(n, [n]))
    return out


def unknown(names) -> list:
    return [n for n in names or [] if n not in STEPS and n not in GROUPS]


def config_path(root: pathlib.Path) -> pathlib.Path:
    return root / HOME / "config.json"


def project_steps(root: pathlib.Path, key: str) -> list:
    path = config_path(root)
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    return list((data.get("steps") or {}).get(key) or [])


def project_off(root: pathlib.Path) -> list:
    return project_steps(root, "off")


def run_overrides(run) -> dict:
    path = pathlib.Path(run) / "steps.json" if run else None
    data = json.loads(path.read_text(encoding="utf-8")) if path and path.exists() else {}
    return {"off": list(data.get("off") or []), "on": list(data.get("on") or [])}


def state(root: pathlib.Path, run) -> dict:
    """step -> (on: bool, source)"""
    p_off, p_on = expand(project_off(root)), expand(project_steps(root, "on"))
    r = run_overrides(run)
    r_off, r_on = expand(r["off"]), expand(r["on"])
    out = {}
    for step in STEPS:
        if step in r_off:
            out[step] = (False, "run")
        elif step in r_on:
            out[step] = (True, "run")
        elif step in p_off:
            out[step] = (False, "project")
        elif step in p_on:
            out[step] = (True, "project")
        else:
            out[step] = (step not in OPT_IN, "default")
    return out


def root_for(args) -> pathlib.Path:
    if args.run:
        for parent in pathlib.Path(args.run).resolve().parents:
            if parent.name == HOME:
                return parent.parent
        raise SystemExit(f"{args.run} is not inside a {HOME}/ folder")
    return pathlib.Path(args.root).resolve()


def refuse(name: str) -> int:
    if name in CORE:
        print(f"error: '{name}' is part of the core flow and cannot be switched off", file=sys.stderr)
    else:
        print(f"error: unknown step '{name}'. Steps: {', '.join([*STEPS, *GROUPS])}", file=sys.stderr)
    return 2


def cmd_list(args) -> int:
    root = root_for(args)
    bad = (unknown(project_off(root)) + unknown(project_steps(root, "on"))
           + unknown(sum(run_overrides(args.run).values(), [])))
    for name in bad:
        print(f"warning: unknown step '{name}' is ignored (config.json steps.off / steps.on or the run's steps.json)")
    st = state(root, args.run)
    for step, (stage, agents, _) in STEPS.items():
        on, source = st[step]
        print(f"{step:20} {'on ' if on else 'off'} ({source:7}) stage={stage} agents={agents}")
    waiting = [s for s, (on, source) in st.items() if not on and source == "default"]
    off = [s for s, (on, source) in st.items() if not on and source != "default"]
    print(f"not opted in: {', '.join(waiting) if waiting else 'none'}")
    print(f"off: {', '.join(off) if off else 'none'}")
    return 0


def cmd_enabled(args) -> int:
    if args.step not in STEPS:
        return refuse(args.step)
    on, source = state(root_for(args), args.run)[args.step]
    print(f"step={args.step} enabled={'yes' if on else 'no'} source={source}")
    if not on:
        print(f"while off: {STEPS[args.step][2]}")
    return 0 if on else 1


def without(names: list, step: str) -> list:
    """Remove a step (or a group's steps) from a list; a group that covered it keeps its other members."""
    gone = expand([step])
    out = []
    for n in names:
        if n == step or n in gone:
            continue
        if n in GROUPS and set(GROUPS[n]) & gone:
            out += [s for s in GROUPS[n] if s not in gone and s not in out]
            continue
        out.append(n)
    return out


def cmd_set(args) -> int:
    if args.step not in STEPS and args.step not in GROUPS:
        return refuse(args.step)
    root = root_for(args)
    turn_on = args.value == "on"
    entry = {"step": args.step, "value": args.value, "scope": "run" if args.run else "project", "reason": args.reason}
    if args.run:
        r = run_overrides(args.run)
        keep, add = ("off", "on") if turn_on else ("on", "off")
        r[keep] = without(r[keep], args.step)
        r[add] = without(r[add], args.step) + [args.step]
        (pathlib.Path(args.run) / "steps.json").write_text(json.dumps(r, indent=2) + "\n", encoding="utf-8",
                                                           newline="\n")
        log(root, args.run, entry)
        where = "this run"
    else:
        path = config_path(root)
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        steps = data.setdefault("steps", {})
        off = without(list(steps.get("off") or []), args.step)
        on = without(list(steps.get("on") or []), args.step)
        opt_in = set(expand([args.step])) <= set(OPT_IN)
        steps["off"] = off if turn_on or opt_in else off + [args.step]  # an opt-in step is off by not being on
        on = on + [args.step] if turn_on and opt_in else on
        if on:
            steps["on"] = on
        else:
            steps.pop("on", None)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8", newline="\n")
        log(root, None, entry)
        commit(root, args.step, args.value)
        where = "the project"
    print(f"step={args.step} {args.value} for {where}")
    return 0


def log(root: pathlib.Path, run, entry: dict):
    entry = {"time": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S"), **entry}
    target = (pathlib.Path(run) / "steps.jsonl") if run else (root / HOME / "steps.jsonl")
    with open(target, "a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(entry) + "\n")


def commit(root: pathlib.Path, step: str, value: str):
    import run as runmod  # noqa: E402  (same engine folder)
    if runmod.runs_mode(root) == "local" or runmod.git(root, "rev-parse", "--git-dir").returncode != 0:
        return
    paths = [f"{HOME}/config.json", f"{HOME}/steps.jsonl"]
    runmod.git(root, "add", "--", *paths)
    runmod.git(root, "commit", "-q", "-m", f"fyzxsflow: step {step} {value}", "--", *paths)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("list", "enabled", "set"):
        s = sub.add_parser(name)
        if name != "list":
            s.add_argument("step")
        if name == "set":
            s.add_argument("value", choices=("on", "off"))
            s.add_argument("--reason", required=True)
        s.add_argument("--run")
        s.add_argument("--root", default=".")
    args = p.parse_args(argv)
    return {"list": cmd_list, "enabled": cmd_enabled, "set": cmd_set}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())

"""Model compare: run an agent at its tier AND one tier below (a shadow), validate both, and learn whether
the cheaper tier is good enough. Off by default: it can double the tokens of every shadowed dispatch.

  python -I .agentflow/engine/compare.py should --run <dir> --agent <name> [--host claude]
      -> "shadow=yes model=<m> tier=<t>"  or  "shadow=no reason=<why>"
  python -I .agentflow/engine/compare.py record --run <dir> --agent <name> --primary-tier deep --primary-model opus
      --shadow-tier standard --shadow-model sonnet --primary-verdict pass --shadow-verdict corrected
      [--shadow-majors 0] [--missed-majors 0] [--note "..."]
  python -I .agentflow/engine/compare.py summary [--root .]
      -> per agent and tier: comparisons, shadow-ok rate, and keep / reduce / insufficient

config.json -> compare:
  { "enabled": false, "agents": [], "sample_rate": 1.0, "max_per_run": 3, "min_samples": 5,
    "reduce_when_ok_rate": 0.9 }
  agents: [] means every eligible agent (fast and auto have no lower tier, so they are never shadowed).

Scoring (deterministic, so every host scores the same way):
  conclusive  the primary's Validator verdict is pass or corrected (a failed primary proves nothing)
  shadow_ok   conclusive, shadow verdict pass or corrected, no major findings on the shadow, and the shadow
              missed none of the primary's major findings (reviewers)
  reduce      at least min_samples conclusive comparisons, and shadow_ok rate >= reduce_when_ok_rate
"""

import argparse
import hashlib
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import models  # noqa: E402

DEFAULTS = {"enabled": False, "agents": [], "sample_rate": 1.0, "max_per_run": 3, "min_samples": 5,
            "reduce_when_ok_rate": 0.9}
VERDICTS = ("pass", "corrected", "fail")


def root_of(run: pathlib.Path) -> pathlib.Path:
    for parent in run.resolve().parents:
        if parent.name == ".agentflow":
            return parent.parent
    raise SystemExit(f"{run} is not inside a .agentflow/ folder")


def settings(root: pathlib.Path) -> dict:
    cfg = root / ".agentflow" / "config.json"
    data = json.loads(cfg.read_text(encoding="utf-8")) if cfg.exists() else {}
    out = dict(DEFAULTS)
    out.update(data.get("compare") or {})
    return out


def records(path: pathlib.Path) -> list:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def cmd_should(args) -> int:
    run = pathlib.Path(args.run)
    root = root_of(run)
    cfg = settings(root)
    if not cfg["enabled"]:
        print("shadow=no reason=compare-disabled")
        return 0
    if cfg["agents"] and args.agent not in cfg["agents"]:
        print("shadow=no reason=agent-not-selected")
        return 0
    agent_file = root / ".agentflow" / "agents" / f"{args.agent}.agent.md"
    if not agent_file.exists():
        print(f"no agent file {agent_file}", file=sys.stderr)
        return 2
    tier = models.tier_of(agent_file.read_text(encoding="utf-8"))
    low = models.shadow(tier, models.model_map(root, args.host))
    if low is None:
        print(f"shadow=no reason=no-lower-tier tier={tier}")
        return 0
    done = len(records(run / "compare.jsonl"))
    if done >= cfg["max_per_run"]:
        print(f"shadow=no reason=max-per-run ({done}/{cfg['max_per_run']})")
        return 0
    # Deterministic sampling: the same run, agent and dispatch count always decide the same way.
    digest = hashlib.sha256(f"{run.name}:{args.agent}:{done}".encode()).hexdigest()
    if int(digest[:8], 16) / 0xFFFFFFFF >= cfg["sample_rate"]:
        print("shadow=no reason=not-sampled")
        return 0
    print(f"shadow=yes model={low[1] or 'inherit'} tier={low[0]}")
    return 0


def cmd_record(args) -> int:
    run = pathlib.Path(args.run)
    for v in (args.primary_verdict, args.shadow_verdict):
        if v not in VERDICTS:
            print(f"verdicts must be one of {', '.join(VERDICTS)}", file=sys.stderr)
            return 2
    path = run / "compare.jsonl"
    conclusive = args.primary_verdict in ("pass", "corrected")
    shadow_ok = (conclusive and args.shadow_verdict in ("pass", "corrected")
                 and args.shadow_majors == 0 and args.missed_majors == 0)
    rec = {"id": f"C-{len(records(path)) + 1}", "run": run.name, "agent": args.agent,
           "primary": {"tier": args.primary_tier, "model": args.primary_model, "verdict": args.primary_verdict},
           "shadow": {"tier": args.shadow_tier, "model": args.shadow_model, "verdict": args.shadow_verdict,
                      "major_findings": args.shadow_majors, "missed_primary_majors": args.missed_majors},
           "conclusive": conclusive, "shadow_ok": shadow_ok}
    if args.note:
        rec["note"] = args.note
    with open(path, "a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(rec) + "\n")
    print(f"{rec['id']} conclusive={'yes' if conclusive else 'no'} shadow_ok={'yes' if shadow_ok else 'no'}")
    return 0


def cmd_summary(args) -> int:
    root = pathlib.Path(args.root).resolve()
    cfg = settings(root)
    groups = {}
    for path in sorted((root / ".agentflow" / "runs").rglob("compare.jsonl")):
        if "_adhoc" in path.parts:
            continue
        for r in records(path):
            key = (r["agent"], r["primary"]["tier"], r["shadow"]["tier"])
            g = groups.setdefault(key, {"conclusive": 0, "ok": 0, "inconclusive": 0})
            if r["conclusive"]:
                g["conclusive"] += 1
                g["ok"] += 1 if r["shadow_ok"] else 0
            else:
                g["inconclusive"] += 1
    if not groups:
        print("no comparisons recorded yet")
        return 0
    for (agent, tier, low), g in sorted(groups.items()):
        n, ok = g["conclusive"], g["ok"]
        rate = ok / n if n else 0.0
        if n < cfg["min_samples"]:
            verdict = f"insufficient ({n}/{cfg['min_samples']})"
        elif rate >= cfg["reduce_when_ok_rate"]:
            verdict = f"reduce: {tier} -> {low}"
        else:
            verdict = "keep"
        print(f"{agent:24} {tier:>8} vs {low:<8} {ok}/{n} ok ({rate:.0%}), {g['inconclusive']} inconclusive -> {verdict}")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("should")
    s.add_argument("--run", required=True); s.add_argument("--agent", required=True)
    s.add_argument("--host", default="claude", choices=["claude", "copilot"])
    r = sub.add_parser("record")
    for a in ("--run", "--agent", "--primary-tier", "--primary-model", "--shadow-tier", "--shadow-model",
              "--primary-verdict", "--shadow-verdict"):
        r.add_argument(a, required=True)
    r.add_argument("--shadow-majors", type=int, default=0)
    r.add_argument("--missed-majors", type=int, default=0)
    r.add_argument("--note")
    m = sub.add_parser("summary")
    m.add_argument("--root", default=".")
    args = p.parse_args(argv)
    return {"should": cmd_should, "record": cmd_record, "summary": cmd_summary}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())

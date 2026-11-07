"""Resolve which model an agentflow agent runs on, from its tier and the project's model map.

  python -I .agentflow/engine/models.py <agent> [--host claude] [--up N]   -> model=<m> tier=<t> ...
  python -I .agentflow/engine/models.py --list [--host claude]             -> every agent, its tier and model

Agents declare `tier: deep | standard | fast` in their frontmatter, never a model name, so agent files stay
host-neutral. .agentflow/config.json -> models.<host>.<tier> maps tiers to the host's model names; an empty
value (or no entry) means "inherit the session's model". Built-in defaults apply when the project has no map.

--up N escalates N tiers (fast -> standard -> deep), capped at deep: the Orchestrator uses it when a
Validator has failed the same agent's output twice in a run.
--down 1 gives the shadow model for a model-compare run (engine/compare.py); fast and auto have no lower tier.

`tier: auto` means "the harness decides" (e.g. GitHub Copilot's Auto model selection). Map it per host to
the host's own keyword in models.<host>.auto; on a host without the capability leave it empty (inherit).
Escalating from auto goes to deep. auto is never shadowed: there is no defined tier below it.
"""

import argparse
import json
import pathlib
import re
import sys

ORDER = ["fast", "standard", "deep"]
TIERS = ORDER + ["auto"]
DEFAULTS = {
    "claude": {"deep": "opus", "standard": "sonnet", "fast": "haiku", "auto": ""},  # no harness auto: inherit
    "copilot": {},  # unverified model names (and the Auto keyword): inherit until the project maps them
}
TIER = re.compile(r"\A---\n(?:.*\n)*?tier:\s*(deep|standard|fast|auto)\s*\n(?:.*\n)*?---\n", re.M)


def tier_of(text: str) -> str:
    m = TIER.match(text)
    return m.group(1) if m else "standard"


def model_map(root: pathlib.Path, host: str) -> dict:
    mapping = dict(DEFAULTS.get(host, {}))
    cfg = root / ".agentflow" / "config.json"
    if cfg.exists():
        project = (json.loads(cfg.read_text(encoding="utf-8")).get("models") or {}).get(host)
        if project is not None:
            mapping = dict(project)  # a project map replaces the defaults for that host entirely
    return mapping


def resolve(tier: str, mapping: dict, up: int = 0):
    """Returns (tier used, model or '' for inherit, capped)."""
    if tier == "auto":
        if up <= 0:
            return "auto", (mapping.get("auto") or "").strip(), False
        tier, up = "deep", up - 1  # the harness's pick wasn't enough: go to the strongest tier
    i = ORDER.index(tier) + max(0, up)
    capped = i > len(ORDER) - 1  # asked to go above deep
    used = ORDER[min(i, len(ORDER) - 1)]
    return used, (mapping.get(used) or "").strip(), capped


def shadow(tier: str, mapping: dict):
    """The tier and model one below `tier` for a model compare, or None when there is no lower tier."""
    if tier in ("auto", "fast"):
        return None
    lower = ORDER[ORDER.index(tier) - 1]
    return lower, (mapping.get(lower) or "").strip()


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("agent", nargs="?")
    p.add_argument("--host", default="claude", choices=["claude", "copilot"])
    p.add_argument("--up", type=int, default=0)
    p.add_argument("--down", action="store_true", help="the shadow model one tier below (model compare)")
    p.add_argument("--list", action="store_true")
    p.add_argument("--root", default=".")
    p.add_argument("--agents-dir", default=".agentflow/agents")
    args = p.parse_args(argv)
    root = pathlib.Path(args.root).resolve()
    agents = root / args.agents_dir
    mapping = model_map(root, args.host)
    if args.list:
        for f in sorted(agents.glob("*.agent.md")):
            tier = tier_of(f.read_text(encoding="utf-8"))
            _, model, _ = resolve(tier, mapping)
            print(f"{f.name.replace('.agent.md', ''):24} {tier:9} {model or 'inherit'}")
        return 0
    if not args.agent:
        p.error("give an agent name, or --list")
    f = agents / f"{args.agent}.agent.md"
    if not f.exists():
        print(f"no agent file {f}", file=sys.stderr)
        return 2
    declared = tier_of(f.read_text(encoding="utf-8"))
    if args.down:
        low = shadow(declared, mapping)
        print(f"shadow=none declared={declared}" if low is None
              else f"model={low[1] or 'inherit'} tier={low[0]} declared={declared}")
        return 0
    used, model, capped = resolve(declared, mapping, args.up)
    print(f"model={model or 'inherit'} tier={used} declared={declared} escalated={'yes' if used != declared else 'no'}"
          f"{' capped=yes' if capped else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

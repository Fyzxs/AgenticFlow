"""Which work packages run in parallel, and why the rest run in series.

  python -I .fyzxsflow/package/engine/waves.py check --run <run> [--json]
      -> the wave table ("wave 1: WP-01 | wave 2: WP-02, WP-03 (parallel)"), then any problems. Exit 0 = the plan
         holds, 1 = a problem (listed), 2 = usage.

A wave is the packages whose every `depends_on` is in an earlier wave; the packages of one wave run in parallel
(engine/lanes.py), up to config.json -> build.max_parallel (default 3) at a time.

Fails when:
  - a `depends_on` names a package that doesn't exist, or the dependencies form a cycle;
  - two packages of the same wave share a file in their `## Scope` (`create:` / `change:` lines): they would
    collide when the lanes merge. Make one depend on the other (reason `same file`), or move the shared edit to an
    integration package;
  - a `depends_on` entry has no reason in the package's `## Series reasons` section:
        - WP-01: contract — consumes the OrderExport interface WP-01 defines
    with one of the reasons: contract, same file, shared resource, risk first.
Warns when two packages of the same wave use Runner modes holding the same lock (config.json "lock"): they will
wait for each other at the done-check, which is safe but slower.
"""

import argparse
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from layout import HOME  # noqa: E402

REASONS = ("contract", "same file", "shared resource", "risk first")
FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n", re.S)
BACKTICK = re.compile(r"`([^`\n]+)`")
SECTION = r"^## {name}[^\n]*$(.*?)(?=^## |\Z)"
WP_ID = re.compile(r"\bWP-\d+\b")
MODE = re.compile(r"(?:--|runner\.py\s+)([a-z][\w-]*)")
DEFAULT_MAX_PARALLEL = 3


def section(text: str, name: str) -> str:
    m = re.search(SECTION.format(name=re.escape(name)), text, re.M | re.S)
    return m.group(1) if m else ""


def parse(path: pathlib.Path) -> dict:
    text = path.read_text(encoding="utf-8")
    fm = FRONTMATTER.match(text)
    meta = {}
    for line in (fm.group(1).splitlines() if fm else []):
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.split("#", 1)[0].strip()
    wp = meta.get("id") or (WP_ID.search(path.name).group(0) if WP_ID.search(path.name) else path.stem)
    deps = WP_ID.findall(meta.get("depends_on", ""))
    scope = set()
    for line in section(text, "Scope").splitlines():
        if re.match(r"^\s*-\s*(create|change)\s*:", line):
            scope.update(t.strip().rstrip("/") for t in BACKTICK.findall(line) if "..." not in t)
    reasons = {}
    for line in section(text, "Series reasons").splitlines():
        m = re.match(r"^\s*-\s*(WP-\d+)\s*:\s*([a-z ]+?)\s*(?:—|-|:|$)", line)
        if m:
            reasons[m.group(1)] = m.group(2).strip()
    modes = set()
    for line in section(text, "Done check").splitlines():
        if "Runner" in line or "runner.py" in line:
            for tok in BACKTICK.findall(line) or [line]:
                modes.update(m for m in MODE.findall(tok) if m not in ("scope", "run", "root", "allow-destructive"))
    return {"id": wp, "file": path.name, "depends_on": deps, "scope": sorted(scope), "reasons": reasons,
            "modes": sorted(modes)}


def load(run: pathlib.Path) -> list:
    return [parse(p) for p in sorted((run / "work-packages").glob("*.md"))]


def config(run: pathlib.Path) -> dict:
    for parent in run.resolve().parents:
        if parent.name == HOME:
            p = parent / "config.json"
            return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    return {}


def max_parallel(run: pathlib.Path) -> int:
    return max(1, int((config(run).get("build") or {}).get("max_parallel", DEFAULT_MAX_PARALLEL)))


def waves(packages: list):
    """(list of waves, each a list of ids in plan order; problems)."""
    ids = [p["id"] for p in packages]
    by_id = {p["id"]: p for p in packages}
    problems = []
    for p in packages:
        for d in p["depends_on"]:
            if d not in by_id:
                problems.append(f"{p['id']}: depends_on {d}, which is not a package of this run")
    level, done, out = {}, set(), []
    remaining = [i for i in ids]
    while remaining:
        ready = [i for i in remaining if all(d in done or d not in by_id for d in by_id[i]["depends_on"])]
        if not ready:
            problems.append("dependency cycle among: " + ", ".join(remaining))
            out.append(remaining)
            break
        out.append(ready)
        done.update(ready)
        remaining = [i for i in remaining if i not in ready]
    for n, w in enumerate(out, 1):
        for i in w:
            level[i] = n
    return out, problems


def check(run: pathlib.Path):
    packages = load(run)
    by_id = {p["id"]: p for p in packages}
    out, problems = waves(packages)
    warnings = []
    modes = config(run).get("modes") or {}
    for p in packages:
        for d in p["depends_on"]:
            r = p["reasons"].get(d)
            if d in by_id and not r:
                problems.append(f"{p['id']}: depends_on {d} with no reason under '## Series reasons' "
                                f"(one of: {', '.join(REASONS)})")
            elif r and r not in REASONS:
                problems.append(f"{p['id']}: series reason '{r}' for {d} is not one of: {', '.join(REASONS)}")
    for w in out:
        for i, a in enumerate(w):
            for b in w[i + 1:]:
                shared = sorted(set(by_id[a]["scope"]) & set(by_id[b]["scope"]))
                if shared:
                    problems.append(f"{a} and {b} are in the same wave but both change {', '.join(shared)}: make one "
                                    "depend on the other (reason: same file), or move that edit to an integration "
                                    "package")
                locks = {(modes.get(m) or {}).get("lock") for m in by_id[a]["modes"]} & \
                        {(modes.get(m) or {}).get("lock") for m in by_id[b]["modes"]}
                locks.discard(None)
                if locks:
                    warnings.append(f"{a} and {b} share the Runner lock {', '.join(sorted(locks))}: their done-checks "
                                    "will wait for each other")
    return out, problems, warnings


def cmd_check(args) -> int:
    run = pathlib.Path(args.run)
    if not (run / "work-packages").is_dir():
        print(f"{run}: no work-packages/ folder", file=sys.stderr)
        return 2
    out, problems, warnings = check(run)
    cap = max_parallel(run)
    if args.json:
        print(json.dumps({"waves": out, "max_parallel": cap, "problems": problems, "warnings": warnings}, indent=2))
    else:
        parts = []
        for n, w in enumerate(out, 1):
            note = f" (parallel, {min(len(w), cap)} at a time)" if len(w) > 1 else ""
            parts.append(f"wave {n}: {', '.join(w)}{note}")
        print(" | ".join(parts) if parts else "no packages")
        for w in warnings:
            print(f"warning: {w}")
        for p in problems:
            print(f"FAIL {p}")
        print(f"waves: {'pass' if not problems else 'fail'} ({len(problems)} problems)")
    return 1 if problems else 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check"); c.add_argument("--run", required=True); c.add_argument("--json", action="store_true")
    args = p.parse_args(argv)
    return cmd_check(args)


if __name__ == "__main__":
    sys.exit(main())

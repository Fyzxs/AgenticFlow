"""Which work packages run in parallel, which share a PR, and why the rest run in series.

  python -I .fyzxsflow/package/engine/waves.py check --run <run> [--json]
      -> the done packages, the wave table of what is left ("wave 1: WP-02, WP-03 (parallel, 2 at a time) | wave 2:
         WP-04"), the PR groups and what each waits for, then any problems. Exit 0 = the plan holds, 1 = a problem
         (listed), 2 = usage.

Done packages (`status: done`) count as already built: they are never built again, and a package whose only
remaining dependencies are done is in the first wave.

PR groups: each package names its group in frontmatter (`pr_group: <slug>`; default, its own id). A group is one
lane and one PR into the run branch; packages share one only when one can't be reviewed without the other. A group
starts as soon as every group it depends on has its PR completed into the run branch (engine/lanes.py), never
waiting for a wave or for an unrelated group; up to config.json -> build.max_parallel (default 3) lanes at once.
Waves are the planning view: a wave is the packages whose every remaining dependency is in an earlier wave.

Fails when:
  - a `depends_on` names a package that doesn't exist, or the dependencies form a cycle (of packages or of groups);
  - two groups that may build at the same time (neither depends on the other, directly or not) share a file in
    their packages' `## Scope` (`create:` / `change:` lines): their PRs would collide. Make one depend on the other
    (reason `same file`), or move the shared edit to an integration package;
  - a `depends_on` entry has no reason in the package's `## Series reasons` section:
        - WP-01: contract — consumes the OrderExport interface WP-01 defines
    with one of the reasons: contract, same file, shared resource, risk first.
Warns when two such groups use Runner modes holding the same lock (config.json "lock"): their done-checks wait for
each other, which is safe but slower.
A problem that names only done packages is reported as info, never a failure: done packages are left exactly as
they are, so a run planned before these rules can still go on.
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
    named = re.sub(r"[^a-z0-9-]+", "-", meta.get("pr_group", "").lower()).strip("-")
    group = named or wp
    return {"id": wp, "file": path.name, "depends_on": deps, "scope": sorted(scope), "reasons": reasons,
            "modes": sorted(modes), "done": meta.get("status", "").lower() == "done", "group": group}


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
    """(list of waves of the packages not yet done, each a list of ids in plan order; problems).
    A done package counts as already built, so whatever depends only on done packages is in wave 1."""
    by_id = {p["id"]: p for p in packages}
    problems = []
    for p in packages:
        for d in p["depends_on"]:
            if d not in by_id:
                problems.append(f"{p['id']}: depends_on {d}, which is not a package of this run")
    built = {p["id"] for p in packages if p["done"]}
    remaining = [p["id"] for p in packages if not p["done"]]
    out = []
    while remaining:
        ready = [i for i in remaining if all(d in built or d not in by_id for d in by_id[i]["depends_on"])]
        if not ready:
            problems.append("dependency cycle among: " + ", ".join(remaining))
            out.append(remaining)
            break
        out.append(ready)
        built.update(ready)
        remaining = [i for i in remaining if i not in ready]
    return out, problems


def groups(packages: list) -> dict:
    """group -> its package ids, in plan order."""
    out = {}
    for p in packages:
        out.setdefault(p["group"], []).append(p["id"])
    return out


def group_deps(packages: list) -> dict:
    """group -> the other groups its packages depend on."""
    by_id = {p["id"]: p for p in packages}
    out = {p["group"]: set() for p in packages}
    for p in packages:
        for d in p["depends_on"]:
            if d in by_id and by_id[d]["group"] != p["group"]:
                out[p["group"]].add(by_id[d]["group"])
    return out


def closure(deps: dict) -> dict:
    """group -> every group it depends on, directly or not."""
    out = {}
    for g in deps:
        seen, stack = set(), list(deps[g])
        while stack:
            x = stack.pop()
            if x not in seen:
                seen.add(x)
                stack.extend(deps.get(x, ()))
        out[g] = seen
    return out


def done_groups(packages: list) -> set:
    """Groups whose every package is done: already built into the run branch."""
    return {g for g, ids in groups(packages).items() if all(p["done"] for p in packages if p["group"] == g)}


def waiting(packages: list, completed: set) -> list:
    """(group, the groups it still waits for) for every group not completed, in plan order. Done groups count as
    completed; a group may start when its list is empty."""
    deps, completed = group_deps(packages), set(completed) | done_groups(packages)
    return [(g, sorted(d for d in deps[g] if d not in completed)) for g in groups(packages) if g not in completed]


def check(run: pathlib.Path):
    """(waves, problems, warnings, info). A problem that names only done packages is info."""
    packages = load(run)
    by_id = {p["id"]: p for p in packages}
    done = {p["id"] for p in packages if p["done"]}
    out, raw = waves(packages)
    found = [(t, {i for i in by_id if not by_id[i]["done"]} if t.startswith("dependency cycle")
              else {t.split(":")[0]}) for t in raw]
    warnings = []
    modes = config(run).get("modes") or {}
    for p in packages:
        for d in p["depends_on"]:
            r = p["reasons"].get(d)
            if d in by_id and not r:
                found.append((f"{p['id']}: depends_on {d} with no reason under '## Series reasons' "
                              f"(one of: {', '.join(REASONS)})", {p["id"]}))
            elif r and r not in REASONS:
                found.append((f"{p['id']}: series reason '{r}' for {d} is not one of: {', '.join(REASONS)}",
                              {p["id"]}))
    deps = group_deps(packages)
    reach = closure(deps)
    members = groups(packages)
    for g, ds in reach.items():
        if g in ds:
            found.append((f"group {g} depends on itself through: {', '.join(sorted(ds - {g}))}", set(members[g])))
    names = list(members)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            if b in reach[a] or a in reach[b]:
                continue
            pa, pb = [by_id[x] for x in members[a]], [by_id[x] for x in members[b]]
            shared = sorted({f for p in pa for f in p["scope"]} & {f for p in pb for f in p["scope"]})
            if shared:
                found.append((f"groups {a} and {b} may build at the same time but both change {', '.join(shared)}: "
                              "make one depend on the other (reason: same file), or move that edit to an "
                              "integration package", set(members[a]) | set(members[b])))
            locks = {(modes.get(m) or {}).get("lock") for p in pa for m in p["modes"]} & \
                    {(modes.get(m) or {}).get("lock") for p in pb for m in p["modes"]}
            locks.discard(None)
            if locks and not all(p["done"] for p in pa + pb):
                warnings.append(f"groups {a} and {b} share the Runner lock {', '.join(sorted(locks))}: their "
                                "done-checks will wait for each other")
    problems = [t for t, ids in found if not ids <= done]
    info = [t for t, ids in found if ids <= done]
    return out, problems, warnings, info


def cmd_check(args) -> int:
    run = pathlib.Path(args.run)
    if not (run / "work-packages").is_dir():
        print(f"{run}: no work-packages/ folder", file=sys.stderr)
        return 2
    out, problems, warnings, info = check(run)
    cap = max_parallel(run)
    packages = load(run)
    members, deps = groups(packages), group_deps(packages)
    done = [p["id"] for p in packages if p["done"]]
    if args.json:
        print(json.dumps({"done": done, "waves": out, "groups": members,
                          "group_deps": {g: sorted(d) for g, d in deps.items()}, "max_parallel": cap,
                          "problems": problems, "warnings": warnings, "info": info}, indent=2))
    else:
        parts = [f"wave {n}: {', '.join(w)}" + (f" (parallel, {min(len(w), cap)} at a time)" if len(w) > 1 else "")
                 for n, w in enumerate(out, 1)]
        if done:
            print(f"done: {', '.join(done)}")
        print(" | ".join(parts) if parts else "nothing left to build")
        finished = done_groups(packages)
        for g, ids in members.items():
            if g in finished:
                continue
            print(f"group {g}: {', '.join(ids)}; after {', '.join(sorted(deps[g])) or 'nothing'}")
        for w in warnings:
            print(f"warning: {w}")
        for i in info:
            print(f"info (done packages, left as they are): {i}")
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

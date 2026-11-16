"""Which work packages run in parallel, which share a PR, and why the rest run in series.

  python -I .fyzxsflow/package/engine/waves.py check --run <run> [--json] [--verbose]
      -> the done packages, the wave table of what is left ("wave 1: WP-02, WP-03 (parallel, 2 at a time) | wave 2:
         WP-04"), the PR groups and what each waits for, then any problems. Exit 0 = the plan holds, 1 = a problem
         (listed), 2 = usage.

Done packages (`status: done`) count as already built: they are never built again, and a package whose only
remaining dependencies are done is in the first wave.
Deferred packages (`status: deferred`, set by `lanes.py park` when the owner holds one) are set aside: they and
every package that depends on them, directly or not, are left out of the waves and listed as held (a warning), and
a group with a held package waits on the deferred group. Problems that name only done or deferred packages are info.

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
Warns once per Runner lock (config.json "lock") that two or more not-done groups which may build at the same time
share: their done-checks queue one at a time, which is safe but slower. The line names every such group; --verbose
(and --json, as lock_pairs) lists the pairs behind it. A group that is done never builds again, so a pair with a done
group is never a lock warning, and a file both change is info, not a problem.
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
    done_check = section(text, "Done check")
    for line in done_check.splitlines():
        if "Runner" in line or "runner.py" in line:
            for tok in BACKTICK.findall(line) or [line]:
                modes.update(m for m in MODE.findall(tok) if m not in ("scope", "run", "root", "allow-destructive"))
    named = re.sub(r"[^A-Za-z0-9-]+", "-", meta.get("pr_group", "")).strip("-")  # kept as written, like the default
    group = named or wp
    return {"id": wp, "file": path.name, "depends_on": deps, "scope": sorted(scope), "reasons": reasons,
            "modes": sorted(modes), "done": meta.get("status", "").lower() == "done", "group": group,
            "deferred": meta.get("status", "").lower() == "deferred",
            "done_check": done_check}


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
    held = held_ids(packages)
    remaining = [p["id"] for p in packages if not p["done"] and p["id"] not in held]
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


def held_ids(packages: list) -> set:
    """Deferred packages and every not-done package that depends on one, directly or not."""
    by_id = {p["id"]: p for p in packages}
    held = {p["id"] for p in packages if p.get("deferred")}
    grew = True
    while grew:
        grew = False
        for p in packages:
            if p["id"] not in held and not p["done"] and any(d in held for d in p["depends_on"] if d in by_id):
                held.add(p["id"])
                grew = True
    return held


def parked_groups(packages: list) -> set:
    """Groups with a deferred package and nothing left to build otherwise: set aside until it returns."""
    return {g for g, ids in groups(packages).items()
            if any(p.get("deferred") for p in packages if p["group"] == g)
            and all(p.get("deferred") or p["done"] for p in packages if p["group"] == g)}


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
    parked = parked_groups(packages)
    return [(g, sorted(d for d in deps[g] if d not in completed)) for g in groups(packages)
            if g not in completed and g not in parked]


def check(run: pathlib.Path):
    """(waves, problems, warnings, info). A problem that names only done packages is info."""
    d = check_detail(run)
    return d["waves"], d["problems"], d["warnings"], d["info"]


def check_detail(run: pathlib.Path) -> dict:
    """Everything check() finds, plus the lock pairs behind each lock warning."""
    packages = load(run)
    by_id = {p["id"]: p for p in packages}
    done = {p["id"] for p in packages if p["done"]}
    held = held_ids(packages)
    settled = done | {p["id"] for p in packages if p.get("deferred")}  # left exactly as they are
    out, raw = waves(packages)
    found = [(t, {i for i in by_id if not by_id[i]["done"]} if t.startswith("dependency cycle")
              else {t.split(":")[0]}) for t in raw]
    warnings = []
    deferred = [p["id"] for p in packages if p.get("deferred")]
    if deferred:
        waits = [p["id"] for p in packages if p["id"] in held and not p.get("deferred")]
        warnings.append(f"deferred: {', '.join(deferred)}" + (f"; held until it returns: {', '.join(waits)}"
                                                                 if waits else ""))
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
    for p in packages:  # a mode named by its config key ("`ci` passes") counts too, not only `--ci` / runner.py ci
        for m in modes:
            if re.search(rf"`{re.escape(m)}`|\b{re.escape(m)} mode\b", p["done_check"]):
                p["modes"] = sorted(set(p["modes"]) | {m})
    deps = group_deps(packages)
    reach = closure(deps)
    members = groups(packages)
    for g, ds in reach.items():
        if g in ds:
            found.append((f"group {g} depends on itself through: {', '.join(sorted(ds - {g}))}", set(members[g])))
    names = list(members)
    finished = done_groups(packages) | {g for g, ids in members.items() if all(i in held or i in done for i in ids)}
    pairs = []  # (lock, group a, group b) for not-done groups that may build at the same time
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            if b in reach[a] or a in reach[b]:
                continue
            pa, pb = [by_id[x] for x in members[a]], [by_id[x] for x in members[b]]
            either_done = a in finished or b in finished  # a done (or held) group doesn't build now
            shared = sorted({f for p in pa for f in p["scope"]} & {f for p in pb for f in p["scope"]})
            if shared:
                text = (f"groups {a} and {b} may build at the same time but both change {', '.join(shared)}: "
                        "make one depend on the other (reason: same file), or move that edit to an "
                        "integration package")
                found.append((text, settled if either_done else set(members[a]) | set(members[b])))
            if either_done:
                continue
            locks = {(modes.get(m) or {}).get("lock") for p in pa for m in p["modes"]} & \
                    {(modes.get(m) or {}).get("lock") for p in pb for m in p["modes"]}
            locks.discard(None)
            pairs += [(lock, a, b) for lock in sorted(locks)]
    for lock in sorted({l for l, _, _ in pairs}):
        sharing = [g for g in names if any(l == lock and g in (a, b) for l, a, b in pairs)]
        warnings.append(f"lock {lock}: {len(sharing)} groups' done-checks queue one at a time when their lanes "
                        f"overlap ({', '.join(sharing)})")
    problems = [t for t, ids in found if not ids <= settled]
    info = [t for t, ids in found if ids <= settled]
    return {"waves": out, "problems": problems, "warnings": warnings, "info": info,
            "lock_pairs": [{"lock": l, "groups": [a, b]} for l, a, b in pairs]}


def cmd_check(args) -> int:
    run = pathlib.Path(args.run)
    if not (run / "work-packages").is_dir():
        print(f"{run}: no work-packages/ folder", file=sys.stderr)
        return 2
    detail = check_detail(run)
    out, problems, warnings, info = detail["waves"], detail["problems"], detail["warnings"], detail["info"]
    cap = max_parallel(run)
    packages = load(run)
    members, deps = groups(packages), group_deps(packages)
    done = [p["id"] for p in packages if p["done"]]
    if args.json:
        print(json.dumps({"done": done, "waves": out, "groups": members,
                          "group_deps": {g: sorted(d) for g, d in deps.items()}, "max_parallel": cap,
                          "problems": problems, "warnings": warnings, "lock_pairs": detail["lock_pairs"],
                          "info": info}, indent=2))
    else:
        parts = [f"wave {n}: {', '.join(w)}" + (f" (parallel, {min(len(w), cap)} at a time)" if len(w) > 1 else "")
                 for n, w in enumerate(out, 1)]
        if done:
            print(f"done: {', '.join(done)}")
        print(" | ".join(parts) if parts else "nothing left to build")
        finished = done_groups(packages) | parked_groups(packages)
        for g, ids in members.items():
            if g in finished:
                continue
            print(f"group {g}: {', '.join(ids)}; after {', '.join(sorted(deps[g])) or 'nothing'}")
        for w in warnings:
            print(f"warning: {w}")
        if args.verbose:
            for pair in detail["lock_pairs"]:
                print(f"  lock {pair['lock']}: {pair['groups'][0]} and {pair['groups'][1]} may build at the same time")
        for i in info:
            print(f"info (done or deferred packages, left as they are): {i}")
        for p in problems:
            print(f"FAIL {p}")
        print(f"waves: {'pass' if not problems else 'fail'} ({len(problems)} problems)")
    return 1 if problems else 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check"); c.add_argument("--run", required=True); c.add_argument("--json", action="store_true")
    c.add_argument("--verbose", action="store_true", help="also list each pair of groups behind a lock warning")
    args = p.parse_args(argv)
    if getattr(args, "run", None):  # a bare run id resolves under .fyzxsflow/runs/
        sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
        from layout import resolve_run
        args.run = str(resolve_run(args.run))
    return cmd_check(args)


if __name__ == "__main__":
    sys.exit(main())

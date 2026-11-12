"""Parallel lanes: each work package of a wave builds in its own git worktree, then merges back in plan order.

  python -I .fyzxsflow/package/engine/lanes.py open --run <run> --wave <n>
      -> one line per lane opened: "lane <WP> <worktree path> <branch>"; "waiting <WP>" for packages beyond
         config.json -> build.max_parallel (open them after this batch merges); "in place <WP>" when the wave has a
         single package left (no lane: build it in the run's own checkout, as before); "done <WP>" for packages
         already built (`status: done`), which are never built again. Exit 1 if waves.py check fails or
         the run's checkout has uncommitted product changes (a lane would not see them).
  python -I .fyzxsflow/package/engine/lanes.py status --run <run>
  python -I .fyzxsflow/package/engine/lanes.py merge --run <run> --wave <n>
      -> merges every open lane of the wave into the run's branch, in plan order, one merge commit per package
         ("build(<run-id>): WP-nn"). A lane with uncommitted changes, or no commits, is skipped and named. A conflict
         is aborted and marked: that package re-runs in series on top of the merged branch. Exit 1 if any lane was
         skipped or conflicted.
  python -I .fyzxsflow/package/engine/lanes.py close --run <run> [--force]
      -> removes the worktrees of merged and conflicted lanes and deletes merged lane branches. An open lane with
         unmerged work stays unless --force.

Lanes live out of the working tree, in the git common directory (.git/fyzxsflow-lanes/<run-id>/<WP>), on
branches fyzxsflow-lanes/<run-id>/<WP> cut from the run's branch, which holds every earlier wave. Each lane is
committed by path from its agents' reports before it merges, like any product change. Run the Runner inside a lane
with `runner.py <mode> --run <the run folder> --root <lane path>`; Runner locks are shared across lanes and runs.
"""

import argparse
import json
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from layout import HOME  # noqa: E402
import waves as wmod  # noqa: E402


def git(cwd, *args) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)


def repo_root(run: pathlib.Path) -> pathlib.Path:
    for parent in run.resolve().parents:
        if parent.name == HOME:
            return parent.parent
    raise SystemExit(f"{run} is not inside a {HOME}/ folder")


def common_dir(root: pathlib.Path) -> pathlib.Path:
    out = git(root, "rev-parse", "--git-common-dir").stdout.strip()
    if not out:
        raise SystemExit(f"{root} is not a git repository: lanes need git worktrees")
    p = pathlib.Path(out)
    return (p if p.is_absolute() else root / p).resolve()


def lanes_dir(root: pathlib.Path, run: pathlib.Path) -> pathlib.Path:
    return common_dir(root) / "fyzxsflow-lanes" / run.resolve().name


def load(root, run) -> dict:
    p = lanes_dir(root, run) / "lanes.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def save(root, run, data: dict):
    d = lanes_dir(root, run)
    d.mkdir(parents=True, exist_ok=True)
    (d / "lanes.json").write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def dirty(cwd: pathlib.Path) -> list:
    """Uncommitted changes, ignoring the run folders (their ledger and reports are committed by run.py)."""
    out = git(cwd, "status", "--porcelain", "--untracked-files=all").stdout.splitlines()
    return [l[3:] for l in out if l.strip() and not l[3:].startswith(f"{HOME}/runs/")]


def cmd_open(args) -> int:
    run = pathlib.Path(args.run).resolve()
    root = repo_root(run)
    out, problems, _ = wmod.check(run)
    if problems:
        for p in problems:
            print(f"FAIL {p}")
        print("refused: fix the plan first (waves.py check)", file=sys.stderr)
        return 1
    if not 1 <= args.wave <= len(out):
        print(f"no wave {args.wave}: the plan has {len(out)}", file=sys.stderr)
        return 2
    done = {p["id"] for p in wmod.load(run) if p["done"]}
    for wp in out[args.wave - 1]:
        if wp in done:
            print(f"done {wp}")
    wave = [wp for wp in out[args.wave - 1] if wp not in done]
    if not wave:
        return 0
    if len(wave) == 1:
        print(f"in place {wave[0]}")
        return 0
    changes = dirty(root)
    if changes:
        print("refused: the run's checkout has uncommitted changes a lane would not see: " + ", ".join(changes[:5]),
              file=sys.stderr)
        return 1
    data = load(root, run)
    cap = wmod.max_parallel(run)
    open_now = [w for w in wave if data.get(w, {}).get("state") == "open"]
    for wp in open_now:
        print(f"lane {wp} {data[wp]['path']} {data[wp]['branch']} (already open)")
    slots = cap - len(open_now)
    for wp in wave:
        if wp in data:
            continue
        if slots <= 0:
            print(f"waiting {wp}")
            continue
        path = lanes_dir(root, run) / wp
        branch = f"fyzxsflow-lanes/{run.name}/{wp}"
        made = git(root, "worktree", "add", "-q", "-b", branch, str(path), "HEAD")
        if made.returncode:
            print(f"could not open a lane for {wp}: {made.stderr.strip()}", file=sys.stderr)
            return 1
        data[wp] = {"wave": args.wave, "path": str(path), "branch": branch, "state": "open",
                    "base": git(root, "rev-parse", "HEAD").stdout.strip()}
        save(root, run, data)
        slots -= 1
        print(f"lane {wp} {path} {branch}")
    return 0


def cmd_status(args) -> int:
    run = pathlib.Path(args.run).resolve()
    root = repo_root(run)
    data = load(root, run)
    if not data:
        print("no lanes")
    for wp, lane in data.items():
        ahead = git(root, "rev-list", "--count", f"{lane['base']}..{lane['branch']}").stdout.strip() or "?"
        print(f"{wp:8} wave {lane['wave']}  {lane['state']:8} {ahead} commit(s)  {lane['path']}")
    return 0


def cmd_merge(args) -> int:
    run = pathlib.Path(args.run).resolve()
    root = repo_root(run)
    data = load(root, run)
    out, _, _ = wmod.check(run)
    order = out[args.wave - 1] if 1 <= args.wave <= len(out) else []
    lanes = [wp for wp in order if data.get(wp, {}).get("state") == "open"]
    if not lanes:
        print(f"no open lanes in wave {args.wave}")
        return 0
    changes = dirty(root)
    if changes:
        print("refused: the run's checkout has uncommitted changes: " + ", ".join(changes[:5]), file=sys.stderr)
        return 1
    bad = False
    for wp in lanes:
        lane = data[wp]
        left = dirty(pathlib.Path(lane["path"]))
        if left:
            print(f"skipped {wp}: uncommitted in its lane: {', '.join(left[:5])} (commit them by path first)")
            bad = True
            continue
        if (git(root, "rev-list", "--count", f"{lane['base']}..{lane['branch']}").stdout.strip() or "0") == "0":
            print(f"skipped {wp}: nothing committed in its lane")
            bad = True
            continue
        m = git(root, "merge", "--no-ff", "--no-edit", "-m", f"build({run.name}): {wp}", lane["branch"])
        if m.returncode:
            git(root, "merge", "--abort")
            lane["state"] = "conflict"
            print(f"conflict {wp}: merge aborted; re-run {wp} in series on top of the merged branch, and log a "
                  "replan finding for the overlap the plan missed")
            bad = True
        else:
            lane["state"] = "merged"
            print(f"merged {wp}")
        save(root, run, data)
    return 1 if bad else 0


def cmd_close(args) -> int:
    run = pathlib.Path(args.run).resolve()
    root = repo_root(run)
    data = load(root, run)
    for wp, lane in data.items():
        if lane["state"] == "closed":
            continue
        if lane["state"] == "open" and not args.force:
            print(f"kept {wp}: still open (merge it, or --force to drop its work)")
            continue
        git(root, "worktree", "remove", "--force", lane["path"])
        git(root, "branch", "-d" if lane["state"] == "merged" else "-D", lane["branch"])
        lane["state"] = "closed"
        print(f"closed {wp}")
    git(root, "worktree", "prune")
    save(root, run, data)
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    o = sub.add_parser("open"); o.add_argument("--run", required=True); o.add_argument("--wave", type=int, required=True)
    s = sub.add_parser("status"); s.add_argument("--run", required=True)
    m = sub.add_parser("merge"); m.add_argument("--run", required=True); m.add_argument("--wave", type=int, required=True)
    c = sub.add_parser("close"); c.add_argument("--run", required=True); c.add_argument("--force", action="store_true")
    args = p.parse_args(argv)
    return {"open": cmd_open, "status": cmd_status, "merge": cmd_merge, "close": cmd_close}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())

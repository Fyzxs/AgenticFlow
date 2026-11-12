"""Lanes: each PR group builds in its own git worktree, and reaches the run branch through its own PR.

A PR group (`pr_group:` in its packages' frontmatter; by default one package) is one lane, one branch and one PR
into the run branch. A group starts as soon as every group it depends on is completed into the run branch; it never
waits for a wave or an unrelated group. The engine never completes, merges or auto-completes a PR: the owner does.

  python -I .fyzxsflow/package/engine/lanes.py open --run <run>
      -> first pulls the remote run branch into the local one (completed group PRs merge there), then one line per
         group not yet completed: "lane <group> <path> <branch> <packages>" for each lane opened now,
         "open <group> ..." for one already open, "queued <group>" when build.max_parallel lanes are already open,
         "waiting <group> on <groups>" while a group it depends on isn't completed. Exit 1 if waves.py check fails
         or the run's checkout has uncommitted product changes (a lane would not see them).
  python -I .fyzxsflow/package/engine/lanes.py pr --run <run> --group <g> [--publish]
      -> pushes the run branch (the PR's target) and the group's lane branch, and opens the group's PR into the run
         branch as a draft (or, when it exists, just pushes the new commits to it). --publish marks it ready for
         review: the Orchestrator's signal that the group is done (done-check green, reviews finished).
  python -I .fyzxsflow/package/engine/lanes.py refresh --run <run>
      -> reads each group PR's state from the host (draft, published, completed, abandoned), pulls the run branch,
         and says which groups can start now.
  python -I .fyzxsflow/package/engine/lanes.py status --run <run>
  python -I .fyzxsflow/package/engine/lanes.py merge --run <run> [--group <g>]
      -> without PRs (the `pr` step off, or no PR host): merges each open group whose dependencies are merged into
         the run branch locally, in plan order, one merge commit per group. A conflict is aborted and marked: the
         group re-runs on top of the merged branch. Exit 1 if any group was skipped or conflicted.
  python -I .fyzxsflow/package/engine/lanes.py close --run <run> [--force]
      -> removes the lanes of completed, abandoned, merged or conflicted groups. A lane whose PR is still open, or
         whose local work isn't merged, stays unless --force.

Lanes live out of the working tree, in the git common directory (.git/fyzxsflow-lanes/<run-id>/<group>), on branches
fyzxsflow-lanes/<run-id>/<group> cut from the run branch, which holds every completed group. Each lane is committed
by path from its agents' reports. Run the Runner inside a lane with `runner.py <mode> --run <the run folder>
--root <lane path>`; Runner locks are shared across lanes and runs. Hosts: GitHub (gh) and Azure DevOps (az repos),
from the remote's URL or the profile's `PR host:`.
"""

import argparse
import json
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from layout import HOME  # noqa: E402
import pr as prmod  # noqa: E402
import waves as wmod  # noqa: E402

OPEN_STATES = ("open", "draft", "published")
DONE_STATES = ("completed", "merged")


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


def run_branch(root: pathlib.Path) -> str:
    return git(root, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()


def has_remote(root) -> bool:
    return git(root, "remote", "get-url", "origin").returncode == 0


def pull(root: pathlib.Path) -> str:
    """Merge the remote run branch (where completed group PRs land) into the local one. Returns a note."""
    branch = run_branch(root)
    if not has_remote(root):
        return ""
    if git(root, "fetch", "-q", "origin", branch).returncode:
        return ""  # not pushed yet: nothing completed remotely
    behind = git(root, "rev-list", "--count", "HEAD..FETCH_HEAD").stdout.strip()
    if behind in ("", "0"):
        return ""
    merged = git(root, "merge", "--no-edit", "FETCH_HEAD")
    if merged.returncode:
        git(root, "merge", "--abort")
        raise SystemExit(f"could not merge origin/{branch} into the run branch: {merged.stdout.strip()[:200]}; "
                         "resolve it by hand, then run this again")
    return f"pulled {behind} commit(s) from origin/{branch}"


def completed(data: dict) -> set:
    return {g for g, lane in data.items() if lane["state"] in DONE_STATES}


def cmd_open(args) -> int:
    run = pathlib.Path(args.run).resolve()
    root = repo_root(run)
    _, problems, _, _ = wmod.check(run)
    if problems:
        for p in problems:
            print(f"FAIL {p}")
        print("refused: fix the plan first (waves.py check)", file=sys.stderr)
        return 1
    changes = dirty(root)
    if changes:
        print("refused: the run's checkout has uncommitted changes a lane would not see: " + ", ".join(changes[:5]),
              file=sys.stderr)
        return 1
    note = pull(root)
    if note:
        print(note)
    data = load(root, run)
    packages = wmod.load(run)
    members = wmod.groups(packages)
    slots = wmod.max_parallel(run) - sum(1 for lane in data.values() if lane["state"] in OPEN_STATES)
    for g, wait in wmod.waiting(packages, completed(data)):
        lane = data.get(g)
        if lane and lane["state"] in OPEN_STATES:
            print(f"open {g} {lane['path']} {lane['branch']} {','.join(members[g])}")
            continue
        if wait:
            print(f"waiting {g} on {', '.join(wait)}")
            continue
        if slots <= 0:
            print(f"queued {g}")
            continue
        path = lanes_dir(root, run) / g
        branch = f"fyzxsflow-lanes/{run.name}/{g}"
        if lane:  # a conflicted or abandoned lane: start it again from the current run branch
            git(root, "worktree", "remove", "--force", str(path))
            git(root, "branch", "-D", branch)
        made = git(root, "worktree", "add", "-q", "-b", branch, str(path), "HEAD")
        if made.returncode:
            print(f"could not open a lane for {g}: {made.stderr.strip()}", file=sys.stderr)
            return 1
        data[g] = {"path": str(path), "branch": branch, "state": "open", "packages": members[g],
                   "base": git(root, "rev-parse", "HEAD").stdout.strip(), "into": run_branch(root)}
        save(root, run, data)
        slots -= 1
        print(f"lane {g} {path} {branch} {','.join(members[g])}")
    return 0


def lane_or_exit(data: dict, group: str) -> dict:
    if group not in data:
        raise SystemExit(f"no lane for group {group}: lanes.py open opens it")
    return data[group]


def cmd_pr(args) -> int:
    run = pathlib.Path(args.run).resolve()
    root = repo_root(run)
    data = load(root, run)
    lane = lane_or_exit(data, args.group)
    path = pathlib.Path(lane["path"])
    left = dirty(path)
    if left:
        print(f"refused: uncommitted in the lane: {', '.join(left[:5])} (commit them by path first)", file=sys.stderr)
        return 1
    if (git(root, "rev-list", "--count", f"{lane['base']}..{lane['branch']}").stdout.strip() or "0") == "0":
        print("refused: nothing committed in the lane yet (the draft opens with its first commit)", file=sys.stderr)
        return 1
    for branch in (lane["into"], lane["branch"]):
        pushed = git(root, "push", "-q", "-u", "origin", branch)
        if pushed.returncode:
            print(f"push of {branch} failed: {pushed.stderr.strip()}", file=sys.stderr)
            return 1
    host = prmod.host(root)
    title = f"{args.group}: " + ", ".join(lane["packages"])
    if not lane.get("pr"):
        body = (f"Work package(s) {', '.join(lane['packages'])} of run `{run.name}`, into the run branch "
                f"`{lane['into']}`.\n\n> **Draft: in progress.** Published when its done-check is green and its "
                "reviews are finished. Completing it is the owner's call; the run branch then goes to the default "
                "branch in one roll-up PR.\n")
        if host == "github":
            out = prmod.call(["gh", "pr", "create", "--draft", "--base", lane["into"], "--head", lane["branch"],
                              "--title", title, "--body", body], root)
            url = out.stdout.strip().splitlines()[-1] if out.returncode == 0 and out.stdout.strip() else ""
            number = url.rstrip("/").rsplit("/", 1)[-1] if url else ""
        else:
            out = prmod.call(["az", "repos", "pr", "create", "--draft", "true", "--source-branch", lane["branch"],
                              "--target-branch", lane["into"], "--title", title, "--description", body,
                              "--output", "json"], root)
            info = json.loads(out.stdout) if out.returncode == 0 and out.stdout.strip().startswith("{") else {}
            number = str(info.get("pullRequestId", ""))
            url = info.get("url", "") or (f"pull request {number}" if number else "")
        if out.returncode or not number:
            print(f"could not open the group PR: {(out.stderr or out.stdout).strip()[:300]}", file=sys.stderr)
            return 1
        lane["pr"] = {"host": host, "number": number, "url": url}
        lane["state"] = "draft"
        print(f"draft {args.group} {url}")
    else:
        print(f"pushed {args.group} to {lane['pr']['url']}")
    if args.publish:
        n = lane["pr"]["number"]
        out = prmod.call(["gh", "pr", "ready", n], root) if lane["pr"]["host"] == "github" else \
            prmod.call(["az", "repos", "pr", "update", "--id", n, "--draft", "false"], root)
        if out.returncode:
            print(f"could not publish: {(out.stderr or out.stdout).strip()[:300]}", file=sys.stderr)
            save(root, run, data)
            return 1
        lane["state"] = "published"
        print(f"published {args.group} {lane['pr']['url']}")
    save(root, run, data)
    return 0


def pr_state(root, pr: dict) -> str:
    """draft | published | completed | abandoned, from the host ('' when it can't tell)."""
    if pr["host"] == "github":
        out = prmod.call(["gh", "pr", "view", pr["number"], "--json", "state,isDraft"], root)
        info = json.loads(out.stdout) if out.returncode == 0 and out.stdout.strip().startswith("{") else {}
        state = str(info.get("state", "")).upper()
        if state == "MERGED":
            return "completed"
        if state == "CLOSED":
            return "abandoned"
    else:
        out = prmod.call(["az", "repos", "pr", "show", "--id", pr["number"], "--output", "json"], root)
        info = json.loads(out.stdout) if out.returncode == 0 and out.stdout.strip().startswith("{") else {}
        state = str(info.get("status", "")).lower()
        if state == "completed":
            return "completed"
        if state == "abandoned":
            return "abandoned"
    if not info:
        return ""
    return "draft" if info.get("isDraft") else "published"


def report(run: pathlib.Path, data: dict):
    packages = wmod.load(run)
    for g, lane in data.items():
        link = f"  {lane['pr']['url']}" if lane.get("pr") else ""
        print(f"{g:24} {lane['state']:10} {','.join(lane['packages'])}{link}")
    left = wmod.waiting(packages, completed(data))
    can = [g for g, wait in left if not wait and (g not in data or data[g]["state"] in ("abandoned", "conflict"))]
    if can:
        print("can start: " + ", ".join(can))
    for g, wait in left:
        if wait:
            print(f"waiting {g} on {', '.join(wait)}")


def cmd_refresh(args) -> int:
    run = pathlib.Path(args.run).resolve()
    root = repo_root(run)
    data = load(root, run)
    for g, lane in data.items():
        if lane.get("pr") and lane["state"] in OPEN_STATES:
            st = pr_state(root, lane["pr"])
            if st and st != lane["state"]:
                print(f"{g}: {lane['state']} -> {st}")
                lane["state"] = st
    save(root, run, data)
    if not dirty(root):
        note = pull(root)
        if note:
            print(note)
    report(run, data)
    return 0


def cmd_status(args) -> int:
    run = pathlib.Path(args.run).resolve()
    data = load(repo_root(run), run)
    if not data:
        print("no lanes")
    report(run, data)
    return 0


def cmd_merge(args) -> int:
    run = pathlib.Path(args.run).resolve()
    root = repo_root(run)
    data = load(root, run)
    packages = wmod.load(run)
    if dirty(root):
        print("refused: the run's checkout has uncommitted changes: " + ", ".join(dirty(root)[:5]), file=sys.stderr)
        return 1
    bad = False
    for g in wmod.groups(packages):
        lane = data.get(g)
        if not lane or lane["state"] != "open" or (args.group and g != args.group):
            continue
        wait = dict(wmod.waiting(packages, completed(data))).get(g, [])
        if wait:
            print(f"skipped {g}: waiting on {', '.join(wait)}")
            continue
        left = dirty(pathlib.Path(lane["path"]))
        if left:
            print(f"skipped {g}: uncommitted in its lane: {', '.join(left[:5])} (commit them by path first)")
            bad = True
            continue
        if (git(root, "rev-list", "--count", f"{lane['base']}..{lane['branch']}").stdout.strip() or "0") == "0":
            print(f"skipped {g}: nothing committed in its lane")
            bad = True
            continue
        m = git(root, "merge", "--no-ff", "--no-edit", "-m", f"build({run.name}): {g}", lane["branch"])
        if m.returncode:
            git(root, "merge", "--abort")
            lane["state"] = "conflict"
            print(f"conflict {g}: merge aborted; lanes.py open starts it again on top of the merged branch; log a "
                  "replan finding for the overlap the plan missed")
            bad = True
        else:
            lane["state"] = "merged"
            print(f"merged {g}")
        save(root, run, data)
    return 1 if bad else 0


def cmd_close(args) -> int:
    run = pathlib.Path(args.run).resolve()
    root = repo_root(run)
    data = load(root, run)
    for g, lane in data.items():
        if lane.get("closed"):
            continue
        if lane["state"] in OPEN_STATES and not args.force:
            why = "its PR is still open" if lane.get("pr") else "its work isn't merged"
            print(f"kept {g}: {why} (--force drops it)")
            continue
        git(root, "worktree", "remove", "--force", lane["path"])
        git(root, "branch", "-D", lane["branch"])
        lane["closed"] = True
        print(f"closed {g} ({lane['state']})")
    git(root, "worktree", "prune")
    save(root, run, data)
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("open", "refresh", "status"):
        x = sub.add_parser(name); x.add_argument("--run", required=True)
    r = sub.add_parser("pr"); r.add_argument("--run", required=True); r.add_argument("--group", required=True)
    r.add_argument("--publish", action="store_true")
    m = sub.add_parser("merge"); m.add_argument("--run", required=True); m.add_argument("--group")
    c = sub.add_parser("close"); c.add_argument("--run", required=True); c.add_argument("--force", action="store_true")
    args = p.parse_args(argv)
    return {"open": cmd_open, "pr": cmd_pr, "refresh": cmd_refresh, "status": cmd_status, "merge": cmd_merge,
            "close": cmd_close}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())

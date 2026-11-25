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
  python -I .fyzxsflow/package/engine/lanes.py pr --run <run> --group <g> [--publish [--body-file <file>]]
      -> pushes the run branch (the PR's target) and the group's lane branch, and opens the group's PR into the run
         branch as a draft (or, when it exists, just pushes the new commits to it). The title is the package's own
         heading ("WP-45 — Blob storage adapter"); the link printed is the PR's web page. --publish marks it ready
         for review: the Orchestrator's signal that the group is done (done-check green, reviews finished). It
         first refuses while the lane would conflict with the run branch (run `sync`), or while the host reports
         conflicts, and it replaces the draft's "in progress" description with the given file (the group's report
         summary and evidence) or, without one, a ready-for-review description listing the packages.
  python -I .fyzxsflow/package/engine/lanes.py sync --run <run> --group <g>
      -> merges the run branch into the group's lane (the run folder's findings.jsonl, ledger.md and reviews.jsonl
         merge by the drivers below, never by hand). Says whether product files changed, so the done-check is run
         again. A product conflict is aborted and listed: resolve it in the lane.
  python -I .fyzxsflow/package/engine/lanes.py refresh --run <run>
      -> reads each group PR's state from the host (draft, published, completed, abandoned), pulls the run branch,
         says which groups can start now, and names every open lane that would conflict with the run branch as it
         is now (it moves under them).
  python -I .fyzxsflow/package/engine/lanes.py status --run <run>
  python -I .fyzxsflow/package/engine/lanes.py merge --run <run> [--group <g>]
      -> without PRs (the `pr` step off, or no PR host): merges each open group whose dependencies are merged into
         the run branch locally, in plan order, one merge commit per group. A conflict is aborted and marked: the
         group re-runs on top of the merged branch. Exit 1 if any group was skipped or conflicted.
  python -I .fyzxsflow/package/engine/lanes.py park --run <run> --group <g> --reason "<the owner's words>"
      -> the owner holds a group: its committed work is kept on the branch fyzxsflow-parked/<run-id>/<g> (pushed when
         there is a remote), only that lane's worktree is removed, and its packages get `status: deferred`, so
         waves.py sets them and their dependents aside. Commit the package files by path. Refuses uncommitted work.
  python -I .fyzxsflow/package/engine/lanes.py unpark --run <run> --group <g>
      -> gives the packages back their status; the next `open` reopens the lane from the parked branch.
  python -I .fyzxsflow/package/engine/lanes.py grant --run <run> --group <g> --path <p> [<p> ...]
      -> a granted scope-request: the lane may change these paths too. Each lane's record (lane_resolve.py: run,
         group, packages, owns = its packages' Scope paths, branch, into) lives in the lane's git directory; the
         hooks hold an implementer or tester in a lane to it.
  python -I .fyzxsflow/package/engine/lanes.py close --run <run> [--group <g>] [--force]
      -> removes the lanes of completed, abandoned, merged or conflicted groups (with --group, only that one). A lane
         whose PR is still open, or whose local work isn't merged, stays unless --force.
  python -I .fyzxsflow/package/engine/lanes.py move --run <run> --group <g> [--to <dir>]
      -> moves a lane's worktree (by default to where new lanes go) and records the new path; for lanes opened by
         0.3.x inside .git.

Lanes are sibling worktrees of the run's checkout, `<checkout>-<group>` beside it (a checkout at
~/src/shop-run gets ~/src/shop-run-WP-45), so the owner and their tools can open them like any folder. Their
branches are fyzxsflow-lanes/<run-id>/<group>, cut from the run branch, which holds every completed group. lanes.json
(each lane's path, branch, state and PR) stays in the git common directory, fyzxsflow-lanes/<run-id>/, where every
worktree finds it. Each lane is committed by path from its agents' reports. Run the Runner inside a lane with
`runner.py <mode> --run <the run folder> --root <lane path>`; Runner locks are shared across lanes and runs. Hosts:
GitHub (gh) and Azure DevOps (az repos), from the remote's URL or the profile's `PR host:`.

Opening a lane registers, in the repo's local git config (never a committed file), the merge drivers for the run
folder: findings.jsonl merges by finding id (findings.py merge-driver), ledger.md and reviews.jsonl by union. Finding
ids come from one counter shared by every worktree, so lanes never mint the same id.
"""

import argparse
import json
import pathlib
import re
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from layout import HOME  # noqa: E402
import pr as prmod  # noqa: E402
import waves as wmod  # noqa: E402
import lane_resolve  # noqa: E402

OPEN_STATES = ("open", "draft", "published")
DONE_STATES = ("completed", "merged")
DRIVER = "fyzxsflow-findings"
ATTRIBUTES = (f"{HOME}/runs/**/findings.jsonl merge={DRIVER}", f"{HOME}/runs/**/ledger.md merge=union",
              f"{HOME}/runs/**/reviews.jsonl merge=union")


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


def lane_path(root: pathlib.Path, group: str) -> pathlib.Path:
    """A sibling of the run's checkout: <checkout>-<group>."""
    return root.parent / f"{root.name}-{group}"


def load(root, run) -> dict:
    p = lanes_dir(root, run) / "lanes.json"
    data = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    try:  # a group named before 0.4.0 was lowercased; match it to the group as the plan now writes it
        names = list(wmod.groups(wmod.load(run)))
    except OSError:
        return data
    for g in names:
        if g not in data:
            old = next((k for k in data if k.lower() == g.lower() and k not in names), None)
            if old:
                data[g] = data.pop(old)
    return data


def register_drivers(root: pathlib.Path):
    """The run folder's merge drivers, in the repo's local config and info/attributes (shared by every worktree)."""
    engine = pathlib.Path(__file__).resolve().parent
    git(root, "config", f"merge.{DRIVER}.name", "FyzxsFlow findings.jsonl, merged by finding id")
    git(root, "config", f"merge.{DRIVER}.driver",
        f'"{sys.executable}" -I "{engine / "findings.py"}" merge-driver %O %A %B %P')
    attrs = common_dir(root) / "info" / "attributes"
    attrs.parent.mkdir(parents=True, exist_ok=True)
    have = attrs.read_text(encoding="utf-8").splitlines() if attrs.exists() else []
    missing = [a for a in ATTRIBUTES if a not in have]
    if missing:
        with open(attrs, "a", encoding="utf-8", newline="\n") as fh:
            if have and have[-1].strip():
                fh.write("\n")
            fh.write("\n".join(missing) + "\n")


def conflicts(root: pathlib.Path, ours: str, theirs: str) -> list:
    """Files that would conflict merging `theirs` into `ours`, nothing touched. The run folder's files with a merge
    driver (findings.jsonl, ledger.md, reviews.jsonl) never count: they merge by driver."""
    out = git(root, "merge-tree", "--write-tree", "--name-only", "--no-messages", ours, theirs)
    if out.returncode in (0, 1):  # git 2.38+
        files = [l for l in out.stdout.splitlines()[1:] if l.strip()] if out.returncode == 1 else []
    else:  # older git: the trivial merge-tree, whose conflicts show as markers under "changed in both"
        base = git(root, "merge-base", ours, theirs).stdout.strip()
        old = git(root, "merge-tree", base, ours, theirs).stdout if base else ""
        files, current = [], None
        for line in old.splitlines():
            if line == "changed in both" or line in ("added in both", "removed in local", "removed in remote"):
                current = "pending"
            elif current == "pending" and line.startswith("  our "):
                current = line.split()[-1]
            elif current and current != "pending" and line.startswith("+<<<<<<<") and current not in files:
                files.append(current)
    driven = {a.split()[0].rsplit("/", 1)[-1] for a in ATTRIBUTES}
    return [f for f in dict.fromkeys(files)
            if not (f.startswith(f"{HOME}/runs/") and f.rsplit("/", 1)[-1] in driven)]


def titles(run: pathlib.Path, ids: list) -> dict:
    """package id -> its heading ("WP-45 — Blob storage adapter"), from the package file."""
    out = {}
    for p in sorted((run / "work-packages").glob("*.md")):
        info = wmod.parse(p)
        if info["id"] in ids:
            m = re.search(r"^# (.+)$", p.read_text(encoding="utf-8"), re.M)
            out[info["id"]] = m.group(1).strip() if m else info["id"]
    return out


def pr_title(run: pathlib.Path, group: str, packages: list) -> str:
    named = titles(run, packages)
    if len(packages) == 1:
        return named.get(packages[0], packages[0])[:200]
    return (f"{group}: " + "; ".join(named.get(i, i) for i in packages))[:200]


def ready_body(run: pathlib.Path, lane: dict) -> str:
    named = titles(run, lane["packages"])
    lines = [f"Work package(s) of run `{run.name}`, into the run branch `{lane['into']}`.", "",
             "**Ready for review**: the done-check is green and the reviews are finished. Completing it is the "
             "owner's call; the run branch then goes to the default branch in one roll-up PR.", ""]
    lines += [f"- {named.get(i, i)}" for i in lane["packages"]]
    return "\n".join(lines) + "\n"


def save(root, run, data: dict):
    d = lanes_dir(root, run)
    d.mkdir(parents=True, exist_ok=True)
    (d / "lanes.json").write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def dirty(cwd: pathlib.Path) -> list:
    """Uncommitted changes, ignoring the run folders (their ledger and reports are committed by run.py)."""
    out = git(cwd, "status", "--porcelain", "--untracked-files=all").stdout.splitlines()
    return [l[3:] for l in out if l.strip() and not l[3:].startswith(f"{HOME}/runs/") and "__pycache__/" not in l]


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
    register_drivers(root)
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
        path = lane_path(root, g)
        branch = f"fyzxsflow-lanes/{run.name}/{g}"
        if lane and lane["state"] == "unparked":  # back from the owner's hold: reopen on its own work
            branch = lane["parked"]
            made = git(root, "worktree", "add", "-q", str(path), branch)
        else:
            if lane:  # a conflicted or abandoned lane: start it again from the current run branch
                git(root, "worktree", "remove", "--force", lane.get("path", str(path)))
                git(root, "branch", "-D", branch)
            if path.exists():
                print(f"could not open a lane for {g}: {path} already exists (move it, or lanes.py move the lane "
                      "that uses it)", file=sys.stderr)
                return 1
            made = git(root, "worktree", "add", "-q", "-b", branch, str(path), "HEAD")
        if made.returncode:
            print(f"could not open a lane for {g}: {made.stderr.strip()}", file=sys.stderr)
            return 1
        data[g] = {**({"pr": lane["pr"]} if lane and lane.get("pr") and lane["state"] == "unparked" else {}),
                   "path": str(path), "branch": branch, "state": "open", "packages": members[g],
                   "base": git(root, "rev-parse", "HEAD").stdout.strip(), "into": run_branch(root)}
        save(root, run, data)
        record_lane(path, run, g, members[g], packages, branch, run_branch(root))
        slots -= 1
        print(f"lane {g} {path} {branch} {','.join(members[g])}")
    return 0


def record_lane(path: pathlib.Path, run: pathlib.Path, group: str, ids: list, packages: list, branch: str,
                into: str, extra: list = ()):
    """The lane's record for hooks and repo guards (lane_resolve.py): what its packages may change."""
    owns = sorted({s for p in packages if p["id"] in ids for s in p["scope"]} | set(extra))
    lane_resolve.write(path, {"run": str(path / run.relative_to(repo_root(run))), "run_id": run.name, "group": group,
                              "packages": ids, "owns": owns, "branch": branch, "into": into})


def cmd_grant(args) -> int:
    """A granted scope-request: the lane may change these paths too (the Build Coordinator's call)."""
    run = pathlib.Path(args.run).resolve()
    root = repo_root(run)
    lane = lane_or_exit(load(root, run), args.group)
    info = lane_resolve.find(lane["path"]) or {}
    extra = sorted(set(info.get("owns") or []) | set(args.path))
    record_lane(pathlib.Path(lane["path"]), run, args.group, lane["packages"], wmod.load(run), lane["branch"],
                lane.get("into", ""), extra)
    print(f"granted {args.group}: {', '.join(args.path)}")
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
    title = pr_title(run, args.group, lane["packages"])
    if args.publish:
        clash = conflicts(root, lane["into"], lane["branch"])
        if clash:
            print(f"refused: {args.group} would conflict with the run branch in {', '.join(clash[:8])}: run "
                  f"lanes.py sync --group {args.group}, resolve, rerun the done-check, then publish", file=sys.stderr)
            return 1
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
            url = prmod.web_url(root, info, number)
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
        if pr_conflicted(root, lane["pr"]):
            print(f"refused: the host reports conflicts on {lane['pr']['url']}: run lanes.py sync --group "
                  f"{args.group}, resolve, rerun the done-check, then publish", file=sys.stderr)
            save(root, run, data)
            return 1
        body = pathlib.Path(args.body_file).read_text(encoding="utf-8") if args.body_file else ready_body(run, lane)
        if lane["pr"]["host"] == "github":
            edit = prmod.call(["gh", "pr", "edit", n, "--title", title, "--body", body], root)
        else:
            edit = prmod.call(["az", "repos", "pr", "update", "--id", n, "--title", title,
                               "--description", body[:4000]], root)
        if edit.returncode:
            print(f"could not update the description: {(edit.stderr or edit.stdout).strip()[:300]}", file=sys.stderr)
            save(root, run, data)
            return 1
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


def pr_conflicted(root, pr: dict) -> bool:
    """True when the host says the PR has merge conflicts (GitHub mergeable, Azure mergeStatus)."""
    if pr["host"] == "github":
        out = prmod.call(["gh", "pr", "view", pr["number"], "--json", "mergeable"], root)
        info = json.loads(out.stdout) if out.returncode == 0 and out.stdout.strip().startswith("{") else {}
        return str(info.get("mergeable", "")).upper() == "CONFLICTING"
    out = prmod.call(["az", "repos", "pr", "show", "--id", pr["number"], "--output", "json"], root)
    info = json.loads(out.stdout) if out.returncode == 0 and out.stdout.strip().startswith("{") else {}
    return str(info.get("mergeStatus", "")).lower() == "conflicts"


def report(run: pathlib.Path, data: dict):
    packages = wmod.load(run)
    for g, lane in data.items():
        link = f"  {lane['pr']['url']}" if lane.get("pr") else ""
        where = f"  {lane['path']}" if lane["state"] in OPEN_STATES and not lane.get("closed") else ""
        print(f"{g:24} {lane['state']:10} {','.join(lane['packages'])}{link}{where}")
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
    for g, lane in data.items():  # the run branch moves under open lanes
        if lane["state"] in OPEN_STATES and not lane.get("closed"):
            clash = conflicts(root, lane["into"], lane["branch"])
            if not clash and lane.get("pr") and pr_conflicted(root, lane["pr"]):
                clash = ["(the host reports conflicts)"]
            if clash:
                print(f"conflict {g}: would conflict with the run branch in {', '.join(clash[:8])}: "
                      f"lanes.py sync --group {g}")
    report(run, data)
    return 0


def cmd_sync(args) -> int:
    run = pathlib.Path(args.run).resolve()
    root = repo_root(run)
    data = load(root, run)
    lane = lane_or_exit(data, args.group)
    path = pathlib.Path(lane["path"])
    left = dirty(path)
    if left:
        print(f"refused: uncommitted in the lane: {', '.join(left[:5])} (commit them by path first)", file=sys.stderr)
        return 1
    register_drivers(root)
    before = git(path, "rev-parse", "HEAD").stdout.strip()
    m = git(path, "merge", "--no-edit", "-m", f"sync({run.name}): {lane['into']} into {args.group}", lane["into"])
    if m.returncode:
        clash = git(path, "diff", "--name-only", "--diff-filter=U").stdout.split()
        git(path, "merge", "--abort")
        print(f"conflict {args.group}: merge aborted; resolve in {path}: {', '.join(clash) or m.stdout.strip()[:200]}",
              file=sys.stderr)
        return 1
    changed = git(path, "diff", "--name-only", before, "HEAD").stdout.split()
    product = [f for f in changed if not f.startswith(f"{HOME}/")]
    if not changed:
        print(f"{args.group}: already up to date with {lane['into']}")
    elif product:
        print(f"synced {args.group}: {len(product)} product file(s) changed ({', '.join(product[:5])}): rerun the "
              "done-check before publishing")
    else:
        print(f"synced {args.group}: run-folder files only, no product change")
    return 0


def set_status(run: pathlib.Path, ids: list, status: str = None, restore: dict = None) -> dict:
    """Sets (or restores) the frontmatter status of the given packages. Returns id -> the status it had."""
    had = {}
    for p in sorted((run / "work-packages").glob("*.md")):
        info = wmod.parse(p)
        if info["id"] not in ids:
            continue
        text = p.read_text(encoding="utf-8")
        m = re.search(r"^status:[ \t]*([^\n#]*)", text, re.M)
        had[info["id"]] = m.group(1).strip() if m else ""
        new = (restore or {}).get(info["id"], status) or "planned"
        if m:
            text = text[:m.start()] + f"status: {new}" + text[m.end():]
        else:
            text = text.replace("---\n", f"---\nstatus: {new}\n", 1)
        p.write_text(text, encoding="utf-8", newline="\n")
    return had


def cmd_park(args) -> int:
    run = pathlib.Path(args.run).resolve()
    root = repo_root(run)
    data = load(root, run)
    lane = lane_or_exit(data, args.group)
    if lane["state"] not in OPEN_STATES or lane.get("closed"):
        print(f"refused: {args.group} is {lane['state']}, not an open lane", file=sys.stderr)
        return 1
    left = dirty(pathlib.Path(lane["path"]))
    if left:
        print(f"refused: uncommitted in the lane: {', '.join(left[:5])} (commit them by path first)", file=sys.stderr)
        return 1
    parked = f"fyzxsflow-parked/{run.name}/{args.group}"
    if git(root, "branch", "-f", parked, lane["branch"]).returncode:
        print(f"could not keep the work on {parked}", file=sys.stderr)
        return 1
    note = "kept locally"
    if has_remote(root):
        pushed = git(root, "push", "-q", "origin", f"{parked}:{parked}")
        note = "pushed" if pushed.returncode == 0 else f"kept locally (push failed: {pushed.stderr.strip()[:120]})"
    git(root, "worktree", "remove", "--force", lane["path"])
    git(root, "branch", "-D", lane["branch"])
    had = set_status(run, lane["packages"], "deferred")
    lane.update({"state": "parked", "parked": parked, "was": had, "reason": args.reason.strip()})
    save(root, run, data)
    files = [str(p.relative_to(root)) for p in sorted((run / "work-packages").glob("*.md"))
             if wmod.parse(p)["id"] in lane["packages"]]
    print(f"parked {args.group}: work on {parked} ({note}); {', '.join(lane['packages'])} now status: deferred. "
          f"Commit by path: {' '.join(files)}" + (f". Its PR stays open: {lane['pr']['url']}" if lane.get("pr") else ""))
    return 0


def cmd_unpark(args) -> int:
    run = pathlib.Path(args.run).resolve()
    root = repo_root(run)
    data = load(root, run)
    lane = lane_or_exit(data, args.group)
    if lane["state"] != "parked":
        print(f"refused: {args.group} is {lane['state']}, not parked", file=sys.stderr)
        return 1
    set_status(run, lane["packages"], restore=lane.get("was") or {})
    lane["state"] = "unparked"
    save(root, run, data)
    print(f"unparked {args.group}: lanes.py open reopens it from {lane['parked']}; commit the package files by path")
    return 0


def cmd_move(args) -> int:
    run = pathlib.Path(args.run).resolve()
    root = repo_root(run)
    data = load(root, run)
    lane = lane_or_exit(data, args.group)
    new = pathlib.Path(args.to).resolve() if args.to else lane_path(root, args.group)
    if pathlib.Path(lane["path"]).resolve() == new:
        print(f"{args.group} is already at {new}")
        return 0
    if new.exists():
        print(f"refused: {new} exists", file=sys.stderr)
        return 1
    moved = git(root, "worktree", "move", lane["path"], str(new))
    if moved.returncode:
        print(f"could not move {args.group}: {moved.stderr.strip()}", file=sys.stderr)
        return 1
    old, lane["path"] = lane["path"], str(new)
    save(root, run, data)
    print(f"moved {args.group}: {old} -> {new}")
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
    register_drivers(root)
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
        # Uncommitted files in the run checkout that the lane also changed (often the run's own ledger.md, which
        # `run.py log` appends to) make git refuse the merge: that is not an overlap between groups.
        local = {l[3:] for l in git(root, "status", "--porcelain", "--untracked-files=all").stdout.splitlines() if l.strip()}
        theirs = set(git(root, "diff", "--name-only", f"{lane['base']}..{lane['branch']}").stdout.split())
        blocked = sorted(local & theirs)
        if blocked:
            print(f"refused {g}: uncommitted here and changed in the lane: {', '.join(blocked[:5])}; commit the run "
                  "folder first (run.py checkpoint) and merge again")
            bad = True
            continue
        m = git(root, "merge", "--no-ff", "--no-edit", "-m", f"build({run.name}): {g}", lane["branch"])
        if m.returncode and "would be overwritten" in m.stderr + m.stdout:
            git(root, "merge", "--abort")
            print(f"refused {g}: local changes block the merge ({(m.stderr or m.stdout).strip().splitlines()[0]}); "
                  "commit them by path and merge again")
            bad = True
            continue
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
    if args.group:
        lane_or_exit(data, args.group)
    for g, lane in data.items():
        if lane.get("closed") or (args.group and g != args.group) or lane["state"] in ("parked", "unparked"):
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
    r.add_argument("--body-file", help="with --publish: the description (the group's report summary and evidence)")
    m = sub.add_parser("merge"); m.add_argument("--run", required=True); m.add_argument("--group")
    c = sub.add_parser("close"); c.add_argument("--run", required=True); c.add_argument("--group")
    c.add_argument("--force", action="store_true")
    gr = sub.add_parser("grant"); gr.add_argument("--run", required=True); gr.add_argument("--group", required=True)
    gr.add_argument("--path", nargs="+", required=True, help="paths (or folder/ or globs) the lane may now change")
    for name in ("sync", "unpark", "move", "park"):
        x = sub.add_parser(name); x.add_argument("--run", required=True); x.add_argument("--group", required=True)
        if name == "park":
            x.add_argument("--reason", required=True, help="the owner's words")
        if name == "move":
            x.add_argument("--to", help="the new folder (default: beside the run's checkout, <checkout>-<group>)")
    args = p.parse_args(argv)
    if getattr(args, "run", None):  # a bare run id resolves under .fyzxsflow/runs/
        sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
        from layout import resolve_run
        args.run = str(resolve_run(args.run))
    return {"open": cmd_open, "pr": cmd_pr, "refresh": cmd_refresh, "status": cmd_status, "merge": cmd_merge,
            "close": cmd_close, "grant": cmd_grant, "sync": cmd_sync, "park": cmd_park, "unpark": cmd_unpark, "move": cmd_move}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())

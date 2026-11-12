"""The run's pull request: a draft from the first product commit, ready for review only once the run ships.

  This is the run's roll-up PR: the run's own branch into the default branch. Every commit on it ships, run records
  included. With PR groups (engine/lanes.py) the work reaches the run branch through one PR per group, and this PR
  lists them.
  python -I .fyzxsflow/package/engine/pr.py push --run <run>
      -> pushes the run's branch.
  python -I .fyzxsflow/package/engine/pr.py draft --run <run>
      -> once the branch has a product commit (a file outside .fyzxsflow/): pushes it and opens the PR as a **draft**
         with a work-in-progress description (criteria and packages as checklists), recorded in <run>/pr.json.
  python -I .fyzxsflow/package/engine/pr.py update --run <run> [--body-file <file>]
      -> pushes the branch, then refreshes the description: the given file (the PR Producer's pr-description.md), or the
         work-in-progress description with the packages done so far ticked.
  python -I .fyzxsflow/package/engine/pr.py ready --run <run>
      -> marks the draft ready for review, only when `run.py ship-check <run>` says ready=yes (exit 1 otherwise,
         with its table): a published PR always means "pending final approval", never "still in progress".
  python -I .fyzxsflow/package/engine/pr.py status --run <run> | body --run <run>

Every command that pushes or calls the host is an external write: the Orchestrator runs it only when the profile
says `Opening a PR: pre-authorised` or the owner said yes for this run. The host comes from the remote's URL:
github.com -> `gh`, dev.azure.com / visualstudio.com -> `az repos`; `PR host: github | azure` in the profile's Pull
requests section overrides it. The target is the profile's `Target branch:`, else the run's base branch.
"""

import argparse
import json
import pathlib
import re
import shutil
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from layout import HOME, PACKAGE  # noqa: E402

def product_commits(root, since: str, branch: str) -> list:
    """Commits on the branch that touch a file outside .fyzxsflow/ (the run folder's checkpoints don't count)."""
    out = []
    for sha in git(root, "rev-list", "--reverse", f"{since}..{branch}").stdout.split():
        files = git(root, "show", "--name-only", "--format=", sha).stdout.split()
        if any(not f.startswith(f"{HOME}/") for f in files):
            out.append(sha)
    return out


def git(cwd, *args) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)


def repo_root(run: pathlib.Path) -> pathlib.Path:
    for parent in run.resolve().parents:
        if parent.name == HOME:
            return parent.parent
    raise SystemExit(f"{run} is not inside a {HOME}/ folder")


def front(path: pathlib.Path) -> dict:
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    m = re.match(r"\A---\n(.*?)\n---\n", text, re.S)
    out = {}
    for line in (m.group(1).splitlines() if m else []):
        if ":" in line:
            k, v = line.split(":", 1)
            out[k.strip()] = v.split("#", 1)[0].strip()
    return out


def profile(root: pathlib.Path) -> dict:
    p = root / HOME / "profile.md"
    text = p.read_text(encoding="utf-8") if p.exists() else ""

    def line(label):
        m = re.search(rf"^-\s*{re.escape(label)}:\s*(.+)$", text, re.M)
        return m.group(1).strip() if m else ""
    return {"target": line("Target branch"), "host": line("PR host").lower()}


def state_path(run: pathlib.Path) -> pathlib.Path:
    return run / "pr.json"


def load(run) -> dict:
    p = state_path(run)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def save(run, data: dict):
    state_path(run).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8", newline="\n")


def branches(run: pathlib.Path, root: pathlib.Path):
    meta, prof = front(run / "input.md"), profile(root)
    branch = meta.get("branch") or git(root, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    target = prof["target"] if prof["target"] and "UNRESOLVED" not in prof["target"] else meta.get("base_branch", "")
    if not target:
        raise SystemExit("no target branch: set 'Target branch:' under Pull requests in .fyzxsflow/profile.md")
    return branch, target, meta.get("base", "")


def push(run: pathlib.Path) -> int:
    root = repo_root(run)
    branch, target, _ = branches(run, root)
    pushed = git(root, "push", "-q", "-u", "origin", branch)
    if pushed.returncode:
        print(f"push failed: {pushed.stderr.strip()}", file=sys.stderr)
        return 1
    print(f"pushed {branch}")
    return 0


# ---------------------------------------------------------------- the host

def host(root: pathlib.Path) -> str:
    chosen = profile(root)["host"]
    if chosen in ("github", "azure"):
        return chosen
    url = git(root, "remote", "get-url", "origin").stdout.strip()
    if "github.com" in url:
        return "github"
    if "dev.azure.com" in url or "visualstudio.com" in url:
        return "azure"
    raise SystemExit(f"can't tell the PR host from the remote ({url or 'no origin'}): add 'PR host: github | azure' "
                     "under Pull requests in .fyzxsflow/profile.md")


def call(cmd: list, cwd) -> subprocess.CompletedProcess:
    if not shutil.which(cmd[0]):
        raise SystemExit(f"'{cmd[0]}' is not installed or not on PATH; it opens and updates the PR")
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)


def wip_body(run: pathlib.Path) -> str:
    brief = (run / "brief.md").read_text(encoding="utf-8") if (run / "brief.md").exists() else ""
    title = next((l[2:].strip() for l in brief.splitlines() if l.startswith("# ")), "") or \
        (run / "input.md").read_text(encoding="utf-8").split("---")[-1].strip().splitlines()[0]
    criteria = [re.sub(r"^\s*-\s*", "", l) for l in brief.splitlines() if re.match(r"^\s*-\s*\**AC-\d+", l)]
    packages = []
    for p in sorted((run / "work-packages").glob("*.md")):
        meta = front(p)
        packages.append(f"- [{'x' if meta.get('status') == 'done' else ' '}] {p.stem}")
    lines = [f"## {title}", "",
             "> **Draft: work in progress.** This PR is updated as each work package lands. FyzxsFlow marks it ready "
             "for review only when the run passes its ship check; the full description replaces this one then.", ""]
    groups = group_prs(run)
    if groups:
        lines += ["### Group PRs (into the run branch)", ""] + groups + [""]
    if packages:
        lines += ["### Work packages", ""] + packages + [""]
    if criteria:
        lines += ["### Acceptance criteria", ""] + [f"- [ ] {c}" for c in criteria] + [""]
    return "\n".join(lines)


def group_prs(run: pathlib.Path) -> list:
    """One line per PR group of the run (engine/lanes.py), with its link and state."""
    import lanes  # noqa: E402  (same folder; imported here because lanes imports this module)
    try:
        data = lanes.load(repo_root(run), run)
    except SystemExit:
        return []
    return [f"- {g} ({', '.join(lane['packages'])}): {lane['state']}"
            + (f", {lane['pr']['url']}" if lane.get("pr") else "") for g, lane in data.items()]


def title_of(run: pathlib.Path) -> str:
    body = wip_body(run)
    return body.splitlines()[0][3:].strip()[:120]


def write_body(run: pathlib.Path, body_file):
    if body_file:
        return pathlib.Path(body_file)
    import tempfile
    f = tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8")
    f.write(wip_body(run))
    f.close()
    return pathlib.Path(f.name)


def ship_ready(run: pathlib.Path):
    """(ok, ship-check output)."""
    check = subprocess.run([sys.executable, "-I", str(pathlib.Path(__file__).resolve().parent / "run.py"),
                            "ship-check", str(run)], capture_output=True, text=True)
    return check.returncode == 0, check.stdout.strip()


def cmd_push(args) -> int:
    return push(pathlib.Path(args.run))


def cmd_draft(args) -> int:
    run = pathlib.Path(args.run)
    root = repo_root(run)
    data = load(run)
    if data.get("url"):
        print(f"already open: {data['url']} ({data.get('state')})")
        return 0
    branch, target, base = branches(run, root)
    if not product_commits(root, base or target, branch):
        print("nothing to draft yet: no product commit on the run's branch (the draft opens with the first one)",
              file=sys.stderr)
        return 1
    code = push(run)
    if code:
        return code
    data = {"branch": branch, "target": target}
    body = write_body(run, None)
    h = host(root)
    if h == "github":
        out = call(["gh", "pr", "create", "--draft", "--base", data["target"], "--head", data["branch"],
                    "--title", title_of(run), "--body-file", str(body)], root)
        url = out.stdout.strip().splitlines()[-1] if out.returncode == 0 and out.stdout.strip() else ""
        number = url.rstrip("/").rsplit("/", 1)[-1] if url else ""
    else:
        out = call(["az", "repos", "pr", "create", "--draft", "true", "--source-branch", data["branch"],
                    "--target-branch", data["target"], "--title", title_of(run),
                    "--description", body.read_text(encoding="utf-8")[:4000], "--output", "json"], root)
        info = json.loads(out.stdout) if out.returncode == 0 and out.stdout.strip().startswith("{") else {}
        number = str(info.get("pullRequestId", ""))
        url = info.get("url", "") or (f"pull request {number}" if number else "")
    if out.returncode or not number:
        print(f"could not open the draft PR: {(out.stderr or out.stdout).strip()[:300]}", file=sys.stderr)
        return 1
    data.update({"host": h, "number": number, "url": url, "state": "draft"})
    save(run, data)
    print(f"draft {url}")
    return 0


def cmd_update(args) -> int:
    run = pathlib.Path(args.run)
    root = repo_root(run)
    data = load(run)
    if not data.get("number"):
        print("no PR yet: pr.py draft opens it", file=sys.stderr)
        return 1
    code = push(run)
    if code:
        return code
    body = write_body(run, args.body_file)
    if data["host"] == "github":
        out = call(["gh", "pr", "edit", data["number"], "--body-file", str(body)], root)
    else:
        out = call(["az", "repos", "pr", "update", "--id", data["number"],
                    "--description", body.read_text(encoding="utf-8")[:4000]], root)
    if out.returncode:
        print(f"could not update the PR: {(out.stderr or out.stdout).strip()[:300]}", file=sys.stderr)
        return 1
    print(f"updated {data['url']} ({data.get('state')})")
    return 0


def cmd_ready(args) -> int:
    run = pathlib.Path(args.run)
    root = repo_root(run)
    data = load(run)
    if not data.get("number"):
        print("no PR yet: pr.py draft opens it", file=sys.stderr)
        return 1
    ok, table = ship_ready(run)
    if not ok:
        print(table)
        print("refused: the PR stays a draft until ship-check says ready=yes", file=sys.stderr)
        return 1
    if data["host"] == "github":
        out = call(["gh", "pr", "ready", data["number"]], root)
    else:
        out = call(["az", "repos", "pr", "update", "--id", data["number"], "--draft", "false"], root)
    if out.returncode:
        print(f"could not mark the PR ready: {(out.stderr or out.stdout).strip()[:300]}", file=sys.stderr)
        return 1
    data["state"] = "ready"
    save(run, data)
    print(f"ready for review {data['url']}")
    return 0


def cmd_status(args) -> int:
    data = load(pathlib.Path(args.run))
    if not data.get("number"):
        print("no PR yet")
    else:
        print(f"{data['state']} {data['url']} branch {data['branch']} -> {data['target']}")
    return 0


def cmd_body(args) -> int:
    print(wip_body(pathlib.Path(args.run)), end="")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("push", "draft", "ready", "status", "body"):
        x = sub.add_parser(name); x.add_argument("--run", required=True)
    u = sub.add_parser("update"); u.add_argument("--run", required=True); u.add_argument("--body-file")
    args = p.parse_args(argv)
    return {"push": cmd_push, "draft": cmd_draft, "update": cmd_update, "ready": cmd_ready, "status": cmd_status,
            "body": cmd_body}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())

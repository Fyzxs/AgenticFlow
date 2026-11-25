"""Which lane a path is in, and what that lane may change. Shipped for FyzxsFlow's own hooks and for a repo's own
guard to import (no env var needed: a Copilot `task` subagent shares its parent's environment, so a per-process
variable can't name the lane).

  python -I .fyzxsflow/package/engine/lane_resolve.py <path>      -> the lane's JSON, or "none" (exit 1)

  import lane_resolve; info = lane_resolve.find(path); lane_resolve.owns(info, path) -> bool

lanes.py open writes the lane's record into the lane worktree's own git directory
(.git/worktrees/<name>/fyzxsflow-lane.json), never into the work tree, so it can't make a lane look dirty or be
committed:
  {"run": "<run folder in the lane>", "run_id": "...", "group": "...", "packages": ["WP-01", ...],
   "owns": ["src/a.py", "src/b/", "docs/spec/codes.md", ...], "branch": "...", "into": "<run branch>",
   "root": "<the lane's work tree>"}
`owns` is every path in the group's packages' ## Scope (create, change and derived lines); an entry ending in "/"
covers that folder, and * ? glob. The run folder (.fyzxsflow/runs/) is always writable. lanes.py grant adds paths
when the Build Coordinator grants a scope-request.
"""

import fnmatch
import json
import pathlib
import sys

RECORD = "fyzxsflow-lane.json"


def git_dir(worktree: pathlib.Path):
    """A linked worktree's private git directory (its .git is a file: "gitdir: <path>"); None for a main checkout."""
    dot = worktree / ".git"
    if not dot.is_file():
        return None
    line = dot.read_text(encoding="utf-8").strip()
    if not line.startswith("gitdir:"):
        return None
    d = pathlib.Path(line.split(":", 1)[1].strip())
    return d if d.is_absolute() else (worktree / d).resolve()


def find(path) -> dict:
    """The lane record for the worktree holding `path` (a file that may not exist yet), or None."""
    p = pathlib.Path(path).resolve()
    for d in (p, *p.parents):
        if (d / ".git").exists():
            g = git_dir(d)
            if g is None or not (g / RECORD).is_file():
                return None
            try:
                info = json.loads((g / RECORD).read_text(encoding="utf-8"))
            except ValueError:
                return None
            info["root"] = str(d)
            return info
    return None


def write(worktree: pathlib.Path, info: dict) -> pathlib.Path:
    g = git_dir(pathlib.Path(worktree))
    if g is None:
        raise SystemExit(f"{worktree} is not a linked worktree")
    f = g / RECORD
    f.write_text(json.dumps({k: v for k, v in info.items() if k != "root"}, indent=2) + "\n", encoding="utf-8")
    return f


def relative(info: dict, path) -> str:
    try:
        return pathlib.Path(path).resolve().relative_to(pathlib.Path(info["root"]).resolve()).as_posix()
    except ValueError:
        return ""


def owns(info: dict, path) -> bool:
    rel = relative(info, path)
    if not rel:
        return False  # outside the lane
    if rel.startswith(".fyzxsflow/runs/"):
        return True
    for entry in info.get("owns") or []:
        e = entry.strip().lstrip("./")
        if e.endswith("/") and rel.startswith(e):
            return True
        if rel == e.rstrip("/") or fnmatch.fnmatchcase(rel, e):
            return True
    return False


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    info = find(argv[0]) if argv else None
    print(json.dumps(info, indent=2) if info else "none")
    return 0 if info else 1


if __name__ == "__main__":
    sys.exit(main())

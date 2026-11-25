"""Preflight before a run's first stage: what would stop the flow mid-run, found before it starts.

  python -I .fyzxsflow/package/engine/doctor.py [--root .] [--skip-restore]
      -> one line per check, "ok", "warn" or "FAIL", then "doctor: ready" (exit 0) or "doctor: N problem(s)" (exit 1)

Checks (from a Copilot run that met each of these only mid-run):
  hooks      every repo hook outside FyzxsFlow (.github/hooks/*.json, .claude/settings.json) dry-run against the
             flow's own tool calls (git add / commit by path, git push of the run branch): one that denies them
             would stop the run at its first commit
  checkout   no uncommitted changes outside the run folders (lanes.py open refuses a dirty checkout)
  pr-host    the PR host's CLI is signed in (gh auth status; az account show + the azure-devops extension)
  docker     running, when a Runner mode in config.json uses it
  restore    `dotnet restore` reports no NuGet audit warning (NU190x) not listed in the profile's
             "- Audit exceptions: NU1902, ..." line (--skip-restore skips it)
  agents     .github/agents/*.agent.md: frontmatter Copilot can parse (a description with ": " quoted, no `tier`),
             each file within the size budget (layout.AGENT_BUDGET_KB)
  copilot    .github/hooks/fyzxsflow.json present and its scripts installed; the repo in Copilot's trustedFolders
             (warn: an untrusted folder skips repo hooks, and `copilot --resume` can't take --trust-folder, so every
             resumed session, the one after each owner pause, would run with no FyzxsFlow hook)
"""

import argparse
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from layout import AGENT_BUDGET_KB, HOME, PACKAGE  # noqa: E402
OURS = f"{HOME}/{PACKAGE}/engine/hooks/"
PROBES = ["git add src/app.py", 'git commit -m "build: WP-01" -- src/app.py', "git push -u origin fyzxsflow/doctor"]


def sh(cmd, cwd, timeout=60, env=None, stdin=None):
    try:
        return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout, env=env, input=stdin,
                              shell=isinstance(cmd, str))
    except (OSError, subprocess.SubprocessError) as e:
        return subprocess.CompletedProcess(cmd, 127, "", str(e))


def denied(p: subprocess.CompletedProcess) -> bool:
    if p.returncode == 2:
        return True
    try:
        out = json.loads(p.stdout or "{}")
    except ValueError:
        return False
    if not isinstance(out, dict):
        return False
    spec = out.get("hookSpecificOutput") or {}
    return "deny" in (out.get("permissionDecision"), spec.get("permissionDecision")) or out.get("decision") == "block"


def repo_hooks(root: pathlib.Path) -> list:
    """(source, event, matcher, command) for every pre-tool hook that isn't FyzxsFlow's."""
    found = []
    files = sorted((root / ".github" / "hooks").glob("*.json")) + [root / ".claude" / "settings.json"]
    for f in files:
        try:
            hooks = json.loads(f.read_text(encoding="utf-8")).get("hooks") or {}
        except (OSError, ValueError, AttributeError):
            continue
        for event, entries in hooks.items():
            if event not in ("preToolUse", "PreToolUse"):
                continue
            for e in entries or []:
                inner = e.get("hooks") if isinstance(e.get("hooks"), list) else [e]
                for h in inner:
                    cmd = h.get("command") or h.get("bash") or ""
                    if cmd and OURS not in cmd:
                        found.append((f.relative_to(root).as_posix(), event, e.get("matcher", ""), cmd))
    return found


def check_hooks(root):
    rows = []
    env = {**os.environ, "COPILOT_PROJECT_DIR": str(root), "CLAUDE_PROJECT_DIR": str(root)}
    for source, event, matcher, cmd in repo_hooks(root):
        tool = "Bash" if event == "PreToolUse" else "bash"
        if matcher and not re.fullmatch(matcher, tool):
            continue
        for probe in PROBES:
            payload = ({"tool_name": tool, "tool_input": {"command": probe}, "session_id": "doctor",
                        "hook_event_name": "PreToolUse", "cwd": str(root)} if event == "PreToolUse" else
                       {"toolName": tool, "toolArgs": json.dumps({"command": probe}), "sessionId": "doctor",
                        "cwd": str(root)})
            p = sh(cmd, root, timeout=30, env=env, stdin=json.dumps(payload))
            if denied(p):
                why = (p.stderr or p.stdout).strip().splitlines()[:1]
                rows.append(("FAIL", "hooks", f"{source} ({event}) denies the flow's own `{probe}`"
                             + (f": {why[0][:160]}" if why else "") + ". Change that hook to allow it before the run"))
    return rows or [("ok", "hooks", "no repo hook denies the flow's git add, commit or push")]


def check_checkout(root):
    out = sh(["git", "status", "--porcelain", "--untracked-files=all"], root).stdout.splitlines()
    dirty = [l[3:] for l in out if l.strip() and not l[3:].startswith(f"{HOME}/runs/") and "__pycache__/" not in l]
    if dirty:
        return [("FAIL", "checkout", "uncommitted changes (lanes.py open refuses them): " + ", ".join(dirty[:8])
                 + (f" and {len(dirty) - 8} more" if len(dirty) > 8 else ""))]
    return [("ok", "checkout", "clean")]


def check_pr_host(root):
    import pr as prmod
    try:
        host = prmod.host(root)
    except SystemExit as e:
        return [("warn", "pr-host", str(e))]
    if host == "github":
        p = sh(["gh", "auth", "status"], root)
        return [("ok" if p.returncode == 0 else "FAIL", "pr-host",
                 "gh signed in" if p.returncode == 0 else "gh isn't signed in: run `gh auth login`")]
    rows = []
    p = sh(["az", "account", "show"], root)
    rows.append(("ok" if p.returncode == 0 else "FAIL", "pr-host",
                 "az signed in" if p.returncode == 0 else "az isn't signed in: run `az login`"))
    p = sh(["az", "extension", "show", "--name", "azure-devops"], root)
    rows.append(("ok" if p.returncode == 0 else "FAIL", "pr-host",
                 "azure-devops extension present" if p.returncode == 0 else
                 "the azure-devops extension is missing: `az extension add --name azure-devops`"))
    return rows


def check_docker(root):
    cfg = root / HOME / "config.json"
    text = cfg.read_text(encoding="utf-8") if cfg.exists() else ""
    if not re.search(r"\bdocker\b", text):
        return []
    p = sh(["docker", "info"], root, timeout=30)
    return [("ok" if p.returncode == 0 else "FAIL", "docker",
             "running" if p.returncode == 0 else "a Runner mode uses Docker and it isn't running: start it")]


def check_restore(root, skip):
    projects = [p for p in list(root.glob("*.sln")) + list(root.glob("*.slnx")) + list(root.glob("*/*.csproj"))
                + list(root.glob("*/*/*.csproj"))]
    if not projects:
        return []
    if skip:
        return [("warn", "restore", "skipped (--skip-restore)")]
    if not shutil.which("dotnet"):
        return [("FAIL", "restore", "a .NET repo and no `dotnet` on PATH")]
    p = sh(["dotnet", "restore"], root, timeout=900)
    codes = sorted(set(re.findall(r"\bNU190\d\b", p.stdout + p.stderr)))
    prof = root / HOME / "profile.md"
    m = re.search(r"^-\s*Audit exceptions:\s*(.+)$", prof.read_text(encoding="utf-8") if prof.exists() else "", re.M)
    allowed = set(re.findall(r"NU\d{4}", m.group(1))) if m else set()
    bad = [c for c in codes if c not in allowed]
    if p.returncode and not codes:
        return [("FAIL", "restore", f"dotnet restore failed: {(p.stdout + p.stderr).strip().splitlines()[-1:]}")]
    if bad:
        return [("FAIL", "restore", f"NuGet audit: {', '.join(bad)} (fix the package, or list it under the profile's "
                 f"'- Audit exceptions:' with the owner's reason)")]
    return [("ok", "restore", "no NuGet audit warnings" + (f" outside the exceptions ({', '.join(codes)})" if codes else ""))]


def check_agents(root):
    rows = []
    for f in sorted((root / ".github" / "agents").glob("*.agent.md")):
        text = f.read_text(encoding="utf-8")
        m = re.match(r"\A---\n(.*?)\n---\n", text, re.S)
        if not m:
            rows.append(("FAIL", "agents", f"{f.name}: no frontmatter"))
            continue
        for line in m.group(1).splitlines():
            if line.startswith("tier:"):
                rows.append(("FAIL", "agents", f"{f.name}: `tier` (Copilot ignores it): reinstall"))
            if line.startswith("description:"):
                value = line.split(":", 1)[1].strip()
                if ": " in value and not value.startswith(('"', "'")):
                    rows.append(("FAIL", "agents", f"{f.name}: unquoted description with ': ' (Copilot drops the "
                                 f"agent): reinstall"))
        size = len(text.encode("utf-8")) / 1024
        if size > AGENT_BUDGET_KB:
            rows.append(("FAIL", "agents", f"{f.name}: {size:.1f} KB, over the {AGENT_BUDGET_KB} KB budget (the "
                         f"Curator's learned entries for it need compacting: /fyzxsflow-compact)"))
    if not rows and (root / ".github" / "agents").is_dir():
        rows.append(("ok", "agents", "frontmatter valid, every file within budget"))
    return rows


def check_copilot(root):
    f = root / ".github" / "hooks" / "fyzxsflow.json"
    if not (root / ".github" / "agents").is_dir():
        return []
    if not f.exists():
        return [("FAIL", "copilot", ".github/hooks/fyzxsflow.json is missing: reinstall with --host copilot")]
    missing = [s for s in re.findall(rf"{re.escape(OURS)}[\w.]+\.py", f.read_text(encoding="utf-8"))
               if not (root / s).exists()]
    if missing:
        return [("FAIL", "copilot", f"hook scripts missing: {', '.join(sorted(set(missing)))}: reinstall")]
    return [("ok", "copilot", "repo hooks installed")] + check_trusted(root)


def trusted_folders() -> list:
    home = pathlib.Path(os.environ.get("COPILOT_HOME") or pathlib.Path.home() / ".copilot")
    try:  # config.json starts with // comment lines
        text = "\n".join(l for l in (home / "config.json").read_text(encoding="utf-8").splitlines()
                         if not l.lstrip().startswith("//"))
        folders = json.loads(text).get("trustedFolders") or []
    except (OSError, ValueError, AttributeError):
        return []
    return [pathlib.Path(f).expanduser().resolve() for f in folders if isinstance(f, str)]


def check_trusted(root):
    if any(root == f or f in root.parents for f in trusted_folders()):
        return [("ok", "copilot", "folder trusted: repo hooks run in resumed sessions too")]
    return [("warn", "copilot", f"{root} isn't in Copilot's trustedFolders: an untrusted folder skips the repo hooks, "
             "and `copilot --resume` (each reply after an owner pause) can't take --trust-folder, so those sessions run "
             "with no FyzxsFlow hook. Start copilot here once and answer \"Yes, and remember this folder\"")]


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--root", default=".")
    p.add_argument("--skip-restore", action="store_true")
    args = p.parse_args(argv)
    root = pathlib.Path(args.root).resolve()
    rows = (check_hooks(root) + check_checkout(root) + check_pr_host(root) + check_docker(root)
            + check_restore(root, args.skip_restore) + check_agents(root) + check_copilot(root))
    for level, name, detail in rows:
        print(f"{level:4}  {name:9} {detail}")
    fails = sum(1 for r in rows if r[0] == "FAIL")
    print("doctor: ready" if not fails else f"doctor: {fails} problem(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())

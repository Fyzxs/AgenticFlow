"""Install FyzxsFlow into a repo, or re-sync host files from the repo's installed copy.

From the FyzxsFlow source repo:
  python -I engine/install.py --target <repo> --host claude [--host copilot]
Inside a repo where FyzxsFlow is installed (after the Curator edits .fyzxsflow/learned/*):
  python -I .fyzxsflow/package/engine/install.py --sync --target . --host claude

Installed layout (engine/layout.py):
  .fyzxsflow/                the project's own files; an install never overwrites them
    config.json profile.md gates.json feature-flags.md docs/ feedback/ runs/ baselines/
    learned/<agent>.md       the Curator's Learned entries for this project, one file per agent
  .fyzxsflow/package/        installer-owned: deleted and rewritten by every install; never edit it
    engine/ (no tests)  agents/  context/  templates/  skills/  instructions/  prompts/  INSTALLED.json
Host files generated from it (each agent = package/agents/<a>.agent.md + its learned/<a>.md entries):
  claude:  .claude/agents/<name>.md, .claude/rules/fyzxsflow-working-agreement.md,
           .claude/commands/<prompt>.md, kill-by-name hook merged into .claude/settings.json
  copilot: .github/agents/<name>.agent.md, .github/instructions/fyzxsflow-working-agreement.instructions.md,
           .github/prompts/<prompt>.prompt.md

Migration: a repo with the earlier `.agentflow/` folder is moved to this layout on install: project files move
to .fyzxsflow/, Learned entries move out of the agent files into learned/, the old package and host files are
removed, and paths in the moved project docs are rewritten. It refuses while a run is active (finish or
abandon it first), and never touches git: review the result and stage it by path.
"""

import argparse
import json
import pathlib
import re
import shutil
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from layout import HOME, LEARNED, LEGACY_HOMES, NAME, PACKAGE  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent
VERSION = "0.2.0"
HOOK_CMD = f'python -I "$CLAUDE_PROJECT_DIR/{HOME}/{PACKAGE}/engine/hooks/block_kill_by_name.py"'
LEARNED_HEADING = re.compile(r"^## Learned\s*$", re.M)
PACKAGE_PARTS = ("engine", "agents", "context", "templates", "skills", "instructions", "prompts", "INSTALLED.json")
ADHOC_COMMENT = f"# {HOME[1:]}: ad-hoc runner/gate output outside a run"
ADHOC_LINE = f"{HOME}/runs/_adhoc/"


def split_frontmatter(text: str):
    m = re.match(r"\A---\n(.*?)\n---\n", text, re.S)
    if not m:
        return {}, text
    fm = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            fm[k.strip()] = v.strip()
    return fm, text[m.end():]


def copy_tree(src: pathlib.Path, dst: pathlib.Path, skip=("tests", "__pycache__")):
    for path in src.rglob("*"):
        rel = path.relative_to(src)
        if any(part in skip for part in rel.parts) or path.is_dir():
            continue
        target = dst / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)


def write(path: pathlib.Path, text: str, written: list):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists() or path.read_text(encoding="utf-8") != text:
        path.write_text(text, encoding="utf-8", newline="\n")
        written.append(path)


def source_commit(source: pathlib.Path) -> str:
    proc = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=source, capture_output=True, text=True)
    return proc.stdout.strip() if proc.returncode == 0 else "unknown"


def install_package(source: pathlib.Path, target: pathlib.Path, written: list):
    pkg = target / HOME / PACKAGE
    if pkg.exists():
        shutil.rmtree(pkg)  # installer-owned: files dropped upstream must not linger
    copy_tree(source / "engine", pkg / "engine")
    for name in ("agents", "context", "skills", "instructions", "prompts"):
        copy_tree(source / ".apm" / name, pkg / name)
    copy_tree(source / "templates", pkg / "templates")
    write(pkg / "INSTALLED.json",
          json.dumps({HOME[1:]: VERSION, "source": source_commit(source)}, indent=2) + "\n", written)
    written.append(pkg)
    ensure_gitignore(target, written)
    ensure_feedback_inbox(source, target, written)


def ensure_feedback_inbox(source: pathlib.Path, target: pathlib.Path, written: list):
    """The owner's feedback inbox. Created once with its guide; the owner's items are never touched."""
    readme = target / HOME / "feedback" / "README.md"
    if not readme.exists():
        tpl = source / "templates" / "project" / HOME / "feedback" / "README.md"
        write(readme, tpl.read_text(encoding="utf-8"), written)


def ensure_gitignore(target: pathlib.Path, written: list):
    """Ad-hoc Runner/gate invocations outside a run are scratch; runs themselves are kept (profile Runs: commit)."""
    gi = target / ".gitignore"
    text = gi.read_text(encoding="utf-8") if gi.exists() else ""
    lines = [l.strip() for l in text.splitlines()]
    if ADHOC_LINE not in lines:
        text = text.rstrip("\n") + ("\n\n" if text else "") + f"{ADHOC_COMMENT}\n{ADHOC_LINE}\n"
        gi.write_text(text, encoding="utf-8", newline="\n")
        written.append(gi)
    if any(l in (f"{HOME}/runs/", f"{HOME}/runs", f"{HOME}/runs/*") for l in lines):
        print(f"warning: .gitignore ignores {HOME}/runs/, so runs are not kept; remove that line unless the "
              "profile says Runs: local")


def learned_entries(path: pathlib.Path) -> str:
    """A learned/<agent>.md file's entries: everything but its title line and HTML comments."""
    if not path.exists():
        return ""
    text = re.sub(r"<!--.*?-->", "", path.read_text(encoding="utf-8"), flags=re.S)
    text = re.sub(r"\A\s*# .*\n", "", text)
    return text.strip()


def learned_file(agent: str, entries: str) -> str:
    return (f"# Learned: {agent}\n<!-- Maintained by the Curator for this project. Each entry: the rule, evidence "
            f"(run/finding ids), hits, date added.\n     install.py adds these entries to the {agent} host files; "
            f"run `python -I {HOME}/{PACKAGE}/engine/install.py --sync --target . --host <host>` after editing. -->\n\n"
            f"{entries.strip()}\n")


def with_learned(agent_text: str, entries: str) -> str:
    if not entries:
        return agent_text
    return agent_text.rstrip("\n") + "\n\n" + entries + "\n"


def with_model(text: str, model: str) -> str:
    """Set (or clear) the host `model:` frontmatter line from the agent's tier; '' means inherit."""
    m = re.match(r"\A---\n(.*?)\n---\n", text, re.S)
    if not m:
        return text
    lines = [l for l in m.group(1).splitlines() if not l.startswith("model:")]
    if model:
        anchor = next((i for i, l in enumerate(lines) if l.startswith("tier:")),
                      next((i for i, l in enumerate(lines) if l.startswith("name:")), 0))
        lines.insert(anchor + 1, f"model: {model}")
    return "---\n" + "\n".join(lines) + "\n---\n" + text[m.end():]


def sync_hosts(target: pathlib.Path, hosts: list, written: list):
    sys.path.insert(0, str(target / HOME / PACKAGE / "engine"))
    import models  # noqa: E402  (the installed copy, so --sync uses the project's own engine)
    pkg = target / HOME / PACKAGE
    agents = sorted((pkg / "agents").glob("*.agent.md"))
    agreement = (pkg / "instructions" / "working-agreement.instructions.md").read_text(encoding="utf-8")
    _, agreement_body = split_frontmatter(agreement)
    prompts = sorted((pkg / "prompts").glob("*.prompt.md"))
    prefix = HOME[1:]
    for host in hosts:
        mapping = models.model_map(target, host)

        def hosted(a: pathlib.Path) -> str:
            text = a.read_text(encoding="utf-8")
            _, model, _ = models.resolve(models.tier_of(text), mapping)
            entries = learned_entries(target / HOME / LEARNED / a.name.replace(".agent.md", ".md"))
            return with_model(with_learned(text, entries), model)

        if host == "claude":
            for a in agents:
                write(target / ".claude" / "agents" / a.name.replace(".agent.md", ".md"), hosted(a), written)
            write(target / ".claude" / "rules" / f"{prefix}-working-agreement.md",
                  f"<!-- generated by {prefix} install.py from {HOME}/{PACKAGE}/instructions; do not edit -->\n"
                  + agreement_body, written)
            for p in prompts:
                fm, body = split_frontmatter(p.read_text(encoding="utf-8"))
                text = f"---\ndescription: {fm.get('description', '')}\n---\n{body.rstrip()}\n\nRequest: $ARGUMENTS\n"
                write(target / ".claude" / "commands" / p.name.replace(".prompt.md", ".md"), text, written)
            merge_claude_hook(target / ".claude" / "settings.json", written)
        elif host == "copilot":
            for a in agents:
                write(target / ".github" / "agents" / a.name, hosted(a), written)
            write(target / ".github" / "instructions" / f"{prefix}-working-agreement.instructions.md",
                  f'---\napplyTo: "**"\ndescription: "{NAME} working agreement"\n---\n' + agreement_body, written)
            for p in prompts:
                write(target / ".github" / "prompts" / p.name, p.read_text(encoding="utf-8"), written)
        else:
            raise SystemExit(f"unknown host '{host}' (claude, copilot)")


def merge_claude_hook(settings: pathlib.Path, written: list):
    data = json.loads(settings.read_text(encoding="utf-8")) if settings.exists() else {}
    pre = data.setdefault("hooks", {}).setdefault("PreToolUse", [])
    for entry in pre:
        for h in entry.get("hooks", []):
            if h.get("command") == HOOK_CMD:
                return
    pre.append({"matcher": "Bash|PowerShell", "hooks": [{"type": "command", "command": HOOK_CMD}]})
    write(settings, json.dumps(data, indent=2) + "\n", written)


# ---------------------------------------------------------------- migration from an earlier folder name

def legacy_path_rules(old: str):
    o = re.escape(old)
    parts = "|".join(p for p in PACKAGE_PARTS if p != "INSTALLED.json")
    return [
        (rf"{o}/({parts})\b", rf"{HOME}/{PACKAGE}/\1"),
        (rf"{o}/INSTALLED\.json", f"{HOME}/{PACKAGE}/INSTALLED.json"),
        (rf"{o}\b", HOME),
        (rf"(?<=/){re.escape(old[1:])}-", f"{HOME[1:]}-"),  # generated rule/instruction file names
    ]


def migrate_legacy(target: pathlib.Path, written: list, migrated: list) -> int:
    """Move an earlier `.agentflow/` install to the current layout (names appended to migrated). Returns an exit code."""
    new = target / HOME
    for old_name in LEGACY_HOMES:
        old = target / old_name
        if not old.is_dir():
            continue
        if new.exists():
            print(f"both {old_name}/ and {HOME}/ exist; move what you need from {old_name}/ by hand", file=sys.stderr)
            return 2
        active = [p.name for p in (old / "runs" / "active").glob("*") if p.is_dir()]
        if active:
            print(f"{old_name}/ has an active run ({', '.join(active)}); finish or abandon it before migrating, "
                  f"so no run changes layout halfway", file=sys.stderr)
            return 2
        new.mkdir()
        # Learned entries: whatever the project added under each agent's ## Learned heading
        for agent in sorted((old / "agents").glob("*.agent.md")):
            text = agent.read_text(encoding="utf-8")
            m = LEARNED_HEADING.search(text)
            entries = re.sub(r"<!--.*?-->", "", text[m.end():], flags=re.S).strip() if m else ""
            if entries:
                name = agent.name.replace(".agent.md", "")
                write(new / LEARNED / f"{name}.md", learned_file(name, entries), written)
        # project files move; the old package is dropped
        for entry in sorted(old.iterdir()):
            if entry.name in PACKAGE_PARTS or entry.name == "__pycache__":
                shutil.rmtree(entry) if entry.is_dir() else entry.unlink()
            else:
                shutil.move(str(entry), str(new / entry.name))
        old.rmdir()
        # paths inside the moved project docs (runs keep their history as written)
        rules = legacy_path_rules(old_name)
        for f in sorted(new.rglob("*")):
            if not f.is_file() or f.suffix not in (".md", ".json") or "runs" in f.relative_to(new).parts[:1]:
                continue
            s = f.read_text(encoding="utf-8")
            t = s
            for a, b in rules:
                t = re.sub(a, b, t)
            if t != s:
                f.write_text(t, encoding="utf-8", newline="\n")
                written.append(f)
        remove_legacy_host_files(target, old_name, written)
        migrate_gitignore(target, old_name, written)
        print(f"migrated {old_name}/ -> {HOME}/ (project files) + {HOME}/{PACKAGE}/ (package)")
        migrated.append(old_name)
    return 0


def remove_legacy_host_files(target: pathlib.Path, old_name: str, written: list):
    prefix = old_name[1:]
    for folder, glob in ((".claude/rules", f"{prefix}-*.md"), (".github/instructions", f"{prefix}-*.instructions.md")):
        for f in sorted((target / folder).glob(glob)) if (target / folder).is_dir() else []:
            if f"generated by {prefix}" in f.read_text(encoding="utf-8"):
                f.unlink()
                written.append(f)
    for f in (target / ".claude" / "commands" / f"{prefix}-init.md",
              target / ".github" / "prompts" / f"{prefix}-init.prompt.md"):
        if f.exists():
            f.unlink()
            written.append(f)
    settings = target / ".claude" / "settings.json"
    if settings.exists():
        data = json.loads(settings.read_text(encoding="utf-8"))
        pre = data.get("hooks", {}).get("PreToolUse", [])
        kept = [e for e in pre if not any(f"/{old_name}/engine/hooks/" in h.get("command", "")
                                          for h in e.get("hooks", []))]
        if len(kept) != len(pre):
            data["hooks"]["PreToolUse"] = kept
            write(settings, json.dumps(data, indent=2) + "\n", written)


def migrate_gitignore(target: pathlib.Path, old_name: str, written: list):
    gi = target / ".gitignore"
    if not gi.exists():
        return
    s = gi.read_text(encoding="utf-8")
    t = s.replace(f"# {old_name[1:]}: ad-hoc runner/gate output outside a run", ADHOC_COMMENT)
    t = t.replace(f"{old_name}/", f"{HOME}/")
    if t != s:
        gi.write_text(t, encoding="utf-8", newline="\n")
        written.append(gi)


def report_outside_mentions(target: pathlib.Path, old_name: str):
    proc = subprocess.run(["git", "grep", "-l", "-F", f"{old_name}/", "--", ".", f":(exclude){HOME}/runs"],
                          cwd=target, capture_output=True, text=True)
    files = [f for f in proc.stdout.splitlines() if f and not f.startswith(f"{old_name}/")]
    if files:
        print(f"note: these tracked files still mention {old_name}/ (yours to update; not changed):")
        for f in files[:20]:
            print(f"  {f}")


def write_pointers(target: pathlib.Path):
    if (target / HOME / "docs" / "segments").is_dir():
        import pointers  # noqa: E402  (same engine folder)
        pointers.main(["--root", str(target)])


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--target", required=True)
    p.add_argument("--host", action="append", required=True, choices=["claude", "copilot"])
    p.add_argument("--sync", action="store_true", help=f"only regenerate host files from {HOME}/")
    args = p.parse_args(argv)
    target = pathlib.Path(args.target).resolve()
    written, migrated = [], []
    if not args.sync:
        source = HERE.parent
        if not (source / ".apm" / "agents").is_dir():
            print(f"run without --sync from the {NAME} source repo (engine/install.py)", file=sys.stderr)
            return 2
        code = migrate_legacy(target, written, migrated)
        if code:
            return code
        install_package(source, target, written)
    elif not (target / HOME / PACKAGE / "agents").is_dir():
        print(f"{NAME} is not installed in {target}", file=sys.stderr)
        return 2
    sync_hosts(target, args.host, written)
    if not args.sync:
        write_pointers(target)  # segment pointers follow the installed names (fyzxsflow-<segment>)
    for old_name in migrated:
        report_outside_mentions(target, old_name)  # after host files are regenerated
    for w in written:
        print("wrote", w.relative_to(target).as_posix() + ("/" if w.is_dir() else ""))
    print(f"{NAME} {VERSION}: {len(written)} files written for {', '.join(args.host)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

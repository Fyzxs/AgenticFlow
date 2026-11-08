"""Install agentflow into a repo, or re-sync host files from the repo's installed copy.

From the agentflow source repo:
  python -I engine/install.py --target <repo> --host claude [--host copilot]
Inside a repo where agentflow is installed (after the Curator edits .agentflow/agents/*):
  python -I .agentflow/engine/install.py --sync --target . --host claude

Installed layout (host-neutral, the single source inside the repo):
  .agentflow/engine/      scripts (no tests)            .agentflow/context/    shared fragments
  .agentflow/agents/      canonical agent files          .agentflow/templates/  project + run templates
  .agentflow/skills/      skills                         .agentflow/INSTALLED.json
Host files generated from it:
  claude:  .claude/agents/<name>.md, .claude/rules/agentflow-working-agreement.md,
           .claude/commands/<prompt>.md, kill-by-name hook merged into .claude/settings.json
  copilot: .github/agents/<name>.agent.md, .github/instructions/agentflow-working-agreement.instructions.md,
           .github/prompts/<prompt>.prompt.md
Re-installing preserves each agent's Learned section in .agentflow/agents/. Project files written by the
Cartographer (.agentflow/profile.md, config.json, docs/, ...) are never touched.
"""

import argparse
import json
import pathlib
import re
import shutil
import sys

HERE = pathlib.Path(__file__).resolve().parent
VERSION = "0.1.0"
HOOK_CMD = 'python -I "$CLAUDE_PROJECT_DIR/.agentflow/engine/hooks/block_kill_by_name.py"'
LEARNED = re.compile(r"^## Learned\s*$", re.M)


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


def preserve_learned(new_text: str, old_text: str) -> str:
    """Keep the Learned section from the existing copy when re-installing."""
    old = LEARNED.search(old_text)
    new = LEARNED.search(new_text)
    if not old or not new:
        return new_text
    return new_text[:new.start()] + old_text[old.start():]


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


def install_package(source: pathlib.Path, target: pathlib.Path, written: list):
    af = target / ".agentflow"
    copy_tree(source / "engine", af / "engine")
    copy_tree(source / ".apm" / "context", af / "context")
    copy_tree(source / ".apm" / "skills", af / "skills")
    copy_tree(source / "templates", af / "templates")
    for name in ("instructions", "prompts"):
        copy_tree(source / ".apm" / name, af / name)
    for agent in sorted((source / ".apm" / "agents").glob("*.agent.md")):
        new = agent.read_text(encoding="utf-8")
        dest = af / "agents" / agent.name
        if dest.exists():
            new = preserve_learned(new, dest.read_text(encoding="utf-8"))
        write(dest, new, written)
    write(af / "INSTALLED.json", json.dumps({"agentflow": VERSION}, indent=2) + "\n", written)
    ensure_gitignore(target, written)
    ensure_feedback_inbox(source, target, written)


def ensure_feedback_inbox(source: pathlib.Path, target: pathlib.Path, written: list):
    """The owner's feedback inbox. Created once with its guide; the owner's items are never touched."""
    readme = target / ".agentflow" / "feedback" / "README.md"
    if not readme.exists():
        tpl = source / "templates" / "project" / ".agentflow" / "feedback" / "README.md"
        write(readme, tpl.read_text(encoding="utf-8"), written)


def ensure_gitignore(target: pathlib.Path, written: list):
    """Ad-hoc Runner/gate invocations outside a run are scratch; runs themselves are kept (profile Runs: commit)."""
    gi = target / ".gitignore"
    text = gi.read_text(encoding="utf-8") if gi.exists() else ""
    lines = [l.strip() for l in text.splitlines()]
    if ".agentflow/runs/_adhoc/" not in lines:
        text = text.rstrip("\n") + ("\n\n" if text else "") + "# agentflow: ad-hoc runner/gate output outside a run\n.agentflow/runs/_adhoc/\n"
        gi.write_text(text, encoding="utf-8", newline="\n")
        written.append(gi)
    if any(l in (".agentflow/runs/", ".agentflow/runs", ".agentflow/runs/*") for l in lines):
        print("warning: .gitignore ignores .agentflow/runs/, so runs are not kept; remove that line unless the "
              "profile says Runs: local")


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
    sys.path.insert(0, str(target / ".agentflow" / "engine"))
    import models  # noqa: E402  (the installed copy, so --sync uses the project's own engine)
    af = target / ".agentflow"
    agents = sorted((af / "agents").glob("*.agent.md"))
    agreement = (af / "instructions" / "working-agreement.instructions.md").read_text(encoding="utf-8")
    _, agreement_body = split_frontmatter(agreement)
    prompts = sorted((af / "prompts").glob("*.prompt.md"))
    for host in hosts:
        mapping = models.model_map(target, host)

        def hosted(a: pathlib.Path) -> str:
            text = a.read_text(encoding="utf-8")
            _, model, _ = models.resolve(models.tier_of(text), mapping)
            return with_model(text, model)

        if host == "claude":
            for a in agents:
                write(target / ".claude" / "agents" / a.name.replace(".agent.md", ".md"), hosted(a), written)
            write(target / ".claude" / "rules" / "agentflow-working-agreement.md",
                  "<!-- generated by agentflow install.py from .agentflow/instructions; do not edit -->\n" + agreement_body,
                  written)
            for p in prompts:
                fm, body = split_frontmatter(p.read_text(encoding="utf-8"))
                text = f"---\ndescription: {fm.get('description', '')}\n---\n{body.rstrip()}\n\nRequest: $ARGUMENTS\n"
                write(target / ".claude" / "commands" / p.name.replace(".prompt.md", ".md"), text, written)
            merge_claude_hook(target / ".claude" / "settings.json", written)
        elif host == "copilot":
            for a in agents:
                write(target / ".github" / "agents" / a.name, hosted(a), written)
            write(target / ".github" / "instructions" / "agentflow-working-agreement.instructions.md",
                  '---\napplyTo: "**"\ndescription: "agentflow working agreement"\n---\n' + agreement_body, written)
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


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--target", required=True)
    p.add_argument("--host", action="append", required=True, choices=["claude", "copilot"])
    p.add_argument("--sync", action="store_true", help="only regenerate host files from .agentflow/")
    args = p.parse_args(argv)
    target = pathlib.Path(args.target).resolve()
    written = []
    if not args.sync:
        source = HERE.parent
        if not (source / ".apm" / "agents").is_dir():
            print("run without --sync from the agentflow source repo (engine/install.py)", file=sys.stderr)
            return 2
        install_package(source, target, written)
    elif not (target / ".agentflow" / "agents").is_dir():
        print(f"agentflow is not installed in {target}", file=sys.stderr)
        return 2
    sync_hosts(target, args.host, written)
    for w in written:
        print("wrote", w.relative_to(target).as_posix())
    print(f"agentflow {VERSION}: {len(written)} files written for {', '.join(args.host)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

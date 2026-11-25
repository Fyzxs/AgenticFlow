"""Install FyzxsFlow into a repo, or re-sync host files from the repo's installed copy.

From the FyzxsFlow source repo:
  python -I engine/install.py --target <repo> --host claude [--host copilot]
Inside a repo where FyzxsFlow is installed (after the Curator edits .fyzxsflow/learned/*):
  python -I .fyzxsflow/package/engine/install.py --sync --target . --host claude

Installed layout (engine/layout.py):
  .fyzxsflow/                the project's own files; an install never overwrites them
    config.json profile.md gates.json feature-flags.md docs/ feedback/ runs/ baselines/
    config.json.readme.md (installer-owned: rewritten on every install)
    learned/<agent>.md       the Curator's Learned entries for this project, one file per agent
    compacted/               the Compactor's smaller package files; copied into package/ while they still fit
                             the upstream file they were made from (engine/compact.py)
  .fyzxsflow/package/        installer-owned: deleted and rewritten by every install; never edit it
    engine/ (no tests)  agents/  context/  templates/  skills/  instructions/  prompts/  INSTALLED.json
Host files generated from it (each agent = package/agents/<a>.agent.md + its learned/<a>.md entries):
  claude:  .claude/agents/<name>.md, .claude/rules/fyzxsflow-working-agreement.md,
           .claude/commands/<prompt>.md, .claude/skills/<skill>/SKILL.md,
           merged into .claude/settings.json: the kill-by-name hook, the orchestrator hook
           (hooks/orchestrator_guard_claude.py: review gate + delegation reminder), and
           "agent": "orchestrator", so the main session is the orchestrator and does no work itself (--no-main-agent
           leaves `agent` out; a plain session is then `claude` as usual). Entries that aren't ours are never touched.
  copilot: .github/agents/<name>.agent.md (the orchestrator's carries hooks/orchestrator_guard_copilot.py as
           agent-scoped `hooks:` entries with --scoped, for hosts that run them; Copilot CLI doesn't),
           .github/hooks/fyzxsflow.json (kill-by-name, and orchestrator_guard_copilot.py prompt/pre/post for every
           session: skill-agent check, never-list, review gate, delegation reminder),
           .github/instructions/fyzxsflow-working-agreement.instructions.md,
           .github/skills/<prompt>/SKILL.md   (the slash commands, as VS Code agent skills; the prompt files
                                              earlier installs wrote to .github/prompts/ are removed)
           .github/skills/<skill>/SKILL.md    (the package skills, which the model may pick by description)
  A package skill's host copy is its SKILL.md only; its scripts stay in package/skills/<skill>/, where the
  SKILL.md points. Host copies of skills dropped upstream are removed (they carry a generated marker).

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
VERSION = "0.6.1"
HOOK_SCRIPT = f'"$CLAUDE_PROJECT_DIR/{HOME}/{PACKAGE}/engine/hooks/block_kill_by_name.py"'
GUARD_SCRIPT = f'"$CLAUDE_PROJECT_DIR/{HOME}/{PACKAGE}/engine/hooks/orchestrator_guard_claude.py"'
OLD_GUARD_MARKERS = ("/engine/hooks/orchestrator_guard.py",)  # 0.4.4-0.4.9: one script for both hosts
MAIN_AGENT = "orchestrator"
GUARD_TOOLS = "Edit|Write|MultiEdit|NotebookEdit|Bash|PowerShell|Agent|Task"


def python_name() -> str:
    """The interpreter name the hook calls: `python` where it exists, else `python3` (some hosts have only that)."""
    if shutil.which("python"):
        return "python"
    return "python3" if shutil.which("python3") else "python"


def hook_cmd() -> str:
    return f"{python_name()} -I {HOOK_SCRIPT}"


def claude_hooks(probe: bool) -> list:
    """(script marker, matcher, command) for each PreToolUse entry FyzxsFlow owns in .claude/settings.json."""
    py = python_name()
    return [(HOOK_SCRIPT, "Bash|PowerShell", hook_cmd()),
            (GUARD_SCRIPT, GUARD_TOOLS, f"{py} -I {GUARD_SCRIPT}" + (" --probe" if probe else ""))]
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
    # The config reference describes the installed engine, so it is installer-owned like package/.
    ref = "config.json.readme.md"
    write(target / HOME / ref, (source / "templates" / "project" / HOME / ref).read_text(encoding="utf-8"), written)


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


def sync_hosts(target: pathlib.Path, hosts: list, written: list, main_agent: bool = True, probe: bool = False,
               state: dict = None):
    """state: INSTALLED.json's claude_settings from before this install (what we wrote into settings.json)."""
    sys.dont_write_bytecode = True  # importing the installed engine must not leave __pycache__ in the project
    sys.path.insert(0, str(target / HOME / PACKAGE / "engine"))
    import models  # noqa: E402  (the installed copy, so --sync uses the project's own engine)
    pkg = target / HOME / PACKAGE
    agents = sorted((pkg / "agents").glob("*.agent.md"))
    agreement = (pkg / "instructions" / f"{HOME[1:]}-working-agreement.instructions.md").read_text(encoding="utf-8")
    _, agreement_body = split_frontmatter(agreement)
    prompts = sorted((pkg / "prompts").glob("*.prompt.md"))
    prefix = HOME[1:]
    skills = sorted(d for d in (pkg / "skills").iterdir() if (d / "SKILL.md").is_file()) if (pkg / "skills").is_dir() else []
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
                hint = f"argument-hint: {fm['argument-hint']}\n" if fm.get("argument-hint") else ""
                text = f"---\ndescription: {fm.get('description', '')}\n{hint}---\n{body.rstrip()}\n\nRequest: $ARGUMENTS\n"
                write(target / ".claude" / "commands" / p.name.replace(".prompt.md", ".md"), text, written)
            sync_skills(target / ".claude" / "skills", skills, written)
            state = merge_claude_settings(target / ".claude" / "settings.json", written, main_agent, probe,
                                          state or {})
            record_settings(target, state, written)
        elif host == "copilot":
            for a in agents:
                text = copilot_frontmatter(hosted(a))
                if a.name == f"{MAIN_AGENT}.agent.md":
                    text = with_scoped_guard(text, probe)
                write(target / ".github" / "agents" / a.name, text, written)
            write(target / ".github" / "hooks" / f"{prefix}.json", copilot_hooks(probe), written)
            write(target / ".github" / "instructions" / f"{prefix}-working-agreement.instructions.md",
                  f'---\napplyTo: "**"\ndescription: "{NAME} working agreement"\n---\n' + agreement_body, written)
            for p in prompts:
                name = p.name.replace(".prompt.md", "")
                write(target / ".github" / "skills" / name / "SKILL.md", copilot_skill(name, p), written)
                old = target / ".github" / "prompts" / p.name  # written by installs before 0.4.1
                if old.exists():
                    old.unlink()
                    written.append(old)
            sync_skills(target / ".github" / "skills", skills, written)
            prompts_dir = target / ".github" / "prompts"
            if prompts_dir.is_dir() and not any(prompts_dir.iterdir()):
                prompts_dir.rmdir()
        else:
            raise SystemExit(f"unknown host '{host}' (claude, copilot)")


SKILL_MARKER = f"<!-- generated by {HOME[1:]} install.py from {HOME}/{PACKAGE}/skills; do not edit -->"


def host_skill(skill_md: pathlib.Path) -> str:
    """A package skill as a host skill: same frontmatter (name + description, so the model can pick it), the marker
    after it, then the body."""
    text = skill_md.read_text(encoding="utf-8")
    m = re.match(r"\A---\n.*?\n---\n", text, re.S)
    head, body = (text[:m.end()], text[m.end():]) if m else ("", text)
    return head + SKILL_MARKER + "\n" + body


def sync_skills(dest: pathlib.Path, skills: list, written: list):
    """Write each package skill to <dest>/<skill>/SKILL.md; remove generated copies of skills no longer shipped.
    The owner's own skills (no marker) are never touched."""
    names = {d.name for d in skills}
    for d in skills:
        write(dest / d.name / "SKILL.md", host_skill(d / "SKILL.md"), written)
    for f in sorted(dest.glob("*/SKILL.md")) if dest.is_dir() else []:
        if f.parent.name not in names and SKILL_MARKER in f.read_text(encoding="utf-8"):
            f.unlink()
            written.append(f)
            if not any(f.parent.iterdir()):
                f.parent.rmdir()


ACT_AS = re.compile(r"\AAct as the FyzxsFlow \*\*([\w-]+)\*\*(.*?)\.\s.*?(?:\n\n|\Z)", re.S)


def copilot_skill(name: str, prompt: pathlib.Path) -> str:
    """A package prompt as a Copilot agent skill: run only when typed as /<name> (disable-model-invocation), since
    each one starts a run or changes files. A skill can't pin its agent, and reading a 46 KB agent file through a
    tool truncates it, so the body never says "act as <agent>, read its file": it says the skill runs in that
    agent, selected with /agent or --agent, where the agent file is the system prompt. The repo hook
    (orchestrator_guard_copilot.py prompt/pre) blocks the skill in any other agent."""
    fm, body = split_frontmatter(prompt.read_text(encoding="utf-8"))
    m = ACT_AS.match(body.lstrip("\n"))
    if m:
        agent, mode = m.group(1), m.group(2).strip()
        gate = (f"This command runs in the FyzxsFlow **{agent}** custom agent{(' ' + mode) if mode else ''}. Your agent "
                f"file is already your instructions; don't read it as a file. If you are not running as the "
                f"{agent} agent, do nothing else: tell the owner to select it (`/agent {agent}`, or start "
                f"`copilot --agent {agent}`) and run /{name} again.\n\n")
        body = gate + body.lstrip("\n")[m.end():]
    hint = fm.get("argument-hint", "").strip().strip('"')
    lines = ["---", f"name: {name}", f"description: {json.dumps(fm.get('description', ''), ensure_ascii=False)}"]
    if hint:
        lines.append(f"argument-hint: {json.dumps(hint, ensure_ascii=False)}")
    lines += ["disable-model-invocation: true", "---"]
    return "\n".join(lines) + "\n" + body.lstrip("\n").rstrip() + \
        "\n\nThe request is the text typed after the command.\n"


def with_scoped_guard(text: str, probe: bool) -> str:
    """The Copilot orchestrator agent with the guard as an agent-scoped hook: it runs only while the orchestrator is
    the selected agent, which is what tells the hook the call is the orchestrator's own (Copilot's hook input
    names no main agent; a subagent's call carries agent_id and is never touched). PreToolUse runs the review gate
    (a deny is only possible before the call), PostToolUse the delegation reminder (Copilot CLI documents
    additionalContext only after the call)."""
    m = re.match(r"\A---\n(.*?)\n---\n", text, re.S)
    if not m:
        return text
    script = f"{python_name()} -I {HOME}/{PACKAGE}/engine/hooks/orchestrator_guard_copilot.py"
    probe_flag = " --probe" if probe else ""
    hooks = (f"hooks:\n  PreToolUse:\n    - type: command\n      command: {script} pre --scoped{probe_flag}\n"
             f"      timeoutSec: 15\n"
             f"  PostToolUse:\n    - type: command\n      command: {script} post --scoped\n      timeoutSec: 15")
    return "---\n" + m.group(1) + "\n" + hooks + "\n---\n" + text[m.end():]


def copilot_hooks(probe: bool = False) -> str:
    """Repository hooks for GitHub Copilot (CLI and VS Code), loaded for every session in the trusted folder:
    kill-by-name in the Claude-compatible PascalCase form (snake_case input, Claude tool names), and the FyzxsFlow
    hooks (engine/hooks/orchestrator_guard_copilot.py): the skill-agent check on each prompt, the never-list, skill
    check and review gate before each tool call, the delegation reminder after it. Repo-wide because agent-scoped
    frontmatter hooks never fired on Copilot CLI (1.0.116)."""
    py = python_name()
    kill = f"{py} -I {HOME}/{PACKAGE}/engine/hooks/block_kill_by_name.py"
    guard = f"{py} -I {HOME}/{PACKAGE}/engine/hooks/orchestrator_guard_copilot.py"
    return json.dumps({"version": 1, "hooks": {
        "PreToolUse": [{"type": "command", "matcher": "Bash", "command": kill, "timeoutSec": 15}],
        "userPromptSubmitted": [{"type": "command", "command": f"{guard} prompt", "timeoutSec": 30}],
        "preToolUse": [{"type": "command", "command": f"{guard} pre" + (" --probe" if probe else ""),
                        "timeoutSec": 30}],
        "postToolUse": [{"type": "command", "command": f"{guard} post", "timeoutSec": 30}],
    }}, indent=2) + "\n"


def copilot_frontmatter(text: str) -> str:
    """Copilot rejects an agent whose frontmatter isn't valid YAML (an unquoted ': ' in a description dropped 7
    agents) and warns on fields it doesn't know (`tier`). Quote the description and drop tier: the model ladder
    already reached `model:`."""
    m = re.match(r"\A---\n(.*?)\n---\n", text, re.S)
    if not m:
        return text
    lines = []
    for line in m.group(1).splitlines():
        if line.startswith("tier:"):
            continue
        if line.startswith("description:"):
            value = line.split(":", 1)[1].strip()
            if not (value.startswith('"') and value.endswith('"') and len(value) > 1):
                line = "description: " + json.dumps(value.strip("'") if value.startswith("'") else value,
                                                    ensure_ascii=False)
        lines.append(line)
    return "---\n" + "\n".join(lines) + "\n---\n" + text[m.end():]


def merge_claude_settings(settings: pathlib.Path, written: list, main_agent: bool, probe: bool, state: dict) -> dict:
    """Merge FyzxsFlow's hooks (and `agent`) into .claude/settings.json without touching anything else: our entries
    are found by script path and updated in place, missing ones appended; other entries, keys and their order are
    kept. `agent` is set only when absent, and removed only if we wrote it. Writes only when something changed,
    keeping the file's line endings. Returns what we own now, for INSTALLED.json."""
    raw = settings.read_bytes().decode("utf-8") if settings.exists() else ""
    crlf = "\r\n" in raw
    data = json.loads(raw) if raw.strip() else {}
    before = json.dumps(data, sort_keys=False)
    pre = data.setdefault("hooks", {}).setdefault("PreToolUse", [])
    for marker, matcher, cmd in claude_hooks(probe):
        markers = (marker, *(OLD_GUARD_MARKERS if marker == GUARD_SCRIPT else ()))
        mine = [(e, h) for e in pre for h in e.get("hooks", []) if any(m in h.get("command", "") for m in markers)]
        if mine:
            for e, h in mine:
                h["command"] = cmd  # ours, whatever interpreter, mode or script name it was installed with
                e["matcher"] = matcher
        else:
            pre.append({"matcher": matcher, "hooks": [{"type": "command", "command": cmd}]})
    wrote_agent = bool(state.get("agent"))
    if main_agent:
        if "agent" not in data:
            data["agent"] = MAIN_AGENT
            wrote_agent = True
        elif data["agent"] != MAIN_AGENT:
            print(f"warning: .claude/settings.json sets \"agent\": \"{data['agent']}\"; left as is, so the main "
                  f"session is not the {MAIN_AGENT} and its guard is off (set it to \"{MAIN_AGENT}\" to turn it on)")
            wrote_agent = False
    elif data.get("agent") == MAIN_AGENT and wrote_agent:
        del data["agent"]
        wrote_agent = False
    if json.dumps(data, sort_keys=False) != before or not settings.exists():
        text = json.dumps(data, indent=2) + "\n"
        settings.parent.mkdir(parents=True, exist_ok=True)
        settings.write_bytes(text.replace("\n", "\r\n" if crlf else "\n").encode("utf-8"))
        written.append(settings)
    return {"agent": wrote_agent, "probe": probe}


def record_settings(target: pathlib.Path, state: dict, written: list):
    """Remember in INSTALLED.json what we own in .claude/settings.json (so a later install removes only our `agent`)."""
    f = target / HOME / PACKAGE / "INSTALLED.json"
    data = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
    if data.get("claude_settings") != state:
        data["claude_settings"] = state
        write(f, json.dumps(data, indent=2) + "\n", written)


def record_hosts(target: pathlib.Path, hosts: list, written: list, add: bool):
    """Remember in INSTALLED.json the hosts FyzxsFlow is installed for: pointers.py writes only for them, so a
    Copilot-only repo gets no .claude/ files even when an older .claude/ folder is still there. A full install sets
    the list; --sync (the Curator and Compactor sync one host per call) adds to it."""
    f = target / HOME / PACKAGE / "INSTALLED.json"
    data = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
    want = sorted(set(hosts) | (set(data.get("hosts") or []) if add else set()))
    if data.get("hosts") != want:
        data["hosts"] = want
        write(f, json.dumps(data, indent=2) + "\n", written)


def previous_settings_state(target: pathlib.Path) -> dict:
    f = target / HOME / PACKAGE / "INSTALLED.json"
    try:
        return json.loads(f.read_text(encoding="utf-8")).get("claude_settings") or {}
    except (OSError, ValueError):
        return {}


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


def migrate_legacy(target: pathlib.Path, written: list, migrated: list, hosts: list) -> int:
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
        remove_legacy_host_files(target, old_name, written, hosts)
        migrate_gitignore(target, old_name, written)
        print(f"migrated {old_name}/ -> {HOME}/ (project files) + {HOME}/{PACKAGE}/ (package)")
        migrated.append(old_name)
    return 0


def remove_legacy_host_files(target: pathlib.Path, old_name: str, written: list, hosts: list):
    """The old name's generated host files, only for the hosts being installed: a --host copilot install never
    touches .claude/, and a --host claude install never touches .github/."""
    prefix = old_name[1:]
    per_host = {
        "claude": ((".claude/rules", f"{prefix}-*.md"), target / ".claude" / "commands" / f"{prefix}-init.md"),
        "copilot": ((".github/instructions", f"{prefix}-*.instructions.md"),
                    target / ".github" / "prompts" / f"{prefix}-init.prompt.md"),
    }
    for host in hosts:
        (folder, glob), init = per_host[host]
        for f in sorted((target / folder).glob(glob)) if (target / folder).is_dir() else []:
            if f"generated by {prefix}" in f.read_text(encoding="utf-8"):
                f.unlink()
                written.append(f)
        if init.exists():
            init.unlink()
            written.append(init)
    settings = target / ".claude" / "settings.json"
    if "claude" in hosts and settings.exists():
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
    p.add_argument("--no-main-agent", action="store_true",
                   help=f"claude: don't make the main session the {MAIN_AGENT} (its guard then never applies)")
    p.add_argument("--probe-hooks", action="store_true",
                   help="install the orchestrator guard in log-only mode (engine/hooks/orchestrator_probe.py report)")
    args = p.parse_args(argv)
    target = pathlib.Path(args.target).resolve()
    written, migrated = [], []
    state = previous_settings_state(target)  # read before the package (and its INSTALLED.json) is rewritten
    if not args.sync:
        source = HERE.parent
        if not (source / ".apm" / "agents").is_dir():
            print(f"run without --sync from the {NAME} source repo (engine/install.py)", file=sys.stderr)
            return 2
        code = migrate_legacy(target, written, migrated, args.host)
        if code:
            return code
        install_package(source, target, written)
    elif not (target / HOME / PACKAGE / "agents").is_dir():
        print(f"{NAME} is not installed in {target}", file=sys.stderr)
        return 2
    import compact  # noqa: E402  (same engine folder)
    for warning in compact.apply(target, written):
        print("warning:", warning)
    sync_hosts(target, args.host, written, main_agent=not args.no_main_agent, probe=args.probe_hooks, state=state)
    record_hosts(target, args.host, written, add=args.sync)
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

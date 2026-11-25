"""The orchestrator's hook rules, shared by the host entry scripts (orchestrator_guard_claude.py,
orchestrator_guard_copilot.py). Nothing here reads stdin or prints: each entry script turns these answers into its
host's hook output.

Two rules, for the orchestrator's own calls only (a subagent's call carries agent_id and is never touched):
1. Delegation reminder (reminder()): the orchestrator does no work; it dispatches the agent that owns it. Prose said
   so and failed twice in one day (DocMcStorage F-1984, F-1986). Denying those calls (0.4.4) got in the way when the
   orchestrator had a real reason (Quinn, 2026-11-24), so this never blocks: the host adds a reminder naming the
   agent to dispatch.
2. Review gate (review_gate()): while the run waits on the owner's review (review.py open), the orchestrator may not
   dispatch agents or move lanes and PRs. This one blocks. A Build pause holds only its own PR group, so it doesn't.

Whose call it is:
  Claude Code: the payload's `agent_type` is "orchestrator" and it has no `agent_id` (install.py makes the main
    session the orchestrator with `"agent": "orchestrator"` in .claude/settings.json).
  GitHub Copilot (scoped=True): the hooks are declared in the orchestrator agent's own `hooks:` frontmatter, so they
    run only while that agent is selected; a call with no `agent_id` is the orchestrator's own.

What draws no reminder:
  Edits: only its own run-folder bookkeeping, EDITABLE below (review files, input.md, review-requests.md).
  Shell: only the commands in the allow-list below, every segment of a compound command. No command substitution,
    no heredocs, no output redirection to a file (a redirect is an edit by another name).
The lists are constants here on purpose; a project that needs another bookkeeping command proposes it upstream.
"""

import json
import os
import pathlib
import re
import shlex
import sys

sys.dont_write_bytecode = True  # never leave __pycache__ in the project
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from layout import HOME, PACKAGE  # noqa: E402

ROLE = "orchestrator"

# ---------------------------------------------------------------- the allow-lists (one place; widen upstream only)

# Run-folder files the orchestrator writes itself (orchestrator.agent.md: review files at every hand-off, the raw
# request in input.md, the owner's mid-run review requests).
EDITABLE = re.compile(r"(^|/)\.fyzxsflow/runs/[^/]+/[^/]+/(input\.md|review-requests\.md|reviews/[^/]+\.md)$")

# Engine bookkeeping scripts (.fyzxsflow/package/engine/<name>.py), with subcommands that are another agent's.
ENGINE = {"run", "lanes", "findings", "feedback", "steps", "review", "waves", "ac_trace", "pr", "models", "compare",
          "checks", "preceptee"}
ENGINE_NOT = {("pr", "comment"): "pr-producer"}

GIT = {"add", "commit", "push", "status", "log", "fetch", "pull", "diff", "show", "rev-parse", "ls-files",
       "merge-base", "remote", "worktree", "branch"}
GIT_ONLY = {"worktree": {"list"}, "remote": {"-v", "get-url", "show"},
            "branch": {"--list", "-l", "--show-current", "-a", "-r", "-v", "-vv", "--contains"}}
READS = {"ls", "cat", "head", "tail", "wc", "grep", "pwd", "cd", "echo", "date", "sort", "uniq", "true",
         "get-content", "get-childitem", "select-string", "set-location", "test-path", "write-output"}

# ---------------------------------------------------------------- who owns what

DISPATCH = ("Dispatch the agent that owns it: implementer, iac-implementer or tester for code, tests and pipelines; "
            "docs-gardener for rules and project docs; build-coordinator for work packages; curator for learned/; "
            "pr-producer for PR descriptions and comments; build-test-runner for every Runner mode.")
OWNERS = [  # (pattern on the command or path, owner)
    (r"(^|/)\.fyzxsflow/learned/", "curator"),
    (r"(^|/)\.fyzxsflow/runs/[^/]+/[^/]+/work-packages/", "build-coordinator (Plan mode)"),
    (r"(^|/)\.fyzxsflow/runs/[^/]+/[^/]+/pr-(bodies/|description)", "pr-producer"),
    (r"(^|/)(\.claude/rules|\.github/instructions|\.fyzxsflow/(docs|profile\.md))|(^|/)[^/]*\.md$",
     "docs-gardener (feedback mode)"),
    (r"(^|/)(\.github/workflows|\.azure-pipelines|pipelines?|infra|iac|deploy)/|\.(ya?ml|bicep|tf)$",
     "iac-implementer"),
    (r"\brunner\.py\b|^(dotnet|npm|npx|pnpm|yarn|pytest|mvn|gradle|cargo|go|make|node|tox|nox)\b",
     "build-test-runner"),
    (r"\bgates\.py\b", "gate-analyst"),
    (r"\b(install|compact|docs_check|pointers)\.py\b", "curator, compactor or docs-gardener"),
    (r"^az devops invoke|^az repos pr (create|update)|^gh (api|pr (comment|create|edit|review))\b", "pr-producer"),
]


def owner_of(text: str) -> str:
    for pattern, owner in OWNERS:
        if re.search(pattern, text):
            return owner
    return ""


def denial(what: str, owner: str) -> str:
    who = f"Dispatch {owner} for work like this." if owner else DISPATCH
    return (f"FyzxsFlow reminder: delegate. The orchestrator does no work itself ({what}). {who} If there was a real "
            "reason to do it yourself, say why in the ledger (`run.py log <run> <stage> decided \"did it in-session: "
            "<why>\"`). The orchestrator's own work is bookkeeping: the engine's run/lanes/findings/feedback/steps/"
            "review/waves/ac_trace/pr commands, review files, git add/commit/push by path, and talking to the owner.")


# ---------------------------------------------------------------- payloads (Claude Code, VS Code and Copilot CLI shapes)

EDIT_TOOLS = {"edit", "write", "multiedit", "notebookedit", "create", "str_replace_editor", "apply_patch",
              "editfiles", "createfile", "insert_edit_into_file", "replace_string_in_file"}
SHELL_TOOLS = {"bash", "powershell", "shell", "runinterminal", "run_in_terminal"}


def fields(payload: dict):
    """(tool name lower-case, tool input dict, agent_id, agent_type) from either naming style."""
    tool = str(payload.get("tool_name") or payload.get("toolName") or "")
    args = payload.get("tool_input") if "tool_input" in payload else payload.get("toolArgs")
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except ValueError:
            args = {"command": args}
    return (tool.lower(), args if isinstance(args, dict) else {},
            payload.get("agent_id") or payload.get("agentId") or "",
            payload.get("agent_type") or payload.get("agentType") or "")


def edited_paths(args: dict) -> list:
    paths = [args[k] for k in ("file_path", "notebook_path", "path", "filePath") if isinstance(args.get(k), str)]
    for key in ("patch", "input"):
        if isinstance(args.get(key), str):
            paths += re.findall(r"^\*\*\* (?:Add|Update|Delete) File: (.+?)\s*$", args[key], re.M)
    for f in args.get("files") or []:
        if isinstance(f, str):
            paths.append(f)
    return [p.replace("\\", "/") for p in paths]


# ---------------------------------------------------------------- the shell rules

def shell_problem(command: str):
    """None when every segment is allowed; else (what, owner)."""
    if "$(" in command or "`" in command:
        return "command substitution", ""
    if re.search(r"<<-?\s*['\"]?\w", command):
        return "a heredoc (commit with -m)", ""
    try:
        lex = shlex.shlex(command.replace("\r", "").replace("\n", " ; "), posix=True, punctuation_chars=True)
        lex.whitespace_split = True
        tokens = list(lex)
    except ValueError:
        return "a command the guard can't parse", ""
    segments, cur, i = [], [], 0
    while i < len(tokens):
        t = tokens[i]
        if t in ("&&", "||", ";", "|", "&", ";;", "|&"):
            segments.append(cur)
            cur = []
        elif t in ("(", ")"):
            return "a subshell", ""
        elif set(t) <= set("<>&|") and ">" in t:  # >, >>, >|, &>, >&
            target = tokens[i + 1] if i + 1 < len(tokens) else ""
            if t == ">&" or target in ("/dev/null", "$null", "NUL") or (t.endswith("&") and target.isdigit()):
                i += 2
                if cur and cur[-1].isdigit():
                    cur.pop()  # the fd number before 2>&1
                continue
            return f"output redirected to {target or 'a file'}", owner_of(target)
        elif t.startswith("<"):
            i += 2
            continue
        else:
            cur.append(t)
        i += 1
    segments.append(cur)
    for words in segments:
        words = [w for w in words if not re.fullmatch(r"\w+=.*", w)] if words and "=" in words[0] else words
        if not words:
            continue
        bad = segment_problem(words)
        if bad:
            return bad
    return None


def segment_problem(words: list):
    cmd = words[0].replace("\\", "/").rsplit("/", 1)[-1].lower().removesuffix(".exe")
    line = " ".join(words)
    if cmd in READS:
        return None
    if cmd in ("python", "python3", "py"):
        rest, skip = [], False
        for w in words[1:]:
            if skip:
                skip = False
            elif w in ("-X", "-W", "-3"):
                skip = w != "-3"
            elif not w.startswith("-") or w in ("-c", "-m") or rest:
                rest.append(w)
        if not rest or rest[0] in ("-c", "-m"):
            return "inline Python", ""
        script = rest[0].replace("\\", "/")
        m = re.search(r"(?:^|/)\.fyzxsflow/package/engine/(\w+)\.py$", script)
        if not m or m.group(1) not in ENGINE:
            return f"`{script}`", owner_of(script)
        sub = rest[1] if len(rest) > 1 else ""
        if (m.group(1), sub) in ENGINE_NOT:
            return f"`{m.group(1)}.py {sub}`", ENGINE_NOT[(m.group(1), sub)]
        return None
    if cmd == "git":
        args = list(words[1:])
        while args and args[0] in ("-C", "-c"):
            args = args[2:]
        while args and args[0].startswith("--") and "=" in args[0]:
            args = args[1:]
        sub = args[0] if args else ""
        if sub not in GIT:
            return f"`git {sub}`", ""
        if sub in GIT_ONLY and len(args) > 1 and args[1] not in GIT_ONLY[sub]:
            return f"`git {sub} {args[1]}`", ""
        if sub == "worktree" and len(args) == 1:
            return "`git worktree`", ""
        return None
    if cmd in ("docker", "docker-compose"):
        rest = words[2:] if cmd == "docker" and len(words) > 1 and words[1] == "compose" else words[1:]
        if (cmd == "docker-compose" or words[1:2] == ["compose"]) and "down" in rest:
            return None
        return f"`{line[:60]}`", ""
    if cmd == "az" and words[1:3] == ["repos", "pr"] and len(words) > 3 and words[3] in ("show", "list"):
        return None
    if cmd == "gh" and words[1:2] == ["pr"] and len(words) > 2 and words[2] in ("view", "list", "checks", "status"):
        return None
    return f"`{line[:60]}`", owner_of(line)


# ---------------------------------------------------------------- main

def probe_log(payload: dict, scoped: bool):
    root = project_root(payload)
    out = root / ".fyzxsflow" / "runs" / "_adhoc" / "hook-probe.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    tool, _, agent_id, agent_type = fields(payload)
    row = {"tool": tool, "agent_id": agent_id, "agent_type": agent_type, "scoped": scoped,
           "has_agent_id": "agent_id" in payload or "agentId" in payload,
           "session": payload.get("session_id") or payload.get("sessionId") or "",
           "keys": sorted(payload)}
    with out.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


def reminder(payload: dict, scoped: bool):
    """None when the call is the orchestrator's own bookkeeping (or not its call at all), else the reminder."""
    if not is_orchestrators_call(payload, scoped):
        return None  # a subagent, a plain session, or another agent's session
    tool, args, _, _ = fields(payload)
    if tool in EDIT_TOOLS:
        paths = edited_paths(args)
        bad = [p for p in paths if not EDITABLE.search(p)]
        if paths and not bad:
            return None
        target = bad[0] if bad else "a file"
        return denial(f"editing {target}", owner_of(target))
    if tool in SHELL_TOOLS:
        problem = shell_problem(str(args.get("command") or args.get("script") or ""))
        return denial(problem[0], problem[1]) if problem else None
    return None


# ---------------------------------------------------------------- the review gate

DISPATCH_TOOLS = {"agent", "task", "runsubagent", "run_subagent"}
MOVES = re.compile(r"(?:^|[\s/'\"])\.fyzxsflow/package/engine/(lanes|pr)\.py\s+(\w[\w-]*)")
READ_ONLY_MOVES = {("lanes", "refresh"), ("lanes", "status"), ("pr", "status"), ("pr", "show")}


def project_root(payload: dict) -> pathlib.Path:
    start = pathlib.Path(os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or ".").resolve()
    for d in (start, *start.parents):
        if (d / HOME).is_dir():
            return d
    return start


def blocking_pauses(root: pathlib.Path) -> list:
    """(run folder, pause) for every open review pause outside Build in the active runs."""
    engine = pathlib.Path(__file__).resolve().parent.parent
    if str(engine) not in sys.path:
        sys.path.insert(0, str(engine))
    import review  # noqa: E402  (the installed engine's own)
    out = []
    active = root / HOME / "runs" / "active"
    for run in sorted(active.iterdir()) if active.is_dir() else []:
        if run.is_dir():
            out += [(run, p) for p in review.open_pauses(run) if (p.get("stage") or "") != "build"]
    return out


def dispatch_target(args: dict) -> str:
    return str(args.get("agent_type") or args.get("subagent_type") or args.get("agentName") or args.get("agent") or "")


def unchecked_handoffs(run: pathlib.Path) -> list:
    """Agent reports, stamped or not, whose hand-off was never checked with `review.py needed` (validators are
    part of their target's hand-off; the build-coordinator's execute report is its close-out, not a hand-off). A
    report counts from the moment it exists: in the first live Copilot run the orchestrator stamped late, after it
    had already dispatched the next agent."""
    import json as _json
    checked = []
    f = run / "reviews.jsonl"
    for line in (f.read_text(encoding="utf-8").splitlines() if f.exists() else []):
        try:
            e = _json.loads(line)
        except ValueError:
            continue
        if isinstance(e, dict) and e.get("decision") in ("checked", "pending"):
            checked.append((e.get("agent"), str(e.get("target") or "")))
    out = []
    for rep in sorted((run / "reports").glob("*.md")) if (run / "reports").is_dir() else []:
        text = rep.read_text(encoding="utf-8")
        fm = re.match(r"\A---\n(.*?)\n---\n", text, re.S)
        meta = dict(re.findall(r"^(\w[\w-]*):\s*(.*?)\s*$", fm.group(1), re.M)) if fm else {}
        agent, target = meta.get("agent", ""), meta.get("target", "")
        if not agent or agent == "validator" or rep.name.endswith(".execute.md"):
            continue
        package = re.match(r"WP-\d+", target)
        ok = any(a == agent and (not package or (t.lower() == package.group(0).lower()
                                                 or t.lower().startswith(package.group(0).lower() + "-")))
                 for a, t in checked)
        if not ok:
            out.append((rep.name, agent, package.group(0) if package else ""))
    return out


def handoff_gate(payload: dict, scoped: bool):
    """None, or why the orchestrator may not dispatch the next agent yet: a returned agent's hand-off was never
    checked for review (review.py needed), so a pause the owner asked for could be skipped. Its Validator may
    still be dispatched (it runs before the check)."""
    if not is_orchestrators_call(payload, scoped):
        return None
    tool, args, _, _ = fields(payload)
    if tool not in DISPATCH_TOOLS or dispatch_target(args).lower() == "validator":
        return None
    try:
        root = project_root(payload)
        active = root / HOME / "runs" / "active"
        missing = [(run, m) for run in (sorted(active.iterdir()) if active.is_dir() else []) if run.is_dir()
                   for m in unchecked_handoffs(run)]
    except Exception:  # noqa: BLE001  (a broken run folder must not wedge the session)
        return None
    if not missing:
        return None
    run, (name, agent, package) = missing[0]
    where = f"--package {package} " if package else "--stage <its stage> "
    return (f"Blocked by FyzxsFlow: {agent}'s output (reports/{name}) was never checked for review, so the next "
            f"dispatch has to wait. Stamp it (run.py stamp), run `python -I {HOME}/{PACKAGE}/engine/review.py needed --run {run.name} --agent "
            f"{agent} {where}...`, write its review file, and on review=pause stop for the owner "
            f"(**Human review between hand-offs**, orchestrator/review.md).")


def is_orchestrators_call(payload: dict, scoped: bool) -> bool:
    """The orchestrator's own call, not a subagent's: Claude Code names it (agent_type); a Copilot agent-scoped hook
    (scoped) runs only for it; a Copilot repo hook reads the session's selected agent."""
    _, _, agent_id, agent_type = fields(payload)
    if agent_id:
        return False
    if scoped or agent_type == ROLE:
        return True
    return not agent_type and copilot_selected_agent(session_id(payload)) == (True, ROLE)


def review_gate(payload: dict, scoped: bool):
    """None, or why this call must wait for the owner's review."""
    if not is_orchestrators_call(payload, scoped):
        return None
    tool, args, _, _ = fields(payload)
    if tool in DISPATCH_TOOLS:
        what = "dispatching an agent"
    elif tool in SHELL_TOOLS:
        m = MOVES.search(str(args.get("command") or args.get("script") or "").replace("\\", "/"))
        if not m or (m.group(1), m.group(2)) in READ_ONLY_MOVES:
            return None
        what = f"`{m.group(1)}.py {m.group(2)}`"
    else:
        return None
    try:
        pauses = blocking_pauses(project_root(payload))
    except Exception:  # noqa: BLE001  (a broken run folder must not wedge the session)
        return None
    if not pauses:
        return None
    run, p = pauses[0]
    return (f"Blocked by FyzxsFlow: the run is waiting for the owner's review of {p.get('agent')} on "
            f"{p.get('target')} ({p.get('reason')}), so {what} has to wait. Stop and show the owner the review "
            f"(`review.py show --review-file <its review file>`). When the owner replies, record the reply verbatim: "
            f"`python -I {HOME}/{PACKAGE}/engine/review.py decide --run {run.name} --agent {p.get('agent')} "
            f"--target {p.get('target')} --reply \"<the owner's words>\" --review-file <its review file>`; that "
            f"closes the pause. Never write a reply the owner didn't give. Open pauses: `review.py open --run {run.name}`.")


# ---------------------------------------------------------------- the never-list (every role, both hosts: blocks)

NEVER_PR = ("lanes.py and pr.py open, push, update and publish PRs; the owner completes every PR. Ask the "
            "orchestrator, which runs them.")


def never_segments(command: str) -> list:
    """Word lists of a shell command's segments (&&, ||, ;, |, newlines), tolerant of what it can't parse."""
    try:
        lex = shlex.shlex(command.replace("\r", "").replace("\n", " ; "), posix=True, punctuation_chars=True)
        lex.whitespace_split = True
        tokens = list(lex)
    except ValueError:
        tokens = command.split()
    out, cur = [], []
    for t in tokens:
        if t in ("&&", "||", ";", "|", "&", "|&", "(", ")", ";;"):
            out.append(cur)
            cur = []
        else:
            cur.append(t)
    out.append(cur)
    words = []
    for seg in out:
        while seg and re.fullmatch(r"\w+=.*", seg[0]):
            seg = seg[1:]
        if seg:
            words.append(seg)
    return words


def git_out(cwd: pathlib.Path, *args) -> str:
    import subprocess
    try:
        p = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return ""
    return p.stdout.strip() if p.returncode == 0 else ""


def default_branches(cwd: pathlib.Path) -> set:
    head = git_out(cwd, "symbolic-ref", "--short", "refs/remotes/origin/HEAD")
    return ({head.split("/", 1)[1]} if "/" in head else set()) | {"main", "master"}


def never_problem(words: list, cwd: pathlib.Path):
    """None, or why this one command is on the never-list."""
    cmd = words[0].replace("\\", "/").rsplit("/", 1)[-1].lower().removesuffix(".exe")
    if cmd == "git":
        args = list(words[1:])
        while args and args[0] in ("-C", "-c"):
            if args[0] == "-C" and len(args) > 1:
                cwd = (cwd / args[1]) if not pathlib.Path(args[1]).is_absolute() else pathlib.Path(args[1])
            args = args[2:]
        sub = args[0] if args else ""
        rest = args[1:]
        if sub == "worktree" and rest[:1] and rest[0] in ("add", "remove", "move"):
            return f"`git worktree {rest[0]}`: lanes.py opens and closes worktrees (lanes.py open/close)"
        if sub == "merge" and not ({"--abort", "--continue", "--quit"} & set(rest)):
            branch = git_out(cwd, "rev-parse", "--abbrev-ref", "HEAD")
            if branch in default_branches(cwd) or branch.startswith("fyzxsflow/"):
                return (f"`git merge` into `{branch}`: lanes.py merges the flow's branches (lanes.py merge/sync), "
                        f"and only the owner merges into the default branch")
        if sub == "push":
            positional = [a for a in rest if not a.startswith("-")]
            targets = [r.lstrip("+").split(":")[-1].removeprefix("refs/heads/") for r in positional[1:]]
            if not targets:
                targets = [git_out(cwd, "rev-parse", "--abbrev-ref", "HEAD")]
            if "HEAD" in targets:
                targets.append(git_out(cwd, "rev-parse", "--abbrev-ref", "HEAD"))
            hit = [t for t in targets if t in default_branches(cwd)]
            if hit:
                return f"`git push` to `{hit[0]}`: the flow never pushes the default branch; the owner merges PRs"
        return None
    if cmd == "az" and words[1:3] == ["repos", "pr"] and len(words) > 3 and words[3] in ("create", "update",
                                                                                           "complete"):
        return f"`az repos pr {words[3]}`: {NEVER_PR}"
    if cmd == "gh" and words[1:2] == ["pr"] and len(words) > 2 and words[2] in ("create", "edit", "merge", "ready"):
        return f"`gh pr {words[2]}`: {NEVER_PR}"
    return None


def never_list(payload: dict):
    """None, or why this call is never allowed, whoever makes it (orchestrator, subagent, plain session)."""
    tool, args, _, _ = fields(payload)
    if tool not in SHELL_TOOLS:
        return None
    command = str(args.get("command") or args.get("script") or "")
    cwd = pathlib.Path(payload.get("cwd") or ".")
    for words in never_segments(command):
        why = never_problem(words, cwd)
        if why:
            return f"Blocked by FyzxsFlow (never allowed, for any agent): {why}. Don't work around it: stop and report it."
    return None


# ---------------------------------------------------------------- Copilot CLI: who the main session is

def copilot_home() -> pathlib.Path:
    return pathlib.Path(os.environ.get("COPILOT_HOME") or pathlib.Path.home() / ".copilot")


def copilot_selected_agent(session_id: str):
    """(known, agent) for a Copilot CLI session: the last `subagent.selected` in its session state ("" = the default
    agent). known is False when the state isn't written yet (the first prompt of a `-p` session) or is unreadable."""
    if not session_id or not re.fullmatch(r"[\w-]+", session_id):
        return False, ""
    f = copilot_home() / "session-state" / session_id / "events.jsonl"
    try:
        lines = f.read_text(encoding="utf-8").splitlines()
    except OSError:
        return False, ""
    agent = ""
    for line in lines:
        if '"subagent.selected"' not in line and '"subagent.deselected"' not in line:
            continue
        try:
            e = json.loads(line)
        except ValueError:
            continue
        agent = (e.get("data") or {}).get("agentName", "") if e.get("type") == "subagent.selected" else ""
    return True, agent


def session_id(payload: dict) -> str:
    return str(payload.get("sessionId") or payload.get("session_id") or "")


# ---------------------------------------------------------------- skills that need their agent (Copilot)

def skill_agents() -> dict:
    """{skill name: the agent it runs as}, from the package prompts' `agent:` lines."""
    hooks = pathlib.Path(__file__).resolve().parent
    for prompts in (hooks.parent.parent / "prompts", hooks.parent.parent / ".apm" / "prompts"):
        if prompts.is_dir():
            out = {}
            for p in prompts.glob("*.prompt.md"):
                m = re.search(r"^agent:\s*(\S+)\s*$", p.read_text(encoding="utf-8").split("\n---", 1)[0], re.M)
                if m:
                    out[p.name.removesuffix(".prompt.md")] = m.group(1)
            return out
    return {}


def wrong_agent(skill: str, need: str, agent: str) -> str:
    return (f"/{skill} runs as the FyzxsFlow {need} agent, but this session is running as "
            f"{agent or 'the default agent'}. Select it first: `/agent {need}` in this session, or start "
            f"`copilot --agent {need}`; then run /{skill} again.")


def needs_file(root: pathlib.Path, sid: str) -> pathlib.Path:
    return root / HOME / "runs" / "_adhoc" / "copilot-sessions" / f"{sid}.json"


def skill_gate_prompt(payload: dict):
    """userPromptSubmitted: None, or why a FyzxsFlow skill can't run in this session's agent. When the session's
    agent isn't known yet, remember what the skill needs; the first tool call checks it (skill_gate_tool)."""
    if fields(payload)[2]:
        return None  # a subagent's prompt
    m = re.match(r"\s*/([\w-]+)", str(payload.get("prompt") or ""))
    need = skill_agents().get(m.group(1)) if m else None
    sid = session_id(payload)
    if not need:
        if sid and re.fullmatch(r"[\w-]+", sid):
            needs_file(project_root(payload), sid).unlink(missing_ok=True)  # a new request: the old skill's need ends
        return None
    known, agent = copilot_selected_agent(sid)
    if known:
        return None if agent == need else wrong_agent(m.group(1), need, agent)
    if sid and re.fullmatch(r"[\w-]+", sid):
        f = needs_file(project_root(payload), sid)
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps({"skill": m.group(1), "agent": need}) + "\n", encoding="utf-8")
    return None


def skill_gate_tool(payload: dict):
    """preToolUse (main session): None, or why nothing may run because the skill typed needs another agent."""
    sid = session_id(payload)
    if fields(payload)[2] or not sid or not re.fullmatch(r"[\w-]+", sid):
        return None
    f = needs_file(project_root(payload), sid)
    try:
        need = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    known, agent = copilot_selected_agent(sid)
    if not known:
        return None
    if agent == need.get("agent"):
        f.unlink(missing_ok=True)
        return None
    return "Blocked by FyzxsFlow: " + wrong_agent(need.get("skill", ""), need.get("agent", ""), agent)


# ---------------------------------------------------------------- makers stay in their lane's scope (blocks)

MAKER_ROLES = {"implementer", "tester", "iac-implementer", "e2e-implementer"}
SHELL_WRITERS = {"set-content", "out-file", "add-content", "tee", "tee-object"}
NULL_TARGETS = {"/dev/null", "$null", "nul", "/dev/stderr", "/dev/stdout"}


def engine_module(name: str):
    engine = pathlib.Path(__file__).resolve().parent.parent
    if str(engine) not in sys.path:
        sys.path.insert(0, str(engine))
    return __import__(name)


def shell_write_targets(command: str) -> list:
    """Files a shell command writes by redirect or a writer command (Set-Content, Out-File, tee)."""
    try:
        lex = shlex.shlex(command.replace("\r", "").replace("\n", " ; "), posix=True, punctuation_chars="<>|&;")
        lex.whitespace_split = True
        tokens = list(lex)
    except ValueError:
        return []
    out = []
    for i, t in enumerate(tokens):
        if t in (">", ">>", ">|", "&>", "&>>") and i + 1 < len(tokens) and not tokens[i + 1].isdigit():
            out.append(tokens[i + 1])
    for words in never_segments(command):
        cmd = words[0].lower()
        if cmd not in SHELL_WRITERS:
            continue
        rest = words[1:]
        named = [rest[j + 1] for j, w in enumerate(rest[:-1]) if w.lower() in ("-path", "-filepath", "-literalpath")]
        positional = [w for j, w in enumerate(rest) if not w.startswith("-")
                      and (j == 0 or rest[j - 1].lower() not in ("-value", "-encoding", "-inputobject"))]
        out += named or positional[:1]
    return [t for t in out if t.lower() not in NULL_TARGETS and not t.startswith("&")]


def tracked(path: pathlib.Path) -> bool:
    return bool(git_out(path.parent if path.parent.exists() else pathlib.Path("."), "ls-files", "--error-unmatch",
                        "--", str(path)))


def maker_scope(payload: dict):
    """None, or why an implementer or tester in a lane may not write there: outside its packages' Scope (lanes.py
    grant widens it), or a shell write into a tracked file (only the file-edit tools keep encoding and line ends)."""
    tool, args, _, agent_type = fields(payload)
    if agent_type not in MAKER_ROLES:
        return None
    cwd = pathlib.Path(payload.get("cwd") or ".")
    lanes = engine_module("lane_resolve")
    if tool in EDIT_TOOLS:
        for p in edited_paths(args):
            full = (cwd / p) if not pathlib.Path(p).is_absolute() else pathlib.Path(p)
            lane = lanes.find(full)
            if lane and not lanes.owns(lane, full):
                return (f"Blocked by FyzxsFlow: {lanes.relative(lane, full) or p} is outside the scope of lane "
                        f"{lane.get('group')} ({', '.join(lane.get('packages') or [])}). Don't work around it: raise "
                        f"a scope-request finding (findings.py add --kind scope-request) and stop; the Build "
                        f"Coordinator grants it (lanes.py grant) or re-plans.")
        return None
    if tool in SHELL_TOOLS:
        for t in shell_write_targets(str(args.get("command") or args.get("script") or "")):
            full = (cwd / t) if not pathlib.Path(t).is_absolute() else pathlib.Path(t)
            lane = lanes.find(full)
            if lane and lanes.owns(lane, full) and lanes.relative(lane, full).startswith(".fyzxsflow/runs/"):
                continue
            if tracked(full) or (lane and not lanes.owns(lane, full)):
                return (f"Blocked by FyzxsFlow: a shell write into {t}. Change tracked files with the file-edit tool "
                        f"(it keeps the encoding and line endings). Shell writes (>, Set-Content, Out-File, tee) go only "
                        f"to /dev/null, the run folder, or a new file in your scope.")
    return None


# ---------------------------------------------------------------- an agent's report is the agent's (orchestrator: blocks)

REPORT_PATH = re.compile(rf"(?:^|/){re.escape(HOME)}/runs/(?:[^/]+/)+reports/")


def in_place_targets(command: str) -> list:
    """Files `sed -i` / `perl -i` rewrite."""
    out = []
    for words in never_segments(command):
        if words and words[0].lower() in ("sed", "perl") and any(w.startswith("-i") or w.startswith("--in-place")
                                                                  or (w.startswith("-") and not w.startswith("--")
                                                                      and "i" in w[1:]) for w in words[1:]):
            out += [w for w in words[2:] if not w.startswith("-") and ("/" in w or "." in w)]
    return out


def report_guard(payload: dict, scoped: bool):
    """None, or why the orchestrator may not write an agent's report: a report records what that agent did; a
    missing or wrong line goes back to the agent (or is the owner's call), never the orchestrator's edit."""
    if not is_orchestrators_call(payload, scoped):
        return None
    tool, args, _, _ = fields(payload)
    if tool in EDIT_TOOLS:
        targets = edited_paths(args)
    elif tool in SHELL_TOOLS:
        command = str(args.get("command") or args.get("script") or "")
        targets = shell_write_targets(command) + in_place_targets(command)
    else:
        return None
    hit = next((t for t in targets if REPORT_PATH.search(t.replace("\\", "/"))), None)
    if not hit:
        return None
    return (f"Blocked by FyzxsFlow: {hit} is an agent's report, and only that agent writes it. Stamping "
            f"(run.py stamp) adds the model lines, and a missing model_reported is stamped unknown. Anything else "
            f"wrong in it: send it back to the agent with what to fix, or ask the owner.")


# ---------------------------------------------------------------- after an edit: encoding damage (reports, never fixes)

MOJIBAKE = re.compile("â€|Ã[\u0080-¿]|Â[ -¿]|�")


def encoding_problems(payload: dict):
    tool, args, _, _ = fields(payload)
    if tool not in EDIT_TOOLS:
        return None
    cwd = pathlib.Path(payload.get("cwd") or ".")
    found = []
    for p in edited_paths(args):
        full = (cwd / p) if not pathlib.Path(p).is_absolute() else pathlib.Path(p)
        try:
            raw = full.read_bytes()
        except OSError:
            continue
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            found.append(f"{p} is not UTF-8")
            continue
        if MOJIBAKE.search(text):
            found.append(f"{p} has mojibake (e.g. 'â€' for an em dash): text was decoded with the wrong encoding")
        if b"\r\n" in raw:
            head = git_out(full.parent, "show", f"HEAD:./{full.name}")
            if head and "\r" not in head:
                found.append(f"{p} now has CRLF line endings; it had LF")
    if not found:
        return None
    return ("FyzxsFlow found encoding damage in the file you just edited: " + "; ".join(found)
            + ". Fix it now with the file-edit tool (restore the original characters and line endings), and say so "
              "in your report.")

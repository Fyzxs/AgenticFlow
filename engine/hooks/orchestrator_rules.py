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
    tool, args, agent_id, agent_type = fields(payload)
    if agent_id:
        return None  # a subagent (a dispatched orchestrator too)
    if not scoped and agent_type != ROLE:
        return None  # not an orchestrator session (a plain session, or `claude --agent <other>`)
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


def is_orchestrators_call(payload: dict, scoped: bool) -> bool:
    _, _, agent_id, agent_type = fields(payload)
    return not agent_id and (scoped or agent_type == ROLE)


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

"""PreToolUse hook (Bash, PowerShell): refuse killing processes by NAME.

Killing by image name (taskkill /IM dotnet.exe, Stop-Process -Name node, pkill vite, ...) kills every
process with that name: the owner's own dev servers, other worktrees' builds, other sessions' test runs.
Origin: it once took down the owner's running API after the written "kill by PID"
rule had already recurred, so it is mechanized here.

Kill only processes you started, by PID: record the PID when you start a process, then
`Stop-Process -Id <pid>` / `taskkill /PID <pid> /T` / `kill <pid>`. To find a PID for a port, use
`Get-NetTCPConnection -LocalPort <port>` (PowerShell) or `netstat -ano | findstr :<port>`.

Exit code 2 blocks the tool call and shows stderr to the model.
"""

import json
import re
import sys

FLAGS = re.IGNORECASE

PATTERNS = [
    # taskkill /IM name, //IM name (Git Bash), -im name
    ("taskkill by image name", re.compile(r"\btaskkill(?:\.exe)?\b[^|;&\n]*?(?:^|\s)(?:/{1,2}|-)im\b", FLAGS)),
    # Stop-Process -Name / -ProcessName (and the spps / kill aliases)
    ("Stop-Process by name", re.compile(
        r"\b(?:Stop-Process|spps)\b[^|;&\n]*?\s-(?:Name|ProcessName|n)\b", FLAGS)),
    # Stop-Process with a positional non-numeric argument is -Name: Stop-Process node
    ("Stop-Process by name (positional)", re.compile(
        r"\b(?:Stop-Process|spps)\s+(?!-)(?![0-9$(@])[A-Za-z_][\w.*-]*", FLAGS)),
    # Get-Process <name> | Stop-Process  (no -Id)
    ("Get-Process by name piped to Stop-Process", re.compile(
        r"\b(?:Get-Process|gps|ps)\b(?![^|]*\s-Id\b)[^|]*\|\s*(?:Stop-Process|spps|kill)\b", FLAGS)),
    # pkill / killall
    # pkill / killall in command position (start, after ; & | ( or sudo/xargs) — not as an argument to grep etc.
    ("pkill/killall", re.compile(
        r"(?:^\s*|[;&|(]\s*|\bsudo\s+|\bxargs\s+(?:-\S+\s+)*)(?:pkill|killall)(?:\.exe)?\b", FLAGS | re.MULTILINE)),
    # kill $(pgrep name) / pgrep name | xargs kill
    ("kill via pgrep", re.compile(r"\bpgrep\b.*\bkill\b|\bkill\b[^\n]*\$\(\s*pgrep\b", FLAGS)),
    # wmic process where name=... delete/terminate
    ("wmic by name", re.compile(r"\bwmic\b[^\n]*\bprocess\b[^\n]*\bname\s*=.*\b(?:delete|terminate)\b", FLAGS)),
]


def violation(command: str):
    for label, pattern in PATTERNS:
        if pattern.search(command):
            return label
    return None


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (ValueError, OSError):
        return 0
    if payload.get("tool_name") not in ("Bash", "PowerShell"):
        return 0
    command = (payload.get("tool_input") or {}).get("command") or ""
    label = violation(command)
    if label is None:
        return 0
    sys.stderr.write(
        "Blocked by fyzxsflow engine/hooks/block_kill_by_name.py (" + label + "): killing by process NAME also kills the "
        "owner's own dev servers and other worktrees' processes. "
        "Kill only processes you started, by PID: Stop-Process -Id <pid> / taskkill /PID <pid> /T / kill <pid>. "
        "Find the PID for a port with Get-NetTCPConnection -LocalPort <port>. If a stray process you did not "
        "start must die, ask the owner.\n"
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())

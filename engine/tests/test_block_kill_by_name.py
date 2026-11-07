"""Pinned block/allow cases for block-kill-by-name.py. Run: python .claude/hooks/test_block_kill_by_name.py"""

import importlib.util
import json
import pathlib
import subprocess
import sys

HOOK = pathlib.Path(__file__).resolve().parent.parent / "hooks" / "block_kill_by_name.py"
spec = importlib.util.spec_from_file_location("hook", HOOK)
hook = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hook)

BLOCK = [
    "taskkill /IM dotnet.exe /F",
    "taskkill //IM node.exe //F",
    "taskkill /F /im vite.exe",
    "Stop-Process -Name dotnet -Force",
    "Stop-Process -ProcessName node",
    "Stop-Process node",
    "spps -n dotnet",
    "Get-Process dotnet | Stop-Process -Force",
    "Get-Process -Name node | Stop-Process",
    "ps node | kill",
    "pkill -f vite",
    "killall node",
    "sleep 1; pkill dotnet",
    "kill $(pgrep node)",
    "pgrep -f vite | xargs kill",
    "wmic process where name='dotnet.exe' delete",
]

ALLOW = [
    "taskkill /PID 1234 /T /F",
    "Stop-Process -Id 1234 -Force",
    "Stop-Process -Id $pid",
    "Stop-Process $proc",
    "Stop-Process 1234",
    "Get-Process -Id 1234 | Stop-Process",
    "kill 1234",
    "kill -9 $SERVER_PID",
    "Get-Process dotnet",
    "Get-NetTCPConnection -LocalPort 5175",
    "git commit -m 'stop the reaper from killing tenants'",
    "grep -rn killall docs/",
    "dotnet test csharp/src/TcgHoard.CI.slnf",
]


def run_hook(command, tool="Bash"):
    proc = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps({"tool_name": tool, "tool_input": {"command": command}}),
        capture_output=True,
        text=True,
    )
    return proc.returncode


def main() -> int:
    failures = []
    for c in BLOCK:
        if hook.violation(c) is None:
            failures.append("should BLOCK: " + c)
    for c in ALLOW:
        label = hook.violation(c)
        if label is not None:
            failures.append("should ALLOW: " + c + "  (matched " + label + ")")
    # end-to-end through stdin, both tools, plus a non-matching tool
    if run_hook("taskkill /IM dotnet.exe", "Bash") != 2:
        failures.append("e2e Bash block did not exit 2")
    if run_hook("Stop-Process -Name node", "PowerShell") != 2:
        failures.append("e2e PowerShell block did not exit 2")
    if run_hook("Stop-Process -Id 42", "PowerShell") != 0:
        failures.append("e2e PowerShell allow did not exit 0")
    if run_hook("taskkill /IM dotnet.exe", "Read") != 0:
        failures.append("e2e other tool should pass through")
    for f in failures:
        print("FAIL", f)
    print(f"{len(BLOCK)} block + {len(ALLOW)} allow + 4 e2e cases; {len(failures)} failures")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

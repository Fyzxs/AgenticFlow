"""Execute a Build & Test Runner mode from .fyzxsflow/config.json.

  python -I engine/runner.py <mode> [--run <run-dir>] [--scope <scope>] [--config <path>]

For each step in the mode: run its command, write its output to a log, record its exit code. Services the
mode lists are started first (their PIDs recorded) and stopped by PID afterwards, never by name.
Prints a compact summary and writes runner/<invocation>.json in the run folder, with the commit it tested and
whether product files had uncommitted changes ("commit", "dirty"), so a PR can show its evidence covers it.
Exit code: 0 if every step passed, 1 otherwise, 2 on a configuration error, 3 when the mode has destructive
steps and neither --allow-destructive nor the mode's owner-set "allow_destructive" permits them (nothing runs),
4 when another mode holding the same "lock" is still running (nothing runs).

A step passes when it exits 0 and its output checks hold. Tools that exit 0 while reporting failures need them:
  "fail_if_output": "<regex>"   the step fails if any output line matches (e.g. "[1-9][0-9]* failed")
  "expect_output":  "<regex>"   the step fails unless some output line matches
A step that runs past "timeout_s" (default 3600; 0 means no limit) is stopped with its whole process tree (by PID)
and fails with exit 124.

A step (or a whole mode) marked "destructive": true wipes or replaces local state: a database reset, dropping
seeded data. A mode marked "not_applicable": "<why>" is a declared non-capability and exits 0 without running.
A mode with no steps (and no "not_applicable") is a configuration error: exit 2, nothing runs.
A service with a "port" fails the mode if that port is already answering before it starts (a stale process
would otherwise be taken for it), or if the started process exits before the port answers.
A mode with "lock": "<name>" (e.g. "local-db") refuses to start while another mode holding that lock runs, so two
writers never share a resource. Locks are shared by every checkout of the repo (the git common directory), so
parallel lanes and parallel runs wait for each other too.

A mode's "network" says what it may reach (recorded in the summary):
  "connected"  it may call the external (never production) services the project approved (.fyzxsflow/e2e.md);
  "airplane"   everything it needs lives on this machine. The network is never switched off; instead every step
               and service gets proxy settings pointing at a closed local port, container starts must pass
               "--pull never" (exit 2 otherwise, nothing runs), and an egress monitor (engine/egress.py) fails the
               mode if any process the mode started connects to an address that isn't loopback or listed in the
               mode's "offline_allow" (CIDRs, or host names for NO_PROXY). The summary lists what it saw ("egress").

--run takes a run folder or a bare run id (resolved under .fyzxsflow/runs/active/).

config.json shape (see templates/project/.fyzxsflow/config.json):
  { "modes": { "<mode>": { "steps": [ {"name": "build", "run": "dotnet build {scope}", "cwd": ".",
                                       "env": {"K": "V"}, "timeout_s": 1800, "fail_if_output": "..."} ],
                           "default_scope": "...", "services": ["api"], "continue_on_failure": false,
                           "lock": "local-db", "network": "airplane", "offline_allow": ["172.17.0.0/16"] } },
    "services": { "api": { "start": "...", "port": 5000, "cwd": ".", "ready_timeout_s": 90 } } }
"""

import argparse
import datetime
import json
import os
import pathlib
import re
import socket
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from layout import HOME, PACKAGE  # noqa: E402
import egress  # noqa: E402
import time

DEFAULT_TIMEOUT_S = 3600  # a step without "timeout_s"; "timeout_s": 0 means no limit


def load_config(path: pathlib.Path) -> dict:
    if not path.exists():
        raise SystemExit(f"config not found: {path} (run the Repo Cartographer: fyzxsflow-init)")
    return json.loads(path.read_text(encoding="utf-8"))


def port_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            return True
    except OSError:
        return False


def wait_for_port(port: int, timeout_s: float, proc=None):
    """None once the port answers, else why not. Stops waiting as soon as the started process exits."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if proc is not None and proc.poll() is not None:
            return f"exited with code {proc.returncode} before it was ready"
        if port_open(port):
            return None
        time.sleep(0.5)
    return f"not ready on port {port}"


def start_service(name: str, spec: dict, root: pathlib.Path, logdir: pathlib.Path, extra_env=None, monitor=None):
    """Returns (proc or None, log or None, error or None)."""
    port = int(spec["port"]) if spec.get("port") else None
    if port and port_open(port):
        # Something already answers: readiness would be judged on that process, not the one we start.
        return None, None, f"port {port} already in use before service '{name}' started (a stale process?)"
    log = open(logdir / f"service-{name}.log", "w", encoding="utf-8")
    env = {**os.environ, **(extra_env or {})}
    proc = subprocess.Popen(spec["start"], shell=True, cwd=root / spec.get("cwd", "."), env=env,
                            stdout=log, stderr=subprocess.STDOUT, **group_kwargs())
    if monitor is not None:
        monitor.watch(proc.pid, f"service {name}")
    error = None
    if port:
        why = wait_for_port(port, float(spec.get("ready_timeout_s", 90)), proc)
        if why:
            error = f"service '{name}' {why} (see service-{name}.log)"
    return proc, log, error


def group_kwargs() -> dict:
    """Start a child in its own process group, so its whole tree can be stopped by its PID."""
    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def stop_tree(proc) -> None:
    """Stop a process we started, by its PID, with every process it started."""
    if proc.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)
    else:
        import signal
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    try:
        proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        proc.kill()


def output_check(step: dict, logpath: pathlib.Path):
    """None when the step's output checks hold, else why not. Reads the log line by line (logs can be huge)."""
    fail_rx = re.compile(step["fail_if_output"]) if step.get("fail_if_output") else None
    expect_rx = re.compile(step["expect_output"]) if step.get("expect_output") else None
    if not (fail_rx or expect_rx):
        return None
    seen_expected = False
    with open(logpath, encoding="utf-8", errors="replace") as log:
        next(log, None)  # the "$ command" header line
        for n, line in enumerate(log, start=2):
            if fail_rx and fail_rx.search(line):
                return f"output matched fail_if_output at log line {n}: {line.strip()[:160]}"
            if expect_rx and not seen_expected and expect_rx.search(line):
                seen_expected = True
                if not fail_rx:
                    break
    if expect_rx and not seen_expected:
        return f"no output line matched expect_output /{step['expect_output']}/"
    return None


def run_step(step: dict, scope: str, root: pathlib.Path, logpath: pathlib.Path, extra_env=None, monitor=None) -> dict:
    command = step["run"].replace("{scope}", scope)
    env = os.environ.copy()
    env.update({k: str(v) for k, v in (step.get("env") or {}).items()})
    env.update(extra_env or {})  # airplane proxy settings win over a step's own
    started = time.monotonic()
    with open(logpath, "w", encoding="utf-8") as log:
        log.write(f"$ {command}\n\n")
        log.flush()
        proc = subprocess.Popen(command, shell=True, cwd=root / step.get("cwd", "."), env=env,
                                stdout=log, stderr=subprocess.STDOUT, **group_kwargs())
        if monitor is not None:
            monitor.watch(proc.pid, f"step {step['name']}")
        limit = step.get("timeout_s", DEFAULT_TIMEOUT_S) or None  # 0 = no limit
        try:
            code = proc.wait(timeout=limit)
        except subprocess.TimeoutExpired:
            stop_tree(proc)
            log.write(f"\n[fyzxsflow runner] timed out after {limit}s; "
                      f"stopped process tree of PID {proc.pid}\n")
            code = 124
        finally:
            if monitor is not None:
                monitor.unwatch(proc.pid)
    check = output_check(step, logpath) if code == 0 else None
    result = {"name": step["name"], "command": command, "exit": code, "passed": code == 0 and check is None,
              "seconds": round(time.monotonic() - started, 1), "log": str(logpath)}
    if check:
        result["check"] = check
    return result


def pid_alive(pid: int) -> bool:
    if os.name == "nt":
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
            return code.value == 259  # STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)  # signal 0 only checks; never sent on POSIX
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def lock_dir(root: pathlib.Path) -> pathlib.Path:
    """One lock folder for every checkout of the repo (lanes and parallel runs are worktrees): the git common
    directory when there is one, else the checkout's own run folder."""
    out = subprocess.run(["git", "rev-parse", "--git-common-dir"], cwd=root, capture_output=True, text=True)
    if out.returncode == 0 and out.stdout.strip():
        common = pathlib.Path(out.stdout.strip())
        return (common if common.is_absolute() else root / common).resolve() / "fyzxsflow-locks"
    return root / HOME / "runs" / "_adhoc" / "locks"


def take_lock(root: pathlib.Path, name: str, mode: str):
    """Returns the lock file on success, or the holder's description when another live runner holds it."""
    path = lock_dir(root) / f"{name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        try:
            holder = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            holder = {}
        if holder.get("pid") and holder["pid"] != os.getpid() and pid_alive(int(holder["pid"])):
            return None, f"mode '{holder.get('mode')}' (runner PID {holder['pid']}, since {holder.get('since')})"
    path.write_text(json.dumps({"pid": os.getpid(), "mode": mode,
                                "since": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")}),
                    encoding="utf-8")
    return path, None


def tested_tree(root: pathlib.Path) -> dict:
    """What was tested: the commit, and whether product files outside the flow's own folders had uncommitted changes."""
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True)
    if head.returncode != 0:
        return {"commit": None, "dirty": None}
    status = subprocess.run(["git", "status", "--porcelain", "--untracked-files=all", "--", ".",
                             f":(exclude){HOME}", ":(exclude).claude", ":(exclude).github"],
                            cwd=root, capture_output=True, text=True)
    return {"commit": head.stdout.strip(), "dirty": bool(status.stdout.strip())}


def resolve_run(root: pathlib.Path, value):
    if not value:
        return root / HOME / "runs" / "_adhoc"
    path = pathlib.Path(value)
    if path.exists() or len(path.parts) > 1:
        return path
    active = root / HOME / "runs" / "active" / value
    if active.is_dir():
        return active
    raise SystemExit(f"--run {value}: not a folder and not an active run id (see run.py list)")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("mode")
    p.add_argument("--run", help="run folder (default: .fyzxsflow/runs/_adhoc)")
    p.add_argument("--scope", help="replaces {scope} in step commands")
    p.add_argument("--config", default=f"{HOME}/config.json")
    p.add_argument("--root", default=".", help="repo root (default: current directory)")
    p.add_argument("--allow-destructive", action="store_true",
                   help="run steps marked destructive; the Orchestrator passes this only with the owner's approval")
    args = p.parse_args(argv)

    root = pathlib.Path(args.root).resolve()
    config = load_config(root / args.config)
    mode = (config.get("modes") or {}).get(args.mode)
    if mode is None:
        print(f"unknown mode '{args.mode}'. Modes: {', '.join(sorted(config.get('modes') or {}))}", file=sys.stderr)
        return 2
    if mode.get("not_applicable"):
        print(f"mode '{args.mode}' does not apply to this repo: {mode['not_applicable']}")
        return 0
    if not mode.get("steps"):
        print(f"mode '{args.mode}' has no steps: give it steps, or mark it \"not_applicable\": \"<why>\" "
              "in config.json", file=sys.stderr)
        return 2
    destructive = [s["name"] for s in mode.get("steps", []) if s.get("destructive") or mode.get("destructive")]
    if destructive and not (args.allow_destructive or mode.get("allow_destructive")):
        # Checked before anything runs, so a refused mode never half-executes.
        print(f"refused: mode '{args.mode}' has destructive steps ({', '.join(destructive)}) that wipe or replace "
              "local state. Run it with --allow-destructive only after the owner approves, or the owner can set "
              "\"allow_destructive\": true on this mode in config.json.", file=sys.stderr)
        return 3
    network = mode.get("network")
    if network not in (None, "connected", "airplane"):
        print(f"mode '{args.mode}': \"network\" must be \"connected\" or \"airplane\", not {network!r}",
              file=sys.stderr)
        return 2
    extra_env, monitor = None, None
    if network == "airplane":
        commands = [(f"step '{s['name']}'", s.get("run", "")) for s in mode["steps"]]
        commands += [(f"service '{n}'", ((config.get("services") or {}).get(n) or {}).get("start", ""))
                     for n in mode.get("services", [])]
        problems = [f"{where} {why}" for where, cmd in commands if (why := egress.docker_pull_problem(cmd))]
        if problems:
            print(f"refused: airplane mode '{args.mode}': " + "; ".join(problems), file=sys.stderr)
            return 2
        allow = mode.get("offline_allow") or []
        extra_env = egress.proxy_env([a for a in allow if not egress.allowed_networks([a])])
    if mode.get("draft"):
        print(f"note: mode '{args.mode}' is marked draft in config.json; the owner has not confirmed it")
    scope = args.scope or mode.get("default_scope", "")
    run = resolve_run(root, args.run)
    lock = None
    if mode.get("lock"):
        lock, holder = take_lock(root, mode["lock"], args.mode)
        if lock is None:
            print(f"refused: lock '{mode['lock']}' is held by {holder}. Wait for it to finish; never run two "
                  f"'{mode['lock']}' modes at once.", file=sys.stderr)
            return 4
    invocation = f"{args.mode}-{datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d-%H%M%S-%f')}"
    logdir = run / "runner" / invocation
    logdir.mkdir(parents=True, exist_ok=True)

    services, results, service_errors, seen = [], [], [], []
    if network == "airplane":
        monitor = egress.Monitor(allow=mode.get("offline_allow") or []).start()
    try:
        for name in mode.get("services", []):
            spec = (config.get("services") or {}).get(name)
            if spec is None:
                print(f"mode '{args.mode}' lists unknown service '{name}'", file=sys.stderr)
                return 2
            proc, log, error = start_service(name, spec, root, logdir, extra_env, monitor)
            if proc is not None:
                services.append((proc, log))
            if error:
                service_errors.append(error)
                break
        if not service_errors:
            for i, step in enumerate(mode.get("steps", []), start=1):
                result = run_step(step, scope, root, logdir / f"{i:02d}-{step['name']}.log", extra_env, monitor)
                results.append(result)
                if not result["passed"] and not mode.get("continue_on_failure", False):
                    break
    finally:
        if monitor is not None:
            seen = monitor.stop()  # before the services stop, so their connections are still in the table
        for proc, log in services:
            stop_tree(proc)
            log.close()
        if lock is not None:
            lock.unlink(missing_ok=True)

    skipped = [s["name"] for s in mode.get("steps", [])[len(results):]]
    airplane_ok = monitor is None or not (seen or monitor.errors)
    passed = not service_errors and all(r["passed"] for r in results) and not skipped and airplane_ok
    summary = {"mode": args.mode, "scope": scope or "all", "result": "pass" if passed else "fail",
               "steps": results, "skipped": skipped, "service_errors": service_errors, "network": network,
               **tested_tree(root)}
    if monitor is not None:
        summary["egress"] = seen
        if monitor.errors:
            summary["egress_errors"] = monitor.errors
    (run / "runner" / f"{invocation}.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8",
                                                         newline="\n")

    print(f"mode={args.mode} scope={summary['scope']} result={summary['result']}")
    for r in results:
        print(f"  {r['name']} exit={r['exit']} ({r['seconds']}s)" + (f" FAILED CHECK: {r['check']}" if r.get("check") else ""))
    for name in skipped:
        print(f"  {name} skipped (an earlier step failed)")
    for err in service_errors:
        print(f"  {err}")
    for c in seen:
        print(f"  AIRPLANE VIOLATION: {c['process']} (PID {c['pid']}, {c['during']}) connected to {c['remote']}")
    if monitor is not None and monitor.errors:
        print(f"  airplane check could not run, so the mode is not verified: {'; '.join(monitor.errors)}")
    print(f"summary: {run / 'runner' / (invocation + '.json')}")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())

"""Execute a Build & Test Runner mode from .agentflow/config.json.

  python -I engine/runner.py <mode> [--run <run-dir>] [--scope <scope>] [--config <path>]

For each step in the mode: run its command, write its output to a log, record its exit code. Services the
mode lists are started first (their PIDs recorded) and stopped by PID afterwards, never by name.
Prints a compact summary and writes runner/<invocation>.json in the run folder.
Exit code: 0 if every step exited 0, 1 otherwise, 2 on a configuration error.

config.json shape (see templates/project/.agentflow/config.json):
  { "modes": { "<mode>": { "steps": [ {"name": "build", "run": "dotnet build {scope}", "cwd": ".",
                                       "env": {"K": "V"}, "timeout_s": 1800} ],
                           "default_scope": "...", "services": ["api"], "continue_on_failure": false } },
    "services": { "api": { "start": "...", "port": 5000, "cwd": ".", "ready_timeout_s": 90 } } }
"""

import argparse
import datetime
import json
import os
import pathlib
import socket
import subprocess
import sys
import time


def load_config(path: pathlib.Path) -> dict:
    if not path.exists():
        raise SystemExit(f"config not found: {path} (run the Repo Cartographer: agentflow-init)")
    return json.loads(path.read_text(encoding="utf-8"))


def wait_for_port(port: int, timeout_s: float) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return True
        except OSError:
            time.sleep(0.5)
    return False


def start_service(name: str, spec: dict, root: pathlib.Path, logdir: pathlib.Path):
    log = open(logdir / f"service-{name}.log", "w", encoding="utf-8")
    kwargs = {}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    proc = subprocess.Popen(spec["start"], shell=True, cwd=root / spec.get("cwd", "."),
                            stdout=log, stderr=subprocess.STDOUT, **kwargs)
    ready = True
    if spec.get("port"):
        ready = wait_for_port(int(spec["port"]), float(spec.get("ready_timeout_s", 90)))
    return proc, log, ready


def stop_service(proc) -> None:
    """Stop a service we started, by its PID (and its child processes)."""
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


def run_step(step: dict, scope: str, root: pathlib.Path, logpath: pathlib.Path) -> dict:
    command = step["run"].replace("{scope}", scope)
    env = os.environ.copy()
    env.update({k: str(v) for k, v in (step.get("env") or {}).items()})
    started = time.monotonic()
    with open(logpath, "w", encoding="utf-8") as log:
        log.write(f"$ {command}\n\n")
        log.flush()
        try:
            code = subprocess.run(command, shell=True, cwd=root / step.get("cwd", "."), env=env,
                                  stdout=log, stderr=subprocess.STDOUT,
                                  timeout=step.get("timeout_s")).returncode
        except subprocess.TimeoutExpired:
            log.write(f"\n[agentflow runner] timed out after {step.get('timeout_s')}s\n")
            code = 124
    return {"name": step["name"], "command": command, "exit": code,
            "seconds": round(time.monotonic() - started, 1), "log": str(logpath)}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("mode")
    p.add_argument("--run", help="run folder (default: .agentflow/runs/_adhoc)")
    p.add_argument("--scope", help="replaces {scope} in step commands")
    p.add_argument("--config", default=".agentflow/config.json")
    p.add_argument("--root", default=".", help="repo root (default: current directory)")
    args = p.parse_args(argv)

    root = pathlib.Path(args.root).resolve()
    config = load_config(root / args.config)
    mode = (config.get("modes") or {}).get(args.mode)
    if mode is None:
        print(f"unknown mode '{args.mode}'. Modes: {', '.join(sorted(config.get('modes') or {}))}", file=sys.stderr)
        return 2
    if mode.get("draft"):
        print(f"note: mode '{args.mode}' is marked draft in config.json; the owner has not confirmed it")
    scope = args.scope or mode.get("default_scope", "")
    run = pathlib.Path(args.run) if args.run else root / ".agentflow" / "runs" / "_adhoc"
    invocation = f"{args.mode}-{datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d-%H%M%S-%f')}"
    logdir = run / "runner" / invocation
    logdir.mkdir(parents=True, exist_ok=True)

    services, results, service_errors = [], [], []
    try:
        for name in mode.get("services", []):
            spec = (config.get("services") or {}).get(name)
            if spec is None:
                print(f"mode '{args.mode}' lists unknown service '{name}'", file=sys.stderr)
                return 2
            proc, log, ready = start_service(name, spec, root, logdir)
            services.append((proc, log))
            if not ready:
                service_errors.append(f"service '{name}' not ready on port {spec.get('port')} (see service-{name}.log)")
        if not service_errors:
            for i, step in enumerate(mode.get("steps", []), start=1):
                result = run_step(step, scope, root, logdir / f"{i:02d}-{step['name']}.log")
                results.append(result)
                if result["exit"] != 0 and not mode.get("continue_on_failure", False):
                    break
    finally:
        for proc, log in services:
            stop_service(proc)
            log.close()

    skipped = [s["name"] for s in mode.get("steps", [])[len(results):]]
    passed = not service_errors and all(r["exit"] == 0 for r in results) and not skipped
    summary = {"mode": args.mode, "scope": scope or "all", "result": "pass" if passed else "fail",
               "steps": results, "skipped": skipped, "service_errors": service_errors}
    (run / "runner" / f"{invocation}.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"mode={args.mode} scope={summary['scope']} result={summary['result']}")
    for r in results:
        print(f"  {r['name']} exit={r['exit']} ({r['seconds']}s)")
    for name in skipped:
        print(f"  {name} skipped (an earlier step failed)")
    for err in service_errors:
        print(f"  {err}")
    print(f"summary: {run / 'runner' / (invocation + '.json')}")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())

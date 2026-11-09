"""Run the deterministic gates (linters, scanners, custom scripts) declared in .fyzxsflow/gates.json.

  python -I engine/gates.py --stage <quick|ci|extreme|pre-pr> [--run <run-dir>] [--changed <path> ...]
  python -I engine/gates.py --stage extreme --update-baseline <gate>      # owner action: accept current results

A gate runs when it is enabled, lists the requested stage, and (if it declares `paths`) at least one
changed path matches. Each gate's output is normalised into one shape:
  {gate, rule, level (error|warning|note), path, line, message, fingerprint}
Results whose fingerprint is in .fyzxsflow/baselines/<gate>.json are counted as baseline, not new.
A gate fails when its process could not run correctly, or when it has a new result at or above `fail_on`.
Writes gates/<invocation>.json (summary) and gates/<invocation>/<gate>.log in the run folder.
result: pass | fail | empty (no gate was selected, so nothing was checked; never reported as a pass).
Exit 0 = every selected gate passed (or none was selected), 1 = at least one failed, 2 = configuration error.

Dependency and advisory scanners read a live feed, so their results change without any file changing: don't
scope them with `paths`; run them at every pre-pr, report-only (`fail_on: never`) or baselined.

gates.json shape (see templates/project/.fyzxsflow/gates.md):
  { "gates": [ { "name": "semgrep", "enabled": true, "stages": ["extreme", "pre-pr"],
                 "run": "semgrep scan --config auto --sarif --output {out}", "format": "sarif",
                 "fail_on": "error", "ok_exit_codes": [0, 1], "paths": ["src/**"], "timeout_s": 1800 } ] }
  format: "sarif" (the command writes SARIF to {out}) or "exit" (pass/fail by exit code only).
  fail_on: "error" | "warning" | "note" | "never" (report only).
"""

import argparse
import datetime
import hashlib
import json
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from layout import HOME, PACKAGE  # noqa: E402

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from docs_check import glob_to_regex  # noqa: E402

LEVELS = {"note": 1, "warning": 2, "error": 3}
SARIF_LEVEL = {"error": "error", "warning": "warning", "note": "note", "none": "note"}


def fingerprint(gate: str, rule: str, path: str, message: str) -> str:
    # Line numbers are left out on purpose, so unrelated edits above a result don't make it "new".
    return hashlib.sha256(f"{gate}|{rule}|{path}|{message.strip()}".encode("utf-8")).hexdigest()[:16]


def parse_sarif(gate: str, path: pathlib.Path) -> list:
    data = json.loads(path.read_text(encoding="utf-8"))
    results = []
    for run in data.get("runs", []):
        for r in run.get("results", []):
            loc = ((r.get("locations") or [{}])[0].get("physicalLocation") or {})
            uri = (loc.get("artifactLocation") or {}).get("uri", "")
            uri = uri.replace("file:///", "").replace("\\", "/")
            line = (loc.get("region") or {}).get("startLine")
            rule = r.get("ruleId") or (r.get("rule") or {}).get("id") or "unknown"
            message = (r.get("message") or {}).get("text", "")
            level = SARIF_LEVEL.get(r.get("level", "warning"), "warning")
            results.append({"gate": gate, "rule": rule, "level": level, "path": uri, "line": line,
                            "message": message, "fingerprint": fingerprint(gate, rule, uri, message)})
    return results


def selected(gate: dict, stage: str, changed: list) -> bool:
    if not gate.get("enabled", True) or stage not in gate.get("stages", []):
        return False
    globs = gate.get("paths")
    if not globs or not changed:
        return True
    rxs = [glob_to_regex(g) for g in globs]
    return any(rx.match(c) for rx in rxs for c in changed)


def run_gate(gate: dict, root: pathlib.Path, outdir: pathlib.Path) -> dict:
    name = gate["name"]
    out = outdir / f"{name}.sarif"
    command = gate["run"].replace("{out}", str(out))
    log = outdir / f"{name}.log"
    with open(log, "w", encoding="utf-8") as f:
        f.write(f"$ {command}\n\n")
        f.flush()
        try:
            code = subprocess.run(command, shell=True, cwd=root / gate.get("cwd", "."), stdout=f,
                                  stderr=subprocess.STDOUT, timeout=gate.get("timeout_s")).returncode
        except subprocess.TimeoutExpired:
            f.write(f"\n[fyzxsflow gates] timed out after {gate.get('timeout_s')}s\n")
            code = 124
    fmt = gate.get("format", "exit")
    ok_codes = gate.get("ok_exit_codes", [0])
    entry = {"gate": name, "exit": code, "log": str(log), "format": fmt, "results": [], "error": None}
    if fmt == "sarif":
        if code not in ok_codes:
            entry["error"] = f"exited {code}, which is not in ok_exit_codes {ok_codes}"
        elif not out.exists():
            entry["error"] = "no SARIF output was written to {out}"
        else:
            try:
                entry["results"] = parse_sarif(name, out)
            except (ValueError, KeyError) as e:
                entry["error"] = f"could not parse SARIF: {e}"
    elif fmt == "exit":
        if code not in ok_codes:
            entry["results"] = [{"gate": name, "rule": "exit-code", "level": "error", "path": "", "line": None,
                                 "message": f"exited {code}", "fingerprint": fingerprint(name, "exit-code", "", str(code))}]
    else:
        entry["error"] = f"unknown format '{fmt}'"
    return entry


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--stage", required=True)
    p.add_argument("--run", help="run folder (default: .fyzxsflow/runs/_adhoc)")
    p.add_argument("--changed", nargs="*", default=[], help="changed paths; gates with `paths` run only if one matches")
    p.add_argument("--root", default=".")
    p.add_argument("--config", default=f"{HOME}/gates.json")
    p.add_argument("--update-baseline", metavar="GATE", help="accept the gate's current results as baseline (owner action)")
    args = p.parse_args(argv)

    root = pathlib.Path(args.root).resolve()
    cfg_path = root / args.config
    if not cfg_path.exists():
        print(f"no gates registry at {cfg_path}; nothing to run")
        return 0
    gates = json.loads(cfg_path.read_text(encoding="utf-8")).get("gates", [])
    names = [g.get("name") for g in gates]
    if len(set(names)) != len(names) or not all(names):
        print("every gate needs a unique name", file=sys.stderr)
        return 2
    for g in gates:
        if g.get("fail_on", "error") not in (*LEVELS, "never"):
            print(f"gate '{g['name']}': fail_on must be error, warning, note or never", file=sys.stderr)
            return 2
    chosen = [g for g in gates if selected(g, args.stage, args.changed)]
    if args.update_baseline:
        chosen = [g for g in gates if g["name"] == args.update_baseline]
        if not chosen:
            print(f"unknown gate '{args.update_baseline}'", file=sys.stderr)
            return 2

    run = pathlib.Path(args.run) if args.run else root / HOME / "runs" / "_adhoc"
    invocation = f"{args.stage}-{datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d-%H%M%S-%f')}"
    outdir = run / "gates" / invocation
    outdir.mkdir(parents=True, exist_ok=True)
    baselines = root / HOME / "baselines"

    summary, failed = [], False
    for gate in chosen:
        entry = run_gate(gate, root, outdir)
        base_file = baselines / f"{gate['name']}.json"
        if args.update_baseline:
            baselines.mkdir(parents=True, exist_ok=True)
            base_file.write_text(json.dumps(sorted({r["fingerprint"] for r in entry["results"]}), indent=2), encoding="utf-8")
            print(f"baseline for {gate['name']}: {len(entry['results'])} results accepted -> {base_file}")
            return 0 if not entry["error"] else 1
        known = set(json.loads(base_file.read_text(encoding="utf-8"))) if base_file.exists() else set()
        new = [r for r in entry["results"] if r["fingerprint"] not in known]
        threshold = gate.get("fail_on", "error")
        blocking = [] if threshold == "never" else [r for r in new if LEVELS[r["level"]] >= LEVELS[threshold]]
        entry.update({"new": new, "baseline_count": len(entry["results"]) - len(new),
                      "blocking_count": len(blocking), "passed": not entry["error"] and not blocking})
        del entry["results"]
        failed = failed or not entry["passed"]
        summary.append(entry)

    skipped = [g["name"] for g in gates if g not in chosen]
    # A stage that selected nothing proved nothing: it is "empty", never "pass".
    outcome = "fail" if failed else "pass" if summary else "empty"
    declared = [g["name"] for g in gates if g.get("enabled", True) and args.stage in g.get("stages", [])]
    result = {"stage": args.stage, "result": outcome, "gates": summary, "not_selected": skipped,
              "declared_for_stage": declared}
    (run / "gates" / f"{invocation}.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"stage={args.stage} result={result['result']} gates={len(summary)}")
    if outcome == "empty":
        why = (f"{len(declared)} gate(s) declare this stage but none matched the changed paths: {', '.join(declared)}"
               if declared else "no gate declares this stage")
        print(f"  nothing ran: {why}")
    for e in summary:
        counts = {lvl: sum(1 for r in e["new"] if r["level"] == lvl) for lvl in ("error", "warning", "note")}
        status = "pass" if e["passed"] else "FAIL"
        detail = e["error"] or f"new: {counts['error']} error, {counts['warning']} warning, {counts['note']} note; baseline: {e['baseline_count']}"
        print(f"  {e['gate']} {status} exit={e['exit']} — {detail}")
    print(f"summary: {run / 'gates' / (invocation + '.json')}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

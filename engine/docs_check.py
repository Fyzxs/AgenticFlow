"""Mechanical checks on a repo's fyzxsflow docs (.fyzxsflow/**/*.md, excluding runs/).

  python -I engine/docs_check.py [--root <repo>]

Fails when:
  - a backticked repo path cited in a doc does not exist (a trailing :line is ignored);
  - a segment doc's `paths:` glob matches no tracked file;
  - a segment's context pack (the doc plus its `pack:` files) exceeds docs.pack_budget_kb in config.json;
  - a doc still contains UNRESOLVED (reported as a warning unless --strict);
  - config.json lacks a Runner capability the repo needs: quick, ci and extreme always; db-migrate, db-verify,
    db-reset and seed when the profile lists a Database surface; http when it lists an API. A capability that
    truly doesn't apply is declared with "not_applicable": "<why>". db-reset must be marked destructive;
    steps that look destructive but aren't marked are warnings, and UNRESOLVED steps are warnings (failures
    with --strict);
  - end-to-end testability: a missing e2e-airplane or e2e-connected mode is a warning (define it, or declare it
    not_applicable); a defined one must say "network": "airplane" / "connected"; and .fyzxsflow/e2e.md saying
    `Status: ready` needs at least one of them defined.
Planned (greenfield, before the code exists): a doc whose frontmatter says `status: planned` describes intended
code, so its globs matching no file and its cited paths not existing yet are warnings; a config.json mode or step
with "planned": true is a warning. Every planned item fails with --strict: the Repo Cartographer's confirm mode
clears them once the code exists.
Exit 0 = pass, 1 = fail.
"""

import argparse
import json
import os
import pathlib
import re
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from layout import HOME, PACKAGE  # noqa: E402

BACKTICK = re.compile(r"`([^`\n]+)`")
PATHLIKE = re.compile(r"^[A-Za-z0-9_.\-][A-Za-z0-9_.\-/\\]*/[A-Za-z0-9_.\-/\\]*$")
FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n", re.S)


def tracked_files(root: pathlib.Path) -> list:
    try:
        out = subprocess.run(["git", "ls-files"], cwd=root, capture_output=True, text=True, check=True).stdout
        files = out.splitlines()
        if files:
            return files
    except (OSError, subprocess.CalledProcessError):
        pass
    files = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in (".git", "node_modules", "bin", "obj")]
        for f in filenames:
            files.append(pathlib.Path(dirpath, f).relative_to(root).as_posix())
    return files


def glob_to_regex(g: str):
    r, i = "", 0
    while i < len(g):
        if g[i:i + 3] == "**/":
            r += "(?:.*/)?"; i += 3
        elif g[i:i + 2] == "**":
            r += ".*"; i += 2
        elif g[i] == "*":
            r += "[^/]*"; i += 1
        elif g[i] == "?":
            r += "[^/]"; i += 1
        elif g[i] == "{":
            j = g.index("}", i)
            r += "(?:" + "|".join(re.escape(x) for x in g[i + 1:j].split(",")) + ")"; i = j + 1
        else:
            r += re.escape(g[i]); i += 1
    return re.compile("^" + r + "$")


def frontmatter_list(text: str, key: str) -> list:
    m = FRONTMATTER.match(text)
    if not m:
        return []
    block = re.search(r"^" + re.escape(key) + r":\s*\n((?:\s+-\s+.*\n?)+)", m.group(1) + "\n", re.M)
    if not block:
        return []
    return [x.strip().strip("\"'") for x in re.findall(r"^\s+-\s+(.*)$", block.group(1), re.M)]


def frontmatter_value(text: str, key: str) -> str:
    m = FRONTMATTER.match(text)
    if not m:
        return ""
    v = re.search(r"^" + re.escape(key) + r":[ \t]*(\S[^\n]*)$", m.group(1), re.M)
    return v.group(1).strip().strip("\"'") if v else ""


def is_planned(text: str) -> bool:
    return frontmatter_value(text, "status").lower() == "planned"


def project_docs(base: pathlib.Path) -> list:
    """The project's own docs: the installed package and run folders are not project documentation."""
    docs = [base / n for n in ("profile.md", "feature-flags.md", "gates.md", "e2e.md") if (base / n).exists()]
    if (base / "docs").is_dir():
        docs += [d for d in (base / "docs").rglob("*.md") if not d.name.startswith("_")]
    return docs


def planned_modes(modes: dict) -> list:
    out = []
    for name, mode in modes.items():
        if mode.get("not_applicable"):
            continue
        if mode.get("planned"):
            out.append(f"mode '{name}'")
        out += [f"mode '{name}' step '{s.get('name')}'" for s in mode.get("steps", []) if s.get("planned")]
    return out


def planned(root: pathlib.Path) -> list:
    """Everything still marked planned: docs with `status: planned`, config.json modes or steps with "planned"."""
    base = root / HOME
    out = [d.relative_to(root).as_posix() for d in project_docs(base) if is_planned(d.read_text(encoding="utf-8"))]
    cfg = base / "config.json"
    if cfg.exists():
        out += [f"config.json {m}" for m in planned_modes(json.loads(cfg.read_text(encoding="utf-8")).get("modes") or {})]
    return out


def cited_paths(text: str) -> list:
    out = []
    body = re.sub(r"```.*?```", "", text, flags=re.S)
    body = re.sub(r"<!--.*?-->", "", body, flags=re.S)
    for token in BACKTICK.findall(body):
        token = token.strip()
        if any(c in token for c in "<>*{}$ ") or token.startswith(("http", "-", f"{HOME}/runs")):
            continue
        token = re.sub(r":\d+(-\d+)?$", "", token)
        if PATHLIKE.match(token):
            out.append(token.replace("\\", "/"))
    return out


BASE_MODES = ["quick", "ci", "extreme"]
SURFACE_MODES = {  # a surface the profile marks present needs these Runner capabilities
    "database": ["db-migrate", "db-verify", "db-reset", "seed"],
    "api": ["http"],
}
SURFACE_ROW = re.compile(r"^\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|", re.M)
LOOKS_DESTRUCTIVE = re.compile(r"reset|from[-_ ]empty|\bdrop\b|truncate|wipe|db[-_ ]?nuke", re.I)


def config_problems(base: pathlib.Path):
    """Runner capability completeness: every capability the project's surfaces need exists, is declared
    not_applicable, or is visibly UNRESOLVED; destructive steps are labelled."""
    failures, warnings = [], []
    cfg_path = base / "config.json"
    if not cfg_path.exists():
        return ["config.json is missing (run fyzxsflow-init)"], []
    modes = json.loads(cfg_path.read_text(encoding="utf-8")).get("modes") or {}
    required = list(BASE_MODES)
    profile = base / "profile.md"
    if profile.exists():
        for surface, present in SURFACE_ROW.findall(profile.read_text(encoding="utf-8")):
            if present.lower().startswith("yes"):
                for key, needed in SURFACE_MODES.items():
                    if surface.lower().startswith(key):
                        required += [m for m in needed if m not in required]
    for name in required:
        if name not in modes:
            failures.append(f"config.json: no '{name}' mode, which this repo's surfaces need "
                            f"(define it, or add it with \"not_applicable\": \"<why>\")")
    reset = modes.get("db-reset")
    if reset and not reset.get("not_applicable") and not (
            reset.get("destructive") or all(s.get("destructive") for s in reset.get("steps", []))):
        failures.append("config.json: 'db-reset' must be marked \"destructive\": true")
    for name, mode in modes.items():
        if mode.get("not_applicable"):
            continue
        for step in mode.get("steps", []):
            text = f"{step.get('name', '')} {step.get('run', '')}"
            if "UNRESOLVED" in text:
                warnings.append(f"config.json: mode '{name}' step '{step.get('name')}' is UNRESOLVED")
            # Judge the command, not the step name: "seed-after-reset" restores state, it doesn't wipe it.
            elif LOOKS_DESTRUCTIVE.search(step.get("run", "")) and not (step.get("destructive") or mode.get("destructive")):
                warnings.append(f"config.json: mode '{name}' step '{step.get('name')}' looks destructive but is not "
                                "marked \"destructive\": true")
    failures += e2e_problems(base, modes, warnings)
    warnings += [f"config.json: {m} is planned, not yet proven (the Repo Cartographer's confirm mode clears it)"
                 for m in planned_modes(modes)]
    return failures, warnings


E2E_NETWORK = {"e2e-airplane": "airplane", "e2e-connected": "connected"}


def e2e_problems(base: pathlib.Path, modes: dict, warnings: list) -> list:
    failures = []
    for name, network in E2E_NETWORK.items():
        mode = modes.get(name)
        if mode is None:
            warnings.append(f"config.json: no '{name}' mode (end-to-end testing; define it, or add it with "
                            "\"not_applicable\": \"<why>\")")
        elif not mode.get("not_applicable") and mode.get("network") != network:
            failures.append(f"config.json: mode '{name}' must declare \"network\": \"{network}\"")
    e2e = base / "e2e.md"
    if e2e.exists():
        sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
        from run import e2e_status  # noqa: E402
        if e2e_status(base.parent) == "ready" and not any(
                m in modes and not modes[m].get("not_applicable") for m in E2E_NETWORK):
            failures.append("e2e.md says Status: ready, but config.json defines no e2e-airplane or e2e-connected mode")
    return failures


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--root", default=".")
    p.add_argument("--strict", action="store_true", help="treat UNRESOLVED as a failure")
    args = p.parse_args(argv)
    root = pathlib.Path(args.root).resolve()
    base = root / HOME
    if not base.is_dir():
        print("no .fyzxsflow/ folder (run fyzxsflow-init)")
        return 1
    config_path = base / "config.json"
    budget_kb = 24
    if config_path.exists():
        budget_kb = json.loads(config_path.read_text(encoding="utf-8")).get("docs", {}).get("pack_budget_kb", 24)
    files = tracked_files(root)
    fileset = set(files)
    failures, warnings, planned_warnings = [], [], []
    docs = project_docs(base)
    for doc in docs:
        rel = doc.relative_to(root).as_posix()
        text = doc.read_text(encoding="utf-8")
        intended = is_planned(text)
        if intended:
            planned_warnings.append(f"{rel}: status planned, not yet confirmed against the code")
        missing = planned_warnings if intended else failures
        for path in cited_paths(text):
            target = root / path
            if not target.exists() and path.rstrip("/") not in fileset:
                missing.append(f"{rel}: cites `{path}`, which does not exist" + (" yet" if intended else ""))
        for g in frontmatter_list(text, "paths"):
            rx = glob_to_regex(g)
            if not any(rx.match(f) for f in files):
                missing.append(f"{rel}: glob `{g}` matches no tracked file" + (" yet" if intended else ""))
        pack = frontmatter_list(text, "pack")
        if pack:
            size = doc.stat().st_size
            for item in pack:
                f = root / item
                if f.is_file():
                    size += f.stat().st_size
                else:
                    failures.append(f"{rel}: pack file `{item}` does not exist")
            if size > budget_kb * 1024:
                failures.append(f"{rel}: context pack is {size // 1024} KB, over the {budget_kb} KB budget")
        # Template comments explain UNRESOLVED; only the doc's own text counts.
        if "UNRESOLVED" in re.sub(r"<!--.*?-->", "", text, flags=re.S):
            (failures if args.strict else warnings).append(f"{rel}: contains UNRESOLVED")
    cfg_failures, cfg_warnings = config_problems(base)
    failures += cfg_failures
    strict = [w for w in cfg_warnings if "UNRESOLVED" in w or "is planned" in w] + planned_warnings
    (failures if args.strict else warnings).extend(strict)
    warnings.extend(w for w in cfg_warnings if w not in strict)
    for w in warnings:
        print(f"WARN {w}")
    for f in failures:
        print(f"FAIL {f}")
    print(f"docs_check: {'pass' if not failures else 'fail'} ({len(docs)} docs, {len(failures)} failures, {len(warnings)} warnings)")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())

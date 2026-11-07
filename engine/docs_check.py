"""Mechanical checks on a repo's agentflow docs (.agentflow/**/*.md, excluding runs/).

  python -I engine/docs_check.py [--root <repo>]

Fails when:
  - a backticked repo path cited in a doc does not exist (a trailing :line is ignored);
  - a segment doc's `paths:` glob matches no tracked file;
  - a segment's context pack (the doc plus its `pack:` files) exceeds docs.pack_budget_kb in config.json;
  - a doc still contains UNRESOLVED (reported as a warning unless --strict).
Exit 0 = pass, 1 = fail.
"""

import argparse
import json
import os
import pathlib
import re
import subprocess
import sys

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


def cited_paths(text: str) -> list:
    out = []
    body = re.sub(r"```.*?```", "", text, flags=re.S)
    body = re.sub(r"<!--.*?-->", "", body, flags=re.S)
    for token in BACKTICK.findall(body):
        token = token.strip()
        if any(c in token for c in "<>*{}$ ") or token.startswith(("http", "-", ".agentflow/runs")):
            continue
        token = re.sub(r":\d+(-\d+)?$", "", token)
        if PATHLIKE.match(token):
            out.append(token.replace("\\", "/"))
    return out


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--root", default=".")
    p.add_argument("--strict", action="store_true", help="treat UNRESOLVED as a failure")
    args = p.parse_args(argv)
    root = pathlib.Path(args.root).resolve()
    base = root / ".agentflow"
    if not base.is_dir():
        print("no .agentflow/ folder (run agentflow-init)")
        return 1
    config_path = base / "config.json"
    budget_kb = 24
    if config_path.exists():
        budget_kb = json.loads(config_path.read_text(encoding="utf-8")).get("docs", {}).get("pack_budget_kb", 24)
    files = tracked_files(root)
    fileset = set(files)
    failures, warnings = [], []
    # Only the project's own docs: the installed package (agents/, context/, engine/, skills/, templates/)
    # and run folders are not project documentation.
    docs = [base / n for n in ("profile.md", "feature-flags.md", "gates.md") if (base / n).exists()]
    if (base / "docs").is_dir():
        docs += [d for d in (base / "docs").rglob("*.md") if not d.name.startswith("_")]
    for doc in docs:
        rel = doc.relative_to(root).as_posix()
        text = doc.read_text(encoding="utf-8")
        for path in cited_paths(text):
            target = root / path
            if not target.exists() and path.rstrip("/") not in fileset:
                failures.append(f"{rel}: cites `{path}`, which does not exist")
        for g in frontmatter_list(text, "paths"):
            rx = glob_to_regex(g)
            if not any(rx.match(f) for f in files):
                failures.append(f"{rel}: glob `{g}` matches no tracked file")
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
        if "UNRESOLVED" in text:
            (failures if args.strict else warnings).append(f"{rel}: contains UNRESOLVED")
    for w in warnings:
        print(f"WARN {w}")
    for f in failures:
        print(f"FAIL {f}")
    print(f"docs_check: {'pass' if not failures else 'fail'} ({len(docs)} docs, {len(failures)} failures, {len(warnings)} warnings)")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())

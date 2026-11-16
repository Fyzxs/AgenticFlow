"""Mechanical checks on what agents write.

  python -I .fyzxsflow/package/engine/checks.py citations <file> [<file> ...] [--root .]
      -> every `path:line` / `path:line-line` citation points at a file that exists and a line inside it.
         Exit 0 = all resolve, 1 = at least one doesn't.
  python -I .fyzxsflow/package/engine/checks.py run-ids [--base main] [--root .]
      -> no run-local ids (F-12, AC-3, WP-04, WP-04.2) or run-folder paths in lines added to product code since
         the merge base with --base (committed or not). Exit 0 = clean, 1 = found.
  python -I .fyzxsflow/package/engine/checks.py report <report> [--agent <agent>]
      -> the report has a `## ` section for every item its agent file lists under "Report must include" (items
         marked "(if any)" are optional), and every criterion marked met has evidence. The agent comes from the
         report's `agent:` frontmatter unless given. Exit 0 = complete, 1 = something missing (listed).

Citations: a path with a folder must exist (from the repo root, else from the run folder the file is in); a bare
file name is checked only when it exists at the root. Ranges must lie inside the file. `run.py stamp` runs the
citation check on every report it stamps; the Validator runs it on the output it checks.

Run ids belong to the run, not to the product: a comment citing "F-104" or "WP-06.3" means nothing once the run
folder is gone. Files under .fyzxsflow/, .claude/ and .github/ (the flow's own files) are not product code.
"""

import argparse
import pathlib
import re
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from layout import HOME  # noqa: E402

CITATION = re.compile(r"(?<![\w/.:@-])((?:[\w.-]+/)*[\w-][\w.-]*\.[A-Za-z][A-Za-z0-9]{0,7}):(\d+)(?:-(\d+))?(?![\w:])")
RUN_ID = re.compile(r"\b(?:F|AC)-\d+\b|\bWP-\d{2}(?:\.\d+)?\b|" + re.escape(HOME) + r"/runs/")
FLOW_FILES = (f"{HOME}/", ".claude/", ".github/")


def run_folder_of(path: pathlib.Path):
    for parent in path.resolve().parents:
        if (parent / "ledger.md").exists():
            return parent
    return None


def line_count(path: pathlib.Path) -> int:
    with open(path, "rb") as f:
        return sum(1 for _ in f)


def citation_problems(file: pathlib.Path, root: pathlib.Path) -> list:
    text = file.read_text(encoding="utf-8", errors="replace")
    text = re.sub(r"https?://\S+", "", text)  # host:port in URLs is not a citation
    run = run_folder_of(file)
    problems, seen = [], set()
    for m in CITATION.finditer(text):
        rel, start, end = m.group(1), int(m.group(2)), int(m.group(3) or m.group(2))
        if (rel, start, end) in seen:
            continue
        seen.add((rel, start, end))
        candidates = [root / rel] + ([run / rel] if run else [])
        target = next((c for c in candidates if c.is_file()), None)
        if target is None:
            if "/" in rel:
                problems.append(f"{m.group(0)}: no such file")
            continue
        n = line_count(target)
        if start < 1 or end < start or end > n:
            problems.append(f"{m.group(0)}: {rel} has {n} lines")
    return problems


def cmd_citations(args) -> int:
    root = pathlib.Path(args.root).resolve()
    bad = 0
    for name in args.files:
        path = pathlib.Path(name)
        for problem in citation_problems(path, root):
            print(f"{name}: {problem}")
            bad += 1
    print(f"citations: {bad} unresolved")
    return 1 if bad else 0


def git(root: pathlib.Path, *a) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *a], cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace")


def cmd_run_ids(args) -> int:
    root = pathlib.Path(args.root).resolve()
    base = git(root, "merge-base", "HEAD", args.base)
    if base.returncode != 0:
        print(f"cannot find the merge base with '{args.base}': {base.stderr.strip()}", file=sys.stderr)
        return 2
    diff = git(root, "diff", "-U0", "--no-color", base.stdout.strip(), "--")
    hits, current, line_no = [], None, 0
    for line in diff.stdout.splitlines():
        if line.startswith("+++ "):
            current = line[6:] if line.startswith("+++ b/") else None
        elif line.startswith("@@"):
            m = re.search(r"\+(\d+)", line)
            line_no = int(m.group(1)) if m else 0
        elif line.startswith("+") and current:
            if not current.startswith(FLOW_FILES):
                found = RUN_ID.search(line[1:])
                if found:
                    hits.append(f"{current}:{line_no}: '{found.group(0)}' in: {line[1:].strip()[:120]}")
            line_no += 1
    # Untracked files are new product code too.
    untracked = git(root, "ls-files", "--others", "--exclude-standard").stdout.splitlines()
    for rel in untracked:
        if rel.startswith(FLOW_FILES):
            continue
        try:
            text = (root / rel).read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for n, l in enumerate(text.splitlines(), start=1):
            found = RUN_ID.search(l)
            if found:
                hits.append(f"{rel}:{n}: '{found.group(0)}' in: {l.strip()[:120]}")
    for h in hits:
        print(h)
    print(f"run-ids: {len(hits)} in added product lines (since {args.base})")
    return 1 if hits else 0


def agent_file(agent: str):
    here = pathlib.Path(__file__).resolve().parent
    for folder in (here.parent / "agents", here.parent / ".apm" / "agents"):
        f = folder / f"{agent}.agent.md"
        if f.exists():
            return f
    return None


def required_sections(agent: str) -> list:
    """The items an agent file lists under '## Report must include' (separated by '·'), minus '(if any)' ones."""
    f = agent_file(agent)
    if f is None:
        return []
    m = re.search(r"^## Report must include\s*\n(.*?)(?=^## |\Z)", f.read_text(encoding="utf-8"), re.M | re.S)
    if not m:
        return []
    out = []
    for item in " ".join(m.group(1).split()).split("·"):
        item = item.strip().rstrip(".")
        if not item or "(if any)" in item:
            continue
        out.append(re.sub(r"\s*\(.*$", "", item).strip())
    return out


def report_problems(report: pathlib.Path, agent: str = "") -> list:
    text = report.read_text(encoding="utf-8")
    if not agent:
        m = re.search(r"^agent:\s*(\S+)", text, re.M)
        agent = m.group(1) if m else ""
    headings = [re.sub(r"\s*\(.*$", "", h).strip().lower() for h in re.findall(r"^##\s+(.+)$", text, re.M)]
    problems = []
    for item in required_sections(agent):
        want = item.lower()
        if not any(h.startswith(want) or want.startswith(h) for h in headings if h):
            problems.append(f"missing section: {item} (the {agent} agent file requires it)")
    crit = re.search(r"^## Acceptance criteria[^\n]*\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    for row in (crit.group(1).splitlines() if crit else []):
        cells = [c.strip() for c in row.strip().strip("|").split("|")]
        if len(cells) >= 3 and re.match(r"^(AC|WP)-\d", cells[0]) and cells[1].lower() == "met" and \
                cells[2] in ("", "-", "—", "..."):
            problems.append(f"{cells[0]} is met with no evidence")
    return problems


def cmd_report(args) -> int:
    problems = report_problems(pathlib.Path(args.report), args.agent or "")
    for p in problems:
        print(p)
    print(f"report: {'complete' if not problems else 'incomplete'} ({len(problems)} problems)")
    return 1 if problems else 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("citations")
    c.add_argument("files", nargs="+")
    c.add_argument("--root", default=".")
    r = sub.add_parser("run-ids")
    r.add_argument("--base", default="main")
    r.add_argument("--root", default=".")
    rp = sub.add_parser("report")
    rp.add_argument("report")
    rp.add_argument("--agent")
    args = p.parse_args(argv)
    return {"citations": cmd_citations, "run-ids": cmd_run_ids, "report": cmd_report}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())

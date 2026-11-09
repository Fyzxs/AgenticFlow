r"""Acceptance-criteria traceability gate for a run.

  python -I engine/ac_trace.py --run <dir>                     # plan check (after Locate)
  python -I engine/ac_trace.py --run <dir> --require-evidence  # delivery check (before Deliver)

Plan check fails when:
  - brief.md has no acceptance criteria, or a criterion is not tagged (stated) or (inferred);
  - a work package has no "## Acceptance criteria" section, or the section names nothing;
  - a brief criterion is served by no work package;
  - a package claims to serve a criterion the brief does not define.
  - a work package's "## Flag plan" does not state exactly one of: a flag (`flag: \`name\``), `unflaggable`, or
    `not-required`; or an unflaggable / not-required plan gives no `revert:` path;
  - a package says `not-required` while neither the project policy (.fyzxsflow/feature-flags.md
    "Policy: not-required") nor the brief (`flags: not-required`) allows it.
Delivery check also fails when a criterion (brief AC-n or package WP-xx.n) has no report row marking it
"met" with non-empty evidence.
Exit 0 = pass, 1 = fail, 2 = usage error.
"""

import argparse
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from layout import HOME, PACKAGE  # noqa: E402

BRIEF_AC = re.compile(r"\*\*(AC-\d+)\*\*\s*\((stated|inferred)\)", re.I)
ANY_BRIEF_AC = re.compile(r"\*\*(AC-\d+)\*\*")
SERVES = re.compile(r"^\s*-\s*Serves:\s*(.+)$", re.M | re.I)
AC_ID = re.compile(r"\bAC-\d+\b")
WP_CRIT = re.compile(r"\*\*(WP-\d+\.\d+)\*\*")
BAD_WP_CRIT = re.compile(r"\*\*(WP-\d+\.\d+[^\d*\s][^*]*|WP-\d+\.\d+\s*\([^)]*\))\*\*")
RANGE = re.compile(r"AC-\d+\s*(?:\.\.|–|—|-|to)\s*(?:AC-)?\d+\b", re.I)
REPORT_ROW = re.compile(r"^\|\s*((?:AC|WP)-[\d.]+)\s*\|\s*([^|]+?)\s*\|\s*([^|]*?)\s*\|", re.M)


POLICY = re.compile(r"^Policy:\s*`?(required|not-required)`?", re.M | re.I)
BRIEF_FLAGS = re.compile(r"\A---\n.*?^flags:\s*(not-required|required|project-policy)\b.*?\n---\n", re.M | re.S | re.I)
FLAGGED = re.compile(r"^\s*-\s*flag:\s*`(?!<)[^`]+`", re.M)
UNFLAGGABLE = re.compile(r"^\s*-\s*unflaggable\b", re.M | re.I)
NOT_REQUIRED = re.compile(r"^\s*-\s*not-required\b", re.M | re.I)
REVERT = re.compile(r"revert:\s*(?!<)\S", re.I)


def project_policy(root: pathlib.Path) -> str:
    """Fail closed: no file or no Policy line means flags are required."""
    path = root / HOME / "feature-flags.md"
    if not path.exists():
        return "required"
    m = POLICY.search(path.read_text(encoding="utf-8"))
    return m.group(1).lower() if m else "required"


def flag_problems(name: str, plan: str, allowed_not_required: bool) -> list:
    lines = [l for l in plan.splitlines() if "<" not in l]  # unfilled template lines carry <placeholders>
    filled = "\n".join(lines)
    kinds = [k for k, rx in (("flag", FLAGGED), ("unflaggable", UNFLAGGABLE), ("not-required", NOT_REQUIRED))
             if rx.search(filled)]
    if len(kinds) != 1:
        return [f"{name}: flag plan must state exactly one of a flag, unflaggable, or not-required (found {kinds or 'none'})"]
    kind = kinds[0]
    problems = []
    if kind in ("unflaggable", "not-required") and not REVERT.search(filled):
        problems.append(f"{name}: a {kind} flag plan must state its revert path (revert: ...)")
    if kind == "not-required" and not allowed_not_required:
        problems.append(f"{name}: not-required, but neither the project policy nor the brief allows skipping flags")
    return problems


def section(text: str, heading: str) -> str:
    m = re.search(r"^##\s+" + re.escape(heading) + r"\s*$(.*?)(?=^##\s|\Z)", text, re.M | re.S | re.I)
    return m.group(1) if m else ""


def strip_comments(text: str) -> str:
    return re.sub(r"<!--.*?-->", "", text, flags=re.S)


def check(run: pathlib.Path, require_evidence: bool, root: pathlib.Path = None):
    problems = []
    brief_path = run / "brief.md"
    if not brief_path.exists():
        return ["brief.md is missing"], {}
    raw_brief = brief_path.read_text(encoding="utf-8")
    brief = strip_comments(raw_brief)
    if root is None:  # the folder containing .fyzxsflow/, wherever the run sits under runs/
        root = next((p.parent for p in run.resolve().parents if p.name == HOME), run.parent)
    m = BRIEF_FLAGS.match(raw_brief)
    brief_flags = m.group(1).lower() if m else "project-policy"
    allowed_not_required = brief_flags == "not-required" or (
        brief_flags != "required" and project_policy(root) == "not-required")
    ac_section = section(brief, "Acceptance criteria")
    defined = ANY_BRIEF_AC.findall(ac_section)
    if not defined:
        problems.append("brief.md defines no acceptance criteria (no work may be implemented without them)")
    tagged = {m.group(1).upper() for m in BRIEF_AC.finditer(ac_section) if m.group(2)}
    for ac in defined:
        if ac.upper() not in tagged:
            problems.append(f"{ac} is not tagged (stated) or (inferred)")
    brief_acs = {a.upper() for a in defined}

    served = {}
    package_criteria = []
    packages = sorted((run / "work-packages").glob("*.md")) if (run / "work-packages").is_dir() else []
    if not packages:
        problems.append("no work packages")
    for wp in packages:
        text = strip_comments(wp.read_text(encoding="utf-8"))
        sec = section(text, "Acceptance criteria")
        for m in SERVES.finditer(sec):
            if RANGE.search(m.group(1)):
                problems.append(f"{wp.name}: 'Serves: {m.group(1).strip()}' uses a range; list every id "
                                "(a range counts only its two ends)")
        serves = [a.upper() for m in SERVES.finditer(sec) for a in AC_ID.findall(m.group(1))]
        crits = WP_CRIT.findall(sec)
        for bad in BAD_WP_CRIT.findall(sec):
            problems.append(f"{wp.name}: criterion id **{bad}** is not traced: ids are digits only (WP-nn.n)")
        if not serves and not crits:
            problems.append(f"{wp.name}: acceptance criteria section is missing or empty")
        for a in serves:
            served.setdefault(a, []).append(wp.name)
            if a not in brief_acs:
                problems.append(f"{wp.name}: serves {a}, which brief.md does not define")
        package_criteria.extend(crits)
        problems.extend(flag_problems(wp.name, section(text, "Flag plan"), allowed_not_required))
    for a in sorted(brief_acs - set(served)):
        problems.append(f"{a} is not served by any work package")

    if require_evidence:
        met = {}
        reports = sorted((run / "reports").glob("*.md")) if (run / "reports").is_dir() else []
        for r in reports:
            for crit, status, evidence in REPORT_ROW.findall(strip_comments(r.read_text(encoding="utf-8"))):
                if status.strip().lower() == "met" and evidence.strip() and evidence.strip() not in ("-", "..."):
                    met[crit.upper()] = r.name
        for crit in sorted(brief_acs | {c.upper() for c in package_criteria}):
            if crit not in met:
                problems.append(f"{crit} has no report marking it met with evidence")
    return problems, served


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--run", required=True)
    p.add_argument("--require-evidence", action="store_true")
    p.add_argument("--root", help="repo root (default: the folder containing .fyzxsflow/)")
    args = p.parse_args(argv)
    run = pathlib.Path(args.run).resolve()
    if not run.is_dir():
        print(f"run folder not found: {run}", file=sys.stderr)
        return 2
    problems, served = check(run, args.require_evidence, pathlib.Path(args.root).resolve() if args.root else None)
    for a, wps in sorted(served.items()):
        print(f"{a}: {', '.join(wps)}")
    for prob in problems:
        print(f"FAIL {prob}")
    print(f"ac_trace: {'pass' if not problems else 'fail'} ({len(problems)} problems)")
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())

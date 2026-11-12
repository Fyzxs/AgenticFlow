"""Compaction: smaller agent-context files with every rule kept (the Compactor's tools).

  python -I .fyzxsflow/package/engine/compact.py measure [--root .]
      -> every file the flow loads into an agent's context, largest cost first, with its kind:
         package (agents/ context/ instructions/ prompts/ skills/; an agent's cost is its host size = package
         file + its learned entries),
         learned, doc, policy (owner files: propose, never edit). Package files show their overlay state.
  python -I .fyzxsflow/package/engine/compact.py check <after> [--before <file>] [--accept <token>]... [--root .]
      -> fidelity of a compacted file against its original. <before> defaults to the package file for an overlay
         under .fyzxsflow/compacted/, else the file as committed at HEAD. Exit 0 = nothing lost, 1 = lost tokens
         listed ("missing <kind>: <token>"), 2 = usage.
  python -I .fyzxsflow/package/engine/compact.py record <package path> [--accept <token>]... [--root .]
      -> runs check on .fyzxsflow/compacted/<package path> against .fyzxsflow/package/<package path>, then records
         it in compacted/manifest.json. Apply it with install.py --sync.
  python -I .fyzxsflow/package/engine/compact.py status [--root .]
      -> one line per overlay: applied | pending (run install.py --sync) | stale (the package file changed upstream:
         compact it again) | missing (the package dropped the file).
  python -I .fyzxsflow/package/engine/compact.py drop <package path> [--root .]
      -> removes the overlay and its manifest entry; the next install restores the upstream file.

Why overlays: .fyzxsflow/package/ is replaced by every install. A compacted package file lives in
.fyzxsflow/compacted/<package path>, recorded with the hash of the package file it was made from; install.py
copies it into the package only while the package file still has that hash (or already holds the overlay). An
upgrade that changes the file makes the overlay stale: the upstream file is kept, and install says so.

What check keeps (each token from the original must still appear in the compacted text, or be --accept'ed with a
reason in the Compactor's report): frontmatter keys and values (except `description`, which may be shortened),
headings, backtick spans (also wrapped ones; whitespace is ignored), fenced-code lines, link targets, paths,
finding / criterion / package ids, and numbers (except `Hits: n` counts, which merging sums).
It cannot judge meaning: the Validator does.
"""

import argparse
import datetime
import hashlib
import json
import pathlib
import re
import shutil
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from layout import COMPACTED, HOME, LEARNED, PACKAGE  # noqa: E402

OVERLAY_DIRS = ("agents", "context", "instructions", "prompts", "skills")
MANIFEST = "manifest.json"
POLICY = ("profile.md", "feature-flags.md")
PROJECT_DOCS = ("gates.md", "e2e.md")

FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n", re.S)
HEADING = re.compile(r"^#{1,6} .+$", re.M)
BACKTICK = re.compile(r"`((?:[^`\n]|\n(?![ \t]*\n))+?)`")
HITS = re.compile(r"\bHits: \d+")
FENCE = re.compile(r"^```.*?$(.*?)^```", re.M | re.S)
LINK = re.compile(r"\]\(([^)\s]+)\)")
PATH = re.compile(r"(?<![\w`/])(?:[\w.-]+/)+[\w.<>*-]+")
IDS = re.compile(r"\b(?:F|AC|WP|E2E)-\d+(?:\.\d+)?\b")
NUMBER = re.compile(r"(?<![\w.-])\d+(?:\.\d+)?(?![\w])")
LIST_MARKER = re.compile(r"^\s*\d+\.\s", re.M)


def sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def frontmatter(text: str) -> dict:
    m = FRONTMATTER.match(text)
    out = {}
    for line in (m.group(1).splitlines() if m else []):
        if ":" in line and not line.startswith((" ", "\t")):
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip()
    return out


def flat(text: str) -> str:
    return " ".join(text.split())


def tokens(text: str) -> list:
    """(kind, token) pairs a compacted text must keep, in first-seen order, without duplicates."""
    body = FRONTMATTER.sub("", text, count=1)
    found = []
    found += [("heading", h.strip()) for h in HEADING.findall(body)]
    for block in FENCE.findall(body):
        found += [("code", line.strip()) for line in block.splitlines() if line.strip()]
    prose = FENCE.sub("", body)
    found += [("backtick", flat(b)) for b in BACKTICK.findall(prose) if b.strip()]
    found += [("link", l) for l in LINK.findall(prose)]
    found += [("path", p.rstrip(".,;:")) for p in PATH.findall(BACKTICK.sub(" ", prose)) if "/" in p]
    found += [("id", i) for i in IDS.findall(body)]
    # hit counts change when entries merge (summed); the count itself is the Compactor's to get right
    found += [("number", n) for n in NUMBER.findall(HITS.sub("", LIST_MARKER.sub("", HEADING.sub("", prose))))]
    seen, out = set(), []
    for kind, tok in found:
        if tok and tok not in seen:
            seen.add(tok)
            out.append((kind, tok))
    return out


def code_text(text: str) -> str:
    """The text inside backtick spans and fenced blocks, one piece per line."""
    return "\n".join(FENCE.findall(text) + BACKTICK.findall(FENCE.sub("", text)))


def present(kind: str, tok: str, after: str) -> bool:
    if kind == "heading":
        return re.search(rf"^{re.escape(tok)}\s*$", after, re.M) is not None
    if kind == "backtick":  # still code: `pass` rewritten as plain "pass" is a lost literal
        after = code_text(after)
    if kind in ("backtick", "code"):
        after = flat(after)  # a span may be re-wrapped
    # whole token: `pass` is not kept by "passes", nor 2 by "24" or "AC-2"
    left = r"(?<![\w.-])" if kind == "number" else (r"(?<!\w)" if tok[0].isalnum() or tok[0] == "_" else "")
    right = r"(?!\w)" if tok[-1].isalnum() or tok[-1] == "_" else ""
    return re.search(left + re.escape(tok) + right, after) is not None


def compare(before: str, after: str, accept=()) -> list:
    """Lost items as 'missing <kind>: <token>' lines (empty = nothing lost)."""
    lost = []
    fb, fa = frontmatter(before), frontmatter(after)
    for k in sorted(set(fb) | set(fa)):
        if k == "description":
            if k in fb and k not in fa:
                lost.append("missing frontmatter: description")
        elif fb.get(k) != fa.get(k):
            lost.append(f"changed frontmatter: {k} ({fb.get(k)!r} -> {fa.get(k)!r})")
    accepted = set(accept)
    for kind, tok in tokens(before):
        if tok not in accepted and not present(kind, tok, after):
            lost.append(f"missing {kind}: {tok}")
    return lost


# ---------------------------------------------------------------- overlays

def home(root: pathlib.Path) -> pathlib.Path:
    return root / HOME


def manifest_path(root: pathlib.Path) -> pathlib.Path:
    return home(root) / COMPACTED / MANIFEST


def load_manifest(root: pathlib.Path) -> dict:
    p = manifest_path(root)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def save_manifest(root: pathlib.Path, data: dict):
    p = manifest_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(dict(sorted(data.items())), indent=2) + "\n", encoding="utf-8", newline="\n")


def valid_rel(rel: str) -> str:
    rel = pathlib.PurePosixPath(rel.replace("\\", "/")).as_posix()
    parts = rel.split("/")
    if ".." in parts or parts[0] not in OVERLAY_DIRS or not rel.endswith(".md"):
        raise SystemExit(f"{rel}: only .md files under {', '.join(OVERLAY_DIRS)}/ of the package can be compacted "
                         f"(path relative to {HOME}/{PACKAGE}/)")
    return rel


def state(root: pathlib.Path, rel: str, entry: dict) -> str:
    pkg = home(root) / PACKAGE / rel
    overlay = home(root) / COMPACTED / rel
    if not overlay.exists():
        return "no-overlay"
    if not pkg.exists():
        return "missing"
    cur = sha(pkg)
    if cur == entry.get("overlay_sha") and sha(overlay) == entry.get("overlay_sha"):
        return "applied"
    if cur == entry.get("source_sha"):
        return "pending" if sha(overlay) == entry.get("overlay_sha") else "edited"
    return "stale"


def apply(root: pathlib.Path, written: list = None) -> list:
    """Copy each recorded overlay into the installed package where it still fits. Returns warnings to print."""
    warnings = []
    for rel, entry in sorted(load_manifest(root).items()):
        st = state(root, rel, entry)
        if st == "pending":
            dst = home(root) / PACKAGE / rel
            shutil.copyfile(home(root) / COMPACTED / rel, dst)
            if written is not None:
                written.append(dst)
        elif st == "stale":
            warnings.append(f"compacted {rel} is stale: the package file changed upstream, so the upstream file is "
                            f"used. Run /{HOME[1:]}-compact {rel} again, or compact.py drop {rel}")
        elif st == "missing":
            warnings.append(f"compacted {rel}: the package no longer has this file; compact.py drop {rel}")
        elif st == "edited":
            warnings.append(f"compacted {rel} changed since it was recorded; not applied. compact.py record {rel}")
        elif st == "no-overlay":
            warnings.append(f"compacted {rel} is in the manifest but its file is gone; compact.py drop {rel}")
    return warnings


# ---------------------------------------------------------------- commands

def git_head(root: pathlib.Path, path: pathlib.Path):
    rel = path.resolve().relative_to(root.resolve()).as_posix()
    proc = subprocess.run(["git", "show", f"HEAD:{rel}"], cwd=root, capture_output=True)
    return proc.stdout.decode("utf-8") if proc.returncode == 0 else None


def report(before: str, after: str, lost: list, label: str) -> int:
    b, a = len(before.encode("utf-8")), len(after.encode("utf-8"))
    pct = f"{(a - b) * 100 / b:+.0f}%" if b else "n/a"
    for line in lost:
        print(line)
    print(f"{label}: {b} -> {a} bytes ({pct}); {'lost ' + str(len(lost)) if lost else 'nothing lost'}")
    if a > b:
        print(f"warning: {label} grew")
    return 1 if lost else 0


def cmd_check(args) -> int:
    root = pathlib.Path(args.root).resolve()
    after = pathlib.Path(args.after).resolve()
    if not after.exists():
        print(f"{args.after}: not found", file=sys.stderr)
        return 2
    if args.before:
        before = pathlib.Path(args.before).read_text(encoding="utf-8")
    else:
        try:
            rel = after.relative_to((home(root) / COMPACTED).resolve()).as_posix()
            src = home(root) / PACKAGE / rel
            before = src.read_text(encoding="utf-8") if src.exists() else None
        except ValueError:
            before = git_head(root, after)
        if before is None:
            print(f"{args.after}: no original found; pass --before <file>", file=sys.stderr)
            return 2
    text = after.read_text(encoding="utf-8")
    return report(before, text, compare(before, text, args.accept), args.after)


def cmd_record(args) -> int:
    root = pathlib.Path(args.root).resolve()
    rel = valid_rel(args.path)
    pkg, overlay = home(root) / PACKAGE / rel, home(root) / COMPACTED / rel
    for p in (pkg, overlay):
        if not p.exists():
            print(f"{p.relative_to(root).as_posix()}: not found", file=sys.stderr)
            return 2
    before, after = pkg.read_text(encoding="utf-8"), overlay.read_text(encoding="utf-8")
    code = report(before, after, compare(before, after, args.accept), rel)
    if code:
        print(f"not recorded: restore what was lost, or --accept each token you meant to drop", file=sys.stderr)
        return code
    data = load_manifest(root)
    cur, old = sha(pkg), data.get(rel, {})
    applied = old and cur == old.get("overlay_sha")  # the package holds the previous overlay: keep its source
    data[rel] = {
        "source_sha": old["source_sha"] if applied else cur,
        "source_bytes": old.get("source_bytes", len(before.encode("utf-8"))) if applied else len(before.encode("utf-8")),
        "overlay_sha": sha(overlay),
        "overlay_bytes": len(after.encode("utf-8")),
        "accepted": sorted(set(args.accept)),
        "recorded": datetime.date.today().isoformat(),
    }
    save_manifest(root, data)
    print(f"recorded {rel}; apply with: python -I {HOME}/{PACKAGE}/engine/install.py --sync --target . --host <host>")
    return 0


def cmd_status(args) -> int:
    root = pathlib.Path(args.root).resolve()
    data = load_manifest(root)
    if not data:
        print("no compacted package files")
    for rel, entry in sorted(data.items()):
        print(f"{rel:48} {state(root, rel, entry):10} {entry.get('source_bytes', '?')} -> "
              f"{entry.get('overlay_bytes', '?')} bytes, recorded {entry.get('recorded', '?')}")
    return 0


def cmd_drop(args) -> int:
    root = pathlib.Path(args.root).resolve()
    rel = valid_rel(args.path)
    data = load_manifest(root)
    overlay = home(root) / COMPACTED / rel
    if rel not in data and not overlay.exists():
        print(f"{rel}: not compacted", file=sys.stderr)
        return 2
    data.pop(rel, None)
    save_manifest(root, data)
    if overlay.exists():
        overlay.unlink()
    print(f"dropped {rel}; the next install ({HOME}/{PACKAGE}/engine/install.py from the source) restores the "
          f"upstream file")
    return 0


def size(path: pathlib.Path) -> int:
    return path.stat().st_size if path.exists() else 0


def cmd_measure(args) -> int:
    root = pathlib.Path(args.root).resolve()
    base, pkg = home(root), home(root) / PACKAGE
    manifest = load_manifest(root)
    rows = []  # (cost, kind, path, note, file bytes)
    for d in OVERLAY_DIRS:
        for f in sorted((pkg / d).rglob("*.md")) if (pkg / d).is_dir() else []:
            rel = f.relative_to(pkg).as_posix()
            note = state(root, rel, manifest[rel]) if rel in manifest else "not compacted"
            cost = size(f)
            if d == "agents":  # what a dispatch loads: the package file plus the project's learned entries
                cost += size(base / LEARNED / f.name.replace(".agent.md", ".md"))
                note += f"; file {size(f)}, host = file + learned"
            rows.append((cost, "package", f"{HOME}/{PACKAGE}/{rel}", note, size(f)))
    for f in sorted((base / LEARNED).glob("*.md")) if (base / LEARNED).is_dir() else []:
        rows.append((size(f), "learned", f.relative_to(root).as_posix(), "", size(f)))
    docs = [base / n for n in PROJECT_DOCS if (base / n).exists()]
    docs += sorted((base / "docs").rglob("*.md")) if (base / "docs").is_dir() else []
    for f in docs:
        rows.append((size(f), "doc", f.relative_to(root).as_posix(), "", size(f)))
    for n in POLICY:
        if (base / n).exists():
            rows.append((size(base / n), "policy", f"{HOME}/{n}", "owner's: propose, never edit", size(base / n)))
    rows.sort(key=lambda r: -r[0])
    for b, kind, path, note, _ in rows:
        print(f"{b:>7}  {kind:8} {path}" + (f"  ({note})" if note else ""))
    totals = {}
    for _, kind, _, _, b in rows:  # file sizes, so learned entries count once
        totals[kind] = totals.get(kind, 0) + b
    print("total: " + ", ".join(f"{k} {v}" for k, v in sorted(totals.items())) + f"; all {sum(totals.values())} bytes")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("measure"); m.add_argument("--root", default=".")
    c = sub.add_parser("check"); c.add_argument("after"); c.add_argument("--before")
    c.add_argument("--accept", action="append", default=[]); c.add_argument("--root", default=".")
    r = sub.add_parser("record"); r.add_argument("path")
    r.add_argument("--accept", action="append", default=[]); r.add_argument("--root", default=".")
    s = sub.add_parser("status"); s.add_argument("--root", default=".")
    d = sub.add_parser("drop"); d.add_argument("path"); d.add_argument("--root", default=".")
    args = p.parse_args(argv)
    return {"measure": cmd_measure, "check": cmd_check, "record": cmd_record, "status": cmd_status,
            "drop": cmd_drop}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())

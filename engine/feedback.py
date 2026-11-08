"""The owner's feedback inbox: .agentflow/feedback/. Any file, any length, any time; the Orchestrator acts on it.

  python -I .agentflow/engine/feedback.py scan [--root .]
      -> every item that is new, or whose text changed since it was last handled: "new|changed <path>: <first line>"
  python -I .agentflow/engine/feedback.py set <item> --status in-progress|waiting|applied|declined
      --action docs|agent-input|rework|new-work|none [--action ...] --note "<what was done, or why not>" [--ref <run|F-n|sha> ...]
      -> records how the item was handled in its frontmatter; applied and declined items move to feedback/done/
  python -I .agentflow/engine/feedback.py list [--root .] [--all]
      -> open items (and with --all, done ones) with their status and note

The owner writes plain text; the system adds a frontmatter block (status, actions, note, refs, seen_hash, updated)
and never edits the owner's words. seen_hash covers the text below the frontmatter, so an item the owner edits
after it was handled shows up in scan again, even from done/ (it is reopened). README.md is the folder's guide,
not an item.
"""

import argparse
import datetime
import hashlib
import pathlib
import re
import sys

STATUSES = ("in-progress", "waiting", "applied", "declined")
ACTIONS = ("docs", "agent-input", "rework", "new-work", "none")
FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n?", re.S)
KEYS = ("status", "actions", "note", "refs", "seen_hash", "updated")


def inbox(root: pathlib.Path) -> pathlib.Path:
    return root / ".agentflow" / "feedback"


def split(text: str):
    m = FRONTMATTER.match(text)
    if not m:
        return {}, text
    meta = dict(re.findall(r"^(\w[\w_-]*):\s*(.*?)\s*$", m.group(1), re.M))
    return meta, text[m.end():]


def body_hash(body: str) -> str:
    return hashlib.sha256(body.strip().replace("\r\n", "\n").encode("utf-8")).hexdigest()[:16]


def items(root: pathlib.Path, include_done: bool = True) -> list:
    base = inbox(root)
    if not base.is_dir():
        return []
    found = [f for f in sorted(base.rglob("*")) if f.is_file() and f.name.lower() != "readme.md"
             and not f.name.startswith(".")]
    if not include_done:
        found = [f for f in found if "done" not in f.relative_to(base).parts[:-1]]
    return found


def first_line(body: str) -> str:
    for line in body.splitlines():
        line = line.strip().lstrip("#").strip()
        if line:
            return line[:100]
    return "(empty)"


def cmd_scan(args) -> int:
    root = pathlib.Path(args.root).resolve()
    pending = 0
    for f in items(root):
        meta, body = split(f.read_text(encoding="utf-8"))
        if not body.strip():
            continue
        if not meta.get("seen_hash"):
            state = "new"
        elif meta["seen_hash"] != body_hash(body):
            state = "changed"
        else:
            continue
        pending += 1
        print(f"{state} {f.relative_to(root).as_posix()}: {first_line(body)}")
    print(f"inbox: {pending} to process")
    return 0


def cmd_set(args) -> int:
    root = pathlib.Path(args.root).resolve()
    f = pathlib.Path(args.item)
    if not f.is_absolute():
        f = (root / f) if (root / f).exists() else f.resolve()
    if not f.exists():
        print(f"no feedback item {args.item}", file=sys.stderr)
        return 2
    meta, body = split(f.read_text(encoding="utf-8"))
    meta.update({
        "status": args.status,
        "actions": ", ".join(args.action),
        "note": args.note.replace("\n", " ").strip(),
        "refs": ", ".join(args.ref or []) or "none",
        "seen_hash": body_hash(body),
        "updated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
    })
    head = "\n".join(f"{k}: {meta[k]}" for k in KEYS if k in meta)
    text = f"---\n{head}\n---\n\n{body.lstrip(chr(10))}"
    base = inbox(root)
    in_done = "done" in f.resolve().relative_to(base.resolve()).parts[:-1]
    dest = f
    if args.status in ("applied", "declined") and not in_done:
        dest = base / "done" / f.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        f.unlink()
    elif args.status in ("in-progress", "waiting") and in_done:  # reopened
        dest = base / f.name
        f.unlink()
    dest.write_text(text, encoding="utf-8", newline="\n")
    print(f"{dest.relative_to(root).as_posix()}: {args.status} ({meta['actions']})")
    return 0


def cmd_list(args) -> int:
    root = pathlib.Path(args.root).resolve()
    shown = 0
    for f in items(root, include_done=args.all):
        meta, body = split(f.read_text(encoding="utf-8"))
        status = meta.get("status", "open")
        if meta.get("seen_hash") and meta["seen_hash"] != body_hash(body):
            status += ", edited since"
        shown += 1
        print(f"[{status}] {f.relative_to(root).as_posix()}: {first_line(body)}"
              + (f" -- {meta['note']}" if meta.get("note") else ""))
    if not shown:
        print("inbox: empty")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("scan"); s.add_argument("--root", default=".")
    st = sub.add_parser("set")
    st.add_argument("item"); st.add_argument("--root", default=".")
    st.add_argument("--status", required=True, choices=STATUSES)
    st.add_argument("--action", action="append", required=True, choices=ACTIONS)
    st.add_argument("--note", required=True); st.add_argument("--ref", action="append")
    ls = sub.add_parser("list"); ls.add_argument("--root", default="."); ls.add_argument("--all", action="store_true")
    args = p.parse_args(argv)
    return {"scan": cmd_scan, "set": cmd_set, "list": cmd_list}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())

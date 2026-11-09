"""The owner's feedback inbox: .fyzxsflow/feedback/. Any file, any length, any time; the Orchestrator acts on it.

  python -I .fyzxsflow/package/engine/feedback.py scan [--root .]
      -> every item that is new, or whose text changed since it was last handled: "new|changed <path>: <first line>"
  python -I .fyzxsflow/package/engine/feedback.py set <item> --status in-progress|waiting|applied|declined
      --action docs|agent-input|rework|new-work|none [--action ...] --note "<what was done, or why not>" [--ref <run|F-n|sha> ...]
      -> records how the item was handled in its frontmatter; applied and declined items move to feedback/done/
  python -I .fyzxsflow/package/engine/feedback.py list [--root .] [--all]
      -> open items (and with --all, done ones) with their status and note
  python -I .fyzxsflow/package/engine/feedback.py record-review <review file> [--root .]
      -> records the file's ## Human Feedback as an owner-feedback finding in its run:
         "F-n run=<run> state=<active|completed> agent=<a> target=<WP-n|stage>"

The owner writes plain text; the system adds a frontmatter block (status, actions, note, refs, seen_hash, updated)
and never edits the owner's words. seen_hash covers the text below the frontmatter, so an item the owner edits
after it was handled shows up in scan again, even from done/ (it is reopened). README.md is the folder's guide,
not an item. A file that isn't UTF-8 text (a screenshot, a PDF) is an item too: scan and list show it as
"(binary file <path>, <size> bytes; open it to read)", its record goes in a sidecar <name>.feedback-meta.md
(the owner's file is never rewritten), and seen_hash covers its bytes.

Review files: every hand-off writes one, whatever the agent's review level, so the owner can comment on any
output later, in place. scan also lists review files (active and completed runs) whose `## Human Feedback`
section is new or edited since it was last recorded: "review <path>: <first line> (run=<run> state=<state>)".
What was recorded is kept in each run's reviews/.feedback-seen.json (review.py decide writes it too), so a
section is recorded once, and again only when the owner edits it.
"""

import argparse
import datetime
import hashlib
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from layout import HOME, PACKAGE  # noqa: E402

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

STATUSES = ("in-progress", "waiting", "applied", "declined")
ACTIONS = ("docs", "agent-input", "rework", "new-work", "none")
FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n?", re.S)
KEYS = ("status", "actions", "note", "refs", "seen_hash", "updated")
META_SUFFIX = ".feedback-meta.md"  # the record of a binary item, beside it


def inbox(root: pathlib.Path) -> pathlib.Path:
    return root / HOME / "feedback"


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
             and not f.name.startswith(".") and not f.name.endswith(META_SUFFIX)]
    if not include_done:
        found = [f for f in found if "done" not in f.relative_to(base).parts[:-1]]
    return found


def sidecar(f: pathlib.Path) -> pathlib.Path:
    return f.with_name(f.name + META_SUFFIX)


def read_item(root: pathlib.Path, f: pathlib.Path):
    """(meta, body, hash, binary). A text item carries its record in frontmatter; a file that isn't UTF-8 text
    (a screenshot) can't, so its record lives in a sidecar and its hash covers the bytes."""
    data = f.read_bytes()
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        side = sidecar(f)
        meta = split(side.read_text(encoding="utf-8"))[0] if side.exists() else {}
        body = f"(binary file {f.relative_to(root).as_posix()}, {len(data)} bytes; open it to read)"
        return meta, body, hashlib.sha256(data).hexdigest()[:16], True
    meta, body = split(text.replace("\r\n", "\n").replace("\r", "\n"))
    return meta, body, body_hash(body), False


def first_line(body: str) -> str:
    for line in body.splitlines():
        line = line.strip().lstrip("#").strip()
        if line:
            return line[:100]
    return "(empty)"


SEEN = ".feedback-seen.json"
REVIEW_STATES = ("active", "completed")  # abandoned runs are not scanned


def review_files(root: pathlib.Path) -> list:
    runs = root / HOME / "runs"
    return [f for state in REVIEW_STATES for f in sorted((runs / state).glob("*/reviews/*.md"))]


def review_parts(review_file: pathlib.Path):
    """reviews/<stem>.<agent>.md -> (run dir, state, agent, target): target is the WP id, or the stage."""
    run = review_file.parent.parent
    state = run.parent.name
    stem, _, agent = review_file.name[:-len(".md")].rpartition(".")
    m = re.match(r"WP-\d+", stem)
    return run, state, agent or "unknown", (m.group(0) if m else stem or review_file.stem)


def load_seen(run: pathlib.Path) -> dict:
    path = run / "reviews" / SEEN
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except ValueError:
        return {}


def mark_seen(review_file, finding: str, section: str):
    """Remember which Human Feedback text was recorded for a review file, and as which finding."""
    review_file = pathlib.Path(review_file)
    run = review_file.parent.parent
    seen = load_seen(run)
    seen[review_file.name] = {"hash": body_hash(section), "finding": finding}
    path = run / "reviews" / SEEN
    path.write_text(json.dumps(seen, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def unseen_section(review_file: pathlib.Path):
    """The review's Human Feedback text when it is new or edited since last recorded, else None."""
    from review import human_feedback  # noqa: E402  (same engine folder)
    section = human_feedback(review_file)
    if not section:
        return None
    entry = load_seen(review_file.parent.parent).get(review_file.name) or {}
    return None if entry.get("hash") == body_hash(section) else section


def cmd_record_review(args) -> int:
    root = pathlib.Path(args.root).resolve()
    f = pathlib.Path(args.review_file)
    if not f.is_absolute():
        f = (root / f) if (root / f).exists() else f.resolve()
    if not f.exists():
        print(f"no review file {args.review_file}", file=sys.stderr)
        return 2
    f = f.resolve()  # one spelling of the path as root: on Windows a short (8.3) name can't be compared to a long one
    section = unseen_section(f)
    if section is None:
        print(f"{f.name}: no new Human Feedback")
        return 0
    from review import record_feedback  # noqa: E402
    run, state, agent, target = review_parts(f)
    earlier = (load_seen(run).get(f.name) or {}).get("finding")
    lead = (f"Written in the review file after hand-off (edited since {earlier}); the run did not wait for it."
            if earlier else "Written in the review file after hand-off; the run did not wait for it.")
    finding = record_feedback(run, argparse.Namespace(agent=agent, target=target, review_file=str(f)),
                              "late", "", f"{section}\n\n({lead})")
    if finding == "none":
        print(f"could not record feedback from {f.name}", file=sys.stderr)
        return 2
    mark_seen(f, finding, section)
    print(f"{finding} run={run.name} state={state} agent={agent} target={target}")
    return 0


def cmd_scan(args) -> int:
    root = pathlib.Path(args.root).resolve()
    reviews = 0
    for f in review_files(root):
        section = unseen_section(f)
        if section is None:
            continue
        reviews += 1
        run, state, _, _ = review_parts(f)
        print(f"review {f.relative_to(root).as_posix()}: {first_line(section)} (run={run.name} state={state})")
    pending = 0
    for f in items(root):
        meta, body, digest, _ = read_item(root, f)
        if not body.strip():
            continue
        if not meta.get("seen_hash"):
            state = "new"
        elif meta["seen_hash"] != digest:
            state = "changed"
        else:
            continue
        pending += 1
        print(f"{state} {f.relative_to(root).as_posix()}: {first_line(body)}")
    print(f"inbox: {pending} to process")
    print(f"reviews: {reviews} with new feedback")
    return 0


def cmd_set(args) -> int:
    root = pathlib.Path(args.root).resolve()
    f = pathlib.Path(args.item)
    if not f.is_absolute():
        f = (root / f) if (root / f).exists() else f.resolve()
    if not f.exists():
        print(f"no feedback item {args.item}", file=sys.stderr)
        return 2
    f = f.resolve()  # one spelling of the path as root: on Windows a short (8.3) name can't be compared to a long one
    meta, body, digest, binary = read_item(root, f)
    meta.update({
        "status": args.status,
        "actions": ", ".join(args.action),
        "note": args.note.replace("\n", " ").strip(),
        "refs": ", ".join(args.ref or []) or "none",
        "seen_hash": digest,
        "updated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
    })
    head = "\n".join(f"{k}: {meta[k]}" for k in KEYS if k in meta)
    record = f"---\n{head}\n---\n"
    base = inbox(root)
    in_done = "done" in f.resolve().relative_to(base.resolve()).parts[:-1]
    dest = f
    if args.status in ("applied", "declined") and not in_done:
        dest = base / "done" / f.name
    elif args.status in ("in-progress", "waiting") and in_done:  # reopened
        dest = base / f.name
    dest.parent.mkdir(parents=True, exist_ok=True)
    if binary:  # never rewrite the owner's file: move it as it is and keep the record beside it
        if dest != f:
            f.replace(dest)
            sidecar(f).unlink(missing_ok=True)
        sidecar(dest).write_text(record, encoding="utf-8", newline="\n")
    else:
        if dest != f:
            f.unlink()
        dest.write_text(f"{record}\n{body.lstrip(chr(10))}", encoding="utf-8", newline="\n")
    print(f"{dest.relative_to(root).as_posix()}: {args.status} ({meta['actions']})")
    return 0


def cmd_list(args) -> int:
    root = pathlib.Path(args.root).resolve()
    shown = 0
    for f in items(root, include_done=args.all):
        meta, body, digest, _ = read_item(root, f)
        status = meta.get("status", "open")
        if meta.get("seen_hash") and meta["seen_hash"] != digest:
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
    rr = sub.add_parser("record-review"); rr.add_argument("review_file"); rr.add_argument("--root", default=".")
    args = p.parse_args(argv)
    return {"scan": cmd_scan, "set": cmd_set, "list": cmd_list, "record-review": cmd_record_review}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())

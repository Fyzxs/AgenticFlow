"""Extract the owner's turns (plus the preceding agent message and tool calls) from Claude Code transcripts.

  python -I -B extract_claude.py --projects "-home-me-src-MyRepo*" "-home-me-src-Other" --out <dir>
                                 [--strip-prefix -home-me-src-] [--exclude-session <id>] [--include-live]

--projects takes one or more globs of folder names under ~/.claude/projects (one folder per working directory,
so a repo with worktrees has several). On Linux/macOS those names start with '-'; that is accepted here.
Sessions written in the last 10 minutes are skipped (one of them is usually the session doing the mining, and
a live session is incomplete); --include-live keeps them. --exclude-session drops a session by id (or prefix).
Writes <out>/turns.jsonl and <out>/digest_<project>.md.

turns.jsonl rows: proj, sess, ts, kind (HUMAN | REJECT | INTERRUPT), text, prev (end of the agent message
before it), tools (its last tool calls), flag (HUMAN rows only: the keyword regex matched; crude, about half
the real corrections).
"""
import argparse, json, glob, os, re, sys, time


def _argv(argv):
    """Let values start with '-' (folder names do; argparse would read them as options): `--projects A B` ->
    `--projects=A --projects=B`, `--strip-prefix -x` -> `--strip-prefix=-x`."""
    out, i = [], 0
    while i < len(argv):
        a = argv[i]; i += 1
        if a == '--projects':
            while i < len(argv) and not argv[i].startswith('--'):
                out.append('--projects=' + argv[i]); i += 1
        elif a in ('--strip-prefix', '--exclude-session', '--root', '--out') and i < len(argv):
            out.append(f'{a}={argv[i]}'); i += 1
        else:
            out.append(a)
    return out


_ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
_ap.add_argument('--projects', required=True, action='append',
                 help='one or more globs of project folder names under ~/.claude/projects')
_ap.add_argument('--out', required=True)
_ap.add_argument('--strip-prefix', default='', help='prefix removed from folder names to label projects')
_ap.add_argument('--root', default=os.path.expanduser('~/.claude/projects'))
_ap.add_argument('--exclude-session', action='append', default=[], help='session id (or prefix) to skip')
_ap.add_argument('--include-live', action='store_true', help='keep sessions written in the last 10 minutes')
_args = _ap.parse_args(_argv(sys.argv[1:]))
ROOT = _args.root
OUT = _args.out
os.makedirs(OUT, exist_ok=True)
sys.stdout.reconfigure(encoding='utf-8')
SKIP_PREFIX = ('<command-name>/clear', '<local-command', '<task-notification', '<system-reminder',
               'This session is being continued', 'Caveat:', 'Another Claude session', 'Base directory for this skill',
               '## Page contract', '<command-message>')
CORR = re.compile(r"\b(no[,.!]|nope|don'?t|do not|stop|wrong|incorrect|i said|i told|already (said|told)|again|actually|instead|not what|why (did|are|is|would)|you (missed|forgot|broke|didn'?t)|revert|undo|should(n'?t| not)|never|always|that'?s not|isn'?t right|please (just|stop)|we (don'?t|do not) use|not supposed)\b", re.I)

def text_of(ct):
    if isinstance(ct, str): return ct
    if isinstance(ct, list):
        return '\n'.join(x.get('text', '') for x in ct if isinstance(x, dict) and x.get('type') == 'text')
    return ''

def short_tool(x):
    inp = x.get('input') or {}
    s = inp.get('command') or inp.get('file_path') or inp.get('description') or inp.get('pattern') or inp.get('prompt') or ''
    return f"{x.get('name')}({str(s)[:120]!r})"

rows = []
files = sorted({f for g in _args.projects for f in glob.glob(os.path.join(ROOT, g, '*.jsonl'))})
if not files:
    sys.exit(f"no transcripts match {_args.projects} under {ROOT}")
skipped = []
for f in files:
    sid = os.path.basename(f)[:-6]
    live = not _args.include_live and time.time() - os.path.getmtime(f) < 600
    if live or any(sid.startswith(x) for x in _args.exclude_session):
        skipped.append(f"{os.path.basename(os.path.dirname(f))}/{sid[:8]}" + (' (live)' if live else ''))
        continue
    folder = os.path.basename(os.path.dirname(f))
    proj = (folder[len(_args.strip_prefix):] if _args.strip_prefix and folder.startswith(_args.strip_prefix) else folder).lstrip('-') or '(root)'
    sess = os.path.basename(f)[:8]
    last_text, tools = '', []
    for line in open(f, encoding='utf-8', errors='replace'):
        if '"type":"user"' not in line and '"type":"assistant"' not in line: continue
        try: o = json.loads(line)
        except Exception: continue
        if o.get('isSidechain'): continue
        t = o.get('type'); m = o.get('message') or {}; ct = m.get('content')
        if t == 'assistant':
            if isinstance(ct, list):
                for x in ct:
                    if x.get('type') == 'text' and x.get('text', '').strip():
                        last_text = x['text']; tools = []
                    elif x.get('type') == 'tool_use':
                        tools.append(short_tool(x))
            continue
        if t != 'user' or o.get('isMeta'): continue
        kind = (o.get('origin') or {}).get('kind')
        if kind in ('task-notification', 'peer'): continue
        ts = (o.get('timestamp') or '')[:16]
        # tool rejections carrying user feedback
        if isinstance(ct, list):
            for x in ct:
                if x.get('type') == 'tool_result':
                    s = text_of(x.get('content')) if isinstance(x.get('content'), list) else str(x.get('content') or '')
                    if s.startswith("The user doesn't want to proceed") or 'the user said:' in s.lower()[:400]:
                        rows.append(dict(proj=proj, sess=sess, ts=ts, kind='REJECT', text=s[:1500], prev=last_text[-600:], tools=tools[-4:]))
                elif x.get('type') == 'text' and x.get('text', '').startswith('[Request interrupted'):
                    rows.append(dict(proj=proj, sess=sess, ts=ts, kind='INTERRUPT', text=x['text'], prev=last_text[-600:], tools=tools[-4:]))
        txt = text_of(ct).strip()
        if not txt or txt.startswith(SKIP_PREFIX) or txt.startswith('[Request interrupted') or txt.startswith('[Image'):
            continue
        if isinstance(ct, list) and not kind and all(x.get('type') != 'text' for x in ct): continue
        m2 = re.search(r'<command-name>(.*?)</command-name>.*?<command-args>(.*?)</command-args>', txt, re.S)
        if m2: txt = f"[slash] {m2.group(1)} {m2.group(2)}".strip()
        rows.append(dict(proj=proj, sess=sess, ts=ts, kind='HUMAN', flag=bool(CORR.search(txt)),
                         text=txt[:2500] + (' …[truncated]' if len(txt) > 2500 else ''), prev=last_text[-600:], tools=tools[-4:]))
        last_text, tools = '', []

with open(os.path.join(OUT, 'turns.jsonl'), 'w', encoding='utf-8') as w:
    for r in rows: w.write(json.dumps(r, ensure_ascii=False) + '\n')
by = {}
for r in rows: by.setdefault(r['proj'], []).append(r)
for p, rs in by.items():
    with open(os.path.join(OUT, f'digest_{p}.md'), 'w', encoding='utf-8') as w:
        cur = None
        for r in sorted(rs, key=lambda r: r['ts']):
            if r['sess'] != cur:
                cur = r['sess']; w.write(f"\n# Session {cur} ({p})\n")
            tag = r['kind'] + (' ⚑' if r.get('flag') else '')
            w.write(f"\n---\n**[{r['ts']}] {tag}**\n")
            if r['prev'] or r['tools']:
                w.write(f"> Claude before: {r['prev'].strip()[-600:]!s}\n".replace('\n', '\n> ') + '\n')
                if r['tools']: w.write(f"> tools: {'; '.join(r['tools'])}\n")
            w.write(f"\nUSER: {r['text']}\n")
import collections
c = collections.Counter((r['proj'], r['kind'] + ('*' if r.get('flag') else '')) for r in rows)
for k, v in sorted(c.items()): print(v, k)
print('total', len(rows))
if skipped: print('skipped sessions:', ', '.join(skipped))

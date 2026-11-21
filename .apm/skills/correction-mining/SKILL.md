---
name: correction-mining
description: Mine an agent host's past session transcripts (~/.claude/projects) for the owner's corrections, group them into ranked themes, audit the repo's existing agent docs (CLAUDE.md, AGENTS.md, rules, instructions, agent files) against them, and propose where each lesson belongs (always-on instruction, path-scoped doc, hook or test, skill, agent, or delete). Use when setting up FyzxsFlow in a repo with history, when the owner says they keep repeating themselves to the agent, asks what keeps going wrong, wants a retro on their agent setup, or asks which documented rules aren't sticking — even if they don't say "correction mining".
---

# Correction mining

Corrections are the most honest signal about an agent setup: every "no", "I said", "once again" or
interrupted run is a lesson that did not carry forward. This skill finds them and routes each lesson to
where it would actually be enforced. The output is a proposal; the repo changes only after the owner approves.

Run the scripts with `python -I -B`: `-I` keeps the target repo's files off the import path, `-B` stops
Python writing `__pycache__` into a repo you were asked only to read.

## 1. Extract (script, no model cost)
Transcripts are large (mostly tool output). Reduce them to the owner's messages, each with the end of the
agent message before it and its last few tool calls:

```
python -I -B .fyzxsflow/package/skills/correction-mining/scripts/extract_claude.py \
    --projects "-home-me-src-MyRepo*" "-home-me-src-Other" --out <dir> --strip-prefix -home-me-src-
```

`--projects` takes one or more globs of folder names under `~/.claude/projects` (one folder per working
directory, so worktrees each have one; on Linux/macOS the names start with `-`, which is fine). It writes
`turns.jsonl` and one `digest_<project>.md` per project. Sessions written in the last 10 minutes are skipped
and listed — one of them is usually this session, which would otherwise mine itself (`--include-live` keeps
them; `--exclude-session <id>` drops one by id).

Row shape: `proj, sess, ts, kind (HUMAN | REJECT | INTERRUPT), text, prev, tools`, plus `flag` on HUMAN rows,
set when a keyword regex matched. The flag catches about half the real corrections, so it is a reading aid,
not a filter: the next step judges every message.

Other hosts: add an extractor per host that emits the same shape. GitHub Copilot's transcript location is not
yet known; see `adapters/copilot/README.md`.

## 2. Catalog
Split the digests across subagents when they are large (one per big digest, then merge). Without subagents,
catalog inline, digest by digest, and say in the report that you did — a reader weighs a single-pass catalog
differently.

For every message decide: correction, restated preference, clarification exposing a wrong assumption,
frustration, approval, or neutral. Group corrections into themes ranked by frequency × cost. For each theme
record a one-line rule, the evidence, what the agent did that triggered it, and the count.

Evidence is quoted **verbatim** with project + timestamp, the owner's typos included: the report is checked
against the transcripts, and a tidied quote reads as invented. Mark any cut as `[...]` and any typo you were
tempted to fix as `[sic]`.

Also list repeated workflows (skill candidates), things the owner approved (behaviours to keep), and
**decisions the owner settled or withdrew** — a proposal that re-opens one of those wastes the owner's time.

## 3. Audit the existing docs
For the repo's CLAUDE.md / AGENTS.md / instructions / rules / agent files / lessons registers, record load mode
and size (what loads every session), stale references, contradictions between files, and whether each
correction theme was **already documented**.

```
python -I -B .fyzxsflow/package/skills/correction-mining/scripts/check_refs.py --root .
```

`check_refs.py` covers the hand-written host docs: load mode, size, `paths:`/`applyTo:` globs that match no file
(a rule whose folder was renamed silently stops loading), and backticked paths that don't exist. Its path
matching is a heuristic, so confirm each hit. Add the owner's user-level `~/.claude/CLAUDE.md` to the always-on
size (it loads in every project), and note where it repeats a repo file word for word. Read the auto-memory of
every mined folder too (`~/.claude/projects/<folder>/memory/`, `ls` each one rather than assuming): a lesson kept
there loads only in sessions started in that exact folder, so one stranded under an old worktree's folder is
effectively undocumented. `.fyzxsflow/package/engine/docs_check.py` checks FyzxsFlow's own
docs, and only once `fyzxsflow-init` has run.

Audit the checkout in front of you first: it is what the owner will set up from, so its stale lines are findings
even when a later branch fixed them. Then, if the owner works on another branch or worktree, compare: mark each
item "stale here, fixed on <branch>" or "stale everywhere". A stale-here item still needs a fix here (or a
merge); a branch can make a fixed problem look current, or hide a new one.

A theme that was documented and still recurred is the most valuable result: prose did not work, so it needs a
hook, test or a different home.

## 4. Route and propose
Give each theme one **primary home** — always-on instruction · path-scoped doc · skill (a repeated workflow) ·
agent (only for isolated specialist work) · delete (stale) — **plus a hook or test when the rule can be checked
mechanically**. The pairing matters: the doc explains the why so the agent applies it to cases the check
doesn't cover; the check catches the misses. Say which themes have no mechanical check and why.

Write the proposal as a document for the owner. Change nothing in the repo until the owner approves.

## Output
`correction-mining-report.md` with:
1. How it was made: projects and sessions mined, sessions skipped, inline or split catalog.
2. The ranked themes (rule, verbatim evidence, trigger, count).
3. The cross-check table: theme → already documented? (file:line) → why it still happened → primary home +
   enforcement.
4. The doc audit (check_refs output, confirmed; contradictions; always-on size).
5. Settled or withdrawn decisions — don't re-propose.
6. The proposed changes in phases, smallest-risk first.

---
name: correction-mining
description: Mine an agent host's past session transcripts for the owner's corrections, group them into themes, audit the repo's existing agent docs against them, and propose where each lesson belongs (always-on instruction, path-scoped doc, hook or test, skill, agent, or delete). Use when setting up FyzxsFlow in a repo with history, or periodically to find what keeps going wrong.
---

# Correction mining

Corrections are the most honest signal about an agent setup: every "no", "I said", "once again" or
interrupted run is a lesson that did not carry forward. This skill finds them and routes each lesson to
where it would actually be enforced.

## 1. Extract (script, no model cost)
Transcripts are large (mostly tool output). Reduce them to the owner's messages, each with the end of the
agent message before it and its last few tool calls:

```
python -I .fyzxsflow/package/skills/correction-mining/scripts/extract_claude.py --projects "<glob of ~/.claude/projects dirs>" --out <dir>
```

This writes `turns.jsonl` and one `digest_<project>.md` per project. It flags likely corrections with a
keyword regex, which is crude: the next step must judge every message, flagged or not.

Other hosts: add an extractor per host that emits the same `turns.jsonl` shape
(`proj, sess, ts, kind, text, prev, tools`). GitHub Copilot's transcript location is not yet known; see
`adapters/copilot/README.md`.

## 2. Catalog (one agent per large digest, then merge)
For every message decide: correction, restated preference, clarification exposing a wrong assumption,
frustration, approval, or neutral. Group corrections into themes ranked by frequency × cost. For each
theme record a one-line rule, verbatim evidence (project + timestamp), what the agent did that triggered
it, and the count. Also list repeated workflows and things the owner approved (behaviours to keep).

## 3. Audit the existing docs
For the repo's CLAUDE.md / AGENTS.md / instructions / rules / agent files / lessons registers, record:
load mode and size (what loads every session), stale references (cited paths that no longer exist,
globs that match nothing — `.fyzxsflow/package/engine/docs_check.py` does the mechanical part), contradictions between
files, and whether each correction theme was **already documented**. A theme that was documented and
still recurred is the most valuable result: prose did not work, so it needs a hook, test or a different
home.

## 4. Route and propose
For each theme, propose one home: always-on instruction · path-scoped doc · hook or test (if it can be
checked mechanically) · skill (if it is a repeated workflow) · agent (only for isolated specialist work)
· delete (if it is stale). Write the proposal as a document for the owner. Change nothing in the repo
until the owner approves.

## Output
`correction-mining-report.md` with: the ranked themes, the cross-check table (theme → already documented?
→ why it still happened → fix), the doc audit, and the proposed changes in phases.

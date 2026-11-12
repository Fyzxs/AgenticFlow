# Plan: the Compactor agent

Goal: an agent, shipped in the package for projects that install FyzxsFlow, that shrinks every file the flow
loads into agent contexts (the package's own agent, context, instruction, prompt and skill files, the project's
`learned/` entries and its docs) without losing a rule, so each dispatch costs fewer tokens.

## Owner decisions (2026-11-12)
1. Scope: everything, including the package's agent files themselves, inside an installed project.
2. Trigger: on demand only (`/fyzxsflow-compact`). No automatic step.
3. Budget: no size budget enforced by a script.

## What grows (checked 2026-11-12)
| Source | Lands in context as | Bound before this change |
|---|---|---|
| `.fyzxsflow/learned/<agent>.md` | appended to every host agent file (`install.py` `with_learned`) | none |
| `.fyzxsflow/docs/**` | context packs | `docs.pack_budget_kb`, `docs_check.py` |
| package `agents/ context/ instructions/ prompts/ skills/` | the base of every host agent file; context read first by every agent | none; 244 KB of agent files in v0.2.0 (orchestrator 29.7 KB) |

## Design
- **Overlays survive upgrades.** `.fyzxsflow/package/` is replaced by every install, so a compacted package file
  lives in `.fyzxsflow/compacted/<package path>`, recorded in `compacted/manifest.json` with the hash of the
  package file it was made from. `install.py` (install and `--sync`) copies each overlay into the package when
  the package file still has that hash; after an upgrade that changed the file, the overlay is stale: the
  upstream file is kept and install prints a warning to re-run the compaction. Revert: `compact.py drop`, then
  reinstall.
- **Fidelity is a script** (`engine/compact.py check`, also run by `record`): frontmatter keys other than
  `description` unchanged; every heading, backtick span, fenced-code line, link target, path, finding / criterion
  id and number in the original is still present, unless listed with `--accept` (each acceptance explained in the
  report). Meaning is the Validator's job.
- **Learned entries and project docs** are the project's own files: compacted in place; `docs_check.py` and
  `pointers.py --check` keep passing. Owner policy files (`profile.md`, `feature-flags.md`, `config.json`,
  `gates.json`) are proposed, never edited.
- **Run shape**: `/fyzxsflow-compact [targets]` → the Orchestrator's *Compaction runs*: a run with
  `--source compact`, `compactor` + validator, stamp, review file, commit by path, close.

## Pieces
- [x] `engine/compact.py` (measure, check, record, status, drop; `apply` used by install) + `engine/layout.py` COMPACTED
- [x] `engine/install.py` applies overlays; tests in `engine/tests/test_compact.py`
- [x] `.apm/agents/compactor.agent.md`, `.apm/prompts/fyzxsflow-compact.prompt.md`
- [x] Orchestrator *Compaction runs*, `run-folder.md`, README, HOW-TO, design.md, adapters

## Trial (2026-11-12, scratch install)
A subagent followed `compactor.agent.md` on `agents/curator.agent.md` (overlay, 10214 -> 9621 bytes) and a seeded
`learned/implementer.md` (893 -> 510 bytes, two endpoint entries merged, one entry the package states removed);
`install.py --sync` applied the overlay (`status`: applied). Fixed from what it found:
- backtick spans wrapped over two lines were skipped, so losses inside them passed and prose was misread as code
  (2 false "missing" lines); spans now cross a single newline and compare with whitespace collapsed;
- `Hits: n` counts no longer count as numbers to keep (merging sums them);
- `measure` ranks agents by host size (file + learned) and its totals count learned entries once;
- the agent file now covers: headings in docs, `--before` for a second pass, accept scope, check bugs into Risks,
  `path:line` for removed entries, a Risks section, never committing `__pycache__/`.

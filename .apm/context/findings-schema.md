# Findings

A finding is one JSON object per line in `findings.jsonl`. Write findings with
`python -I .agentflow/engine/findings.py add ...`, which validates them. Never hand-edit the file.

| Field | Required | Meaning |
|---|---|---|
| `id` | auto | `F-<n>` within the run |
| `run` | auto | run id |
| `source` | yes | agent that found it (`validator`, `reviewer-narrow`, `runner`, `human`, ...) |
| `target` | yes | what it is about: an agent name (`implementer`), a doc path, or `code` |
| `kind` | yes | see below |
| `severity` | yes | `major` (must fix before merge), `medium` (judgment call), `minor`, `observation` |
| `summary` | yes | one sentence |
| `evidence` | yes | list of `path:line` (or a URL for a PR comment) |
| `rule` | no | the general rule that would have prevented it, written as an instruction |
| `fixed` | no | `true` if the source already corrected the output |

## Kinds
- `instance`: a one-off mistake; the output was wrong but nothing upstream misled it.
- `agent-gap`: the agent file lacked guidance, or its guidance led to the miss.
- `context-gap`: a repo doc lacked or misstated something (the Implementer followed the docs and was wrong).
- `docs-drift`: a doc cites a path or pattern that no longer matches the code.
- `flag`: a feature-flag rule was broken (coverage, placement, off-path, revert speed, data safety).
- `flake`: a test passed on rerun or failed only in shuffled order.
- `env`: environment problem (port, service, config).
- `human-edit`: the owner changed a run artifact between stages (written by `run.py edits --record`).
- `scope-request`: an agent needed to touch something outside its package.
- `replan`: the plan was wrong; Locate must redo it.
- `owner-decision`: only the owner can decide; goes to the next gate.

The Curator reads `kind`, `target` and `rule`. A finding without a `rule` can still be fixed, but cannot
improve anything.

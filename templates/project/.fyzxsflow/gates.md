# Deterministic gates

Every linter, scanner or custom check that can say pass or fail without judgment is declared in
`gates.json` and run by `.fyzxsflow/package/engine/gates.py`. The Gate Analyst reads the results and recommends kick back,
correct, or move on; it never runs a tool directly and never edits this registry.

## Stages
| Stage | When | What belongs here |
|---|---|---|
| `quick` | per work package | very fast checks scoped by `paths` |
| `ci` | every build round, before review | everything CI already enforces, plus fast linters |
| `extreme` | sign-off, with the Runner's `--extreme` | every gate, including slow scanners |
| `pre-pr` | just before the PR is produced | scanners whose results belong in the PR (secrets, dependencies, licences) |

Run gates as often as their cost allows. A gate that runs only at `extreme` finds problems late.

## Fields
| Field | Required | Meaning |
|---|---|---|
| `name` | yes | unique; also the baseline file name |
| `enabled` | no | default `true`; set `false` to keep a gate declared but off |
| `stages` | yes | which stages run it |
| `run` | yes | the command; `{out}` is replaced with the path the tool must write SARIF to |
| `format` | yes | `sarif` (results parsed from `{out}`) or `exit` (pass/fail by exit code) |
| `fail_on` | no | `error` (default), `warning`, `note`, or `never` (report only) |
| `ok_exit_codes` | no | exit codes meaning "the tool ran" (many scanners exit 1 when they find something); default `[0]` |
| `paths` | no | globs; the gate runs only if a changed path matches. Never on dependency or advisory scanners: they read a live feed, so their results change without any file changing |
| `cwd`, `timeout_s` | no | working directory (repo-relative) and time limit |

A stage that selects no gate reports `empty`, not `pass`: nothing was checked.

## Baselines
Results already present when a gate is added go into `.fyzxsflow/baselines/<gate>.json`, so only **new**
results can block. Accepting a baseline is an owner action:
`python -I .fyzxsflow/package/engine/gates.py --stage extreme --update-baseline <gate>`.

## Gates in this repo
<!-- One line per enabled gate: what it checks and why it is at its stage. -->
- UNRESOLVED: list this repo's gates (the owner's scanners go here).

---
agent: <agent name>
target: <WP-01 | review | ...>
run: <run-id>
result: <done | partial | failed>      # validators: pass | corrected | fail
---

# <agent> — <target>

## Acceptance criteria
<!-- One row per criterion this invocation was responsible for. Evidence is a path:line, a test name,
     or a Runner summary path. "met" without evidence counts as not met. -->
| Criterion | Status | Evidence |
|---|---|---|
| AC-1 | met / not met / partial | `path:line`, test `Name`, `runner/<id>.json` |
| WP-01.1 | met | ... |

## Changed files
- `path` — <one line on what changed>

## Flag
- name, seam, off path untouched: yes/no

## Contract
- produced/consumed; matches the package: yes/no

## Assumptions
- <assumption> — basis: <why>

## Findings logged
- F-<n>: <summary>

## Risks
- <anything the next agent or the owner should know>

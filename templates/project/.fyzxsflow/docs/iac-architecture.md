---
paths:
  - "UNRESOLVED/**"
---

# IaC architecture

<!-- Written by the Repo Cartographer from the repo's pipelines and infrastructure code. Every claim cites
     a real file. Loaded by the IaC Implementer, the IaC Reviewer and the Code Indicator. -->

## Where things live
| Kind | Location | Example |
|---|---|---|
| Pipelines | `UNRESOLVED` | `UNRESOLVED` |
| Shared step / job templates | `UNRESOLVED` | |
| Infrastructure modules (Bicep) | `UNRESOLVED` | |
| Per-environment parameters | `UNRESOLVED` | |

## Environments
| Environment | Deployed by | Approval | Agents may preview (what-if)? |
|---|---|---|---|
| UNRESOLVED | | | no |

## Conventions
- Naming: UNRESOLVED
- Tags: UNRESOLVED
- Secrets: UNRESOLVED (the secret store and how pipelines and apps reference it)
- Identities and permissions: UNRESOLVED
- Version pinning (tasks, templates, modules): UNRESOLVED

## Deploy order
UNRESOLVED (e.g. infrastructure → database → backend → frontend)

## Checks agents can run without deploying
- UNRESOLVED (e.g. `az bicep build`, `az bicep lint`, pipeline YAML validation, a what-if against a named
  non-production target)

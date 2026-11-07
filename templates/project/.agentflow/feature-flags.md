# Feature-flag source

<!-- Every agent that plans, builds, tests or reviews a flag reads this file. The Cartographer fills it from
     existing flag usage; it never invents a provider and never changes Policy. -->

## Policy
Policy: required

<!-- The owner's call, set once per project.
     required      every behaviour change ships behind a runtime flag (default off), or is declared
                   `unflaggable` with a reason and a revert path and goes to the plan gate. While Provider
                   is UNRESOLVED, runs stop at Locate.
     not-required  no flags are planned, built, tested or reviewed; each work package records
                   `not-required` and its revert path (usually: revert the commit and redeploy); a
                   missing provider is not a blocker. The rest of this file may stay UNRESOLVED.
     Per run, the owner can override either way in the request ("no feature flag for this one" /
     "flag this one"); the Work Summarizer records it in brief.md as `flags:`. -->

## Provider
UNRESOLVED: the system that holds flag values, and how a flip reaches a running app without a deploy.

## Reading a flag, per layer
| Layer | How to read a flag (exact call or injected reader) | Example |
|---|---|---|
| Backend | UNRESOLVED | `path:line` |
| Frontend | UNRESOLVED | |
| Background jobs | UNRESOLVED | |

## Allowed seams
<!-- Where a flag may be read in each layer, and where it may not. The Feature Flag Reviewer judges
     placement against this section. -->
- Backend: UNRESOLVED (e.g. the dispatch point that selects an implementation; never inside domain logic)
- Frontend: UNRESOLVED (e.g. route or top-level component boundary)

## Naming and registry
- Name pattern: UNRESOLVED (e.g. `<area>.<feature>`)
- Registry: UNRESOLVED (where each flag is declared with owner, created date, default, expiry)
- Default for every new flag: **off**

## Creating and flipping
| Environment | Who may create | Who may flip | Agents may |
|---|---|---|---|
| local | anyone | anyone | create and flip |
| UNRESOLVED | | | nothing (owner gate) |

## Testing both states
UNRESOLVED: how a test, and how a Runner mode, sets a flag off and on.

## Frontend source
UNRESOLVED: how the UI gets the same flag values as the backend.

## Retirement
- Expiry: UNRESOLVED (e.g. 30 days after the flag is on in production)
- A `retire <flag>` run removes the off path, the flag reads, the `FLAGGED` markers and the registry entry.

# End-to-end testing — <repo name>

<!-- Written by the E2E Investigator (when the opt-in `e2e` step is on) and kept current by the E2E Implementer.
     Every agent that plans, builds, proves or reviews end-to-end work reads it. Every claim cites a real path.
     The engine reads only the Status line (run.py ship-check, docs_check.py). -->

Status: not-set-up

<!-- not-set-up    nobody has looked yet (also what a missing file means)
     setup-needed  investigated: the plan below is ready for a setup run, waiting for the owner to start it
     blocked       a dependency has no substitute without a product change or an owner decision (see Questions)
     ready         the modes below pass; from now on ship-check blocks on them (with the e2e step on) -->

## Modes
| Mode | Defined | What it proves |
|---|---|---|
| `e2e-airplane` | no | everything on this machine: containers, emulators, mock servers; no external calls |
| `e2e-connected` | no | the app on this machine, calling only the approved external services below |

<!-- "Airplane" is the intent, not a switch: the network stays on and the Runner checks that nothing the mode
     starts calls out (config.json.readme.md -> network). A project can have either mode, or both. -->

## How the app runs end to end
- Entry points (UI, API, workers) and how each starts locally: UNRESOLVED
- E2E framework and where the scenarios live: UNRESOLVED
- Smoke scenario: UNRESOLVED

## External dependencies
| Dependency | Reached from | Airplane substitute | Kind | Prefetch | Config |
|---|---|---|---|---|---|

<!-- One row per external thing the running system touches: databases, caches, queues, blob storage, identity,
     third-party APIs, email/SMS, feature-flag service, telemetry.
     Kind, in order of preference: emulator (Azurite, Cosmos DB emulator, LocalStack, ...) > container (the real
     software: Postgres, Redis, RabbitMQ, Mailpit, a mock OIDC server) > contract-mock (Prism from an OpenAPI
     spec, WireMock) > fake (in-process, behind an existing seam) > none (blocked: say why under Questions).
     Prefetch: the image with a pinned tag or digest, the package, and its size.
     Config: the local setting that points the app at the substitute (well-known emulator keys only; never a
     real secret). -->

## Connected mode: approved external services
| Service | Environment (never production) | What the tests do there | Approved by |
|---|---|---|---|

<!-- Only services the owner approved, by name and environment. Tests that write there must clean up. -->

## Prefetch (online, once per machine)
- `e2e-prefetch` mode: UNRESOLVED

## Seed data
UNRESOLVED: what the scenarios need, and how it loads without the network.

## Setup plan
<!-- Numbered criteria the setup run must meet (E2E-1..n): substitutes running, the config profile, the modes,
     the smoke scenario passing in each mode. The setup run's brief takes them as its acceptance criteria. -->

## How to run it
<!-- Filled by the E2E Implementer: python -I .fyzxsflow/package/engine/runner.py e2e-prefetch (once, online),
     then e2e-airplane / e2e-connected; how to bring the stack up and down by hand. -->

## Questions for the owner
<!-- One list, each self-contained, with options and a recommendation. -->

## History
<!-- date, run id, what changed (investigated, set up, a dependency added) -->

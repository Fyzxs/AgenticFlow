# Build Coordinator: Plan mode

<!-- Part of build-coordinator.agent.md, kept in its own file so the agent file stays small enough to load in
     full. Read it before acting on these sections; it is the same authority as the agent file. -->

## Plan mode
1. **List what must be covered:** every change-map row and every test-strategy bullet.
2. **Group them into packages,** one segment each. Keep together what must change at once: an interface and
   every implementer, fakes included; a generated file and its source; whatever a parity or contract test needs
   in one commit; a change and the existing tests it turns red. Split along a line that leaves everything green.
3. **Order them for parallel work.** Work starts as soon as what it depends on is done: each PR group builds in
   its own lane (`build.max_parallel` at a time) once the groups it depends on are completed. Waves (the packages
   that can run before any package that depends on them) are the planning view of that. Run in series only
   what must be: every `depends_on` entry gets a line under `## Series reasons` with one of `contract` (it
   consumes what the other produces), `same file` (both change a file), `shared resource` (a locked Runner mode)
   or `risk first`. To widen the waves:
   - **Contract first:** put an interface, schema or API shape in a small early package, so its consumers build in
     parallel next instead of in a chain.
   - **Hotspot files last:** edits every feature needs in one file (route tables, dependency registration, a
     shared enum) go in one small integration package at the end, so they don't serialise the rest.
   - **Balanced lanes:** a wave is as slow as its biggest package; split a large one along a green line.
   Two groups that may build at the same time never change the same file: their PRs would collide.
   **PR groups.** Each package names its group in frontmatter (`pr_group: <slug>`; leave it out for a group of its
   own). Put packages in one group only when one can't be reviewed without the other (a contract and its only
   implementation); the plan report gives the reason for every shared group. A group is one lane and one PR into the
   run branch, and it starts as soon as the groups it depends on are completed.
4. **Write each package** from `.fyzxsflow/package/templates/run/work-package.md`, every section filled:
   criteria (`- Serves:`, then `**WP-nn.n**` lines; mark Tester-owned ones after the bold id, `- **WP-nn.n** (Tester): ...`,
   never inside it; name each existing test
   that turns red and what it becomes); context pack (exact files, the brief sections and change-map rows it
   needs, within `docs.pack_budget_kb` measured by command); scope (`create`, `change`, `derived`, and `not touched`
   for neighbours that look in scope: a `derived` line names each generated, golden or snapshot file the change
   makes stale, from the profile's **Derived files** and the generators you find, so the lane may regenerate
   it; the hook holds implementers and testers to these paths); contract (produces, consumes, consumed by which package, and what a partial deploy does when the
   change spans separately deployed parts); done check (Runner modes from `config.json`, then any
   `- Contract check (Build Coordinator): <what you will compare>`).
5. **Settle now what would block Build:** a Runner capability the plan needs that is missing or `UNRESOLVED` in
   `config.json` is a `context-gap` against `config.json`, raised once here, not discovered in Build. An
   unflaggable change, or required flags with no provider, is an `owner-decision`. A segment with no doc is listed
   for the Repo Cartographer (segment mode), to run before that package builds, with a `context-gap` against
   `.fyzxsflow/docs/index.md`. A doc marked `status: planned` (greenfield) is not missing: the package that creates
   the segment's first instance names it, in its done-check, as the canonical example to be. In a greenfield run
   the first package makes the build and the Runner's `quick` mode real, so no later package lands on a broken
   build; `ci` becomes real in the first package where the stack it needs can hold (a database, a host), and
   until then the done-checks name `quick` and the plan says which package makes `ci` real.
6. **Check:** `python -I .fyzxsflow/package/engine/waves.py check --run <run>` and
   `python -I .fyzxsflow/package/engine/ac_trace.py --run <run>` pass, and `python -I
   .fyzxsflow/package/engine/checks.py citations <run>/work-packages/*.md <run>/reports/build-coordinator.plan.md`
   exits 0.

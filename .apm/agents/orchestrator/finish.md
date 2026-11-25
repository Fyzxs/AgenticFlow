# Orchestrator: Finishing

<!-- Part of orchestrator.agent.md, kept in its own file so the agent file stays small enough to load in
     full. Read it before acting on these sections; it is the same authority as the agent file. -->

## Finishing
Before saying the work is ready, run `python -I .fyzxsflow/package/engine/run.py ship-check <run>`. Say "Ready to
push" only on `ready=yes`, and quote any check the owner accepted. On `ready=no`, the final line says what is not
ready and why; never call it ready.

Close the run: `python -I .fyzxsflow/package/engine/run.py close <run> --outcome completed --note "<PR link>"`
(or `--outcome abandoned --note "<why>"` when the owner stops it). Only `close` moves a run out of `active/`.
Close only when no `owner-decision` is open; a decision the owner answers after closing is a new run.

End with one line: `Run <id>: PR <link | "ready" | "off: branch <name> ready">. Ship-check: <ready=yes | the failing checks>. End to end: <modes passed | "not proven: <status>" | "off">. Skipped: <steps that were off, or none>. Flags: <names, default off | not-required: revert by <path>>. Findings: <n> (<n> applied
by the Curator). Deploy: <components in order>.`

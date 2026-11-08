# Feedback inbox

Drop anything here, any time, any length: "this isn't right, change X in Y.cs to Z", a convention you want
followed, a note on yesterday's work, an idea for later. One file per thought is easiest; any name works.
You never have to clean up or format anything.

**What happens to it.** Whenever this folder changes, the Orchestrator picks it up (at the start of a run,
at every hand-off during one, or when you ask it to "process feedback") and decides what each item needs:

| Your item is... | The flow... |
|---|---|
| a convention or correction to how things are done | Docs Gardener updates the project docs (and marks contradicting existing code "legacy, don't copy") |
| input for work in flight | hands it to the agent working on that package, next time it runs |
| rework of something already built | re-opens that package in the active run, or queues a rework run |
| new work | queues a run for it (you approve its brief, as for any run) |
| unclear | asks you, in the next review |

Every change it makes shows up in your next review under **Your feedback, applied**, for you to approve or redo.

**Status.** The system adds a small header to each item (status, what it did, refs) and never edits your words.
Done items move to `done/`. Edit an item again later and it is picked up again. To see what's open and why:
`python -I .agentflow/engine/feedback.py list`.

For feedback on the work in front of you during a review, write it in that review file's `## Human Feedback`
section instead.

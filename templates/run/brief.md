---
source: prompt            # prompt | ado:<id>
run: <run-id>
---

# <One-sentence goal>

## Problem
<What is wrong or missing today, and for whom. Use the glossary's vocabulary.>

## Acceptance criteria
<!-- REQUIRED. No criteria, no implementation. Each criterion is:
     - numbered AC-<n>, never renumbered once written;
     - checkable: a reader can say pass or fail by looking at behaviour, not intent;
     - one behaviour per criterion (split "and");
     - tagged (stated) when it came from the input, (inferred) when the Work Summarizer derived it.
     Prefer Given / When / Then for behaviour; a plain checkable statement is fine for constraints. -->
- **AC-1** (stated): Given <context>, when <action>, then <observable result>.
- **AC-2** (inferred): <checkable statement>.

## Out of scope
- <What this work explicitly does not do.>

## Constraints
- <Performance, compatibility, security, deadlines, settled decisions that apply.>

## Assumptions
<!-- Every inference the summarizer made. Ones that would change the design are also logged as
     owner-decision findings. -->
- <assumption> — basis: <why>

## Source
<For ado: the item, and its Story / Feature / Epic titles with ids. For prompt: "the prompt in input.md".>

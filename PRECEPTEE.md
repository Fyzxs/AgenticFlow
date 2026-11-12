# Preceptee mode

Preceptee mode turns FyzxsFlow into a preceptor for the engineer running it. The engineer (the *preceptee*) writes
the code and makes the judgment calls; the flow's agents coach instead of doing the work for them. They ask
before they tell, review the preceptee's pull requests the way a senior engineer would, and ease off as the
preceptee improves. It follows a preceptorship model: a senior guides a preceptee on real work, and the tool
doesn't hand over an answer before the learner has tried.

**It is off by default.** Nothing changes for anyone until you turn it on.

## Turn it on

**For one run** (the usual way), start the run with `--preceptee`:

```
/flow --preceptee add CSV export to the orders page
```

On the GitHub Copilot CLI: `copilot --agent=orchestrator --prompt "--preceptee add CSV export to the orders page"`.

**For every run in a project**, switch the `precept` step on:

```
python -I .fyzxsflow/package/engine/steps.py set precept on --reason "this repo is for training"
```

That writes `"steps": { "on": ["precept"] }` into `.fyzxsflow/config.json`. To switch it off again:
`steps.py set precept off --reason "<why>"`. To check where it stands: `steps.py enabled precept`.

**What it needs:**
- FyzxsFlow 0.3.0 or later installed in the repo (reinstall to upgrade; see [HOW-TO → Upgrade](HOW-TO.md#upgrade)).
- For coaching on pull requests (the default): the `pr` step on, a remote on GitHub or Azure DevOps, and `gh` or
  `az` signed in. Without them, coaching happens in the chat session instead.
- One preceptee per machine. The person running the flow is the preceptee. Their handle comes from
  `git config user.name`.

## What happens in a run

The run is a normal FyzxsFlow run, with the same checks, reviews and ship line. At the engineer's steps it stops
and the preceptee goes first:

| Rubric area | When | The preceptee | Then |
|---|---|---|---|
| 6 codebase, build, tests | each work package's Implementer and Tester steps | writes the code, then the tests, in the package's own worktree | it arrives as their own pull request, and the Preceptor reviews it there |
| 1 verifying AI output | each package an agent wrote | reviews the agent's PR first, as review comments | the Preceptor shows what they missed, broad to specific |
| 3 directing agents | Intake | writes the acceptance criteria | compared with the agent's brief |
| 4 calibrated trust | every approve or redo | gives a one-line reason | "why did you accept this?" when an approved output later drew findings |
| 2, 5, 8 debugging, design, security | after a test failure, the plan, the security review | answers a question posted on the PR, when they like | compared with what the agents found |
| 9 learning hygiene | before the final PR | explains every changed file, then a short quiz without AI help | ship-check requires the explanations |

Operations (area 7) is out of the flow's reach.

### Review on the pull request

The preceptee's code arrives as its own pull request into the run's branch. The Preceptor reviews it the way a
senior engineer would: it never posts the fix, and it gets more specific only when the broader comment didn't
lead to a correction:

1. A question on the PR: *"What does the export do with a customer whose name has a comma?"*
2. On the file: *"Something in `src/orders.py` doesn't handle every name. Which input?"*
3. On the method: *"Walk `export_csv` through that name."*
4. On the line, still as a question.
5. A reply that explains it, with a worked example from the codebase.

Each comment starts `Agent AI Preceptor:`. The preceptee answers with a reply or a push to the same PR, and the run
waits for them; `/flow resume` picks up their reply. Their human preceptor reads the whole exchange on the PR.
Once everything is fixed, the PR is published as ready for review, like any group PR.

The same coaching is available in the chat session at any time. Hints there climb the same way: a question, the
doc section, the file, the shape of the answer, a worked example. The agents' version of a step is never shown
before the preceptee attempts it or gives up (`bail`). A script enforces that order.

## Easing off

Each area has a support level:

| Level | What happens |
|---|---|
| `full` | the run pauses, the preceptee goes first, and the Preceptor offers hints and questions |
| `light` | the run pauses and the preceptee goes first; hints only when asked |
| `spot` | one exercise in three pauses; the rest are the agents', with questions afterwards |
| `off` | no coaching in that area |

After **4, 7 and 10** good answers in a row in an area, the Preceptor *asks* whether to step it down. It never lowers
a level itself. A good answer is work the preceptee did themselves: no bail, no hint past the first, and no major or
medium finding on it. Writing code is tracked per language (from the work package's tech docs), so TypeScript can
ease off while SQL stays at `full`. Reaching `off` is not graduation. It means the agent can't judge any further;
only the human preceptor signs an area off.

The preceptee can change any area at any time, without a reason:

```
python -I .fyzxsflow/package/engine/preceptee.py area 8 off               # for good
python -I .fyzxsflow/package/engine/preceptee.py area 3 off --run <run>   # this run only
python -I .fyzxsflow/package/engine/preceptee.py status                   # levels, streaks, sign-offs
```

## The record, and sharing it

The review comments on the PR are public, the way any review is. Everything that measures the person stays on
their machine, in `~/.fyzxsflow/preceptee/`, and never goes into the repo, the run folder or a PR: attempts, how
specific the comments had to get, streaks, prompts, reasons, explanations and quiz answers.

To share it with their preceptor:

```
python -I .fyzxsflow/package/engine/preceptee.py digest --out ~/Documents
```

That writes one Markdown file of evidence per rubric area. The preceptee reads it, removes anything they want, and
sends it however their team shares private files. The preceptor writes under its `## Preceptor notes`, for example
`- area 1: signed off` or `- area 2: level full`, and sends it back. Then:

```
python -I .fyzxsflow/package/engine/preceptee.py import <the returned digest>
```

For an organisation's program measures, `preceptee.py export --consent` prints aggregated numbers only, with no
name, notes or runs.

## Settings

`~/.fyzxsflow/preceptee.json`, every key optional:

```json
{ "handle": "quinn-gil", "prompt_after": { "light": 4, "spot": 7, "off": 10 }, "spot_every": 3, "seed_every": 4 }
```

| Key | Default | Meaning |
|---|---|---|
| `handle` | `git config user.name`, as a slug | the name on the digest |
| `prompt_after` | `4`, `7`, `10` | good answers in a row before the Preceptor offers `light`, `spot`, `off` |
| `spot_every` | `3` | at `spot`, one exercise in this many pauses |
| `seed_every` | `4` | one review in this many (area 1, in the session) contains a planted flaw to find |

**Planted flaws never reach the code.** Only the Seeder agent plants one, and only in preceptee mode. It writes a
practice copy of an agent's change, with its answer key, in the preceptee's own folder, never in the repo, a branch
or a PR. The script refuses a seed outside preceptee mode or inside the repo, and ship-check fails if a planted line
ever appears in the repo. Every other agent is forbidden to introduce a mistake on purpose, in any mode.

## More

- Why it is designed this way, and how it maps the preceptorship rubric: [`docs/preceptee-mode.md`](docs/preceptee-mode.md).
- The agent's own instructions: [`.apm/agents/preceptor.agent.md`](.apm/agents/preceptor.agent.md).
- Every command: `python -I .fyzxsflow/package/engine/preceptee.py --help`.

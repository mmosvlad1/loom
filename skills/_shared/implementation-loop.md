# Implementation Loop

The loop that builds or fixes one implementation phase: implementer, checks, reviewer, and fix attempts. `implement` runs it for every implementation phase. `iterate` runs it for fixes. Both use the same steps, limits, and results, so a phase is done or blocked by the same rules.

You orchestrate. The `loom:implementer` agent changes the code; it never commits. The `loom:implementation-reviewer` agent compares the change with the reference. You run the checks and decide the result.

## Inputs

- **Reference**: the plan path `<task dir>/04-plan.md` and the implementation phase number N. In oneshot mode: the ticket path `<task dir>/00-ticket.md` (the only implementation phase is N = 1).
- **First run**: one of these:
  - **phase mode**: build implementation phase N (`implement`, or `iterate` for a blocked phase with a clean working tree).
  - **Fix mode**: fix a numbered list of fix items (`iterate`). Each item names the file, the expected result, and the reference.
- **Limit**: `implement.maxFixAttempts` from the `loom-state --json` output (default `2`). It counts the fix attempts after the first run.
- **Configuration**: the agents do not read `.claude/loom.json`. Every prompt carries the resolved values from `loom-state --json`, as these lines. Write a command in backticks, and `null` without backticks for a check that is `null` in the state (the project has no such check):
  ```text
  Checks: check = `<checks.check>`; lint = `<checks.lint>`; typecheck = `<checks.typecheck>`; test = `<checks.test>`
  Conventions: <docs.conventions>
  Main branch: <mainBranch>
  ```
  The implementer gets the `Checks:` and `Conventions:` lines. The reviewer gets the `Conventions:` and `Main branch:` lines.

## Steps

1. **Implementer.** Launch `loom:implementer` with a short prompt and the configuration lines above. The agent reads the plan or ticket itself; do not copy their content into the prompt.
   - phase mode: `Implement implementation phase N of the plan at <task dir>/04-plan.md.` (oneshot: `Implement the change in the ticket at <task dir>/00-ticket.md.`)
   - Fix mode: the same reference, the word `Fix`, and the fix items.
   - If the working tree already holds part of the work (a resumed run), add: `The working tree already contains part of this work; continue from it.`
   - If an earlier run was blocked, add the reason as context: `An earlier run was blocked by: <reason>.`
2. **Open problems.** Read the implementer's report. If `Open problems` lists a problem that needs a design decision or a plan change (the form Expected / Found / Why it matters), stop the loop. The result is **blocked**, with that problem as the reason. Do not ask the implementer to guess.
3. **Checks.** Run `checks.check` yourself, once, as the shared `git-flow.md` describes.
   - The `SubagentStop` hook already ran it when the implementer finished. The hook blocks the implementer while the checks fail, but lets it stop after `hooks.maxCheckAttempts` failed attempts.
   - So failing checks here mean the hook gave up. Stop the loop. The result is **blocked**, with the reason `checks.check fails: <the key failure lines>`.
   - Never commit while the checks fail.
4. **Reviewer.** Launch `loom:implementation-reviewer` with the same reference, the `Conventions:` and `Main branch:` lines, the implementer's report, and the fix items (if any). Use fix mode when the run had fix items: write `fix mode` and the items in the prompt.
5. **Verdict.**
   - `pass` (no `blocking` items): the result is **done**.
   - `changes-needed`: if fewer than `implement.maxFixAttempts` fix attempts ran, launch `loom:implementer` in Fix mode with **only** the `blocking` items, copied word for word. Then continue with step 2.
   - `changes-needed` after `implement.maxFixAttempts` fix attempts: the result is **blocked**, with the remaining `blocking` items as the reason.
6. **Record.** Keep for the `log.md` entry, also when the result is done:
   - the checks result (the implementer's one-line summary, e.g. `lint ✓ typecheck ✓ test ✓ (42 passed)`)
   - the verdict and the number of fix attempts
   - every `nit` item
   - every deviation and addition from the reviewer, and every deviation the implementer reported, with its reason
   - the implementer's `Manual verification needed` items
   - the `Files changed` of every implementer run (you stage these)

Send only `blocking` items back to the implementer. Never send `nit` items, deviations that are not blocking, or your own ideas.

## Results

| Result | What you do |
|---|---|
| **done** | Commit as the shared `git-flow.md` describes. Then write the `done` entry in `log.md`. |
| **blocked** | Do not commit. Leave the change in the working tree. Append `## Phase N — blocked` and a `Reason:` line to `log.md`. Stop. `/loom:iterate` fixes a blocked phase. |

The exact `log.md` entries are in the plugin file `skills/implement/references/log-format.md`.

## Rules

- One implementer run per launch. Launch a fresh agent for every implementation phase and every fix attempt.
- Do not edit code yourself. The implementer owns the code change; you own git, `04-plan.md` checkboxes, and `log.md`.
- Treat the agents' reports as claims. Verify file lists with `git status --porcelain` and checks by running them.

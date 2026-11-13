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
  Style guide: <docs.style>
  Screens: <docs.screens>
  Main branch: <mainBranch>
  ```
  The implementer gets the `Checks:` and `Conventions:` lines. The reviewer gets the `Conventions:` and `Main branch:` lines.
  The `Style guide:` line goes into a prompt only when `design.style` is `true`, and the `Screens:` line only when `design.screens` is not empty. Each one then follows the `Conventions:` line in every prompt that has that line, for both agents.
  A run that changes `.claude/loom.json` makes these values out of date: step 3 takes them again.

## Settings change

In auto permission mode Claude Code denies a subagent's edit of a settings file. So the implementer never edits `.claude/settings.json` or `.claude/settings.local.json`. You apply a settings change of the plan yourself, in the main context. The rule holds for every task; implementation phase 1 of the onboarding task is such a phase.

Two skills run this section, before step 1:

- `implement`, before it starts implementation phase N: before the `in-progress` entry in `log.md` and before the implementer.
- `iterate`, before it fixes a blocked phase that has no commit yet (in phase mode or in Fix mode).

The plan gives the change in one fixed form, inside the `### Changes` of `## Phase N:`: the heading `` #### `.claude/settings.json` ``, a line that says that `implement` applies the change and the implementer does not, and one `diff` block. Skip this section when the Changes of phase N have no such heading (oneshot has no plan: skip it).

1. Read `.claude/settings.json` if it exists. Take the `diff` block under the heading `` #### `.claude/settings.json` ``.
2. Find what the `diff` adds and the file lacks: missing keys, and missing rules in `permissions.allow` and `permissions.ask`. The change only adds; never remove or replace a key or a rule. If nothing is missing, skip the rest of this section.
3. Show the `diff` (only the missing part, when the file has some of it). Ask for confirmation once.
4. After "yes", change the file with the Edit tool (the Write tool for a new file). Never write it with a shell command. Keep the file valid JSON.
5. If the user does not say "yes", or the permission system denies the edit, stop. Start nothing of phase N: no `in-progress` entry, no implementer. The final message of `implement`:
   ```text
   Result: implementation phase <N> not started: .claude/settings.json is unchanged
   <the diff block>
   Next: apply the change to .claude/settings.json yourself, then /clear, then /loom:implement. To change the plan instead, run /loom:iterate <feedback>.
   ```
   - When earlier implementation phases of the same run are done, the `Result:` line names them first, for example `implementation phase 1 of 3 done (<hash>); implementation phase 2 not started: .claude/settings.json is unchanged`. Keep their `Manual verification:` steps in the message, also in run mode `all`. When there are manual steps, the `Next:` line starts with `run the manual steps, `: `Next: run the manual steps, apply the change to .claude/settings.json yourself, then /clear, then /loom:implement`.
   - From `iterate`, the phase stays blocked. The `Result:` line is `Result: implementation phase <N> stays blocked: .claude/settings.json is unchanged`. The `Next:` line names `/loom:iterate` in place of `/loom:implement`: `implement` refuses a blocked phase.

The change goes into the commit of phase N. When the plan has a settings change for phase N and `.claude/settings.json` is changed in the working tree, stage the file with the files of the phase. Do this also when an earlier run or the user applied the change. A re-run finds the change in the file and skips this section.

The implementer skips the settings change of the plan and does not report it as a deviation. The reviewer counts it as done when `.claude/settings.json` holds it, in the working tree or in a commit.

## A fix of a settings file

No loom agent can change a settings file. So a fix of `.claude/settings.json` or `.claude/settings.local.json` never goes to the implementer. A *settings item* is an item that needs such a change:

- a `blocking` item of the reviewer (step 6);
- a fix item of the user's feedback (`iterate` checks them before step 1);
- the ticket of a oneshot task (the implementer reports it under Open problems, step 2).

Never send a settings item to the implementer. What you do depends on the phase:

- **A phase without a commit** (a phase that `implement` builds, or a blocked phase that `iterate` fixes): stop the loop. The result is **blocked**, with the reason `settings: <the item>`. A settings item that comes with other `blocking` items stops the loop too: the reviewer finds the other items again on the next run. The final message ends with:

  ```text
  Next: change .claude/settings.json yourself, then /clear, then /loom:iterate
  ```

  On the next `/loom:iterate` of the blocked phase, `iterate` checks each settings item against the file itself.
- **Feedback on a committed phase** (`iterate`, before or after the PR): no blocked phase carries the item. `iterate` leaves a settings item of the feedback out, with a `Warning:` line, and fixes the other items (its own sections say how). A settings item that the reviewer raises during that fix still blocks the fix, as above.

The implementer is the second guard: a settings item that reaches it comes back under Open problems, in the form Expected / Found / Why it matters. Step 2 then stops the loop with the reason `settings: <the item>`.

## Steps

1. **Implementer.** Launch `loom:implementer` with a short prompt and the configuration lines above. The agent reads the plan or ticket itself; do not copy their content into the prompt.
   - phase mode: `Implement implementation phase N of the plan at <task dir>/04-plan.md.` (oneshot: `Implement the change in the ticket at <task dir>/00-ticket.md.`)
   - Fix mode: the same reference, the word `Fix`, and the fix items. A settings item is never a fix item here ([A fix of a settings file](#a-fix-of-a-settings-file)).
   - If the working tree already holds part of the work (a resumed run), add: `The working tree already contains part of this work; continue from it.`
   - If an earlier run was blocked, add the reason as context: `An earlier run was blocked by: <reason>.`
2. **Open problems.** Read the implementer's report. If `Open problems` lists a problem that needs a design decision or a plan change (the form Expected / Found / Why it matters), stop the loop. The result is **blocked**, with that problem as the reason. Do not ask the implementer to guess. A problem that needs a change of `.claude/settings.json` or `.claude/settings.local.json` is a settings item: the reason is `settings: <the item>`.
3. **Configuration change.** Run `git status --porcelain -- .claude/loom.json`. If it shows the file changed, or the implementer's `Files changed` lists `.claude/loom.json`, the configuration you hold came from the state before the change. The report is a claim, so check both. Run `loom-state --json` again. Take the configuration from its output (`checks`, `docs`, `design`, `mainBranch`, `implement`, `hooks`), and use it from now on:
   - for your own `checks.check` run in step 4;
   - for the reviewer prompt in step 5;
   - for the fix attempts in step 6 (the `Checks:` line of their prompt, and `implement.maxFixAttempts`);
   - for the later implementation phases (`implement` only).
   The implementer already ran `loom-state --json` after it changed the file. Implementation phase 1 of the onboarding task is such a run, but the rule holds for every task.
4. **Checks.** Run `checks.check` yourself, once, as the shared `git-flow.md` describes.
   - The `SubagentStop` hook already ran it when the implementer finished. The hook blocks the implementer while the checks fail, but lets it stop after `hooks.maxCheckAttempts` failed attempts.
   - So failing checks here mean the hook gave up. Stop the loop. The result is **blocked**, with the reason `checks.check fails: <the key failure lines>`.
   - Never commit while the checks fail.
5. **Reviewer.** Launch `loom:implementation-reviewer` with the same reference, the `Conventions:` and `Main branch:` lines, the implementer's report, and the fix items (if any). Use fix mode when the run had fix items: write `fix mode` and the items in the prompt.
6. **Verdict.**
   - `pass` (no `blocking` items): the result is **done**.
   - `changes-needed` with a settings item among the `blocking` items: the result is **blocked**, with the reason `settings: <the item>`. Send no item to the implementer ([A fix of a settings file](#a-fix-of-a-settings-file)).
   - `changes-needed`: if fewer than `implement.maxFixAttempts` fix attempts ran, launch `loom:implementer` in Fix mode with **only** the `blocking` items, copied word for word. Then continue with step 2.
   - `changes-needed` after `implement.maxFixAttempts` fix attempts: the result is **blocked**, with the remaining `blocking` items as the reason.
7. **Record.** Keep for the `log.md` entry, also when the result is done:
   - the checks result (the implementer's one-line summary, e.g. `lint ✓ typecheck ✓ test ✓ (42 passed)`)
   - the verdict and the number of fix attempts
   - every `nit` item
   - every deviation and addition from the reviewer, and every deviation the implementer reported, with its reason
   - the implementer's `Manual verification needed` items
   - the `Files changed` of every implementer run (you stage these), and `.claude/settings.json` when the plan has a settings change for phase N and the file is changed in the working tree ([Settings change](#settings-change))

Send only `blocking` items back to the implementer. Never send `nit` items, deviations that are not blocking, settings items, or your own ideas.

## Results

| Result | What you do |
|---|---|
| **done** | Commit as the shared `git-flow.md` describes. Then write the `done` entry in `log.md`. |
| **blocked** | Do not commit. Leave the change in the working tree. Append `## Phase N — blocked` and a `Reason:` line to `log.md`. Stop. `/loom:iterate` fixes a blocked phase. For a `settings:` reason, the final message ends with the `Next:` line of [A fix of a settings file](#a-fix-of-a-settings-file). |

The exact `log.md` entries are in the plugin file `skills/implement/references/log-format.md`.

## Rules

- One implementer run per launch. Launch a fresh agent for every implementation phase and every fix attempt.
- Do not edit code yourself. The implementer owns the code change; you own git, `04-plan.md` checkboxes, `log.md`, and the [settings change](#settings-change) of the plan.
- Treat the agents' reports as claims. Verify file lists with `git status --porcelain` and checks by running them.

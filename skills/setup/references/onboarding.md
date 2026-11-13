# Onboarding Path of `setup`

`/loom:setup` reads this file when `loom-state --setup-path <main>` names the path `onboarding` or `onboarding-rerun`. The Values and the rules of the setup skill apply here too: `<main>`, `<current>`, `<workDir>`, `<n>`, `<branch>`, `<task dir>`, `<drafts>`, `<path>`, `<reason>`, `<found>`, the Bash call rules, and "Read it first, then Write it" for existing files.

An *onboarding task* is a setup task in `full` mode: the setup of a repository with code. On this path, setup does only the kickoff. loom's own phases (research, design, plan, implement) do the rest; then `/loom:describe-pr` and `/loom:finish-task` open and merge the setup PR. Setup never writes the files of the implementation phases: the full `.claude/loom.json`, the checks entry point, CI, the docs, and `CLAUDE.md`. It also never writes the two settings that the design decides: the rules for the check commands and the `statusLine`.

Files you read with this one:

- `onboarding-questions.md`: the template of `01-research-questions.md` with the fixed list of 7 questions.
- `templates/setup-issue-onboarding.md`: the issue body.
- `templates/loom.json` and `templates/settings.json` (read at the start of the skill).
- `ticket-template.md` of start-task, `git-flow.md`, `frontmatter.md`, and `final-answer.md` (read at the start of the skill).

---

## Kickoff

The kickoff steps run in this order. Kickoff step 1 is step 1 of the skill: the path selection and the preconditions chose the path `onboarding` on an up-to-date `<main>` (or on a setup branch whose run stopped after `git switch -c`).

### Plan and confirm

Collect these facts first. They are read-only:

- **Issue and labels**: as "Setup issue and labels" in step 2 of the skill describes. On a setup branch, the issue is `#<n>` of the branch.
- **`.gitignore`**: the line `.loom/` (or `<workDir>/` when `workDir` is not below `.loom/`) is missing when `git check-ignore -q <workDir>` fails.
- **`.claude/settings.json`**: Read it if it exists. Compute the result of [Kickoff settings](#kickoff-settings).
- **Ignored kickoff files**: run `git check-ignore -v -- <path>` for `.claude/loom.json` and `.claude/settings.json`. A global ignore rule for `.claude/` is common.

Show one plan. Then ask for confirmation once. The plan names every command that changes something outside the working tree, exactly as you will run it:

1. **Path**: `onboarding` and `<reason>`. Say: the user can answer `fast` to take the fast path instead (`/loom:setup --oneshot` does the same).
2. **Research questions**: the 7 fixed questions of `onboarding-questions.md`, as they will appear in `01-research-questions.md`. Say: the user can add project-specific questions in the answer. Research reads only this list, never the ticket.
3. **Labels**: the missing loom labels, each as its `gh label create` command (the table in step 2 of the skill). Optional: the user may skip them. Existing labels and label schemes stay. Issues are not migrated.
4. **Issue**: `gh issue create` for "Set up loom" (kickoff step 4), or the open issue you reuse. A reused issue with the size or mode label of the fast path (`size:S`, `mode:oneshot`) gets the labels of this path: show its `gh issue edit` command ("Labels of a reused issue" in step 2 of the skill). Its body stays.
5. **Branch**: `git switch -c <branch>` (not on a setup branch).
6. **Files**: one line per file: `new`, `changed`, or `unchanged`.
   - `.gitignore`: the missing line, as a `diff` block.
   - `.claude/loom.json`: the minimal file of kickoff step 7, in full.
   - `.claude/settings.json`: a `diff` block of kickoff step 8 (a new file: its full content).
   - In the ignored task directory: `00-ticket.md` (mode `full`, size `M`) and `01-research-questions.md` (`approved` with this confirmation).
7. **Ignored files**: each kickoff file that git ignores, with the rule from `git check-ignore -v`. Ask: commit it anyway (`git add -f -- <path>` in kickoff step 9), or stop. loom needs `.claude/loom.json` committed.
8. **Kickoff commit**: `chore(loom): start loom setup (#<n>)`, with `.claude/loom.json`, `.claude/settings.json`, and the changed `.gitignore`.

Apply the answer:

- **Added questions**: rewrite each one in descriptive form, as the research-questions skill requires. Ask what exists, where, and how it works. A question never reveals what will be built: no "should", no "how do we add". Show the rewritten questions, and ask for confirmation again.
- **`fast`**: the fast path. Continue with step 2 of the skill. Nothing of this plan runs. A switch keeps the place: on a setup branch, keep the branch and reuse the open issue #<n>, so the fast path skips its branch step (step 6) and in its issue step (step 5) runs only the `gh issue edit` of the reused issue.
- **Stop on an ignored file**: stop with `Result: setup not applied; <path> is ignored by <rule>`, `Next: remove the ignore rule or answer "commit it anyway", then /loom:setup`.
- **Other changes**: apply them, and show the changed items again.
- Without "yes": stop with `Result: setup not applied; nothing changed`.

### Kickoff steps

Run these in order, without a question in between:

2. **`.gitignore`**: add the `.loom/` line (or `<workDir>/`) if it is missing. It comes first: the issue draft goes below `<workDir>`. The uncommitted change goes with you to the branch.
3. **Labels**: run the confirmed `gh label create` commands, one per label. A label that already exists is not an error; continue.
4. **Issue**: when you reuse an open issue, run only its confirmed `gh issue edit` command, if any, and skip the rest of this step.
   1. Copy `templates/setup-issue-onboarding.md` to `<drafts>/setup-issue-onboarding.md`. If the user gave notes with `/loom:setup <notes>`, append a `## Notes` section with the notes verbatim.
   2. Run `gh issue create --title 'Set up loom' --body-file <drafts>/setup-issue-onboarding.md` with `--label 'type:chore' --label 'size:M' --label 'mode:full'`. Add only labels that exist now.
   3. `<n>` is the number at the end of the URL that `gh issue create` prints.
5. **Branch**: run `git switch -c <branch>` from the up-to-date `<main>`. Skip this step on a setup branch.
6. **Ticket**: run `gh issue view <n> --json title,body,labels,url` after kickoff step 4, so the labels line of the ticket shows the labels after a `gh issue edit`. Write `<task dir>/00-ticket.md` from `ticket-template.md`: `task: <n>-loom-setup`, `phase: ticket`, `mode: full`, `size: M`, `issue: <n>`, `url: <url>`. The body is the issue title as the `# ` heading, the labels, the URL, and the issue body verbatim. The ticket comes right after the branch, so a re-run finds the onboarding path.
7. **`.claude/loom.json`, minimal**: only `version` and `mainBranch`, plus `workDir` when `<workDir>` is not the `workDir` of `templates/loom.json`:

   ```json
   {
     "version": 1,
     "mainBranch": "<main>"
   }
   ```

   Every other key takes its default until implementation phase 1 writes the full file. If the file exists, keep it as it is. Then run `loom-state --json`: `task.setup` is `true` and `task.mode` is `full`. After the plan confirmation this call may ask for permission: the allow rules come only with kickoff step 8. That prompt is expected and harmless. The spec fixes this order of steps 7 and 8.
8. **`.claude/settings.json`, the kickoff settings**: write the result of [Kickoff settings](#kickoff-settings).
9. **Kickoff commit**: see [Kickoff commit](#kickoff-commit).
10. **Research questions**: see [Research questions file](#research-questions-file).
11. **Final message**: see [Final message](#final-message).

Size `M` caps the design rounds at 3. Most questions of the onboarding design are independent, so round 1 carries most of them.

### Kickoff settings

The kickoff writes every setting of `templates/settings.json` that does not depend on the design. The kickoff runs in the main context, after the user confirmed the plan with the `diff` of this file. A subagent cannot write a settings file later: in auto permission mode Claude Code denies it.

- The phases of the onboarding task run `loom-state`, `git`, and read-only `gh` commands many times. Without the allow rules, each call asks the user.
- The `ask` rules (`git push`, `gh pr create`, …) hold from the first phase, also when a loaded project rule says "push without confirmation".

What to write:

- **The kickoff settings**: `extraKnownMarketplaces`, `enabledPlugins`, and the `permissions.allow` and `permissions.ask` rules of `templates/settings.json`, in template order.
- **Left out**: the two things that the design decides later.
  - The rules for the check commands: leave out `Bash(make *)`, and every other rule that runs a check command (for Node, one rule per check command).
  - The `statusLine`.
  - Before implementation phase 1, `/loom:implement` adds them, after one confirmation. The implementer never edits a settings file.
- Replace the template's default work directory in the `mkdir` and `mv` rules with `<workDir>` when `workDir` differs.
- **No file yet**: write a new file with the `$schema` line of the template first, then `extraKnownMarketplaces`, `enabledPlugins`, and the `permissions` key: `allow` and `ask` with the kickoff rules.
- **The file exists**: merge the kickoff settings by the rules of "Merge settings.json" in step 7 of the skill, for `extraKnownMarketplaces`, `enabledPlugins`, `permissions.allow`, and `permissions.ask` only. Never replace the file, and never remove a key.
  - `extraKnownMarketplaces.loom`: add it if missing. If it exists with another source, keep it and ask the user in the plan.
  - `enabledPlugins["loom@loom"]`: set it to `true`. If it is `false`, ask the user in the plan first.
  - Append the missing rules. Keep the existing rules and their order. If a kickoff `allow` rule is also in the file's `deny` or `ask`, keep the stricter rule and say so in a `Warning:` line.
  - Keep every other key as it is.

### Kickoff commit

The kickoff commit holds only `.claude/loom.json`, `.claude/settings.json`, and `.gitignore` when it has uncommitted changes (kickoff step 2, or the same line from a run that stopped before the branch). It keeps the working tree clean: a dirty tree adds a warning to every later phase.

1. Write the message to `<task dir>/commit-msg.txt`: only the subject `chore(loom): start loom setup (#<n>)`. It has no body: the kickoff commit has no `Phase` line.
2. Run `git add -- <paths>` with the paths of this commit that git does not ignore: `.claude/loom.json`, `.claude/settings.json`, and the changed `.gitignore`. Leave every ignored path out of it: `git add` with one ignored path exits 1. Then add each ignored path, only after the user chose "commit it anyway" in the plan, with its own `git add -f -- <path>`. Never use `git add -A` or `git add .`.
3. Run `git status --porcelain --untracked-files=all`. Another staged path does not belong to the kickoff commit: run `git restore --staged -- <path>` for it, and name it in a `Warning:` line.
4. Run `git commit -F <task dir>/commit-msg.txt`. Never pass `--no-verify`.
5. If the commit fails, stop with the error output: `Result: kickoff commit failed: <the error>`, `Next: fix it, then /loom:setup`. A git hook of the project can reject the commit: a `pre-commit` hook, or a `commit-msg` hook that checks the subject. If the hook rejects the subject format, add `Warning: the hook rejects the commit subject format; change the hook's rule first: loom has no setting for another format`. The re-run makes the kickoff commit again.

### Research questions file

Write `<task dir>/01-research-questions.md` from `onboarding-questions.md`:

- Frontmatter: `task: <n>-loom-setup`, `updated: <today>`. Keep `phase: research-questions`, `status: approved`, and `based_on: []`. The user approved the list with the plan confirmation, so setup writes the file as `approved`. It is the one artifact that loom writes as `approved` without `/loom:iterate approve`.
- **Key Context Pointers**: the paths of `<found>`, verbatim. Replace each placeholder with the paths of its list (`instructionFiles`, `workflows`, `prTemplates`, `docsDirs`), each path in backticks, separated by `, `. Write `None.` for an empty list.
- **Questions**: the 7 fixed questions, unchanged. Append each question the user added as item 8, 9, and so on, in the rewritten form the user confirmed. The limit of 2-8 questions of research-questions does not apply to this list.

Write the file once, with the Write tool.

### Final message

Run `loom-state --json`. `next.command` must be `/loom:research`. If it is not, add `Warning: loom-state routes to <next.command>: <next.reason>`.

Use the `final-answer.md` format:

```text
Result: onboarding kickoff on <branch> (<kickoff commit short hash>) for issue #<n>; 01-research-questions.md approved
Warning: <one line per warning, if any>
Next: /clear, then <next.command>
```

- Add `Labels: <created labels, or skipped>` after `Result:` when this run created labels.
- `<kickoff commit short hash>` is `git rev-parse --short HEAD` right after the commit.
- A private repository: add the `Warning:` line of the skill about the ruleset.
- `Next:` comes from `next.command`, mapped as `final-answer.md` describes: normally `/clear, then /loom:research`.

---

## Onboarding re-run

The path `onboarding-rerun`: you are on `<branch>`, and the ticket has mode `full` or the branch has the kickoff commit `chore(loom): start loom setup (#<n>)`. The setup task is an onboarding task. On a setup branch, setup never stops on an active task and never offers a stash: the uncommitted files are the stopped run. Run these steps in this order:

1. **Merged PR first.** Run `git fetch origin <main>`. If `gh pr list --head <branch> --state merged --json number` lists a PR, stop: `Result: the setup PR of #<n> is merged; the cleanup is left`, `Next: git switch <main>, then git pull --ff-only, then /loom:finish-task #<n>`.
2. **Ticket.** These changes touch only the ignored task directory, so they need no question:
   - `<task dir>/00-ticket.md` is missing (a fresh clone): write it as kickoff step 6 describes.
   - Its `mode` is not `full` (another mode, or none): change only the `mode:` line of its frontmatter to `mode: full`. Setup owns the mode of the setup task.
3. **Missing kickoff items.** If `git log --format=%s origin/<main>..HEAD` lists `chore(loom): start loom setup (#<n>)`, the kickoff files and the kickoff commit are done. Otherwise complete only what is missing, in kickoff order:
   - `.claude/loom.json` is missing: kickoff step 7.
   - `.claude/settings.json` lacks a kickoff setting (`extraKnownMarketplaces.loom`, `enabledPlugins["loom@loom"]`, or a kickoff rule): kickoff step 8.
   - The kickoff commit: kickoff step 9, with the files of kickoff steps 2, 7, and 8 that differ from `origin/<main>`.
4. **Research questions file.** `<task dir>/01-research-questions.md` is missing or its `status` is not `approved`: show the question list again, and write the file after the confirmation, as `approved` (kickoff step 10).
   - The file is missing: the list is the 7 fixed questions of `onboarding-questions.md`.
   - The file exists and is not `approved`: it keeps its own questions. Read it, and show the list of that file, not the template, so no question the user added is lost. Write it back with `status: approved` and `updated: <today>`. Keep its Key Context Pointers and its questions, and append the questions the user adds in the answer, as in kickoff step 10.

   On a fresh clone the ignored task directory is missing: setup writes the ticket and the research questions again. Research, design, and plan are lost, as for every task.
5. **Open PR last.** If `gh pr list --head <branch> --state open --json number` lists a PR, stop: `Result: the setup PR is open`, plus the restored items, if any. `Next: /loom:next` (it reads the PR state).
6. Otherwise run `loom-state --json` and stop: `Result: onboarding task #<n> continues on <branch>`, plus the restored items, or `nothing to restore`. `Next:` from `next.command`, mapped as `final-answer.md` describes. If `next.command` is still `/loom:setup`, add `Warning: loom-state routes to /loom:setup: <next.reason>`.

**Confirmation.** Step 2 needs none. Before step 3 runs, check what steps 3 and 4 must do:

- Step 3 writes `.claude/loom.json` or `.claude/settings.json`, or step 4 writes the questions file: show one plan of everything steps 3 and 4 do, the kickoff commit included. It names the path `onboarding-rerun` and `<reason>`, shows files as in the kickoff plan, runs the ignored-file check, and lists the questions. Ask for confirmation once, before step 3 writes or commits anything. Without "yes", nothing of steps 3 and 4 runs: stop with `Result: setup not applied`, plus what step 2 wrote (the restored ticket, or the repaired mode), or `nothing changed`.
- Step 3 only commits the files of the earlier run, and the questions file is `approved`: no plan. Make the kickoff commit.

The re-run never writes the files of the implementation phases. An onboarding task never goes back to the fast path: to start over, the user deletes the branch `<branch>` (local and on `origin`) and `<task dir>`, then runs `/loom:setup --oneshot`.

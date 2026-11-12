# Onboarding Plan

`/loom:plan` reads this file only on the onboarding task: `task.setup` is `true` and `task.mode` is `full`. `/loom:iterate` reads it too on the onboarding task, when it writes a round of `04-plan.md` or changes the plan, so these rules hold after every change of the plan. The onboarding task is the setup of a repository with code. The approved `03-design.md` holds the onboarding decisions: the checks, the required CI check, the docs map, the PR sections, the instruction files, the status line, and the gaps deferred as `Follow-up:` lines.

The rules of the plan skill apply unchanged: the inputs, the layout of `04-plan.md`, vertical implementation phases, and the question rounds. This file adds the rules of the onboarding task. Below, "the plan" is `04-plan.md`, whichever skill writes it, and "you" is that skill.

## Check commands come from the design

Take the check commands from the design, not from `checks` in the state. Until implementation phase 1 the state has the defaults (for example `make check`), which the project may not have.

- Every `Automated:` line of a Verification section uses the commands that the design chose.
- A check that the design set to `null` does not exist: never plan it.

## Implementation phase 1 writes the full `.claude/loom.json`

Implementation phase 1 always writes the full `.claude/loom.json`, so the `SubagentStop` hook and the later implementation phases run the chosen checks.

- `.claude/loom.json` is the first file in the Changes of implementation phase 1: the first line of its file tree, and the first block after the tree.
- Say in the Changes of implementation phase 1: the implementer writes `.claude/loom.json` before every other file. If the implementer stops early, the `SubagentStop` hook already runs the chosen `checks.check`, not the default `make check`.
- The file is the full file of the design: every key of `templates/loom.json`, plus `docs` (the docs map), `ci` with `requiredCheck`, and `pullRequest` with `requiredSections`. The design sets `checks`, `docs`, `ci`, and `pullRequest`. `mainBranch` and `workDir` come from the state: the kickoff file set them. Every other key keeps the value of `templates/loom.json`.

## Templates

The implementer reads only the plan and the project, never plugin files. So the plan carries every loom template that a Changes section uses. You read the templates at the start, before you ask anything: `plan` and `iterate` list them in their shared rules. Copy a template from that Read, never from memory. A change of the plan keeps the template content that the plan already carries, unless the change is about it.

- **Small templates**: copy their content into the Changes, with the placeholders filled:
  - `templates/loom.json`: the full `.claude/loom.json` (above);
  - `templates/settings.json`: the settings that implementation phase 1 adds to `.claude/settings.json` (below);
  - the CI job: the job of `templates/ci.python-uv.yml` or `templates/ci.node.yml` for the stack, when the design adds a job named `check`;
  - `templates/CLAUDE.md`: the `CLAUDE.md` loom section, or the new `CLAUDE.md` with its import line;
  - the docs skeleton of each docs role that the design creates without a draft: `templates/docs/product/vision.md`, `templates/docs/architecture/overview.md`, `templates/docs/conventions.md`;
  - `templates/Makefile`: the targets of a new check entry point, when the design adds one for python-uv.
- **Empty directories of the docs map**: git tracks no empty directory. For a `decisions` or `tasks` directory that the design creates, and that is missing or empty, the Changes add an empty `.gitkeep` file in it (`<docs.decisions.dir>/.gitkeep`, `<docs.tasks>/.gitkeep`), as the fast setup does with `templates/docs/architecture/decisions/.gitkeep` and `templates/docs/tasks/.gitkeep`. Take the directories from the docs map of the design. A mapped directory that already holds files gets no `.gitkeep`.
- **The larger template `templates/loom-statusline.py`**: it does not go into the plan text. Only when the design chose the status line:
  1. Write the content that you read at the start, unchanged, to `<task dir>/templates/loom-statusline.py` with the Write tool. Never write it from memory. If the file exists, Read it before you Write it. A change of the plan that keeps the status line keeps the existing copy.
  2. The Changes name that copy: the implementer copies `<task dir>/templates/loom-statusline.py` unchanged to `.claude/loom-statusline.py`. The task directory is inside the project, so the implementer can read it.

## Settings of implementation phase 1

The kickoff wrote the `permissions.allow` and `permissions.ask` rules of `templates/settings.json`, without the rules for the check commands. Implementation phase 1 merges the other settings into `.claude/settings.json`, by the merge rules of setup: add missing keys and rules; never remove or replace one.

- `extraKnownMarketplaces` and `enabledPlugins` of the template;
- the allow rules for the check commands: `Bash(make *)` for a `Makefile` entry point, else one rule per check command (for example `Bash(npm run check)`);
- the `statusLine` of the template, when the design chose the status line.

Show the change as a `diff` block of `.claude/settings.json`.

## Typical implementation phases

1. **Config and checks**: the full `.claude/loom.json` (first), the missing parts of the check entry point, the settings of implementation phase 1, and the optional status line.
2. **CI**: the required check runs `checks.check`, as topic 6 of the design decided. Never rename an existing job.
3. **Docs**: map, migrate, or create each docs role; the vision and the overview from the approved drafts; the `conventions` document with the CI-only checks and the table of project rules.
4. **Agent instructions**: `CLAUDE.md` and the agreed changes to other instruction files, each as a `diff` (a new file in full).

**A hook change.** When the design changes a git hook of the project that rejects a loom format (topic 2), put that change into implementation phase 1. The commit of implementation phase 1 is the first commit with a `Phase` line, so it must pass the changed hook. A hook that lives outside the repository (`.git/hooks/`, or a hook manager that needs a reinstall) is not a plan change: the plan names it as a step that the user does before `/loom:implement`, in the Goal of implementation phase 1.

Merge or split them where the design needs it. Each implementation phase still passes the checks of the design on its own. The gaps that the design deferred (`Follow-up:` lines) get no implementation phase.

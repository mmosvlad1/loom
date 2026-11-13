# <project name>

<One or two sentences: what the project is and who it is for.>

## Commands

- `<checks.check>`: all checks (lint, typecheck, test). CI runs the same command.
- `<checks.lint>`: lint
- `<checks.typecheck>`: typecheck
- `<checks.test>`: tests

## Docs

- Product vision: `<docs.vision>`
- Architecture: `<docs.overview>`; decisions: `<docs.decisions.dir>/`
- Conventions (code style, testing rules, module layout): `<docs.conventions>`
- Task summaries: `<docs.tasks>/`

## Workflow

This project uses the loom plugin. Work starts from a GitHub issue: `/loom:start-task #<n>`, then `/clear` and the command of the last `Next:` line between phases (`/loom:next` when you do not have that line). Never commit on `<main>`.

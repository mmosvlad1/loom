# <project name>

<One or two sentences: what the project is and who it is for.>

## Commands

- `<checks.check>`: all checks (lint, typecheck, test). CI runs the same command.
- `<checks.lint>`: lint
- `<checks.typecheck>`: typecheck
- `<checks.test>`: tests

## Docs

- Product vision: `docs/product/vision.md`
- Architecture: `docs/architecture/overview.md`; decisions: `docs/architecture/decisions/`
- Conventions (code style, testing rules, module layout): `docs/conventions.md`
- Task summaries: `docs/tasks/`

## Workflow

This project uses the loom plugin. Work starts from a GitHub issue: `/loom:start-task #<n>`, then `/clear` and `/loom:next` between phases. Never commit on `<main>`.

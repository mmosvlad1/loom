## Context

The project starts to use the loom plugin for issue-to-PR work. loom needs its configuration, one checks entry point, CI with a `check` job, Claude Code project settings, and the docs skeleton. `/loom:setup` writes them on this branch.

## Acceptance Criteria

- [ ] `.claude/loom.json` exists and its `checks` commands pass locally
- [ ] `.github/workflows/ci.yml` runs one job named `check` on pull requests and on pushes to the main branch
- [ ] `.claude/settings.json` registers the loom marketplace, enables `loom@loom`, and allowlists the routine commands
- [ ] `docs/` has the skeleton: `product/vision.md`, `architecture/overview.md`, `architecture/decisions/`, `conventions.md`, `tasks/`
- [ ] `CLAUDE.md` is short and points to `docs/`
- [ ] `.gitignore` ignores the loom work directory

## Out of Scope

- The main branch ruleset: `/loom:finish-task` offers it after this PR is merged, when the `check` job exists on the main branch.

## Context

The project starts to use the loom plugin for issue-to-PR work. loom needs its configuration, one checks entry point, a CI job that runs the checks, Claude Code project settings, and the docs skeleton. `/loom:setup` writes them on this branch.

## Acceptance Criteria

- [ ] `.claude/loom.json` exists and its `checks` commands pass locally
- [ ] A CI job runs the checks on pull requests and on pushes to the main branch, and `ci.requiredCheck` in `.claude/loom.json` names its check (default `check`)
- [ ] `.claude/settings.json` registers the loom marketplace, enables `loom@loom`, and allowlists the routine commands
- [ ] The docs skeleton exists: one document or directory per docs role (vision, overview, decisions, conventions, tasks)
- [ ] `CLAUDE.md` is short and points to the docs
- [ ] `.gitignore` ignores the loom work directory

## Out of Scope

- The main branch ruleset: `/loom:finish-task` offers it after this PR is merged, when the required CI check exists on the main branch.

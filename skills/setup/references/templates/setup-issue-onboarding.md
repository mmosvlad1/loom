## Context

The project starts to use the loom plugin for issue-to-PR work. The repository already has code, so this setup runs as a loom task in full mode: research describes the repository, design discusses how loom fits the project, and the plan and its implementation phases write the configuration. `/loom:setup` does only the kickoff: the minimal `.claude/loom.json`, the kickoff settings of `.claude/settings.json`, and the fixed research questions.

## Acceptance Criteria

- [ ] `.claude/loom.json` is complete: the check commands, the docs map, and `ci.requiredCheck`
- [ ] `checks.check` passes on the main branch and finishes within 540 seconds
- [ ] The required CI check runs `checks.check` on pull requests and on pushes to the main branch, and `ci.requiredCheck` names it
- [ ] `.claude/settings.json` registers the loom marketplace, enables `loom@loom`, and allowlists the routine commands and the check commands
- [ ] Each docs role (vision, overview, decisions, conventions, tasks) has a document: mapped, migrated, or created
- [ ] `CLAUDE.md` has the loom section; a new `CLAUDE.md` imports `@AGENTS.md` when the repository has an `AGENTS.md`
- [ ] `.gitignore` ignores the loom work directory

## Out of Scope

- Every other gap of the repository: each one becomes a follow-up issue after this PR.
- No migration of issues, labels, or branches.
- The main branch ruleset: `/loom:finish-task` offers it after this PR is merged, when the required CI check exists on the main branch.

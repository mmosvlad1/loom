---
task: <n>-loom-setup
phase: research-questions
status: approved
based_on: []
updated: YYYY-MM-DD
---

# Research Questions

## Key Context Pointers

- Instruction files: <found.instructionFiles>
- Workflows: <found.workflows>
- PR templates: <found.prTemplates>
- Docs directories: <found.docsDirs>

## Questions

1. **Stacks and check commands.** Which languages, package managers, and lock files does the repository use, and where? Which commands run lint, format check, typecheck, unit tests, build, and e2e tests today (`Makefile`, `justfile`, `Taskfile.yml`, `package.json` scripts, `tox.ini`, `noxfile.py`, `scripts/`)? Is there one root command that runs several of them? Which services, secrets, or network access does each command need? What are the exit status and the run time of each command that research runs (the check runs rule of research)?
2. **CI.** Which workflows exist in `.github/workflows/` (and other CI configuration)? For each: the triggers, the check names as GitHub reports them (job `name`, with matrix suffixes), the commands each job runs, how actions and tools are pinned, and how long the jobs ran in the latest run on the main branch (`gh run list`, `gh run view`).
3. **Documentation.** Where do the docs live (README, `docs/`, `doc/`, ADR directories, wiki links)? What are the structure, the file formats, and the file naming? Which documents describe the product and its users, the architecture and its components, past decisions (with their file name pattern and layout), code conventions, and past work (changelogs, task notes)?
4. **Agent instruction files and Claude Code configuration.**
   - Which of `AGENTS.md`, `.claude/AGENTS.md`, `CLAUDE.md`, `.claude/CLAUDE.md`, `CLAUDE.local.md`, `.claude/rules/`, `.cursorrules`, `.cursor/rules/`, `.github/copilot-instructions.md`, `.github/instructions/`, `GEMINI.md`, and similar files exist, at the git top level and in subdirectories?
   - Which of them does Claude Code load (the instruction files rule of research), and which does `CLAUDE.md` import with `@`?
   - What do they state about branches, commits, push, pull requests, confirmations, the planning workflow, checks, and code? Quote each rule with `file:line`.
   - What else does `.claude/` hold: `commands/`, `skills/`, `agents/`, the hooks and the enabled plugins of `.claude/settings.json`?
5. **Conventions.** Which linter, formatter, and type checker configurations exist, with their main settings? How are tests laid out (directories, naming, fixtures)? How are modules and packages laid out?
6. **Git process.**
   - What are the default branch, the branch name patterns in use, and the commit message format on the main branch?
   - Which merge method does the history show, and which merge methods does the repository allow (`gh repo view --json squashMergeAllowed,mergeCommitAllowed,rebaseMergeAllowed,deleteBranchOnMerge`)?
   - Which local git hooks exist (`.pre-commit-config.yaml`, `.husky/`, `lefthook.yml`, `core.hooksPath`), and what does each run on commit and on push?
   - Which PR templates exist, with which sections? Which CI steps or actions read the PR title, the PR body, or the commit subjects?
   - Which labels, open issues, and milestones exist?
   - Which rulesets or branch protection rules apply to the main branch (required checks, required approvals, signed commits)?
7. **loom requirements.** For each item, does it exist today, and where:
   - one root command that runs lint, typecheck, and unit tests; separate commands for each;
   - a CI job that runs that command on pull requests and on pushes to the main branch;
   - a document in each docs role: `vision` (what the product is, for whom, non-goals), `overview` (components and data flow), `decisions` (decision records), `conventions` (code style, testing rules, module layout), `tasks` (notes on past work);
   - tests, and the result of the latest CI run on the main branch;
   - `.claude/settings.json`, and its keys;
   - a git ignore rule that covers `.claude/`, `CLAUDE.md`, or a document of a docs role (`git check-ignore -v`).

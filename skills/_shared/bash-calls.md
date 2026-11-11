# Bash Calls

Rules for every Bash call of a loom skill. A permission rule such as `Bash(git *)`, `Bash(make *)`, or `Bash(loom-state *)` matches one command. A chained or wrapped call matches no rule, so it needs a permission prompt, or it is denied where no prompt is possible.

## Rules

- Run one command per Bash call. A code block with several commands means several Bash calls.
- Do not run `cd`. Your working directory is already the git top level. Give paths as arguments instead.
- Do not chain commands with `&&`, `||`, `;`, or a newline.
- Add no pipe, redirection, subshell, or shell variable (such as `$TMPDIR`).
- Call a tool by the name the skill uses: `loom-state --json`, not `python3 bin/loom-state --json`. Do not wrap a command in `python3 -m`, `bash -c`, or `sh -c`.
- Read and find files with the Read, Grep, and Glob tools, not with `cat`, `head`, `ls`, `grep`, or `find` through Bash.
- Exception: run a command that a skill gives, and `checks.check` from `.claude/loom.json`, exactly as written, in one Bash call. This also applies when the command chains commands or has a pipe.

For `checks.check`, also follow "Checks" in the shared `git-flow.md`.

# Issue Format

The format of a GitHub issue that loom creates: from `backlog`, from free text in `start-task`, for follow-ups in `describe-pr`, and for a screens task in `screens`. `start-task` copies the issue into `00-ticket.md`, so a good issue is a good ticket.

## Title

- Imperative mood, at most 70 characters, no issue number, no type prefix: "Add token refresh to the auth client".
- `start-task` builds the branch slug from the title (at most 5 words), so put the key words first.

## Body

```markdown
## Context

<Why this work is needed: the problem, who has it, and what exists today. Two to five sentences.
Link the source: the task summary, PR, ADR, or file (`path:line`) that found it.>

## Acceptance Criteria

- [ ] <An observable result that a check or a person can verify>
- [ ] <One criterion per line; 1-6 criteria>

## Screens

- `<path of a screen from design.screens>`

## Out of Scope

- <What this issue does not change, if a reader could expect it. Omit the section otherwise.>
```

- Describe the problem and the expected result, not the implementation. The research and plan phases decide how.
- **Screens** (optional): one line per screen that the issue implements, as its path from `design.screens` in the `loom-state --json` output, in backticks. A screen is one mockup file of the screens directory. Omit the section when the issue implements no screen. An issue whose title starts with `Design screens:` has no `## Screens` section: it changes screens, it does not implement them.
- Dependencies: if the issue needs another open issue done first, end the Context with one line per dependency: `Depends on #<k>`. `backlog` reads these lines to prioritize.
- A follow-up from `describe-pr` starts its Context with `Follow-up from #<n>` (the task issue) and links the PR.
- Apply the shared `writing-style.md`.

## Labels

| Label | Values | Rule |
|---|---|---|
| `type:` | `feat`, `fix`, `chore`, `docs`, `refactor` | Always one. It becomes the branch type and the commit type. |
| `size:` | `S`, `M`, `L` | One, if you can estimate it: `S` is a trivial change, `M` a small or medium change with a clear design, `L` a larger feature or unclear behavior. |
| `mode:` | `oneshot`, `quick`, `full` | Only when the mode is clear and differs from the size default (`S` → oneshot, `M` → quick, `L` → full). |

- Add a label only if it exists in the repository. `gh issue create` fails on an unknown label; then create the issue without that label and add a `Warning:` line.
- `setup` can create the labels.

## Creating issues

1. Draft every issue first. Show the list: title, labels, and the body of each.
2. Wait for the user's confirmation. The user may drop or change issues.
3. Write each body to a file in `<workDir>/_drafts/` (`workDir` from the `loom-state --json` output; git ignores the work directory), also when a task is active. If the file already exists, Read it before you Write it. Then run:
   `gh issue create --title '<title>' --body-file <file> --label '<type label>' --label '<size label>'`
   Quote the title with single quotes and write every `'` in it as `'\''` (the shared `git-flow.md`). Double quotes would expand backticks and `$`.
4. Report the issue numbers and URLs that `gh issue create` prints.

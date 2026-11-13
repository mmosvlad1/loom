# Writing Style

loom uses an STE-lite style, inspired by ASD-STE100. Apply it to every artifact, `docs/` file, commit, PR, and final message you write.

## Rules

### 1. One term, one meaning

Use the glossary below. Do not rotate synonyms. If a word has a glossary meaning, do not use it for anything else.

- Bad: "The stage is done. Approve the step, then the next phase starts."
- Good: "The design phase is done. Approve `03-design.md`, then the plan phase starts."

### 2. Active voice

- Bad: "The checks are run by the hook."
- Good: "The hook runs the checks."

### 3. Short sentences

At most 20 words for an instruction and 25 for a description.

- Bad: "Before you open the pull request you should make sure that the branch has been rebased onto the main branch and that all checks still pass afterwards."
- Good: "Rebase the branch on `origin/main`. Then run `make check`."

### 4. One instruction per sentence

- Bad: "Read the plan and run the checks and update the log."
- Good: "Read the plan. Run the checks. Update `log.md`."

### 5. Lists for 3 or more steps or conditions

- Bad: "Stop if the tree is dirty, the plan is not approved, or a phase is blocked."
- Good:
  ```text
  Stop if:
  - the working tree is dirty
  - the plan is not approved
  - an implementation phase is blocked
  ```

### 6. No introductions, recaps, or filler

- Bad: "Great question! I have now carefully reviewed the research and written a comprehensive design document that covers everything."
- Good: "`03-design.md` is in review with 3 open questions."

### 7. Keep every condition, number, and scope qualifier

Shorter is better only if the meaning stays the same.

- Bad: "Retry failed requests."
- Good: "Retry failed GET requests at most 3 times, with a 1-second delay."

### 8. Define a project-specific term once

Define a term the first time you use it. Then use it with that meaning only.

- Good: "A *run* is one execution of an agent from prompt to final answer. Each run writes one log line."

## Where the rules apply

| Text | Applies |
|---|---|
| research, plan, log, PR, ADR, `docs/` | Yes |
| Final messages of skills | Yes, strictly |
| Skill and agent prompts | Rule 1 always; others where they do not remove nuance |
| Design rationale | Rules 1, 2, 6, 7 |
| The vision document, `backlog` discussion | No |

## Glossary

| Term | Meaning | Avoid for this meaning |
|---|---|---|
| **task** | One GitHub issue being worked on, with one branch and one task directory | "ticket" (the ticket is `00-ticket.md`), "job", "story" |
| **task directory** | `.loom/tasks/<n>-<slug>/` | "task folder", "workspace" |
| **mode** | `oneshot`, `quick`, or `full` | "workflow", "track" |
| **phase** | One workflow step that produces one artifact: research-questions, research, design, plan, implement | "stage", "step" |
| **implementation phase** | One vertical slice inside the plan | "phase" alone when it is ambiguous, "milestone", "slice" alone |
| **artifact** | A markdown file a phase writes into the task directory | "document", "doc" |
| **round** | One batch of open questions in design or plan | "iteration" |
| **approve** | Set an artifact's status to `approved` | "accept" (the user accepts a recommendation), "sign off" |
| **gate** | A phase that cannot start until a previous artifact is `approved` | "checkpoint", "blocker" |
| **checks** | The commands in `loom.json` → `checks` | "tests" when you mean all checks, "CI" |
| **docs role** | One kind of durable document that loom reads or writes: `vision`, `overview`, `decisions`, `conventions`, `tasks` | "doc type", "doc kind" |
| **docs map** | `loom.json` → `docs`: the path of each docs role; skills read it as `docs` from `loom-state` | "doc config", "doc layout" |
| **setup task** | The task of the issue "Set up loom", on the branch `chore/<n>-loom-setup` | "setup issue" (the issue is only its GitHub issue), "bootstrap task" |
| **onboarding task** | A setup task in `full` mode: the setup of a repository with code | "onboarding" alone for the task, "migration" |

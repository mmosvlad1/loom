# Screens Brief Template

The brief is the working artifact of a screens task: `<task dir>/screens-brief.md`. `screens` records the result of each stage in it, so a fresh session continues from the brief. Copy the block below, fill it, and remove every guidance comment.

````markdown
---
task: <n>-loom-screens
updated: <today>
drawing: <canvas | local>
---
## Scope

<!-- One line per screen: the screen ID of its default state, its states, and the vision item or issue it serves.
A screen that serves neither is not in the scope. -->
- `<screen ID>`: default, empty, error; serves <the vision item, or #k>

## Audience

<!-- Who uses the screens, and what each screen must do first. Empty until the user answers. -->

## References

<!-- Sites, screenshots, brand assets, and files that the user gave, one per line; or the single word none. -->

## Direction

<!-- The chosen direction: its name and one sentence. The single word open until the user chooses. -->
open

## Decisions

<!-- One line per decision, newest last: `<today>: <decision>`. A settled decision stays settled. -->

## Screens

| Screen ID | Status |
|---|---|
| <screen ID> | planned |
| <screen ID>--empty | planned |
````

## Rules

- Frontmatter: only `task`, `updated`, and `drawing`. Change `updated` to today on every edit.
- `drawing` is the drawing target of the task: `canvas` or `local`. `screens` chooses it once and keeps it, so later runs draw on the same target without `--local`. Only a confirmed move to local mode changes it to `local`.
- **Scope** names each screen once, by the screen ID of its default state. Its states follow: `default`, and those of `empty`, `loading`, and `error` that apply.
- **Screens** has one row per screen file: the screen ID of each state. The default state has no suffix; another state adds `--<state>`, e.g. `reading-list--empty`. The status is `planned` or `drafted`. Write the screen ID without backticks.
- A screen is `drafted` when its artboard (canvas) or its file `<task dir>/screens/<screen ID>.html` (local mode) exists.
- The result of each stage:

  | Stage | The brief holds its result when |
  |---|---|
  | 1. Brief | Audience has text, and References has text or `none` |
  | 2. Direction | Direction is not `open` |
  | 3. Style guide | `<task dir>/DESIGN.md` exists (the brief records no more) |
  | 4. Screens | every row of Screens is `drafted` |

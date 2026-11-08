# Visual Conventions

Use these rules for trees, diffs, and other visuals in artifacts (design, plan, research), in `docs/`, and in PR bodies.

## When a visual earns its place

- Add a visual only if it helps a decision or makes a shape clear faster than prose.
- Pick the smallest view that makes the point. Show only the files, calls, fields, and boundaries the reader needs for the current question.
- Put each visual next to the short text it supports. Write one or two sentences of prose between visuals; do not stack visuals without text.
- Do not repeat the same information as prose and as a visual.

## Choose the view

| To show | Use |
|---|---|
| Which files exist, or which files a change touches | File tree |
| A change to an existing shape (files, calls, types, config) | `diff` block |
| A new shape (new module, new interface, new flow) | Plain language block or signatures |
| Runtime control flow | Call tree |
| Logic or an algorithm | Pseudocode |
| An exact target the implementer must match | The full code block |

## File trees

Use proper tree glyphs: `├──`, `└──`, `│`. Omit unchanged paths. Add a short comment for each entry that matters.

```text
src/
├── commands/       # parses user actions
├── sessions/       # owns session state
└── transport/
    ├── client.py   # new: HTTP client with retries
    └── stream.py   # new: event stream reader
```

- Do not list a whole directory when one file matters. Show its parent and the file.
- Mark new and changed entries in the comment (`new:`, `changed:`) or use a `diff` block.

## Diff blocks

Use a `diff` block when the surrounding shape already exists and the point is what changes. Start each line with a marker:

- `+` added
- `-` removed
- `~` changed (a loom convention: the line exists before and after, with a different content)
- a space: unchanged context

File layout:

```diff
 src/
 ├── commands/
+│   └── export.py        # new command
 ├── sessions/
-└── transport.py
+└── transport/
+    ├── client.py
+    └── stream.py
```

Call tree:

```diff
 submit_form
   create_session
     persist_prompt
+    expand_skill_mention
     launch_agent
```

Type or config shape:

```diff
 class Settings:
     main_branch: str
~    timeout: float          # was int seconds
+    retries: int = 3
```

Keep only enough unchanged context to show where the change sits.

## New shapes

For a shape that does not exist yet, use a plain language block or key signatures, not a diff:

```text
on save(document)
  if content is unchanged
    return the cached result
  write the new content
  invalidate the cache
  return the fresh result
```

```python
def export_task(task_dir: Path, *, fmt: Literal["md", "json"]) -> Path: ...
```

Show the whole code block only when most of it is new, when omitted context would hide order or ownership, or when the implementer needs an exact target.

## Call trees

Show runtime control flow with indentation, one call per line:

```text
submit_form
  create_session
    persist_prompt
    launch_agent
  navigate_to_session
```

## Mermaid

Use a Mermaid diagram only for interaction between three or more components that a call tree cannot show clearly (e.g. a sequence across processes). GitHub renders Mermaid in PR bodies and in `docs/`; in a terminal it is plain text, so prefer a call tree in task-directory artifacts.

## Markdown inside code blocks

If a code block contains markdown with its own fenced code blocks, make the outer fence longer than the inner ones (````` ```` `````) or use the other character (`~~~`):

~~~markdown
## Example
```bash
make check
```
~~~

An inner fence closes the outer block only if it uses the same character and is at least as long.

# Style Guide Template

The layout of the style guide (the docs role `style`). `screens` drafts it as `<task dir>/DESIGN.md` in stage 3 and lands it at `docs.style`. Keep the six sections in this order. Remove every guidance comment.

- Every color, type role, and spacing step has a name. The code uses the same names for its tokens.
- Name a token by its role (`ink`, `paper`, `accent`), not by its hue.
- `loom-state` does not parse the file; only its existence counts.

````markdown
# Style guide

## Direction

<!-- One named direction, then two sentences: the mood, and what sets it apart. -->
<Name>. <The mood.> <What sets it apart.>

## Colors

<!-- One line per token: `name: #hex`, then its use. Cover the text, the background, the accent, the borders,
and the error color. Each text and background pair has a contrast ratio of 4.5:1 or more. -->
- `<name>: #<hex>`: <use>

## Typography

<!-- The font families, each with a fallback. Then one line per role: family, size/line height, weight. -->
- Families: `<family>, <fallback>`
- `<role>`: <size>/<line height>, <weight>

## Spacing and shape

<!-- The spacing scale with a name per step, the radii, the borders, and the shadows (or "No shadows."). -->
- Spacing scale: `<name>` <size>, `<name>` <size>
- Radius: <value>. Borders: <width> `<color token>`. Shadows: <value, or none>.

## States

<!-- How each state looks, one line each. Focus is always visible. -->
- Empty: <look>
- Loading: <look>
- Error: <look>
- Disabled: <look>
- Focus: <look>

## Rules

<!-- Do and do not, at most 10 lines. -->
- Do: <rule>
- Do not: <rule>
````

# Stack Recipe: python-uv

A Python project managed with uv. The checks entry point is a `Makefile`.

## Detect

- Markers: `pyproject.toml` and `uv.lock` at the git top level.
- `pyproject.toml` without `uv.lock`: ask the user whether the project uses uv. If yes, the plan lists `uv lock` (it writes `uv.lock`; CI runs `uv sync --locked` and needs it).
- A new, empty repository: ask the user whether it is a Python project. If yes, the plan lists `uv init --bare` (it writes only `pyproject.toml`), then `uv lock`.
- These commands run in setup step 7, after the plan is confirmed and before the Makefile is written. Their files go into the setup commit.

## Checks

| Key in `loom.json` → `checks` | Command | Makefile target runs |
|---|---|---|
| `lint` | `make lint` | `uv run ruff check .` and `uv run ruff format --check .` |
| `typecheck` | `make typecheck` | `uv run pyright` |
| `test` | `make test` | `uv run pytest`; exit status 5 (no tests collected) passes |
| `check` | `make check` | `lint`, `typecheck`, `test` |

- Template: `templates/Makefile`. Recipe lines start with a tab character, never with spaces.
- `pytest` exits with 5 when it collects no tests. A new project has no tests yet, so the `test` target accepts exit status 5 and nothing else.

### Reuse an existing Makefile

1. Read the `Makefile`. Find the targets `lint`, `typecheck`, `test`, and `check`.
2. A target exists: keep it as it is. Do not change its recipe.
3. A target is missing: propose to append it from the template. Show the appended lines as a `diff` block.
4. A target has another name (for example `types` or `tests`): ask the user whether to use it. If yes, put `make <name>` into `loom.json` → `checks`.
5. `check` must run the other three. If it exists and does not, say so in the plan and ask.

### Dev dependencies

Read `[dependency-groups]` → `dev` (and the older `[tool.uv]` → `dev-dependencies`) in `pyproject.toml`.

- `ruff`, `pyright`, and `pytest` all listed: nothing to do.
- One or more missing: list `uv add --dev <the missing ones>` in the plan. It changes `pyproject.toml` and `uv.lock`; both go into the setup commit. It runs in setup step 7, after `uv init --bare` and `uv lock`.
- The project uses other tools for the same job (for example `mypy` instead of `pyright`, `flake8` or `black` instead of `ruff`): ask the user which tools the targets run. Use the answer in the Makefile; do not add a second tool for the same job.

## CI

Template: `templates/ci.python-uv.yml`. Fill in:

| Placeholder | Value |
|---|---|
| `<main>` | `mainBranch` |
| `<python version>` | The version in `.python-version`. Else the lowest version that `requires-python` in `pyproject.toml` allows (`>=3.12` → `3.12`). Else ask the user. |

- One job, named `check`. A single Python version.
- `astral-sh/setup-uv` with `enable-cache: true` caches the uv downloads; `uv sync --locked` fails when `uv.lock` does not match `pyproject.toml`.
- Action versions are pinned to exact release tags. The template records the date they were checked.

### Reuse an existing workflow

If `.github/workflows/` already has a workflow that runs the checks on pull requests:

- Show it. Ask the user whether to keep it (loom then needs a job named `check` in it) or to add `ci.yml` from the template.
- Never delete or rewrite an existing workflow without confirmation.

## `.gitignore`

Lines that a new python-uv project needs, if missing: `.venv/`, `__pycache__/`, and the loom work directory (see the skill).

## Permissions

`templates/settings.json` allowlists `Bash(make *)` for this stack.

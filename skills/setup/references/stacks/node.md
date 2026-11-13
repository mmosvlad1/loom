# Stack Recipe: node

A Node project with `package.json`. The checks entry point is the `scripts` section of `package.json`; there is no Makefile.

## Detect

- Markers: `package.json` at the git top level, plus one lock file. The lock file names the package manager:

  | Lock file | Package manager | Run a script | Install in CI |
  |---|---|---|---|
  | `package-lock.json` | npm | `npm run <script>` | `npm ci` |
  | `pnpm-lock.yaml` | pnpm | `pnpm run <script>` | `pnpm install --frozen-lockfile` |
  | `bun.lock` or `bun.lockb` | bun | `bun run <script>` | `bun install --frozen-lockfile` |

- `package.json` without a lock file: ask the user which package manager the project uses. CI needs a lock file; the plan lists the install command that writes it (for example `npm install`). It runs in setup step 7.
- Several lock files: ask the user which one is current.

## Checks

| Key in `loom.json` → `checks` | Command (npm) |
|---|---|
| `lint` | `npm run lint` |
| `typecheck` | `npm run typecheck` |
| `test` | `npm run test` |
| `check` | `npm run check` |

Replace `npm run` with `pnpm run` or `bun run` for the other package managers.

### Reuse the existing scripts

1. Read `scripts` in `package.json`. Find `lint`, `typecheck`, `test`, and `check`.
2. A script exists: keep it. Do not change it.
3. A script has another name (for example `type-check` or `tsc`): ask the user whether to use it. If yes, put `<package manager> run <name>` into `loom.json` → `checks`.
4. A script is missing: propose one in the plan, as a `diff` block of `package.json`:
   - `typecheck`: `tsc --noEmit` when the project has `tsconfig.json` and `typescript` in `devDependencies`. Otherwise ask the user.
   - `lint` and `test`: ask the user which tool the project uses. Do not install a linter or a test runner without confirmation.
   - `check`: run the other three in order and stop at the first failure, e.g. `npm run lint && npm run typecheck && npm run test`.
5. Edit only the `scripts` object. Keep the rest of `package.json` byte for byte, including key order and indentation.

## CI

Template: `templates/ci.node.yml` (npm). Fill in:

| Placeholder | Value |
|---|---|
| `<main>` | `mainBranch` |
| `<node version>` | The version in `.nvmrc` or `.node-version`. Else the lowest major version that `engines.node` in `package.json` allows. Else ask the user. |

For pnpm and bun, change the steps between `actions/checkout` and the `Check` step:

- **pnpm**: add `- uses: pnpm/action-setup@v6.1.1` before `actions/setup-node`; set `cache: pnpm`; install with `pnpm install --frozen-lockfile`; check with `pnpm run check`. The pnpm version comes from `packageManager` in `package.json`.
- **bun**: replace `actions/setup-node` with `- uses: oven-sh/setup-bun@v2.2.0`; install with `bun install --frozen-lockfile`; check with `bun run check`.

- One job, named `check`. A single Node version.
- Action versions are pinned to exact release tags (latest releases checked on 2026-11-09).

### Reuse an existing workflow

The same rule as for python-uv: show an existing workflow, ask whether to keep it or to add `ci.yml`. A kept workflow needs no job named `check`: the check name of the job that runs the checks, as GitHub reports it, goes into `ci.requiredCheck` of `.claude/loom.json`. Never rename a job. The kept job must run `checks.check` (for example `npm run check`) exactly as configured; the skill's "Reused workflow" says what to do when it does not. Never delete or rewrite a workflow without confirmation.

## `.gitignore`

Lines that a new Node project needs, if missing: `node_modules/`, and the loom work directory (see the skill).

## Permissions

`settings.json` allowlists the four check commands exactly, e.g. `Bash(npm run lint)`, `Bash(npm run typecheck)`, `Bash(npm run test)`, `Bash(npm run check)`, in place of `Bash(make *)`.

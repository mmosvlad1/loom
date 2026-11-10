# Checks for this project: one entry point for the implementer, the loom hooks, and CI.
# .claude/loom.json -> checks references these targets; CI runs `make check`.
.PHONY: lint typecheck test check

lint:
	uv run ruff check .
	uv run ruff format --check .

typecheck:
	uv run pyright

# pytest exits with 5 when it collects no tests (a new project); only that case passes.
test:
	uv run pytest || [ $$? -eq 5 ]

check: lint typecheck test

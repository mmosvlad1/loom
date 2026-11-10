# loom development tasks. Standard library Python only (macOS python3 3.9+).
PYTHON ?= python3
CLAUDE ?= claude

.PHONY: test validate check eval

test:
	$(PYTHON) -m unittest discover -s tests -v

# `validate .` checks the marketplace manifest (and the plugin directory);
# the plugin manifest is validated on its own path.
validate:
	$(CLAUDE) plugin validate --strict .
	$(CLAUDE) plugin validate --strict .claude-plugin/plugin.json

check: test validate

# Eval suite (evals/, LOOM_SPEC.md 20.2). Not part of `check`: it calls the model and costs tokens.
# Extra flags go in EVAL_ARGS, e.g. make eval EVAL_ARGS='--case design-full --runs 3 --keep-temp'.
# --case and --tag combine with AND: on macOS, `--case implement-manual` also needs EVAL_FILTER=.
EVAL_MAX_COST ?= 10
EVAL_ARGS ?=
# Gated tools for every case: artifact writes, git, the checks, and loom-state. The last rule
# matches the skills' `!` injection ("<plugin root>"/bin/loom-state --json [--pr]): a skill's own
# allowed-tools cannot widen the grants of an eval run.
EVAL_TOOLS = Write Edit 'Bash(git *)' 'Bash(make *)' 'Bash(loom-state *)' 'Bash(*/bin/loom-state *)'

# PATH for the eval runs (seen live with Claude Code 2.1.318, LOOM_SPEC.md 24.2): the eval runtime
# does not put the plugin's bin/ on the Bash PATH, so bare `loom-state` calls need it here.
EVAL_PATH = $(CURDIR)/bin
# macOS: /usr/bin/python3 and make are xcrun shims that fail inside the eval sandbox, so the
# Command Line Tools directory comes first. Bash `git` stays pinned to /usr/bin/git and fails there,
# so by default only the cases tagged `local` run (implement-manual needs git). EVAL_FILTER= runs all.
ifeq ($(shell uname -s),Darwin)
EVAL_PATH := $(EVAL_PATH):$(shell xcode-select -p 2>/dev/null)/usr/bin
EVAL_FILTER ?= --tag local
else
EVAL_FILTER ?=
endif

eval:
ifeq ($(shell uname -s),Darwin)
ifneq ($(strip $(EVAL_FILTER)),)
	@echo "make eval: skipping implement-manual on macOS (the eval sandbox breaks Bash git, LOOM_SPEC.md 24.2); EVAL_FILTER= runs it anyway."
endif
endif
	PATH="$(EVAL_PATH):$$PATH" $(CLAUDE) plugin eval . \
		--scaffold --ablation none --no-publish --trust-plugin \
		--max-cost-usd $(EVAL_MAX_COST) --allow-tools $(EVAL_TOOLS) $(EVAL_FILTER) $(EVAL_ARGS)

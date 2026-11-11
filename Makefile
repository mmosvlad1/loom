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
# Linux: every skill case fails in the eval sandbox (read-only TMPDIR, likely an upstream Claude Code bug);
# the Evals workflow (.github/workflows/eval.yml) runs every case on a macOS runner instead.
EVAL_MAX_COST ?= 10
EVAL_ARGS ?=
# Gated tools for every case: artifact writes, git, the checks, and loom-state. The last rule
# matches the skills' `!` injection ("<plugin root>"/bin/loom-state --json [--pr]): a skill's own
# allowed-tools cannot widen the grants of an eval run.
EVAL_TOOLS = Write Edit 'Bash(git *)' 'Bash(make *)' 'Bash(loom-state *)' 'Bash(*/bin/loom-state *)'

# PATH for the eval runs (seen live with Claude Code 2.1.318, LOOM_SPEC.md 24.2): the eval runtime
# does not put the plugin's bin/ on the Bash PATH, so bare `loom-state` calls need it here.
EVAL_PATH = $(CURDIR)/bin
# macOS: with only the Command Line Tools, /usr/bin/python3 and make were xcrun shims that failed
# inside the eval sandbox, so the developer directory comes before them. Bash `git` cannot be moved
# this way: the sandboxed shell resolves it to the /usr/bin/git shim regardless of PATH. That shim
# failed with the Command Line Tools and with full Xcode, and worked once Homebrew git was
# installed. The recipe warns when the first git on the caller's PATH is /usr/bin/git (make's own
# PATH, before EVAL_PATH is added: EVAL_PATH holds the developer directory's git); it runs every
# case either way.
ifeq ($(shell uname -s),Darwin)
EVAL_PATH := $(EVAL_PATH):$(shell xcode-select -p 2>/dev/null)/usr/bin
endif

eval:
ifeq ($(shell uname -s),Darwin)
ifeq ($(shell command -v git 2>/dev/null),/usr/bin/git)
	@echo "make eval: the first git on PATH is /usr/bin/git; in the eval sandbox /usr/bin/git (an xcrun shim) fails, so implement-manual and describe-pr-quick will likely fail (LOOM_SPEC.md 24.2). Install git with Homebrew: brew install git"
endif
endif
	PATH="$(EVAL_PATH):$$PATH" $(CLAUDE) plugin eval . \
		--scaffold --ablation none --no-publish --trust-plugin \
		--max-cost-usd $(EVAL_MAX_COST) --allow-tools $(EVAL_TOOLS) $(EVAL_ARGS)

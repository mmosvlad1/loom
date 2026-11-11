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
# macOS: with only the Command Line Tools selected, /usr/bin/python3 and make were xcrun shims that
# failed inside the eval sandbox, so the developer directory comes before them. Bash `git` stays
# pinned to /usr/bin/git: it failed there too (implement-manual then fails), while the macOS CI
# runner, which has full Xcode, passed. The recipe warns about the Command Line Tools; it runs every case.
ifeq ($(shell uname -s),Darwin)
EVAL_PATH := $(EVAL_PATH):$(shell xcode-select -p 2>/dev/null)/usr/bin
endif

eval:
ifeq ($(shell uname -s),Darwin)
ifeq ($(shell xcode-select -p 2>/dev/null),/Library/Developer/CommandLineTools)
	@echo "make eval: xcode-select points to the Command Line Tools, where Bash git failed in the eval sandbox, so implement-manual will likely fail (LOOM_SPEC.md 24.2). The macOS CI runner has full Xcode and passes; to try that: sudo xcode-select -s /Applications/Xcode.app/Contents/Developer"
endif
endif
	PATH="$(EVAL_PATH):$$PATH" $(CLAUDE) plugin eval . \
		--scaffold --ablation none --no-publish --trust-plugin \
		--max-cost-usd $(EVAL_MAX_COST) --allow-tools $(EVAL_TOOLS) $(EVAL_ARGS)

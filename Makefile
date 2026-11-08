# loom development tasks. Standard library Python only (macOS python3 3.9+).
PYTHON ?= python3
CLAUDE ?= claude

.PHONY: test validate check

test:
	$(PYTHON) -m unittest discover -s tests -v

# `validate .` checks the marketplace manifest (and the plugin directory);
# the plugin manifest is validated on its own path.
validate:
	$(CLAUDE) plugin validate --strict .
	$(CLAUDE) plugin validate --strict .claude-plugin/plugin.json

check: test validate

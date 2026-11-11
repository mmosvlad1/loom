#!/usr/bin/env python3
"""PreToolUse (Bash) hook: block filtered check output (LOOM_SPEC.md 11.3).

Denies a check command piped into head, tail, grep, sed, awk, cut, less, or
more, because filtered output hides failures. `| tee <file>` is allowed.

Check commands: the commands in loom.json `checks` (a null check is skipped), plus `make
lint|typecheck|test|check`, pytest, ruff, pyright, mypy, `npm test`, `npm run
test|lint|typecheck`, and any of these behind `uv run` or `python -m`.
A silent no-op outside a git repository and without .claude/loom.json.
"""
from __future__ import annotations

import os
import sys
from typing import Any, Dict, List

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))

REASON = "Run checks unfiltered"

FILTERS = {"head", "tail", "grep", "egrep", "fgrep", "sed", "awk", "gawk", "nawk", "cut", "less", "more"}
MAKE_TARGETS = {"lint", "typecheck", "test", "check"}
CHECK_TOOLS = {"pytest", "py.test", "ruff", "pyright", "mypy"}
NPM_RUN_SCRIPTS = {"test", "lint", "typecheck"}
_UV_ARG_OPTS = {
    "--with", "--with-editable", "--with-requirements", "--package", "--python", "-p",
    "--extra", "--group", "--only-group", "--env-file", "--directory", "--project",
    "--index", "--default-index", "--index-url", "--extra-index-url",
}


def normalize(words: List[str]) -> List[str]:
    """Strip env/wrapper prefixes and `uv run [options]`."""
    words = loomhook.strip_prefixes(words)
    while len(words) >= 2 and os.path.basename(words[0]) == "uv" and words[1] == "run":
        i = 2
        while i < len(words) and words[i].startswith("-"):
            i += 2 if words[i] in _UV_ARG_OPTS else 1
        words = loomhook.strip_prefixes(words[i:])
    return words


def is_builtin_check(words: List[str]) -> bool:
    if not words:
        return False
    name = os.path.basename(words[0])
    args = words[1:]
    if name in ("make", "gmake"):
        return any(a in MAKE_TARGETS for a in args)
    if name in CHECK_TOOLS:
        return True
    if name.startswith("python") and len(args) >= 2 and args[0] == "-m":
        return args[1] in CHECK_TOOLS
    if name == "npm" and args:
        if args[0] in ("test", "t"):
            return True
        if args[0] in ("run", "run-script") and len(args) >= 2:
            return args[1] in NPM_RUN_SCRIPTS
    return False


def configured_patterns(cfg: Dict[str, Any]) -> List[List[str]]:
    """Word prefixes of every simple command in loom.json `checks`."""
    patterns: List[List[str]] = []
    checks = cfg.get("checks") if isinstance(cfg, dict) else None
    if not isinstance(checks, dict):
        return patterns
    for value in checks.values():
        if not isinstance(value, str):
            continue  # a null check: the project has no such check
        for stages in loomhook.parse_pipelines(value) or []:
            for words in stages:
                words = normalize(words)
                if not words or os.path.basename(words[0]) in ("cd", "pushd", "popd"):
                    continue  # directory changes are not checks
                if _is_script(words[0]):
                    words = words[:1]  # a configured script matches with any arguments
                patterns.append(_canonical(words))
    return patterns


def _is_script(word: str) -> bool:
    return "/" in word


def _canonical(words: List[str]) -> List[str]:
    """Normalize a script path, so `./scripts/x.sh` equals `scripts/x.sh`."""
    if words and _is_script(words[0]):
        return [os.path.normpath(words[0])] + words[1:]
    return words


def is_check(words: List[str], patterns: List[List[str]]) -> bool:
    words = normalize(words)
    if is_builtin_check(words):
        return True
    words = _canonical(words)
    return any(words[:len(p)] == p for p in patterns)


def is_filter(words: List[str]) -> bool:
    words = loomhook.strip_prefixes(words)
    return bool(words) and os.path.basename(words[0]) in FILTERS


def find_filtered_check(command: str, patterns: List[List[str]], depth: int = 0) -> bool:
    pipelines = loomhook.parse_pipelines(command)
    if not pipelines:
        return False
    for stages in pipelines:
        seen_check = False
        for words in stages:
            nested = loomhook.nested_shell_command(loomhook.strip_prefixes(words))
            if nested is not None and depth < 3:
                if find_filtered_check(nested, patterns, depth + 1):
                    return True
            if seen_check and is_filter(words):
                return True
            if is_check(words, patterns):
                seen_check = True
    return False


def main() -> None:
    data = loomhook.read_input()
    command = loomhook.bash_command(data)
    if "|" not in command:
        return
    cwd = loomhook.hook_cwd(data)
    ls = loomhook.loom_state()
    top, cfg = ls.load_repo_config(cwd)
    if cfg is None:
        return
    if find_filtered_check(command, configured_patterns(cfg)):
        loomhook.deny(
            "%s: a check command is piped into a filter (head, tail, grep, ...), which hides "
            "failures. Run it without the filter, or use `| tee <file>` to keep a copy." % REASON
        )


if __name__ == "__main__":
    try:
        sys.path.insert(0, HERE)
        import loomhook  # noqa: E402
    except Exception as exc:  # a broken install must not break the session
        sys.stderr.write("loom block-output-filtering hook: skipped, cannot load helpers: %s\n" % exc)
        sys.exit(0)
    loomhook.run_safely(main, "block-output-filtering")

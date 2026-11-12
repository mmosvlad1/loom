#!/usr/bin/env python3
"""PreToolUse (Bash) hook: block filtered check output (LOOM_SPEC.md 11.3).

Denies a check command piped into head, tail, grep, rg, wc, sed, awk, cut,
less, or more, because filtered output hides failures. `| tee <file>` is
allowed. A check inside a group or a shell counts too: `(make check) | tail`,
`{ make check; } | tail`, `bash -c 'make check' | head`.

Check commands: the commands in loom.json `checks` (a null check is skipped;
filter stages and setup steps such as `npm ci` inside a configured check are
not checks), plus `make lint|typecheck|test|check`, pytest, ruff, pyright,
mypy, `npm|pnpm|yarn|bun test`, `npm|pnpm|yarn|bun run test|lint|typecheck`,
`pnpm|yarn lint|typecheck`, and any of these behind `uv run`, `python -m`, or
a wrapper such as `timeout`. Not a check run: `--version`, `--help`, `-h`,
`make -n`, `pytest --collect-only`, `command -v|-V`, `which`, `type`.

A command that is exactly a configured check (after whitespace normalization)
is always allowed: it runs as configured, also when it has a filter.
A silent no-op outside a git repository and without .claude/loom.json.
"""
from __future__ import annotations

import os
import sys
from typing import Any, Dict, List

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))

REASON = "Run checks unfiltered"

FILTERS = {"head", "tail", "grep", "egrep", "fgrep", "rg", "wc", "sed", "awk", "gawk", "nawk", "cut", "less", "more"}
MAKE_TARGETS = {"lint", "typecheck", "test", "check"}
CHECK_TOOLS = {"pytest", "py.test", "ruff", "pyright", "mypy"}
RUN_SCRIPTS = {"test", "lint", "typecheck"}
JS_RUNNERS = {"npm", "pnpm", "yarn", "bun"}
# pnpm and yarn run a package script without `run`: `pnpm lint`.
JS_SHORTCUT_RUNNERS = {"pnpm", "yarn"}
# Arguments that show information instead of running the checks.
INFO_ARGS = {"--version", "--help", "-h"}
# Setup steps that a configured check may chain before the checks
# (`npm ci && npm run check`); they are never check commands themselves.
SETUP_COMMANDS = {
    "npm": {"ci", "install", "i"}, "pnpm": {"install", "i"}, "yarn": {"install"}, "bun": {"install", "i"},
    "uv": {"sync", "pip"}, "pip": {"install"}, "pip3": {"install"}, "poetry": {"install"},
    "bundle": {"install"}, "go": {"mod"}, "cargo": {"fetch"}, "composer": {"install"},
}
SETUP_WORDS = {"cd", "pushd", "popd", "export", "source", ".", "set", "unset", "true", ":", "echo", "mkdir"}
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


def shows_info(words: List[str]) -> bool:
    """`--version`, `--help`, `make -n`, `pytest --collect-only`: no checks run."""
    name = os.path.basename(words[0]) if words else ""
    args = words[1:]
    if any(a in INFO_ARGS for a in args):
        return True
    if name in ("make", "gmake"):
        return any(a in ("--dry-run", "--just-print", "--recon")
                   or (len(a) > 1 and a[0] == "-" and a[1] != "-" and "n" in a[1:]) for a in args)
    if name in ("pytest", "py.test") or (name.startswith("python") and args[:2] in (["-m", "pytest"],)):
        return any(a in ("--collect-only", "--co") for a in args)
    return False


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
    if name in JS_RUNNERS and args:
        if args[0] in ("test", "t") and not (name == "bun" and args[0] == "t"):
            return True
        if args[0] in ("run", "run-script") and len(args) >= 2:
            return args[1] in RUN_SCRIPTS
        if name in JS_SHORTCUT_RUNNERS and args[0] in RUN_SCRIPTS:
            return True
    return False


def is_setup(words: List[str]) -> bool:
    name = os.path.basename(words[0])
    if name in SETUP_WORDS:
        return True
    return len(words) >= 2 and words[1] in SETUP_COMMANDS.get(name, ())


def configured_checks(cfg: Dict[str, Any]) -> List[str]:
    checks = cfg.get("checks") if isinstance(cfg, dict) else None
    if not isinstance(checks, dict):
        return []
    return [v for v in checks.values() if isinstance(v, str) and v.strip()]  # a null check: no such check


def configured_patterns(cfg: Dict[str, Any]) -> List[List[str]]:
    """Word prefixes of the check commands in loom.json `checks`.

    Only the first stage of each pipeline is a check (later stages read its
    output: a filter in a configured check is not a check), and setup steps
    (`cd`, `npm ci`, `uv sync`, ...) are not checks.
    """
    patterns: List[List[str]] = []
    for value in configured_checks(cfg):
        for pipeline in _pipelines(loomhook.parse_script(value) or []):
            words = normalize(pipeline[0])
            if not words or is_setup(words):
                continue
            if _is_script(words[0]):
                words = words[:1]  # a configured script matches with any arguments
            patterns.append(_canonical(words))
    return patterns


def _pipelines(script: List[List[Any]]) -> List[List[List[str]]]:
    """The word lists of every pipeline whose first stage is a simple command, groups included."""
    out: List[List[List[str]]] = []
    for pipeline in script:
        for stage in pipeline:
            if isinstance(stage, loomhook.Group):
                out.extend(_pipelines(stage.script))
        if pipeline and not isinstance(pipeline[0], loomhook.Group) and pipeline[0].words:
            out.append([s.words for s in pipeline if not isinstance(s, loomhook.Group)])
    return out


def _is_script(word: str) -> bool:
    return "/" in word


def _canonical(words: List[str]) -> List[str]:
    """Normalize a script path, so `./scripts/x.sh` equals `scripts/x.sh`."""
    if words and _is_script(words[0]):
        return [os.path.normpath(words[0])] + words[1:]
    return words


def is_check(words: List[str], patterns: List[List[str]]) -> bool:
    words = normalize(words)
    if not words or shows_info(words):
        return False
    if is_builtin_check(words):
        return True
    words = _canonical(words)
    return any(words[:len(p)] == p for p in patterns)


def is_filter(words: List[str]) -> bool:
    words = loomhook.strip_prefixes(words)
    return bool(words) and os.path.basename(words[0]) in FILTERS


def _has_check(stage: Any, patterns: List[List[str]], depth: int) -> bool:
    """A stage runs a check: a check command, a group with one, or a shell that runs one."""
    if isinstance(stage, loomhook.Group):
        return any(_has_check(s, patterns, depth) for p in stage.script for s in p)
    if is_check(stage.words, patterns):
        return True
    nested = loomhook.nested_shell_command(loomhook.strip_prefixes(stage.words))
    if nested is None or depth >= 3:
        return False
    script = loomhook.parse_script(nested) or []
    return any(_has_check(s, patterns, depth + 1) for p in script for s in p)


def find_filtered_check(command: str, patterns: List[List[str]], depth: int = 0) -> bool:
    script = loomhook.parse_script(command)
    return bool(script) and _script_filtered(script, patterns, depth)


def _script_filtered(script: List[List[Any]], patterns: List[List[str]], depth: int) -> bool:
    for stages in script:
        seen_check = False
        for stage in stages:
            if isinstance(stage, loomhook.Group):
                if _script_filtered(stage.script, patterns, depth):
                    return True
            else:
                if depth < 3:
                    for body in stage.subs:
                        if find_filtered_check(body, patterns, depth + 1):
                            return True
                    nested = loomhook.nested_shell_command(loomhook.strip_prefixes(stage.words))
                    if nested is not None and find_filtered_check(nested, patterns, depth + 1):
                        return True
                if seen_check and is_filter(stage.words):
                    return True
            if _has_check(stage, patterns, depth):
                seen_check = True
    return False


def _squash(text: str) -> str:
    return " ".join(text.split())


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
    if _squash(command) in {_squash(c) for c in configured_checks(cfg)}:
        return  # a configured check runs exactly as configured (LOOM_SPEC.md 9.0)
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

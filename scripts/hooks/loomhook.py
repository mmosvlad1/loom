"""Shared helpers for loom hook scripts.

- reading the hook input from stdin,
- loading the loom-state module from bin/loom-state (one source of truth),
- splitting a Bash command into pipelines and simple commands with shlex.

Standard library only; runs on Python 3.9.
"""
from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import os
import re
import shlex
import sys
from typing import Any, Dict, List, Optional

PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LOOM_STATE_PATH = os.path.join(PLUGIN_ROOT, "bin", "loom-state")

_loom_state = None


def loom_state():
    """Import bin/loom-state as a module (it has no .py suffix)."""
    global _loom_state
    if _loom_state is None:
        sys.dont_write_bytecode = True  # keep the plugin directory clean
        loader = importlib.machinery.SourceFileLoader("loom_state", LOOM_STATE_PATH)
        spec = importlib.util.spec_from_loader("loom_state", loader)
        module = importlib.util.module_from_spec(spec)
        loader.exec_module(module)
        _loom_state = module
    return _loom_state


def read_input() -> Dict[str, Any]:
    """Parse the hook JSON from stdin; {} when it is missing or invalid."""
    try:
        raw = sys.stdin.read()
    except (OSError, ValueError):
        return {}
    if not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def hook_cwd(data: Dict[str, Any]) -> str:
    cwd = data.get("cwd")
    if isinstance(cwd, str) and cwd and os.path.isdir(cwd):
        return cwd
    return os.getcwd()


def bash_command(data: Dict[str, Any]) -> str:
    tool_input = data.get("tool_input")
    if isinstance(tool_input, dict):
        command = tool_input.get("command")
        if isinstance(command, str):
            return command
    return ""


def deny(reason: str) -> None:
    """Deny a PreToolUse call with the JSON decision form (exit code 0)."""
    sys.stdout.write(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }) + "\n")


def run_safely(main, name: str) -> None:
    """Run a hook main(); on any unexpected error, warn on stderr and exit 0."""
    try:
        main()
    except Exception as exc:  # a hook must never break the session
        sys.stderr.write("loom %s hook: skipped after error: %s\n" % (name, exc))
    sys.exit(0)


# ---------------------------------------------------------------------------
# Shell command splitting
# ---------------------------------------------------------------------------

_HEREDOC_RE = re.compile(r"<<(-?)\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\2")
_SEPARATOR_CHARS = set(";&|()\n")


def strip_heredocs(command: str) -> str:
    """Remove here-document bodies, so their text is not read as commands."""
    lines = command.split("\n")
    out: List[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        out.append(line)
        i += 1
        for m in _HEREDOC_RE.finditer(line):
            if line[max(0, m.start() - 1):m.start()] == "<":
                continue  # `<<<` here-string
            delimiter, dash = m.group(3), m.group(1) == "-"
            j = i
            while j < len(lines):
                candidate = lines[j].lstrip("\t") if dash else lines[j]
                if candidate.rstrip() == delimiter:
                    break
                j += 1
            if j < len(lines):
                i = j + 1  # drop the body and the terminator line
    return "\n".join(out)


def strip_comments(command: str) -> str:
    """Remove unquoted `# comments` that start a word (bash rules)."""
    out: List[str] = []
    quote = None
    i = 0
    n = len(command)
    while i < n:
        ch = command[i]
        if quote == "'":
            out.append(ch)
            if ch == "'":
                quote = None
        elif quote == '"':
            out.append(ch)
            if ch == "\\" and i + 1 < n:
                out.append(command[i + 1])
                i += 1
            elif ch == '"':
                quote = None
        elif ch == "\\" and i + 1 < n:
            out.append(ch)
            out.append(command[i + 1])
            i += 1
        elif ch in "'\"":
            quote = ch
            out.append(ch)
        elif ch == "#" and (i == 0 or command[i - 1] in " \t\n;&|()"):
            while i < n and command[i] != "\n":
                i += 1
            continue
        else:
            out.append(ch)
        i += 1
    return "".join(out)


def tokenize(command: str) -> Optional[List[str]]:
    """shlex tokens with shell punctuation as separate tokens; None on error."""
    text = strip_comments(strip_heredocs(command.replace("\\\n", " ")))
    lexer = shlex.shlex(text, posix=True, punctuation_chars="();<>|&\n")
    lexer.whitespace = " \t\r"
    lexer.whitespace_split = True
    lexer.commenters = ""
    try:
        return list(lexer)
    except ValueError:
        return None


def _is_operator(token: str) -> bool:
    return bool(token) and all(c in _SEPARATOR_CHARS or c in "<>" for c in token)


def parse_pipelines(command: str) -> Optional[List[List[List[str]]]]:
    """Split a command into pipelines -> stages -> words.

    `&&`, `||`, `;`, `&`, newlines and parentheses end a pipeline; `|` and `|&`
    join stages. Redirections and their targets are dropped. Quoted text stays
    one word, so `echo "git commit"` is the command `echo`.
    Returns None when the command cannot be parsed.
    """
    tokens = tokenize(command)
    if tokens is None:
        return None
    pipelines: List[List[List[str]]] = []
    stages: List[List[str]] = []
    words: List[str] = []
    skip_next = False

    def end_stage() -> None:
        nonlocal words
        if words:
            stages.append(words)
        words = []

    def end_pipeline() -> None:
        nonlocal stages
        end_stage()
        if stages:
            pipelines.append(stages)
        stages = []

    for token in tokens:
        if _is_operator(token):
            skip_next = False
            if "<" in token or ">" in token:
                if words and words[-1].isdigit():
                    words.pop()  # file descriptor of `2>&1`
                skip_next = True
                continue
            if token.replace("\n", "") in ("|", "|&"):
                end_stage()
            else:
                end_pipeline()
            continue
        if skip_next:
            skip_next = False
            continue
        words.append(token)
    end_pipeline()
    return pipelines


_ASSIGNMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_WRAPPERS = {"command", "builtin", "exec", "nohup", "time", "nice", "caffeinate"}
# Shell keywords that may precede a simple command: `{ git push; }`, `if git ...; then git ...`.
_KEYWORDS = {"{", "}", "!", "if", "then", "else", "elif", "do", "while", "until"}
_SUDO_ARG_OPTS = {"-u", "-g", "-C", "-D", "-h", "-p", "-r", "-t", "-U"}
_ENV_ARG_OPTS = {"-u", "-C", "-S", "--unset", "--chdir", "--split-string"}


def strip_prefixes(words: List[str]) -> List[str]:
    """Drop `VAR=value` assignments, shell keywords, and wrappers like env, sudo, time."""
    i = 0
    n = len(words)
    while i < n:
        w = words[i]
        if _ASSIGNMENT_RE.match(w) or w in _KEYWORDS:
            i += 1
        elif w in _WRAPPERS:
            i += 1
            while i < n and words[i].startswith("-"):
                i += 1
        elif w == "env":
            i += 1
            while i < n and (words[i].startswith("-") or _ASSIGNMENT_RE.match(words[i])):
                i += 2 if words[i] in _ENV_ARG_OPTS else 1
        elif w == "sudo":
            i += 1
            while i < n and words[i].startswith("-"):
                i += 2 if words[i] in _SUDO_ARG_OPTS else 1
        else:
            break
    return words[i:]


SHELLS = {"bash", "sh", "zsh", "dash", "ksh"}


def nested_shell_command(words: List[str]) -> Optional[str]:
    """The script of `bash -c '<script>'` or `eval <args>`, if any."""
    if not words:
        return None
    name = os.path.basename(words[0])
    if name == "eval":
        return " ".join(words[1:])
    if name in SHELLS:
        for i, w in enumerate(words[1:], start=1):
            if w.startswith("-") and not w.startswith("--") and "c" in w[1:]:
                return words[i + 1] if i + 1 < len(words) else None
            if not w.startswith("-"):
                return None
    return None

"""Shared helpers for loom hook scripts.

- reading the hook input from stdin,
- loading the loom-state module from bin/loom-state (one source of truth),
- parsing a Bash command into pipelines, groups, and simple commands (a small
  bash parser: quotes, substitutions, here-docs),
- running a check command with a timeout (Stop and SubagentStop hooks).

Standard library only; runs on Python 3.9.
"""
from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import os
import re
import signal
import subprocess
import sys
from typing import Any, Dict, List, Optional, Tuple

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
    """Run a hook main(); on any unexpected error, warn on stderr and exit 0.

    A main() that calls sys.exit(2) on purpose (Stop, SubagentStop) still exits
    2: SystemExit is not an Exception.
    """
    try:
        main()
    except Exception as exc:  # a hook must never break the session
        sys.stderr.write("loom %s hook: skipped after error: %s\n" % (name, exc))
    sys.exit(0)


def system_message(text: str) -> None:
    """Show a warning to the user (JSON `systemMessage`, exit code 0)."""
    sys.stdout.write(json.dumps({"systemMessage": text}) + "\n")


# ---------------------------------------------------------------------------
# Running check commands (Stop and SubagentStop hooks)
# ---------------------------------------------------------------------------


def run_check(command: str, cwd: str, timeout: int) -> Tuple[Optional[int], str]:
    """Run a loom.json check command with the shell, stdout and stderr merged.

    Returns (exit code, output); exit code None means the command timed out.
    The command runs in its own process group, so a timeout also stops the
    processes it started (make, test runners).
    """
    try:
        proc = subprocess.Popen(
            command, shell=True, cwd=cwd, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True,
        )
    except OSError as exc:
        return 127, "cannot run %r: %s" % (command, exc)
    try:
        out, _ = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except OSError:
            proc.kill()
        try:
            out, _ = proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            # A grandchild left the process group and still holds the pipe: give up on its output.
            out = b""
        return None, out.decode("utf-8", "replace")
    return proc.returncode, out.decode("utf-8", "replace")


def output_tail(text: str, max_lines: int = 80, max_chars: int = 6000) -> str:
    """The last lines of a command output, for a hook message."""
    lines = text.rstrip("\n").splitlines()
    shortened = len(lines) > max_lines
    result = "\n".join(lines[-max_lines:])
    if len(result) > max_chars:
        shortened = True
        result = result[-max_chars:]
        if "\n" in result:
            result = result.split("\n", 1)[1]  # drop the cut first line
    if shortened:
        result = "[... output shortened; last lines follow ...]\n" + result
    return result


# ---------------------------------------------------------------------------
# Shell command parsing
# ---------------------------------------------------------------------------
#
# A small bash lexer and parser, enough for the PreToolUse hooks. It keeps
# what they need: pipelines, subshell groups `( … )`, and the code that the
# shell runs although it sits inside a word or a redirection: command
# substitutions `$( … )` and backticks (also inside double quotes), process
# substitutions `<( … )`, and the here-document or here-string that feeds a
# command's stdin. Quoted text stays one word, so `echo "git commit"` is the
# command `echo`. Anything it cannot read gives None: the hooks then use their
# conservative fallback.

# Longest first, so `&&` wins over `&`.
_OPERATORS = sorted(
    [";;&", ";;", ";&", "&&", "||", "|&", "&>>", "&>", ">>", ">|", ">&", "<&", "<<<", "<<-", "<<", "<>",
     ";", "&", "|", "(", ")", "<", ">", "\n"],
    key=len, reverse=True,
)
_OP_CHARS = set(";&|()<>\n")
_BLANKS = " \t\r"
_ANSI_C_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "\\": "\\", "'": "'", '"': '"', "a": "\a", "b": "\b",
                   "e": "\x1b", "E": "\x1b", "f": "\f", "v": "\v", "?": "?"}
# Placeholders for text that only the running shell knows; `$` or the
# ellipsis marks a word as dynamic (see is_dynamic).
SUBST_MARK = "$(…)"
BACKTICK_MARK = "`…`"


class Unparsable(Exception):
    pass


class Token:
    __slots__ = ("op", "value", "subs", "heredoc")

    def __init__(self, op: bool, value: str, subs: Optional[List[str]] = None, heredoc: Optional[str] = None):
        self.op = op  # True for an operator, False for a word
        self.value = value
        self.subs = subs if subs is not None else []  # scripts of substitutions in this word
        self.heredoc = heredoc  # body of a `<<` operator


class _Lexer:
    def __init__(self, text: str):
        self.text = text
        self.n = len(text)

    def lex(self, i: int, nested: bool) -> Tuple[List[Token], int]:
        """Tokens from index i. nested: stop after the `)` that closes a `$(`."""
        text, n = self.text, self.n
        tokens: List[Token] = []
        buf: List[str] = []
        subs: List[str] = []
        state = {"word": False, "quoted": False}
        pending: List[Tuple[Token, str, bool, bool]] = []  # here-docs waiting for their bodies
        depth = 0

        def end_word() -> None:
            if state["word"]:
                tokens.append(Token(False, "".join(buf), list(subs)))
            del buf[:]
            del subs[:]
            state["word"] = state["quoted"] = False

        while i < n:
            ch = text[i]
            if ch == "\\":
                if i + 1 < n and text[i + 1] == "\n":
                    i += 2  # line continuation
                    continue
                if i + 1 < n:
                    buf.append(text[i + 1])
                    state["word"] = True
                i += 2
                continue
            if ch in _BLANKS:
                end_word()
                i += 1
                continue
            if ch == "#" and not state["word"]:
                while i < n and text[i] != "\n":
                    i += 1
                continue
            if ch == "'":
                j = text.find("'", i + 1)
                if j < 0:
                    raise Unparsable("unterminated quote")
                buf.append(text[i + 1:j])
                state["word"] = state["quoted"] = True
                i = j + 1
                continue
            if ch == '"':
                i = self._double(i + 1, buf, subs)
                state["word"] = state["quoted"] = True
                continue
            if ch == "`":
                body, i = self._backtick(i + 1)
                subs.append(body)
                buf.append(BACKTICK_MARK)
                state["word"] = True
                continue
            if ch == "$" and i + 1 < n:
                nxt = text[i + 1]
                if nxt == "'":
                    i = self._ansi_c(i + 2, buf)
                    state["word"] = state["quoted"] = True
                    continue
                if nxt == '"':
                    i = self._double(i + 2, buf, subs)
                    state["word"] = state["quoted"] = True
                    continue
                if nxt == "(":
                    i = self._dollar_paren(i, buf, subs)
                    state["word"] = True
                    continue
                if nxt == "{":
                    i = self._brace(i, buf)
                    state["word"] = True
                    continue
            if ch in _OP_CHARS:
                if ch in "<>" and i + 1 < n and text[i + 1] == "(" and not state["word"]:
                    body, i = self._subst(i + 2)  # process substitution
                    subs.append(body)
                    buf.append(ch + "(…)")
                    state["word"] = True
                    continue
                if ch in "<>" and state["word"] and not state["quoted"] and "".join(buf).isdigit():
                    del buf[:]  # file descriptor of `2>&1`
                    state["word"] = False
                end_word()
                op = next(o for o in _OPERATORS if text.startswith(o, i))
                i += len(op)
                if nested and op == "(":
                    depth += 1
                elif nested and op == ")":
                    if depth == 0:
                        for tok, _, _, _ in pending:
                            tok.heredoc = ""
                        return tokens, i
                    depth -= 1
                tok = Token(True, op)
                tokens.append(tok)
                if op in ("<<", "<<-"):
                    delimiter, quoted, i = self._delimiter(i)
                    pending.append((tok, delimiter, op == "<<-", quoted))
                elif op == "\n" and pending:
                    i = self._heredoc_bodies(i, pending)
                    pending = []
                continue
            buf.append(ch)
            state["word"] = True
            i += 1
        end_word()
        if nested:
            raise Unparsable("unterminated $(")
        for tok, _, _, _ in pending:
            tok.heredoc = ""
        return tokens, i

    def _double(self, i: int, buf: List[str], subs: List[str], heredoc: bool = False) -> int:
        """Text after `"` up to the closing quote (or the end, for a here-doc body)."""
        text, n = self.text, self.n
        while i < n:
            c = text[i]
            if c == '"' and not heredoc:
                return i + 1
            if c == "\\" and i + 1 < n:
                nxt = text[i + 1]
                if nxt in "$`\\" or (nxt == '"' and not heredoc):
                    buf.append(nxt)
                    i += 2
                    continue
                if nxt == "\n":
                    i += 2
                    continue
                buf.append(c)
                i += 1
                continue
            if c == "`":
                body, i = self._backtick(i + 1)
                subs.append(body)
                buf.append(BACKTICK_MARK)
                continue
            if c == "$" and i + 1 < n and text[i + 1] == "(":
                i = self._dollar_paren(i, buf, subs)
                continue
            if c == "$" and i + 1 < n and text[i + 1] == "{":
                i = self._brace(i, buf)
                continue
            buf.append(c)
            i += 1
        if heredoc:
            return i
        raise Unparsable("unterminated double quote")

    def _dollar_paren(self, i: int, buf: List[str], subs: List[str]) -> int:
        """`$(` at i: a command substitution, or `$((` arithmetic."""
        if self.text.startswith("$((", i):
            end = self._match_parens(i + 1)
            buf.append(self.text[i:end])
            return end
        body, end = self._subst(i + 2)
        subs.append(body)
        buf.append(SUBST_MARK)
        return end

    def _subst(self, start: int) -> Tuple[str, int]:
        """The script of a substitution that starts at `start` (after the `(`)."""
        _, end = self.lex(start, nested=True)
        return self.text[start:end - 1], end

    def _match_parens(self, i: int) -> int:
        depth = 0
        while i < self.n:
            c = self.text[i]
            if c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
                if depth == 0:
                    return i + 1
            i += 1
        raise Unparsable("unterminated $((")

    def _brace(self, i: int, buf: List[str]) -> int:
        """`${…}` kept as raw text (it is dynamic)."""
        depth = 0
        start = i
        i += 1
        while i < self.n:
            c = self.text[i]
            if c == "\\":
                i += 2
                continue
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    buf.append(self.text[start:i + 1])
                    return i + 1
            i += 1
        raise Unparsable("unterminated ${")

    def _backtick(self, i: int) -> Tuple[str, int]:
        out: List[str] = []
        while i < self.n:
            c = self.text[i]
            if c == "\\" and i + 1 < self.n and self.text[i + 1] in "`$\\":
                out.append(self.text[i + 1])
                i += 2
                continue
            if c == "`":
                return "".join(out), i + 1
            out.append(c)
            i += 1
        raise Unparsable("unterminated backtick")

    def _ansi_c(self, i: int, buf: List[str]) -> int:
        """`$'…'` with its backslash escapes decoded."""
        while i < self.n:
            c = self.text[i]
            if c == "'":
                return i + 1
            if c == "\\" and i + 1 < self.n:
                nxt = self.text[i + 1]
                buf.append(_ANSI_C_ESCAPES.get(nxt, "\\" + nxt))
                i += 2
                continue
            buf.append(c)
            i += 1
        raise Unparsable("unterminated $'")

    def _delimiter(self, i: int) -> Tuple[str, bool, int]:
        """The here-doc delimiter word after `<<`: (text without quotes, quoted?, next index)."""
        text, n = self.text, self.n
        while i < n and text[i] in _BLANKS:
            i += 1
        out: List[str] = []
        quoted = False
        while i < n and text[i] not in _BLANKS and text[i] not in _OP_CHARS:
            c = text[i]
            if c in "'\"":
                j = text.find(c, i + 1)
                if j < 0:
                    raise Unparsable("unterminated here-doc delimiter")
                out.append(text[i + 1:j])
                quoted = True
                i = j + 1
            elif c == "\\" and i + 1 < n:
                out.append(text[i + 1])
                quoted = True
                i += 2
            else:
                out.append(c)
                i += 1
        if not out and not quoted:
            raise Unparsable("missing here-doc delimiter")
        return "".join(out), quoted, i

    def _heredoc_bodies(self, i: int, pending: List[Tuple[Token, str, bool, bool]]) -> int:
        """Read the bodies of the pending here-docs, line by line from i."""
        text, n = self.text, self.n
        for tok, delimiter, strip_tabs, quoted in pending:
            lines: List[str] = []
            while i < n:
                j = text.find("\n", i)
                line = text[i:j] if j >= 0 else text[i:]
                i = j + 1 if j >= 0 else n
                if strip_tabs:
                    line = line.lstrip("\t")
                if line == delimiter:
                    break
                lines.append(line)
            tok.heredoc = "\n".join(lines)
            if not quoted:
                # An unquoted here-doc expands `$( … )` and backticks in its body.
                body = _Lexer(tok.heredoc)
                body._double(0, [], tok.subs, heredoc=True)
        return i


class Command:
    """A simple command: its words, the scripts of its substitutions, and its stdin text."""

    __slots__ = ("words", "subs", "stdin")

    def __init__(self) -> None:
        self.words: List[str] = []
        self.subs: List[str] = []
        self.stdin: Optional[str] = None  # here-doc body or here-string

    def __bool__(self) -> bool:
        return bool(self.words or self.subs or self.stdin is not None)


class Group:
    """A group: a subshell `( … )` or a brace group `{ …; }`, with its own script."""

    __slots__ = ("script", "subshell")

    def __init__(self, script: List[List[Any]], subshell: bool = True):
        self.script = script
        self.subshell = subshell  # False for `{ …; }`: it runs in the current shell


class Pipeline(list):
    """The stages of one pipeline, and the operator before it.

    op: None (the first pipeline of a script or group), `&&`, `||`, or a
    list separator (`;`, `&`, a newline, `;;`).
    """

    def __init__(self, stages: Any = (), op: Optional[str] = None):
        super().__init__(stages)
        self.op = op


def parse_script(command: str) -> Optional[List[List[Any]]]:
    """Parse a command into a script: Pipelines -> stages (Command or Group).

    `&&`, `||`, `;`, `&` and newlines end a pipeline (Pipeline.op keeps the
    operator); `|` and `|&` join stages. Redirection targets are dropped.
    Returns None when the command cannot be parsed.
    """
    try:
        tokens, _ = _Lexer(command).lex(0, nested=False)
        script, _ = _parse(tokens, 0, 0, None)
    except (Unparsable, RecursionError):
        return None
    return script


MAX_GROUP_DEPTH = 50


def _parse(tokens: List[Token], pos: int, depth: int, closer: Optional[str]) -> Tuple[List[List[Any]], int]:
    """Parse until `closer` (`)` or `}`, None at the top level); groups parse at depth + 1."""
    if depth > MAX_GROUP_DEPTH:
        raise Unparsable("groups nested too deep")
    script: List[List[Any]] = []
    stages: List[Any] = []
    cmd = Command()
    redirect: Optional[str] = None
    op_before: Optional[str] = None

    def end_command() -> None:
        nonlocal cmd
        if cmd:
            stages.append(cmd)
        cmd = Command()

    def end_pipeline(next_op: Optional[str]) -> None:
        nonlocal stages, op_before
        end_command()
        if stages:
            script.append(Pipeline(stages, op_before))
            op_before = next_op
        elif op_before not in ("&&", "||") and script:
            op_before = next_op  # `a &&<newline>b` keeps the `&&`
        stages = []

    while pos < len(tokens):
        tok = tokens[pos]
        pos += 1
        if not tok.op:
            if redirect is None and not cmd and tok.value == "{":
                inner, pos = _parse(tokens, pos, depth + 1, "}")  # brace group
                stages.append(Group(inner, subshell=False))
                continue
            if redirect is None and not cmd and tok.value == "}" and closer == "}":
                end_pipeline(None)
                return script, pos
            cmd.subs.extend(tok.subs)
            if redirect is not None:
                if redirect == "<<<":
                    cmd.stdin = tok.value
                redirect = None
            else:
                cmd.words.append(tok.value)
            continue
        op = tok.value
        redirect = None
        if "<" in op or ">" in op:
            if op in ("<<", "<<-"):
                cmd.stdin = tok.heredoc or ""
                cmd.subs.extend(tok.subs)
            else:
                redirect = op
            continue
        if op in ("|", "|&"):
            end_command()
            continue
        if op == "(":
            if cmd.words and cmd.words[-1].endswith("="):
                pos = _skip_array(tokens, pos, cmd)  # `arr=(a b)`
                continue
            if cmd.words and pos < len(tokens) and tokens[pos].op and tokens[pos].value == ")":
                pos += 1  # `f()`: a function definition; its body follows
                cmd = Command()
                continue
            end_command()
            inner, pos = _parse(tokens, pos, depth + 1, ")")
            stages.append(Group(inner))
            continue
        if op == ")":
            end_pipeline(None)
            if closer == ")":
                return script, pos
            if closer == "}":
                return script, pos - 1  # unbalanced: the enclosing `( … )` closes here
            continue  # a `case` pattern
        end_pipeline(op)
    end_pipeline(None)
    return script, pos


def _skip_array(tokens: List[Token], pos: int, cmd: Command) -> int:
    depth = 1
    while pos < len(tokens):
        tok = tokens[pos]
        pos += 1
        if tok.op and tok.value == "(":
            depth += 1
        elif tok.op and tok.value == ")":
            depth -= 1
            if depth == 0:
                break
        else:
            cmd.subs.extend(tok.subs)
    return pos


def is_dynamic(word: str) -> bool:
    """True if the shell decides the word's value: a variable or a substitution."""
    return "$" in word or "`" in word or "…" in word


_ASSIGNMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\[[^]]*\])?\+?=")
# Shell keywords that may precede a simple command: `{ git push; }`, `if git ...; then git ...`.
_KEYWORDS = {"{", "}", "!", "if", "then", "else", "elif", "do", "while", "until"}
# Wrappers that run the rest of the line as a command, with their options that
# take a separate argument.
_WRAPPERS: Dict[str, set] = {
    "command": set(),
    "builtin": set(),
    "exec": {"-a"},
    "nohup": set(),
    "noglob": set(),
    "nocorrect": set(),
    "time": {"-f", "-o", "--format", "--output"},
    "nice": {"-n", "--adjustment"},
    "ionice": {"-c", "-n", "-p", "-P", "-u", "--class", "--classdata", "--pid", "--pgid", "--uid"},
    "stdbuf": {"-i", "-o", "-e", "--input", "--output", "--error"},
    "caffeinate": {"-t", "-w"},
    "timeout": {"-s", "-k", "--signal", "--kill-after"},
    "xargs": {"-I", "-L", "-n", "-P", "-s", "-d", "-E", "-a", "--max-args", "--max-procs", "--max-chars",
              "--max-lines", "--delimiter", "--arg-file", "--eof", "--process-slot-var"},
    "env": {"-u", "-C", "-S", "--unset", "--chdir", "--split-string"},
    "sudo": {"-u", "-g", "-C", "-D", "-h", "-p", "-r", "-t", "-U"},
}
# Wrappers with positional arguments before the command: `timeout 30 git push`.
_WRAPPER_POSITIONALS = {"timeout": 1}
_ENV_CHDIR_OPTS = ("-C", "--chdir")


class Prefixes:
    """What the prefixes of a simple command set up for it."""

    __slots__ = ("env", "chdir", "words")

    def __init__(self) -> None:
        self.env: Dict[str, str] = {}  # `VAR=value` assignments, also after `env`
        self.chdir: Optional[str] = None  # `env -C <dir>`
        self.words: List[str] = []  # the command and its arguments


def command_prefixes(words: List[str]) -> Prefixes:
    """Split off `VAR=value` assignments, shell keywords, `function <name>`, and wrappers like env, sudo, timeout.

    zsh's `=git` becomes `git`. `command -v|-V <name>` runs nothing: no words.
    """
    result = Prefixes()
    i = 0
    n = len(words)
    while i < n:
        w = words[i]
        match = _ASSIGNMENT_RE.match(w)
        if match:
            name = w[:match.end()].rstrip("=").rstrip("+")
            result.env[name.split("[", 1)[0]] = w[match.end():]
            i += 1
        elif w in _KEYWORDS:
            i += 1
        elif w == "function":
            i += 2  # `function f { …; }`: the body follows the name
        elif w in _WRAPPERS:
            arg_opts = _WRAPPERS[w]
            i += 1
            while i < n and words[i].startswith("-") and words[i] != "-":
                opt = words[i]
                if opt == "--":
                    i += 1
                    break
                if w == "command" and opt[0] == "-" and ("v" in opt[1:] or "V" in opt[1:]):
                    return result  # `command -v git` only looks the name up
                if w == "env" and opt in _ENV_CHDIR_OPTS and i + 1 < n:
                    result.chdir = words[i + 1]
                elif w == "env" and opt.startswith("--chdir="):
                    result.chdir = opt[len("--chdir="):]
                i += 2 if opt in arg_opts else 1
            i += _WRAPPER_POSITIONALS.get(w, 0)
        else:
            break
    rest = words[i:]
    if rest and rest[0].startswith("=") and len(rest[0]) > 1:
        rest = [rest[0][1:]] + rest[1:]  # zsh: `=git` is the git on the PATH
    result.words = rest
    return result


def strip_prefixes(words: List[str]) -> List[str]:
    """The command and its arguments without prefixes (see command_prefixes)."""
    return command_prefixes(words).words


SHELLS = {"bash", "sh", "zsh", "dash", "ksh", "mksh", "ash", "fish"}


def shell_invocation(words: List[str]) -> Tuple[str, Optional[str]]:
    """How a command runs shell code it gets as data.

    ("c", script) for `bash -c '<script>'` (any options before) and `eval`;
    ("stdin", None) for a shell that reads its script from stdin (`bash`,
    `sh -s`); ("", None) for anything else, including a shell running a file.
    """
    if not words:
        return "", None
    name = os.path.basename(words[0])
    if name == "eval":
        return "c", " ".join(words[1:])
    if name not in SHELLS:
        return "", None
    has_c = has_s = False
    i = 1
    while i < len(words):
        w = words[i]
        if w in ("--", "-"):
            i += 1
            break
        if w in ("--rcfile", "--init-file"):
            i += 2
            continue
        if w.startswith("--"):
            i += 1
            continue
        if len(w) > 1 and w[0] in "-+":
            flags = w[1:]
            if w[0] == "-" and "c" in flags:
                has_c = True
            if w[0] == "-" and "s" in flags:
                has_s = True
            i += 2 if flags[-1] in "oO" else 1  # `-o pipefail`, `-euo pipefail`
            continue
        break
    rest = words[i:]
    if has_c:
        return ("c", rest[0]) if rest else ("", None)
    if has_s or not rest:
        return "stdin", None
    return "", None


def nested_shell_command(words: List[str]) -> Optional[str]:
    """The script of `bash -c '<script>'` or `eval <args>`, if any."""
    kind, script = shell_invocation(words)
    return script if kind == "c" else None


def piped_script(prev: Any) -> Optional[str]:
    """The text a pipeline stage writes to the next one, when it is literal.

    `echo '<text>'`, `printf '<text>'`, and `cat` with a here-doc or here-string.
    """
    if not isinstance(prev, Command):
        return None
    words = strip_prefixes(prev.words)
    if not words:
        return None
    name = os.path.basename(words[0])
    args = words[1:]
    if name == "echo":
        while args and args[0] in ("-n", "-e", "-E", "-ne", "-en"):
            args = args[1:]
        return " ".join(args)
    if name == "printf":
        return " ".join(args)
    if name == "cat" and not args and prev.stdin is not None:
        return prev.stdin
    return None

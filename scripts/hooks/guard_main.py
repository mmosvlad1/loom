#!/usr/bin/env python3
"""PreToolUse (Bash) hook: guard the main branch (LOOM_SPEC.md section 11.2).

Denies:
- `git commit` while the current branch is the configured main branch, except
  the very first commit of a repository without commits;
- `git push` while the current branch is the main branch, unless the push
  cannot update the main branch on the remote (explicit refspecs, none of
  them the main branch: tags, other branches, deletions of other branches;
  `--dry-run`), and except the first push of main (no
  refs/remotes/origin/<main>, exactly one commit);
- any `git push` whose refspec targets the main branch, from any branch
  (`origin main`, `HEAD:main`, `+main`, `:main`, `--force ... main`, `--all`,
  `--mirror`, `:`).

Reads the command with loomhook's shell parser: compound commands, subshells
(a `cd` inside `( … )` stays there), brace groups, `cd`/`pushd`/`popd`/`cd -`,
`git -C`, `GIT_DIR`/`GIT_WORK_TREE` and `env -C`, global git options, git
aliases (also `-c alias.<name>=…`), wrappers (`timeout`, `nice`, `xargs`, …),
`bash -c`, shells fed by a here-doc, here-string, or `echo … |`, command and
process substitutions (also inside double quotes), and branch switches earlier
in the same command (`git switch -`, `-c` of an existing branch, `checkout
<branch> --`, `symbolic-ref HEAD`).

Conservative where it cannot know: a directory it cannot resolve (a variable,
a substitution, a directory that does not exist yet) means the original cwd;
a branch it cannot resolve means the real current branch; an alias it cannot
read counts as both commit and push; the right side of `||` is checked with
the branch state from before each command that may have failed; a command it
cannot parse falls back to a linear text search. Text inside quotes is not a
command. git answers are cached for the hook run.
A silent no-op outside a git repository and in repositories without
.claude/loom.json.
"""
from __future__ import annotations

import fnmatch
import itertools
import os
import re
import shlex
import sys
from typing import Any, Dict, Iterator, List, Optional, Set, Tuple

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))

REASON = "Create a task branch with /loom:start-task"
PUSH_OF_MAIN = (
    "git push of the main branch '%s' is blocked: %s. On the main branch only a push that cannot update it "
    "is allowed (tags, other branches, --dry-run). %s"
)

# Nesting depth for code inside code (substitutions, `bash -c`, aliases);
# deeper code gets the text fallback.
MAX_DEPTH = 4

# Global git options that take a separate argument.
_GIT_ARG_OPTS = {"-c", "--namespace", "--super-prefix", "--config-env", "--list-cmds", "--attr-source"}
_GIT_PATH_OPTS = {"--git-dir", "--work-tree"}

# Built-in subcommands: git never lets an alias override them, so no alias lookup.
_BUILTINS = {
    "add", "am", "apply", "bisect", "blame", "branch", "cat-file", "checkout",
    "cherry-pick", "clean", "clone", "commit", "commit-tree", "config", "describe", "diff",
    "fetch", "for-each-ref", "format-patch", "grep", "help", "init", "log",
    "ls-files", "ls-remote", "ls-tree", "merge", "merge-base", "mv", "notes",
    "pull", "push", "rebase", "reflog", "remote", "reset", "restore", "rev-list",
    "rev-parse", "revert", "rm", "shortlog", "show", "show-ref", "stash",
    "status", "submodule", "switch", "symbolic-ref", "tag", "update-ref", "version",
    "worktree",
}

# Environment variables that select the repository, like --git-dir and --work-tree.
_GIT_ENV_PATHS = {"GIT_DIR": "--git-dir", "GIT_WORK_TREE": "--work-tree"}
# Environment variables that add git config (and so possibly aliases).
_GIT_ENV_CONFIG = ("GIT_CONFIG_PARAMETERS", "GIT_CONFIG_COUNT")
_ALIAS_UNKNOWN = "\0alias"  # an alias the guard cannot resolve

_PUSH_ARG_OPTS = {"-o", "--push-option", "--repo", "--receive-pack", "--exec"}
_PLAIN_PUSH_FLAGS = {"-u", "--set-upstream", "-q", "--quiet", "-v", "--verbose"}
_CREATE_OPTS = {"-c", "-C", "-b", "-B", "--create", "--force-create", "--orphan"}
_FORCE_CREATE_OPTS = {"-C", "-B", "--force-create"}

# Fallback for commands the parser cannot read: `git`, then within this many
# words of the same line and command, `commit` or `push`.
_FALLBACK_WINDOW = 32
_FALLBACK_SEGMENT_RE = re.compile(r"[;&|\n]")
_FALLBACK_GIT_RE = re.compile(r"(?:^|[(`$\"'=\\])git$")
_FALLBACK_SUB_RE = re.compile(r"^(commit|push)(?![\w-])")
_FALLBACK_WORD_RE = re.compile(r"[^\s;&|()<>]+")

# Branch state markers (a branch name, or None for a detached HEAD).
_REAL = object()      # the branch as git reports it now
_UNKNOWN = object()   # a previous branch that cannot be known
_NO_BRANCH = object()  # no previous branch: `git switch -` fails


class Repo:
    """loom context of one repository (None fields when loom does not apply)."""

    def __init__(self, top: Optional[str], main_branch: Optional[str]):
        self.top = top
        self.main_branch = main_branch


class Cwd:
    """The working directory while the command runs; a subshell works on a copy."""

    def __init__(self, path: str, old: Optional[str] = None, stack: Optional[List[str]] = None,
                 env: Optional[Dict[str, str]] = None):
        self.path = path
        self.old = old  # $OLDPWD for `cd -`; None when unknown
        self.stack = list(stack or [])  # pushd stack
        self.env = dict(env or {})  # git variables exported earlier in the command

    def copy(self) -> "Cwd":
        return Cwd(self.path, self.old, self.stack, self.env)


class Guard:
    def __init__(self, cwd: str):
        self.ls = loomhook.loom_state()
        self.start_cwd = cwd
        self._repos: Dict[Tuple[str, Tuple[str, ...]], Repo] = {}
        # Branch switches seen earlier in the same command, per repo top-level:
        # (current, previous). Branches are repository state, so a switch inside
        # a subshell counts for the rest of the command.
        self.switched: Dict[str, Tuple[Any, Any]] = {}
        # Branches created earlier in the same command, per repo top-level.
        self.created: Dict[str, Set[str]] = {}
        # git answers for this hook run; the hook never changes the repository.
        self._git_cache: Dict[Tuple[str, Tuple[str, ...]], Tuple[int, str, str]] = {}
        self._configs: Dict[str, Any] = {}

    def _git(self, extra: Any, args: List[str], gdir: str) -> Tuple[int, str, str]:
        """`git <extra> <args>` in gdir, cached per hook run."""
        full = tuple(extra) + tuple(args)
        key = (gdir, full)
        if key not in self._git_cache:
            self._git_cache[key] = self.ls.git(list(full), gdir)
        return self._git_cache[key]

    def _config(self, top: str) -> Any:
        if top not in self._configs:
            self._configs[top] = self.ls.load_config(top)[0]
        return self._configs[top]

    # -- repository context ----------------------------------------------

    def repo(self, gdir: str, extra: Tuple[str, ...]) -> Repo:
        key = (gdir, extra)
        if key not in self._repos:
            top = None
            main_branch = None
            if os.path.isdir(gdir):
                candidates = []
                if any(e.startswith("--git-dir=") for e in extra):
                    # The repository is the git directory: `<top>/.git` belongs to <top>,
                    # also when the work tree is elsewhere or not given.
                    rc, out, _ = self._git(extra, ["rev-parse", "--absolute-git-dir"], gdir)
                    if rc == 0 and os.path.basename(out.strip()) == ".git":
                        candidates.append(os.path.dirname(out.strip()))
                if not candidates:
                    rc, out, _ = self._git(extra, ["rev-parse", "--show-toplevel"], gdir)
                    if rc == 0 and out.strip():
                        candidates.append(out.strip())
                for candidate in candidates:
                    cfg = self._config(candidate)
                    if cfg is not None:
                        top, main_branch = candidate, cfg["mainBranch"]
                        break
            self._repos[key] = Repo(top, main_branch)
        return self._repos[key]

    def branch(self, repo: Repo, gdir: str, extra: Tuple[str, ...]) -> Optional[str]:
        """Branch after the switches seen earlier in this command (None: detached HEAD)."""
        current = self.switched.get(repo.top, (_REAL, _REAL))[0]
        if current is _REAL:
            return self.real_branch(gdir, extra)
        return current

    def real_branch(self, gdir: str, extra: Tuple[str, ...]) -> Optional[str]:
        """The current branch as git reports it now (ignores earlier switches)."""
        rc, out, _ = self._git(extra, ["symbolic-ref", "--quiet", "--short", "HEAD"], gdir)
        return out.strip() if rc == 0 and out.strip() else None

    def previous_branch(self, repo: Repo, gdir: str, extra: Tuple[str, ...], n: int = 1) -> Any:
        """The branch `git switch -` (`@{-n}`) goes to: a name, None (detached), _NO_BRANCH, or _UNKNOWN."""
        if repo.top in self.switched:
            if n != 1:
                return _UNKNOWN
            return self.switched[repo.top][1]
        rc, out, _ = self._git(extra, ["rev-parse", "--symbolic-full-name", "@{-%d}" % n], gdir)
        if rc != 0:
            return _NO_BRANCH
        ref = out.strip()
        return ref[len("refs/heads/"):] if ref.startswith("refs/heads/") else None

    def set_branch(self, repo: Repo, gdir: str, extra: Tuple[str, ...], new: Any) -> None:
        self.switched[repo.top] = (new, self.branch(repo, gdir, extra))

    def unknown_branch(self, repo: Repo) -> None:
        """A switch the guard cannot resolve: use the real current branch from now on."""
        self.switched[repo.top] = (_REAL, _UNKNOWN)

    def branch_exists(self, repo: Repo, gdir: str, extra: Tuple[str, ...], name: str) -> bool:
        return name in self.created.get(repo.top, set()) or self.ref_exists(gdir, extra, "refs/heads/%s" % name)

    def config_value(self, gdir: str, extra: Tuple[str, ...], key: str) -> Optional[str]:
        rc, out, _ = self._git(extra, ["config", "--get", key], gdir)
        return out.strip() if rc == 0 and out.strip() else None

    def has_commits(self, gdir: str, extra: Tuple[str, ...]) -> bool:
        rc, _, _ = self._git(extra, ["rev-parse", "--verify", "--quiet", "HEAD^{commit}"], gdir)
        return rc == 0

    def is_commit(self, gdir: str, extra: Tuple[str, ...], name: str) -> bool:
        rc, _, _ = self._git(extra, ["rev-parse", "--verify", "--quiet", "%s^{commit}" % name], gdir)
        return rc == 0

    def alias(self, gdir: str, extra: Tuple[str, ...], name: str) -> Optional[str]:
        """The raw value of `alias.<name>`, or None."""
        rc, out, _ = self._git(extra, ["config", "--get", "alias.%s" % name], gdir)
        value = out.strip()
        if rc != 0 or not value:
            return None
        return value

    def first_push_of_main(self, gdir: str, extra: Tuple[str, ...], main: str, args: List[str]) -> bool:
        """Bootstrap exception (section 9.1), checked locally without network access.

        True only for a plain first push of the main branch to origin:
        - the real current HEAD (not a switch earlier in the command) is main;
        - the push has no flags other than -u/--set-upstream, -q, -v and no
          refspec other than <main>, HEAD, HEAD:<main>, <main>:<main>,
          refs/heads/<main>;
        - the remote is origin, refs/remotes/origin/<main> does not exist,
          and the main branch has exactly one commit.
        """
        if self.real_branch(gdir, extra) != main:
            return False
        positionals: List[str] = []
        for a in args:
            if a in _PLAIN_PUSH_FLAGS:
                continue
            if a.startswith("-"):
                return False  # force, --all, --mirror, --delete, --, option clusters, ...
            positionals.append(a)
        if positionals:
            remote = positionals[0]
        else:
            remote = (self.config_value(gdir, extra, "branch.%s.pushRemote" % main)
                      or self.config_value(gdir, extra, "remote.pushDefault")
                      or self.config_value(gdir, extra, "branch.%s.remote" % main)
                      or "origin")
        if remote != "origin":
            return False
        allowed = {main, "HEAD", "HEAD:%s" % main, "%s:%s" % (main, main), "refs/heads/%s" % main}
        if any(spec not in allowed for spec in positionals[1:]):
            return False
        if self.ref_exists(gdir, extra, "refs/remotes/origin/%s" % main):
            return False
        rc, out, _ = self._git(extra, ["rev-list", "--count", "refs/heads/%s" % main], gdir)
        return rc == 0 and out.strip() == "1"

    def ref_exists(self, gdir: str, extra: Tuple[str, ...], ref: str) -> bool:
        rc, _, _ = self._git(extra, ["show-ref", "--verify", "--quiet", ref], gdir)
        return rc == 0

    def remote_branch_exists(self, gdir: str, extra: Tuple[str, ...], name: str) -> bool:
        """True when some refs/remotes/<remote>/<name> exists (checkout DWIM)."""
        rc, out, _ = self._git(extra, ["for-each-ref", "--format=%(refname)", "refs/remotes/"], gdir)
        if rc != 0:
            return False
        for ref in out.splitlines():
            parts = ref.strip().split("/", 3)  # refs, remotes, <remote>, <branch>
            if len(parts) == 4 and parts[3] == name:
                return True
        return False

    # -- command analysis --------------------------------------------------

    def check(self, command: str, cwd: Optional[Cwd] = None, depth: int = 0) -> Optional[str]:
        """Return a deny reason for the command, or None to allow it."""
        if cwd is None:
            cwd = Cwd(self.start_cwd)
        if depth > MAX_DEPTH:
            return self._check_unparsable(command)
        script = loomhook.parse_script(command)
        if script is None:
            return self._check_unparsable(command)
        return self._run_script(script, cwd, depth)

    def _state(self) -> Tuple[Dict[str, Any], Dict[str, Set[str]]]:
        return dict(self.switched), {top: set(names) for top, names in self.created.items()}

    def _restore(self, state: Tuple[Dict[str, Any], Dict[str, Set[str]]]) -> None:
        self.switched, self.created = dict(state[0]), {top: set(n) for top, n in state[1].items()}

    def _run_script(self, script: List[List[Any]], cwd: Cwd, depth: int) -> Optional[str]:
        # Branch state before each pipeline of the current `&&`/`||` list.
        chain: List[Tuple[Dict[str, Any], Dict[str, Set[str]]]] = []
        for pipeline in script:
            op = getattr(pipeline, "op", None)
            if op not in ("&&", "||"):
                chain = []
            before = self._state()
            if op == "||" and chain:
                # `a && b || c`: c runs only when a or b failed, so with the branch
                # state from before the command that failed (each case is checked).
                for state in chain:
                    self._restore(state)
                    reason = self._run_pipeline(pipeline, cwd.copy(), depth)
                    if reason:
                        return reason
                self._restore(before)  # later commands: the earlier ones succeeded
                chain.append(before)
                continue
            chain.append(before)
            reason = self._run_pipeline(pipeline, cwd, depth)
            if reason:
                return reason
        return None

    def _run_pipeline(self, pipeline: List[Any], cwd: Cwd, depth: int) -> Optional[str]:
        # Each stage of a real pipeline runs in a subshell: a `cd` there stays there.
        multi = len(pipeline) > 1
        prev = None
        for stage in pipeline:
            here = cwd.copy() if multi else cwd
            if isinstance(stage, loomhook.Group):
                reason = self._run_script(stage.script, cwd.copy() if stage.subshell else here, depth)
            else:
                reason = self._run_command(stage, here, depth, prev)
            if reason:
                return reason
            prev = stage
        return None

    def _run_command(self, cmd: Any, cwd: Cwd, depth: int, prev: Any) -> Optional[str]:
        # The shell runs substitutions first, each in a subshell.
        for body in cmd.subs:
            reason = self.check(body, cwd.copy(), depth + 1)
            if reason:
                return reason
        prefixes = loomhook.command_prefixes(cmd.words)
        words = prefixes.words
        if not words:
            return None
        name = os.path.basename(words[0])
        if name in ("cd", "pushd", "popd"):
            self._chdir(cwd, name, words[1:])
            return None
        if name == "export":
            self._export(cwd, words[1:])
            return None
        kind, script = loomhook.shell_invocation(words)
        if kind == "stdin":
            script = cmd.stdin if cmd.stdin is not None else loomhook.piped_script(prev)
        if kind and script is not None:
            return self.check(script, cwd if name == "eval" else cwd.copy(), depth + 1)
        if name == "git":
            env = dict(cwd.env)
            env.update(prefixes.env)
            here = cwd
            if prefixes.chdir is not None:
                here = cwd.copy()
                here.path = self._resolve_dir(cwd.path, prefixes.chdir)
            return self._check_git(words[1:], here, depth, env)
        return None

    @staticmethod
    def _export(cwd: Cwd, args: List[str]) -> None:
        """Track `export GIT_DIR=…` and the like: git sees them in the rest of the command."""
        for arg in args:
            name, eq, value = arg.partition("=")
            if eq and (name in _GIT_ENV_PATHS or name in _GIT_ENV_CONFIG):
                cwd.env[name] = value

    def _check_unparsable(self, command: str) -> Optional[str]:
        """Conservative fallback for a command the parser cannot read.

        On the main branch (as tracked, or as git reports it), any `git ...
        commit|push` in the text is treated as real. From any branch, a `git
        ... push` followed in its command by a refspec-like word that names
        the main branch (`main`, `HEAD:main`, `:main`, `+main`,
        `refs/heads/main`) is denied. The text scan comes first and is linear;
        git runs only when the text has a match.
        """
        matches = _fallback_matches(command)
        first = next(matches, None)
        if first is None:
            return None
        start = self.start_cwd
        repo = self.repo(start, ())
        if repo.top is None:
            return None
        main = repo.main_branch
        on_main = main in (self.branch(repo, start, ()), self.real_branch(start, ()))
        for sub, rest in itertools.chain([first], matches):
            if on_main and (sub == "push" or self.has_commits(start, ())):
                return "git %s on the main branch '%s' is blocked (command could not be parsed). %s" % (
                    sub, main, REASON)
            if sub == "push":
                target = _fallback_push_target(rest, main)
                if target:
                    return "git push to the main branch '%s' (%s) is blocked (command could not be parsed). %s" % (
                        main, target, REASON)
        return None

    def _resolve_dir(self, base: str, target: str) -> str:
        """An existing directory, or the original cwd when it cannot be known."""
        if loomhook.is_dynamic(target):
            return self.start_cwd
        path = os.path.normpath(os.path.join(base, os.path.expanduser(target)))
        return path if os.path.isdir(path) else self.start_cwd

    def _chdir(self, cwd: Cwd, name: str, args: List[str]) -> None:
        start = self.start_cwd
        if name == "popd":
            if [a for a in args if a != "-n"] or not cwd.stack:
                cwd.old, cwd.path, cwd.stack = cwd.path, start, []  # `popd +N`, or a stack from before
            elif "-n" in args:
                cwd.stack.pop()
            else:
                cwd.old, cwd.path = cwd.path, cwd.stack.pop()
            return
        args = [a for a in args if a not in ("-L", "-P", "-e", "-@", "--")]
        if name == "pushd":
            if "-n" in args:
                return  # only changes the stack
            if not args:
                if cwd.stack:
                    cwd.old, cwd.path, cwd.stack[-1] = cwd.path, cwd.stack[-1], cwd.path
                else:
                    cwd.old, cwd.path = cwd.path, start
                return
            if args[0][:1] in "+-" and args[0][1:].isdigit():
                cwd.old, cwd.path, cwd.stack = cwd.path, start, []  # stack rotation
                return
            cwd.stack.append(cwd.path)
            cwd.old, cwd.path = cwd.path, self._resolve_dir(cwd.path, args[0])
            return
        if not args:
            target = os.path.expanduser("~")
        elif args[0] == "-":
            target = cwd.old if cwd.old is not None else start
        else:
            target = self._resolve_dir(cwd.path, args[0])
        cwd.old, cwd.path = cwd.path, target

    def _check_git(self, args: List[str], cwd: Cwd, depth: int = 0,
                   env: Optional[Dict[str, str]] = None) -> Optional[str]:
        gdir = cwd.path
        extra: List[str] = []
        env = env or {}
        for var, opt in _GIT_ENV_PATHS.items():
            if var in env:
                if loomhook.is_dynamic(env[var]) or not env[var]:
                    gdir, extra = self.start_cwd, []
                    break
                extra.append("%s=%s" % (opt, os.path.join(gdir, env[var])))
        # Aliases from `-c alias.<name>=<value>`; _ALIAS_UNKNOWN when they cannot be known.
        cli_aliases: Dict[str, str] = {}
        unknown_aliases = any(var in env for var in _GIT_ENV_CONFIG)
        i = 0
        while i < len(args):
            a = args[i]
            if a == "-c" and i + 1 < len(args):
                key, eq, value = args[i + 1].partition("=")
                if key.lower().startswith("alias."):
                    name = key[len("alias."):].lower()
                    cli_aliases[name] = value if eq and not loomhook.is_dynamic(args[i + 1]) else _ALIAS_UNKNOWN
                elif loomhook.is_dynamic(key) or key.lower().startswith("include"):
                    unknown_aliases = True
                i += 2
            elif a == "--config-env" or a.startswith("--config-env="):
                spec = a[len("--config-env="):] if "=" in a else (args[i + 1] if i + 1 < len(args) else "")
                key = spec.partition("=")[0]
                if key.lower().startswith("alias."):
                    cli_aliases[key[len("alias."):].lower()] = _ALIAS_UNKNOWN
                elif loomhook.is_dynamic(key) or key.lower().startswith("include"):
                    unknown_aliases = True
                i += 1 if "=" in a else 2
            elif a == "-C" and i + 1 < len(args):
                path = args[i + 1]
                if path:
                    gdir = self._resolve_dir(gdir, path)
                i += 2
            elif a in _GIT_PATH_OPTS and i + 1 < len(args):
                if loomhook.is_dynamic(args[i + 1]):
                    gdir, extra = self.start_cwd, []
                else:
                    extra.append("%s=%s" % (a, os.path.join(gdir, args[i + 1])))
                i += 2
            elif any(a.startswith(o + "=") for o in _GIT_PATH_OPTS):
                opt, _, value = a.partition("=")
                if loomhook.is_dynamic(value):
                    gdir, extra = self.start_cwd, []
                else:
                    extra.append("%s=%s" % (opt, os.path.join(gdir, value)))
                i += 1
            elif a in _GIT_ARG_OPTS:
                i += 2
            elif a.startswith("-"):
                i += 1
            else:
                break
        if i >= len(args):
            return None
        sub, sub_args = args[i], args[i + 1:]
        key = tuple(extra)
        repo = self.repo(gdir, key)
        if repo.top is None:
            return None  # not a git repository with loom.json
        for _ in range(5):  # git expands aliases of aliases
            if sub in _BUILTINS:
                break
            value = cli_aliases.get(sub.lower()) if sub.lower() in cli_aliases else self.alias(gdir, key, sub)
            if value == _ALIAS_UNKNOWN or (not value and unknown_aliases) or (value and loomhook.is_dynamic(value)):
                # An alias the guard cannot read: it may be commit or push.
                return (self._decide(repo, gdir, key, "commit", sub_args)
                        or self._decide(repo, gdir, key, "push", sub_args))
            if not value:
                break
            if value.startswith("!"):
                # Shell alias: git runs it at the top level with the arguments appended.
                script = " ".join([value[1:]] + [shlex.quote(a) for a in sub_args])
                return self.check(script, Cwd(repo.top), depth + 1)
            try:
                expansion = shlex.split(value)
            except ValueError:
                expansion = []
            if not expansion:
                break
            sub, sub_args = expansion[0], expansion[1:] + sub_args
        if sub in ("switch", "checkout"):
            self._track_switch(repo, gdir, key, sub, sub_args)
            return None
        if sub == "symbolic-ref":
            self._track_symbolic_ref(repo, gdir, key, sub_args)
            return None
        if sub == "branch":
            self._track_branch(repo, gdir, key, sub_args)
            return None
        if sub not in ("commit", "push"):
            return None
        return self._decide(repo, gdir, key, sub, sub_args)

    def _decide(self, repo: Repo, gdir: str, key: Tuple[str, ...], sub: str, sub_args: List[str]) -> Optional[str]:
        """The deny reason for `git commit|push <sub_args>`, or None."""
        main = repo.main_branch
        branch = self.branch(repo, gdir, key)
        if sub == "commit":
            if branch == main and self.has_commits(gdir, key):
                return "git commit on the main branch '%s' is blocked. %s" % (main, REASON)
            return None
        push = _parse_push(sub_args)
        if push["dry_run"]:
            return None  # a dry run updates nothing
        if branch == main and self.first_push_of_main(gdir, key, main, sub_args):
            return None  # empty-repository bootstrap (section 9.1)
        target = push["all"] or next((s for s in push["specs"] if _refspec_targets_main(s, main, branch)), None)
        if target:
            return "git push to the main branch '%s' (%s) is blocked. %s" % (main, target, REASON)
        if branch != main:
            return None
        # On the main branch: allowed only when the push cannot update it.
        unresolved = next((s for s in push["specs"] if loomhook.is_dynamic(s)), None)
        if unresolved:
            return PUSH_OF_MAIN % (main, "the refspec `%s` cannot be resolved before it runs" % unresolved, REASON)
        if not push["specs"] and not push["tags"]:
            return PUSH_OF_MAIN % (main, "without a refspec it pushes the current branch", REASON)
        return None

    # -- branch switches earlier in the command -----------------------------

    def _switch_to(self, repo: Repo, gdir: str, extra: Tuple[str, ...], sub: str, target: Any) -> None:
        """Record a switch to a previous branch (a name, None, or a marker)."""
        if target is _UNKNOWN:
            self.unknown_branch(repo)
        elif target is _NO_BRANCH or (target is None and sub == "switch"):
            return  # git fails: no previous branch, or `switch` to a detached HEAD without --detach
        else:
            self.set_branch(repo, gdir, extra, target)

    def _track_switch(self, repo: Repo, gdir: str, extra: Tuple[str, ...], sub: str, args: List[str]) -> None:
        """Record the branch that `git switch|checkout ...` moves to."""
        create: Optional[str] = None
        force = False
        track = detach = False
        guess = True
        positionals: List[str] = []
        after_dashdash: Optional[List[str]] = None
        i = 0
        while i < len(args):
            a = args[i]
            if a == "--":
                after_dashdash = args[i + 1:]
                break
            if a in _CREATE_OPTS:
                if i + 1 >= len(args):
                    return  # git fails: the option needs a value
                create, force = args[i + 1], a in _FORCE_CREATE_OPTS
                i += 2
                continue
            sticky = next((o for o in ("--create=", "--force-create=", "--orphan=") if a.startswith(o)), None)
            if sticky:
                create, force = a[len(sticky):], sticky == "--force-create="
                i += 1
                continue
            if a == "-":
                positionals.append(a)
            elif len(a) > 1 and a[0] == "-" and a[1] != "-":
                # A short option cluster: `-q`, `-b<name>`, `-qb <name>`.
                flags = a[1:]
                for k, flag in enumerate(flags):
                    if flag in "cCbB":
                        value = flags[k + 1:]
                        if not value:
                            if i + 1 >= len(args):
                                return
                            i += 1
                            value = args[i]
                        create, force = value, flag in "CB"
                        break
                    if flag == "t":
                        track = True
                    elif flag == "d":
                        detach = True
            elif a == "--track" or a.startswith("--track="):
                track = True
            elif a == "--detach":
                detach = True
            elif a == "--no-guess":
                guess = False
            elif a == "--guess":
                guess = True
            elif not a.startswith("-"):
                positionals.append(a)
            i += 1
        if after_dashdash is not None:
            if sub == "checkout" and after_dashdash and create is None:
                return  # `checkout <tree-ish> -- <paths>`: the branch does not change
            if sub == "switch":
                positionals.extend(after_dashdash)
        if create is not None:
            if loomhook.is_dynamic(create):
                self.unknown_branch(repo)
            elif force or not self.branch_exists(repo, gdir, extra, create):
                self.set_branch(repo, gdir, extra, create)
                self.created.setdefault(repo.top, set()).add(create)
            # else: git refuses to create an existing branch; the branch does not change
            return
        if sub == "checkout" and len(positionals) > 1:
            return  # `checkout <tree-ish> <paths>`
        if detach and not positionals:
            self.set_branch(repo, gdir, extra, None)  # `--detach`: detached at HEAD
            return
        if len(positionals) != 1:
            return
        name = positionals[0]
        if loomhook.is_dynamic(name):
            self.unknown_branch(repo)
            return
        prev = re.fullmatch(r"@\{-(\d+)\}", name)
        if name == "-" or prev:
            target = self.previous_branch(repo, gdir, extra, int(prev.group(1)) if prev else 1)
            if detach and target is not _UNKNOWN and target is not _NO_BRANCH:
                target = None
            self._switch_to(repo, gdir, extra, "checkout" if detach else sub, target)
            return
        if detach:
            self.set_branch(repo, gdir, extra, None)
            return
        if track:
            # `--track origin/main` creates the local branch `main`; git refuses when it exists.
            local = name[len("refs/remotes/"):] if name.startswith("refs/remotes/") else name
            local = local.split("/", 1)[1] if "/" in local else local
            if not self.branch_exists(repo, gdir, extra, local):
                self.set_branch(repo, gdir, extra, local)
                self.created.setdefault(repo.top, set()).add(local)
            return
        if self.branch_exists(repo, gdir, extra, name):
            self.set_branch(repo, gdir, extra, name)
            return
        if guess and self.remote_branch_exists(gdir, extra, name):
            self.set_branch(repo, gdir, extra, name)  # DWIM: git creates the local branch
            self.created.setdefault(repo.top, set()).add(name)
            return
        if sub == "checkout" and self.is_commit(gdir, extra, name):
            self.set_branch(repo, gdir, extra, None)  # detached HEAD at a commit
        # Otherwise a file, or a name git cannot switch to: the branch does not change.

    def _track_symbolic_ref(self, repo: Repo, gdir: str, extra: Tuple[str, ...], args: List[str]) -> None:
        """`git symbolic-ref HEAD refs/heads/<x>` switches to <x> without a checkout."""
        positionals: List[str] = []
        i = 0
        while i < len(args):
            a = args[i]
            if a in ("-d", "--delete"):
                return
            if a == "-m":
                i += 2
                continue
            if a == "--":
                positionals.extend(args[i + 1:])
                break
            if not a.startswith("-"):
                positionals.append(a)
            i += 1
        if len(positionals) != 2 or positionals[0] != "HEAD":
            return
        ref = positionals[1]
        if loomhook.is_dynamic(ref):
            self.unknown_branch(repo)
        elif ref.startswith("refs/heads/"):
            self.set_branch(repo, gdir, extra, ref[len("refs/heads/"):])
        else:
            self.set_branch(repo, gdir, extra, None)

    def _track_branch(self, repo: Repo, gdir: str, extra: Tuple[str, ...], args: List[str]) -> None:
        """`git branch -m [<old>] <new>` renames; `git branch <name>` creates."""
        positionals = [a for a in args if not a.startswith("-")]
        options = [a for a in args if a.startswith("-")]
        if any(o in ("-m", "-M", "--move") for o in options):
            if any(loomhook.is_dynamic(p) for p in positionals):
                self.unknown_branch(repo)
                return
            current = self.branch(repo, gdir, extra)
            if len(positionals) == 1 and current is not None:
                self.set_branch(repo, gdir, extra, positionals[0])
            elif len(positionals) == 2 and positionals[0] == current:
                self.set_branch(repo, gdir, extra, positionals[1])
            return
        if positionals and all(o in ("-f", "--force", "-t", "--track", "--no-track", "-q", "--quiet")
                               for o in options) and not loomhook.is_dynamic(positionals[0]):
            self.created.setdefault(repo.top, set()).add(positionals[0])


def _fallback_matches(command: str) -> Iterator[Tuple[str, List[str]]]:
    """Every `git ... commit|push` in the text: (subcommand, up to _FALLBACK_WINDOW words after it).

    Linear in the text: each command (a line split at `;`, `&`, `|`) is split
    into words once, `commit`/`push` must follow `git` within
    _FALLBACK_WINDOW words, and the matches come lazily.
    """
    if "commit" not in command and "push" not in command:
        return
    for segment in _FALLBACK_SEGMENT_RE.split(command):
        if "git" not in segment:
            continue
        words = segment.split()
        next_sub = [len(words)] * (len(words) + 1)  # index of the next commit|push word
        for i in range(len(words) - 1, -1, -1):
            next_sub[i] = i if _FALLBACK_SUB_RE.match(words[i]) else next_sub[i + 1]
        for i, word in enumerate(words):
            if word.endswith("git") and _FALLBACK_GIT_RE.search(word):
                j = next_sub[i + 1]
                if j < len(words) and j - i <= _FALLBACK_WINDOW:
                    sub = _FALLBACK_SUB_RE.match(words[j]).group(1)
                    yield sub, words[j + 1:j + 1 + _FALLBACK_WINDOW]


def _fallback_push_target(rest: List[str], main: str) -> Optional[str]:
    """A refspec-like word after `git push` that names the main branch."""
    for word in _FALLBACK_WORD_RE.findall(" ".join(rest)):
        word = word.strip("'\"")
        if not word or word.startswith("-"):
            continue
        spec = word.lstrip("+")
        dst = spec.split(":", 1)[1] if ":" in spec else spec
        if dst in (main, "refs/heads/%s" % main, "heads/%s" % main):
            return word
    return None


def _refspec_targets_main(spec: str, main: str, branch: Optional[str]) -> bool:
    if spec.startswith("+"):
        spec = spec[1:]
    if spec == ":":
        return True  # the matching refspec pushes every branch both sides have
    if ":" in spec:
        src, dst = spec.split(":", 1)
        if not dst:
            dst = src
    else:
        dst = spec
    if dst in ("HEAD", "@"):
        dst = branch or ""
    if not dst:
        return False
    candidates = (main, "refs/heads/%s" % main, "heads/%s" % main)
    if any(ch in dst for ch in "*?["):
        return any(fnmatch.fnmatchcase(c, dst) for c in candidates)
    return dst in candidates


def _parse_push(args: List[str]) -> Dict[str, Any]:
    """The parts of `git push` arguments the guard needs.

    specs: the refspecs other than `tag <name>`; all: `--all`, `--mirror`, or
    `--branches`; dry_run; tags: `--tags` or `tag <name>` (with no other
    refspec, only tags are pushed).
    """
    positionals: List[str] = []
    result: Dict[str, Any] = {"specs": [], "all": None, "dry_run": False, "tags": False}
    repo_option = False
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--":
            positionals.extend(args[i + 1:])
            break
        if a in _PUSH_ARG_OPTS:
            repo_option = repo_option or a == "--repo"
            i += 2
            continue
        if a.startswith("--repo="):
            repo_option = True
        elif a in ("--all", "--mirror", "--branches"):
            result["all"] = a
        elif a == "--dry-run":
            result["dry_run"] = True
        elif a == "--tags":
            result["tags"] = True
        elif len(a) > 1 and a[0] == "-" and a[1] != "-":
            if "n" in a[1:]:
                result["dry_run"] = True
            if a[1:].endswith("o"):
                i += 1  # `-o <option>` at the end of a cluster
        elif not a.startswith("-"):
            positionals.append(a)
        i += 1
    # With --repo every positional is a refspec; otherwise the first is the repository.
    specs = positionals if repo_option else positionals[1:]
    i = 0
    while i < len(specs):
        if specs[i] == "tag":
            result["tags"] = True
            i += 2  # `tag <name>` pushes refs/tags/<name>
            continue
        result["specs"].append(specs[i])
        i += 1
    return result


def main() -> None:
    data = loomhook.read_input()
    command = loomhook.bash_command(data)
    if "git" not in command:
        return
    cwd = loomhook.hook_cwd(data)
    reason = Guard(cwd).check(command, Cwd(cwd))
    if reason:
        loomhook.deny(reason)


if __name__ == "__main__":
    try:
        sys.path.insert(0, HERE)
        import loomhook  # noqa: E402
    except Exception as exc:  # a broken install must not break the session
        sys.stderr.write("loom guard-main hook: skipped, cannot load helpers: %s\n" % exc)
        sys.exit(0)
    loomhook.run_safely(main, "guard-main")

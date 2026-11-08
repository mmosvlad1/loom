#!/usr/bin/env python3
"""PreToolUse (Bash) hook: guard the main branch (LOOM_SPEC.md section 11.2).

Denies:
- `git commit` and `git push` while the current branch is the configured main
  branch, except the very first commit of a repository without commits, and
  the first push of main (no refs/remotes/origin/<main>, exactly one commit);
- any `git push` whose refspec targets the main branch, from any branch
  (`origin main`, `HEAD:main`, `+main`, `:main`, `--force ... main`, `--all`,
  `--mirror`).

Understands compound commands (`&&`, `||`, `;`, `|`, subshells), `cd <dir>`
before git, `git -C <path>`, global git options, git aliases, `bash -c`, and
branch switches earlier in the same command. Text inside quotes is not read as
a command. A silent no-op outside a git repository and in repositories without
.claude/loom.json.
"""
from __future__ import annotations

import fnmatch
import os
import re
import shlex
import sys
from typing import Dict, List, Optional, Tuple

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))

REASON = "Create a task branch with /loom:start-task"

# Global git options that take a separate argument.
_GIT_ARG_OPTS = {"-c", "--namespace", "--super-prefix", "--config-env", "--list-cmds"}
_GIT_PATH_OPTS = {"--git-dir", "--work-tree"}

# Built-in subcommands: git never lets an alias override them, so no alias lookup.
_BUILTINS = {
    "add", "am", "apply", "bisect", "blame", "branch", "cat-file", "checkout",
    "cherry-pick", "clean", "clone", "commit", "config", "describe", "diff",
    "fetch", "for-each-ref", "format-patch", "grep", "help", "init", "log",
    "ls-files", "ls-remote", "ls-tree", "merge", "merge-base", "mv", "notes",
    "pull", "push", "rebase", "reflog", "remote", "reset", "restore", "rev-list",
    "rev-parse", "revert", "rm", "shortlog", "show", "show-ref", "stash",
    "status", "submodule", "switch", "symbolic-ref", "tag", "version",
    "worktree",
}

_PUSH_ARG_OPTS = {"-o", "--push-option", "--repo", "--receive-pack", "--exec"}
_PLAIN_PUSH_FLAGS = {"-u", "--set-upstream", "-q", "--quiet", "-v", "--verbose"}
_CREATE_OPTS = {"-c", "-C", "-b", "-B", "--create", "--force-create", "--orphan"}

# Fallback for commands shlex cannot parse.
_GIT_COMMIT_PUSH_RE = re.compile(r"(?:^|[\s;&|(`$])git(?:\s+[^\s;&|]+)*?\s+(commit|push)\b")


class Repo:
    """loom context of one repository (None fields when loom does not apply)."""

    def __init__(self, top: Optional[str], main_branch: Optional[str]):
        self.top = top
        self.main_branch = main_branch


class Guard:
    def __init__(self, cwd: str):
        self.ls = loomhook.loom_state()
        self.start_cwd = cwd
        self._repos: Dict[Tuple[str, Tuple[str, ...]], Repo] = {}
        # Branch switches seen earlier in the same command, per repo top-level.
        self.branch_override: Dict[str, Optional[str]] = {}

    # -- repository context ----------------------------------------------

    def repo(self, gdir: str, extra: Tuple[str, ...]) -> Repo:
        key = (gdir, extra)
        if key not in self._repos:
            top = None
            main_branch = None
            if os.path.isdir(gdir):
                rc, out, _ = self.ls.git(list(extra) + ["rev-parse", "--show-toplevel"], gdir)
                if rc == 0 and out.strip():
                    candidate = out.strip()
                    cfg, _ = self.ls.load_config(candidate)
                    if cfg is not None:
                        top, main_branch = candidate, cfg["mainBranch"]
            self._repos[key] = Repo(top, main_branch)
        return self._repos[key]

    def branch(self, repo: Repo, gdir: str, extra: Tuple[str, ...]) -> Optional[str]:
        """Branch after the switches seen earlier in this command."""
        if repo.top in self.branch_override:
            return self.branch_override[repo.top]
        return self.real_branch(gdir, extra)

    def real_branch(self, gdir: str, extra: Tuple[str, ...]) -> Optional[str]:
        """The current branch as git reports it now (ignores earlier switches)."""
        rc, out, _ = self.ls.git(list(extra) + ["symbolic-ref", "--quiet", "--short", "HEAD"], gdir)
        return out.strip() if rc == 0 and out.strip() else None

    def config_value(self, gdir: str, extra: Tuple[str, ...], key: str) -> Optional[str]:
        rc, out, _ = self.ls.git(list(extra) + ["config", "--get", key], gdir)
        return out.strip() if rc == 0 and out.strip() else None

    def has_commits(self, gdir: str, extra: Tuple[str, ...]) -> bool:
        rc, _, _ = self.ls.git(list(extra) + ["rev-parse", "--verify", "--quiet", "HEAD^{commit}"], gdir)
        return rc == 0

    def alias(self, gdir: str, extra: Tuple[str, ...], name: str) -> Optional[str]:
        """The raw value of `alias.<name>`, or None."""
        rc, out, _ = self.ls.git(list(extra) + ["config", "--get", "alias.%s" % name], gdir)
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
        rc, out, _ = self.ls.git(list(extra) + ["rev-list", "--count", "refs/heads/%s" % main], gdir)
        return rc == 0 and out.strip() == "1"

    def ref_exists(self, gdir: str, extra: Tuple[str, ...], ref: str) -> bool:
        rc, _, _ = self.ls.git(list(extra) + ["show-ref", "--verify", "--quiet", ref], gdir)
        return rc == 0

    def remote_branch_exists(self, gdir: str, extra: Tuple[str, ...], name: str) -> bool:
        """True when some refs/remotes/<remote>/<name> exists (checkout DWIM)."""
        rc, out, _ = self.ls.git(list(extra) + ["for-each-ref", "--format=%(refname)", "refs/remotes/"], gdir)
        if rc != 0:
            return False
        for ref in out.splitlines():
            parts = ref.strip().split("/", 3)  # refs, remotes, <remote>, <branch>
            if len(parts) == 4 and parts[3] == name:
                return True
        return False

    # -- command analysis --------------------------------------------------

    def check(self, command: str, cwd: str, depth: int = 0) -> Optional[str]:
        """Return a deny reason for the command, or None to allow it."""
        pipelines = loomhook.parse_pipelines(command)
        if pipelines is None:
            return self._check_unparsable(command, cwd)
        if not pipelines:
            return None
        for stages in pipelines:
            for raw_words in stages:
                words = loomhook.strip_prefixes(raw_words)
                if not words:
                    continue
                name = os.path.basename(words[0])
                if name in ("cd", "pushd"):
                    cwd = self._cd(cwd, words[1:])
                    continue
                nested = loomhook.nested_shell_command(words)
                if nested is not None and depth < 3:
                    reason = self.check(nested, cwd, depth + 1)
                    if reason:
                        return reason
                    continue
                if name == "git":
                    reason = self._check_git(words[1:], cwd, depth)
                    if reason:
                        return reason
        return None

    def _check_unparsable(self, command: str, cwd: str) -> Optional[str]:
        """Conservative fallback when shlex cannot parse the command.

        Any `git ... commit|push` in the text is treated as real while the
        current branch of cwd's repository is the main branch.
        """
        match = _GIT_COMMIT_PUSH_RE.search(command)
        if not match:
            return None
        repo = self.repo(cwd, ())
        if repo.top is None:
            return None
        sub = match.group(1)
        if self.branch(repo, cwd, ()) != repo.main_branch:
            return None
        if sub == "commit" and not self.has_commits(cwd, ()):
            return None
        return "git %s on the main branch '%s' is blocked (command could not be parsed). %s" % (
            sub, repo.main_branch, REASON)

    @staticmethod
    def _cd(cwd: str, args: List[str]) -> str:
        args = [a for a in args if a not in ("-L", "-P", "--")]
        if not args:
            return os.path.expanduser("~")
        target = args[0]
        if target == "-":
            return cwd
        target = os.path.expanduser(os.path.expandvars(target))
        return os.path.normpath(os.path.join(cwd, target))

    def _check_git(self, args: List[str], cwd: str, depth: int = 0) -> Optional[str]:
        gdir = cwd
        extra: List[str] = []
        i = 0
        while i < len(args):
            a = args[i]
            if a == "-C" and i + 1 < len(args):
                path = os.path.expanduser(os.path.expandvars(args[i + 1]))
                gdir = os.path.normpath(os.path.join(gdir, path)) if path else gdir
                i += 2
            elif a in _GIT_PATH_OPTS and i + 1 < len(args):
                extra.append("%s=%s" % (a, os.path.join(gdir, args[i + 1])))
                i += 2
            elif any(a.startswith(o + "=") for o in _GIT_PATH_OPTS):
                opt, _, value = a.partition("=")
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
        if sub not in _BUILTINS:
            value = self.alias(gdir, key, sub)
            if value and value.startswith("!"):
                # Shell alias: git runs it with the arguments appended.
                if depth >= 3:
                    return None
                script = " ".join([value[1:]] + [shlex.quote(a) for a in sub_args])
                return self.check(script, repo.top, depth + 1)
            if value:
                try:
                    expansion = shlex.split(value)
                except ValueError:
                    expansion = []
                if expansion:
                    sub, sub_args = expansion[0], expansion[1:] + sub_args
        if sub in ("switch", "checkout"):
            self._track_switch(repo, gdir, key, sub, sub_args)
            return None
        if sub not in ("commit", "push"):
            return None

        main = repo.main_branch
        branch = self.branch(repo, gdir, key)
        if sub == "commit":
            if branch == main and self.has_commits(gdir, key):
                return "git commit on the main branch '%s' is blocked. %s" % (main, REASON)
            return None
        if branch == main:
            if self.first_push_of_main(gdir, key, main, sub_args):
                return None  # empty-repository bootstrap (section 9.1)
            return "git push from the main branch '%s' is blocked. %s" % (main, REASON)
        target = _push_targets_main(sub_args, main, branch)
        if target:
            return "git push to the main branch '%s' (%s) is blocked. %s" % (main, target, REASON)
        return None

    def _track_switch(self, repo: Repo, gdir: str, extra: Tuple[str, ...], sub: str, args: List[str]) -> None:
        """Record the branch that `git switch|checkout ...` moves to."""
        create = None
        track = detach = False
        positionals: List[str] = []
        i = 0
        while i < len(args):
            a = args[i]
            if a == "--":
                if sub == "checkout":
                    if create:
                        break  # `checkout -b x -- <start>`
                    return  # pathspec checkout: the branch does not change
                positionals.extend(args[i + 1:])
                break
            if a in _CREATE_OPTS and i + 1 < len(args):
                create = args[i + 1]
                i += 2
                continue
            if a in ("-t", "--track") or a.startswith("--track="):
                track = True
            elif a in ("-d", "--detach"):
                detach = True
            elif not a.startswith("-") or a == "-":
                positionals.append(a)
            i += 1
        if create:
            self.branch_override[repo.top] = create
            return
        if detach:
            self.branch_override[repo.top] = None
            return
        if len(positionals) != 1 or positionals[0] == "-":
            return  # previous branch, or `checkout <tree-ish> <paths>`: keep the current one
        name = positionals[0]
        if track:
            # `--track origin/main` creates the local branch `main`.
            if name.startswith("refs/remotes/"):
                name = name[len("refs/remotes/"):]
            self.branch_override[repo.top] = name.split("/", 1)[1] if "/" in name else name
            return
        if sub == "switch":
            self.branch_override[repo.top] = name
            return
        # `git checkout <name>`: a branch switch only when <name> is a branch,
        # or a remote branch that git creates locally (DWIM). Otherwise it
        # may be a file or a commit: keep the current branch.
        if self.ref_exists(gdir, extra, "refs/heads/%s" % name) or self.remote_branch_exists(gdir, extra, name):
            self.branch_override[repo.top] = name
        elif self.ref_exists(gdir, extra, "refs/remotes/%s" % name):
            self.branch_override[repo.top] = None  # detached at a remote-tracking ref


def _refspec_targets_main(spec: str, main: str, branch: Optional[str]) -> bool:
    if spec.startswith("+"):
        spec = spec[1:]
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


def _push_targets_main(args: List[str], main: str, branch: Optional[str]) -> Optional[str]:
    """Return the offending argument when a push targets the main branch."""
    positionals: List[str] = []
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--":
            positionals.extend(args[i + 1:])
            break
        if a in _PUSH_ARG_OPTS:
            i += 2
            continue
        if a in ("--all", "--mirror", "--branches"):
            return a
        if not a.startswith("-"):
            positionals.append(a)
        i += 1
    specs = positionals[1:]  # positionals[0] is the repository
    i = 0
    while i < len(specs):
        spec = specs[i]
        if spec == "tag":
            i += 2  # `tag <name>` pushes refs/tags/<name>
            continue
        if _refspec_targets_main(spec, main, branch):
            return spec
        i += 1
    return None


def main() -> None:
    data = loomhook.read_input()
    command = loomhook.bash_command(data)
    if "git" not in command:
        return
    cwd = loomhook.hook_cwd(data)
    reason = Guard(cwd).check(command, cwd)
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

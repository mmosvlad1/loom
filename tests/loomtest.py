"""Shared helpers for loom unit tests (standard library only)."""
from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from typing import Any, Dict, Optional

sys.dont_write_bytecode = True

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOOM_STATE = os.path.join(ROOT, "bin", "loom-state")
HOOKS_DIR = os.path.join(ROOT, "scripts", "hooks")

# Isolate git from the developer's global and system config (signing, hooks,
# default branch, aliases).
os.environ.update({
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_AUTHOR_NAME": "loom test",
    "GIT_AUTHOR_EMAIL": "loom@example.com",
    "GIT_COMMITTER_NAME": "loom test",
    "GIT_COMMITTER_EMAIL": "loom@example.com",
    "GIT_TERMINAL_PROMPT": "0",
})

_module = None


def loom_state():
    global _module
    if _module is None:
        loader = importlib.machinery.SourceFileLoader("loom_state_under_test", LOOM_STATE)
        spec = importlib.util.spec_from_loader("loom_state_under_test", loader)
        module = importlib.util.module_from_spec(spec)
        loader.exec_module(module)
        _module = module
    return _module


def dedent(text: str) -> str:
    return textwrap.dedent(text).lstrip("\n")


def write(path: str, text: str) -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(dedent(text))
    return path


def git(cwd: str, *args: str) -> str:
    proc = subprocess.run(
        ["git"] + list(args), cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False
    )
    if proc.returncode != 0:
        raise AssertionError("git %s failed: %s" % (" ".join(args), proc.stderr.decode()))
    return proc.stdout.decode().strip()


def run_loom_state(cwd: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, LOOM_STATE] + list(args),
        cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True,
    )


def run_hook(
    script: str, payload: Optional[Dict[str, Any]], raw: Optional[str] = None, cwd: Optional[str] = None,
    env: Optional[Dict[str, str]] = None,
) -> subprocess.CompletedProcess:
    """Run a hook script the way Claude Code does: JSON on stdin. `env` adds variables."""
    data = raw if raw is not None else json.dumps(payload)
    full_env = dict(os.environ)
    full_env.update(env or {})
    return subprocess.run(
        [sys.executable, os.path.join(HOOKS_DIR, script)],
        input=data, cwd=cwd or tempfile.gettempdir(), env=full_env,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True,
    )


def bash_payload(command: str, cwd: str) -> Dict[str, Any]:
    return {
        "session_id": "test-session",
        "transcript_path": "/tmp/transcript.jsonl",
        "cwd": cwd,
        "permission_mode": "default",
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": command, "description": "test"},
        "tool_use_id": "toolu_test",
    }


def stop_payload(cwd: str, event: str = "Stop", stop_hook_active: bool = False, **extra: Any) -> Dict[str, Any]:
    """Input of a Stop or SubagentStop hook (fields from the Claude Code hooks docs)."""
    payload: Dict[str, Any] = {
        "session_id": "test-session",
        "transcript_path": "/tmp/transcript.jsonl",
        "cwd": cwd,
        "permission_mode": "default",
        "hook_event_name": event,
        "stop_hook_active": stop_hook_active,
        "last_assistant_message": "done",
    }
    payload.update(extra)
    return payload


class RepoTestCase(unittest.TestCase):
    """A temporary git repository on `main` with one commit and loom.json."""

    loom_config: Optional[Dict[str, Any]] = {}
    initial_commit = True

    def setUp(self) -> None:
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="loom-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.repo = os.path.join(self.tmp, "repo")
        os.makedirs(self.repo)
        git(self.repo, "init", "-q", "-b", "main")
        write(os.path.join(self.repo, ".gitignore"), ".loom/\n")
        if self.loom_config is not None:
            self.write_config(self.loom_config)
        if self.initial_commit:
            write(os.path.join(self.repo, "README.md"), "# fixture\n")
            git(self.repo, "add", "-A")
            git(self.repo, "commit", "-q", "-m", "initial")

    def write_config(self, config: Dict[str, Any]) -> None:
        path = os.path.join(self.repo, ".claude", "loom.json")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(config, fh)

    def path(self, *parts: str) -> str:
        return os.path.join(self.repo, *parts)

    def commit_file(self, rel: str, text: str, message: str = "change") -> str:
        write(self.path(rel), text)
        git(self.repo, "add", rel)
        git(self.repo, "commit", "-q", "-m", message)
        return git(self.repo, "rev-parse", "HEAD")

    def task_dir(self, name: str, work_dir: str = ".loom/tasks") -> str:
        path = self.path(work_dir, name)
        os.makedirs(path, exist_ok=True)
        return path

    def ticket(self, task_dir: str, mode: str = "full", issue: int = 42, pr: Optional[int] = None) -> None:
        extra = "pr: %d\n" % pr if pr is not None else ""
        write(os.path.join(task_dir, "00-ticket.md"), (
            "---\ntask: %s\nmode: %s\nissue: %d\nurl: https://github.com/o/r/issues/%d\n%s---\n# Ticket\n"
            % (os.path.basename(task_dir), mode, issue, issue, extra)
        ))

    def artifact(self, task_dir: str, name: str, phase: str, status: str, body: str = "", **fields: str) -> None:
        lines = ["---", "task: %s" % os.path.basename(task_dir), "phase: %s" % phase, "status: %s" % status]
        lines += ["%s: %s" % (k, v) for k, v in fields.items()]
        lines += ["updated: 2026-11-08", "---", ""]
        write(os.path.join(task_dir, name), "\n".join(lines) + dedent(body))

    def state(self, cwd: Optional[str] = None) -> Dict[str, Any]:
        result = loom_state().compute_state(cwd or self.repo)
        self.assertIsNotNone(result)
        return result

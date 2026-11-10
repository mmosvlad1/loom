#!/usr/bin/env python3
"""Status line for loom: prints `loom-state --line` for the current task.

Written by /loom:setup to .claude/loom-statusline.py and run by the `statusLine`
setting in .claude/settings.json. A settings file cannot name the plugin
directory, and the plugin's bin/ is on the PATH of the Bash tool only, so this
script finds the installed loom plugin itself:

1. LOOM_PLUGIN_ROOT, if set (for example while you develop loom with --plugin-dir).
2. installed_plugins.json in the plugins root: the install of loom@loom for this
   project, else any other install of it.
3. known_marketplaces.json: the loom marketplace, whose root is the plugin root.
4. cache/loom/loom/<version>/: the newest version that is not orphaned.

The plugins root is CLAUDE_CODE_PLUGIN_CACHE_DIR, else CLAUDE_CONFIG_DIR/plugins,
else ~/.claude/plugins. On any failure the script prints nothing and exits 0:
the status line is a convenience and must never show an error.
Standard library only; Python 3.9+.
"""
import glob
import json
import os
import subprocess
import sys

PLUGIN_ID = "loom@loom"
MARKETPLACE = "loom"
PLUGIN = "loom"
STATE = os.path.join("bin", "loom-state")
TIMEOUT = 5


def plugins_root():
    explicit = os.environ.get("CLAUDE_CODE_PLUGIN_CACHE_DIR")
    if explicit:
        return os.path.expanduser(explicit)
    config = os.environ.get("CLAUDE_CONFIG_DIR")
    if config:
        return os.path.join(os.path.expanduser(config), "plugins")
    return os.path.join(os.path.expanduser("~"), ".claude", "plugins")


def read_json(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def usable(root):
    """The loom-state path inside a plugin root, or None."""
    if not root or os.path.exists(os.path.join(root, ".orphaned_at")):
        return None
    path = os.path.join(root, STATE)
    return path if os.path.isfile(path) else None


def same_dir(a, b):
    try:
        return os.path.realpath(a) == os.path.realpath(b)
    except (TypeError, ValueError):
        return False


def from_installs(root, project):
    data = read_json(os.path.join(root, "installed_plugins.json"))
    entries = data.get("plugins", {}).get(PLUGIN_ID) if isinstance(data, dict) else None
    if not isinstance(entries, list):
        return None
    entries = [e for e in entries if isinstance(e, dict)]
    # Prefer the install for this project, then the others in file order.
    entries.sort(key=lambda e: 0 if project and same_dir(e.get("projectPath") or "", project) else 1)
    for entry in entries:
        found = usable(entry.get("installPath"))
        if found:
            return found
    return None


def from_marketplace(root):
    data = read_json(os.path.join(root, "known_marketplaces.json"))
    entry = data.get(MARKETPLACE) if isinstance(data, dict) else None
    if not isinstance(entry, dict):
        return None
    return usable(entry.get("installLocation"))


def from_cache(root):
    versions = glob.glob(os.path.join(root, "cache", MARKETPLACE, PLUGIN, "*"))
    found = [usable(v) for v in versions]
    found = [f for f in found if f]
    if not found:
        return None
    return max(found, key=os.path.getmtime)


def find_loom_state(project):
    override = os.environ.get("LOOM_PLUGIN_ROOT")
    if override:
        return usable(os.path.expanduser(override))
    root = plugins_root()
    return from_installs(root, project) or from_marketplace(root) or from_cache(root)


def session_dir():
    """The session's working directory from the status line JSON on stdin."""
    try:
        data = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        data = {}
    workspace = data.get("workspace") if isinstance(data, dict) else None
    current = workspace.get("current_dir") if isinstance(workspace, dict) else None
    current = current or (data.get("cwd") if isinstance(data, dict) else None)
    return current if current and os.path.isdir(current) else os.getcwd()


def main():
    cwd = session_dir()
    state = find_loom_state(cwd)
    if not state:
        return
    proc = subprocess.run(
        [sys.executable, state, "--line"],
        cwd=cwd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        timeout=TIMEOUT,
    )
    if proc.returncode == 0:
        sys.stdout.write(proc.stdout.decode("utf-8", "replace"))


if __name__ == "__main__":
    try:
        main()
    except Exception:  # never show an error in the status line
        pass
    sys.exit(0)

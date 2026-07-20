#!/usr/bin/env python3
"""session-end-breadcrumb.py — Claude Code SessionEnd hook.

Writes one append-only line to the notes home recording that a session
happened here, even if /session-end was never run: timestamp, repo, branch,
and commits made this session (via the marker session-start-context.py left
behind). Pure script, no model involvement — this is a trace, not a
replacement for the real session note /session-end writes.

Breadcrumbs land at <notes-home>/projects/<project>/breadcrumbs.log, kept
deliberately separate from sessions/*.md so a future /session-start does not
mistake a thin auto-line for a real, model-authored session note.

Never blocks session termination: any failure here is swallowed and the hook
exits 0 having written nothing.

Wire-up (opt-in — see bin/install-claude-hooks.sh, never part of the
default installer) — note the ~/.claude/hooks path, a symlink bin/install.sh
maintains, so moving the checkout leaves a dangling link bin/doctor.sh reports
rather than silently disabling the hook (#264, #312):
  "hooks": { "SessionEnd": [ { "hooks": [
    { "type": "command",
      "command": "python3 ~/.claude/hooks/session-end-breadcrumb.py",
      "timeout": 10 } ] } ] }
Spell the path out with $HOME expanded (no leading ~); settings.json is JSON,
so an unexpanded ~ survives only if the shell that runs the command expands
it — do not rely on that (#312).

Self-test: bin/test-session-hooks.sh
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SLUGIFY = REPO_ROOT / "bin" / "slugify.sh"


def run(cmd: list[str], cwd: str | None = None) -> str:
    try:
        return subprocess.run(
            cmd, capture_output=True, text=True, timeout=5, cwd=cwd
        ).stdout.strip()
    except Exception:  # noqa: BLE001
        return ""


def slugify(name: str) -> str:
    if not SLUGIFY.exists():
        return name.lower()
    try:
        result = subprocess.run(
            [str(SLUGIFY), name], capture_output=True, text=True, timeout=5
        )
        return result.stdout.strip() or name.lower()
    except Exception:  # noqa: BLE001
        return name.lower()


def resolve_notes_home(claude_home: Path) -> Path:
    import os

    env_dir = os.environ.get("BINDLE_NOTES_DIR")
    if env_dir:
        return Path(env_dir)
    legacy_dir = os.environ.get("CLAUDE_KIT_NOTES_DIR")
    if legacy_dir:
        return Path(legacy_dir)
    settings = claude_home / "settings.json"
    if settings.exists():
        try:
            data = json.loads(settings.read_text())
            persisted = data.get("env", {}).get("BINDLE_NOTES_DIR")
            if persisted:
                return Path(persisted)
        except Exception:  # noqa: BLE001
            pass
    return Path.home() / ".bindle"


def read_marker(session_id: str) -> dict:
    if not session_id:
        return {}
    marker_path = Path(tempfile.gettempdir()) / f"bindle-session-{session_id}.json"
    try:
        data = json.loads(marker_path.read_text())
    except Exception:  # noqa: BLE001
        return {}
    try:
        marker_path.unlink()
    except OSError:
        pass
    return data


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except Exception:  # noqa: BLE001
        return
    if data.get("hook_event_name") != "SessionEnd":
        return
    cwd = data.get("cwd") or "."
    session_id = data.get("session_id") or ""
    reason = data.get("reason") or "unknown"

    repo_root = run(["git", "-C", cwd, "rev-parse", "--show-toplevel"], cwd=cwd)
    if not repo_root:
        return  # not a git repo; nothing durable to record

    branch = run(["git", "-C", repo_root, "branch", "--show-current"]) or "(detached HEAD)"
    project = slugify(Path(repo_root).name)

    marker = read_marker(session_id)
    commits = "unknown"
    if marker.get("repo_root") == repo_root and marker.get("head_sha"):
        count = run(
            ["git", "-C", repo_root, "rev-list", "--count", f"{marker['head_sha']}..HEAD"]
        )
        if count.isdigit():
            commits = count

    claude_home = Path.home() / ".claude"
    notes_home = resolve_notes_home(claude_home)
    breadcrumb_dir = notes_home / "projects" / project
    try:
        breadcrumb_dir.mkdir(parents=True, exist_ok=True)
        timestamp = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        line = f"{timestamp} repo={repo_root} branch={branch} commits_this_session={commits} reason={reason}\n"
        with open(breadcrumb_dir / "breadcrumbs.log", "a", encoding="utf-8") as f:
            f.write(line)
    except OSError:
        return


if __name__ == "__main__":
    main()

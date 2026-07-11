#!/usr/bin/env python3
"""session-start-context.py — Claude Code SessionStart hook (matcher:
startup|resume).

Runs bin/session-context.sh for the session's cwd and injects the result via
hookSpecificOutput.additionalContext, so a fresh session opens oriented
without depending on the human remembering to run /session-start (which
remains the deep version). Also drops a small marker under $TMPDIR keyed by
session_id (repo root, HEAD sha, start time) so the paired SessionEnd hook
(session-end-breadcrumb.py) can report commits made this session.

Never blocks a session: any failure here is swallowed and the hook exits 0
with no additionalContext, exactly as if it had not run.

Wire-up (opt-in — see bin/install-session-hooks.sh, never part of the
default installer):
  "hooks": { "SessionStart": [ { "matcher": "startup|resume", "hooks": [
    { "type": "command",
      "command": "python3 /path/to/bindle/global/hooks/session-start-context.py",
      "timeout": 10 } ] } ] }

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
SESSION_CONTEXT = REPO_ROOT / "bin" / "session-context.sh"


def write_start_marker(session_id: str, cwd: str) -> None:
    if not session_id:
        return
    try:
        head_sha = subprocess.run(
            ["git", "-C", cwd, "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()
        repo_root = subprocess.run(
            ["git", "-C", cwd, "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()
    except Exception:  # noqa: BLE001 — marker is best-effort
        return
    if not head_sha or not repo_root:
        return
    marker = {
        "repo_root": repo_root,
        "head_sha": head_sha,
        "started_at": time.time(),
    }
    try:
        marker_path = Path(tempfile.gettempdir()) / f"bindle-session-{session_id}.json"
        marker_path.write_text(json.dumps(marker))
    except OSError:
        return


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except Exception:  # noqa: BLE001
        return
    if data.get("hook_event_name") != "SessionStart":
        return
    cwd = data.get("cwd") or "."
    session_id = data.get("session_id") or ""

    write_start_marker(session_id, cwd)

    if not SESSION_CONTEXT.exists():
        return
    try:
        result = subprocess.run(
            [str(SESSION_CONTEXT), "--cwd", cwd],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception:  # noqa: BLE001 — never block a session over this
        return
    context = result.stdout.strip()
    if not context:
        return

    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": context,
                }
            }
        )
    )


if __name__ == "__main__":
    main()

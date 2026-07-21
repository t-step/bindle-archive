#!/usr/bin/env python3
"""codegraph-chaining-guard.py — Claude Code PreToolUse hook.

Enforces mechanically what global/CLAUDE.md's CodeGraph rule asks for in prose:
CodeGraph bills a flat ~5.5k tokens per call, so it only pays when one call
replaces a lot of reading. Six days of measured Valence transcripts (#309) show
the prose rule did not reduce call volume — and that its largest consumer, the
built-in `Explore` subagent, never sees CLAUDE.md at all.

The rule here is narrower than the prose rule, because it has to be decidable
from the transcript: **allow the first CodeGraph call; deny when the tool call
immediately preceding it was also a CodeGraph call.** Chaining is the measured
pathology — another CodeGraph call is the single most common successor to one,
and the worst observed subagent chained 13 of them for ~68k tokens. Whether a
given call would have replaced 6+ file reads is a judgment no hook can make; it
stays in CLAUDE.md.

Covers both invocation paths: the MCP tool (`mcp__*codegraph*`) and Bash
`codegraph explore`.

Escape hatch: `cg-chain-ok` anywhere in the tool input allows the call through.
A genuinely wide orientation sweep across several subsystems is exactly where
CodeGraph wins; the marker makes that an explicit, greppable assertion.

State is one small temp file keyed by a hash of `transcript_path`. The hook is
wired for every tool call so it can remember the immediately preceding tool
without opening the transcript. Keying on the path preserves subagent isolation:
each subagent has its own transcript path, so concurrent subagents do not share
state. Stale files are cleaned opportunistically on each call.

Fails OPEN — a missing transcript path, unreadable state, unwritable temp dir,
or malformed input allows. This is the opposite of the nested-notes guard's MCP
path (#264), deliberately: that is a correctness gate where a false allow lands
unreviewable prose on a maintainer's issue, while this is an efficiency gate
where a false allow costs ~5.5k tokens and a false deny wedges real work
mid-task.

Wire-up in ~/.claude/settings.json — note the ~/.claude/hooks path, a symlink
bin/install.sh maintains, so moving the checkout leaves a dangling link this
hook's own nonzero exit and bin/doctor.sh both report:
  "hooks": { "PreToolUse": [ { "matcher": ".*",
    "hooks": [ { "type": "command",
    "command": "python3 ~/.claude/hooks/codegraph-chaining-guard.py",
    "timeout": 10 } ] } ] }
Spell the path out with $HOME expanded (no leading ~);
settings.json is JSON, so an unexpanded ~ survives only if the shell that
runs the command expands it — do not rely on that (#312).
Do not wrap the command in `|| true`: for PreToolUse only exit code 2 blocks a
tool call, so a missing hook already fails visibly without blocking anything.

Self-test: bin/test-codegraph-chaining-guard.sh
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path

MARKER = "cg-chain-ok"
STATE_TTL_SECONDS = 24 * 60 * 60
STATE_PREFIX = "codegraph-chain-"

MCP_CODEGRAPH = re.compile(r"^mcp__.*codegraph", re.I)
BASH_CODEGRAPH = re.compile(r"\bcodegraph\b[^|;&]*\bexplore\b", re.I)


def deny(reason: str) -> None:
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                }
            }
        )
    )
    sys.exit(0)


def is_codegraph(tool_name: str, tool_input: dict) -> bool:
    """True when this tool call is a CodeGraph query, by either invocation path."""
    if MCP_CODEGRAPH.search(tool_name or ""):
        return True
    if tool_name == "Bash":
        command = tool_input.get("command")
        if isinstance(command, str) and BASH_CODEGRAPH.search(command):
            return True
    return False


def state_dir() -> Path:
    override = os.environ.get("BINDLE_CODEGRAPH_GUARD_STATE_DIR")
    if override:
        return Path(override)
    return Path(tempfile.gettempdir()) / "bindle-codegraph-chaining-guard"


def state_path(transcript_path: str) -> Path:
    digest = hashlib.sha256(
        transcript_path.encode("utf-8", errors="surrogatepass")
    ).hexdigest()
    return state_dir() / f"{STATE_PREFIX}{digest}.json"


def cleanup_stale(now: float | None = None) -> None:
    """Best-effort cleanup so state files do not accumulate without bound."""
    root = state_dir()
    cutoff = (time.time() if now is None else now) - STATE_TTL_SECONDS
    try:
        entries = list(root.glob(f"{STATE_PREFIX}*.json"))
    except OSError:
        return
    for entry in entries:
        try:
            if entry.stat().st_mtime < cutoff:
                entry.unlink()
        except OSError:
            continue


def read_previous(transcript_path: str) -> tuple[str, dict] | None:
    try:
        with state_path(transcript_path).open("r", encoding="utf-8") as handle:
            record = json.load(handle)
    except (OSError, ValueError, TypeError):
        return None
    if not isinstance(record, dict):
        return None
    name = record.get("tool_name")
    payload = record.get("tool_input")
    if not isinstance(name, str):
        return None
    return name, payload if isinstance(payload, dict) else {}


def write_current(transcript_path: str, tool_name: str, tool_input: dict) -> None:
    root = state_dir()
    path = state_path(transcript_path)
    tmp = path.with_suffix(f".{os.getpid()}.tmp")
    payload = {"tool_name": tool_name, "tool_input": tool_input, "updated_at": time.time()}
    try:
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        with tmp.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, separators=(",", ":"))
            handle.write("\n")
        os.replace(tmp, path)
    except OSError:
        try:
            tmp.unlink()
        except OSError:
            pass


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except Exception:  # noqa: BLE001 — never break the session over the guard
        return
    if not isinstance(data, dict):
        return
    tool_name = data.get("tool_name") or ""
    tool_input = data.get("tool_input")
    if not isinstance(tool_input, dict):
        tool_input = {}
    transcript = data.get("transcript_path")
    if not isinstance(transcript, str) or not transcript:
        return

    cleanup_stale()
    current_is_codegraph = is_codegraph(tool_name, tool_input)
    previous = read_previous(transcript)
    write_current(transcript, tool_name, tool_input)

    if not current_is_codegraph:
        return
    if MARKER in json.dumps(tool_input, default=str):
        return
    if previous is None or not is_codegraph(previous[0], previous[1]):
        return

    deny(
        "CodeGraph chaining guard: the previous tool call was already a CodeGraph "
        "query, and each one bills a flat ~5.5k tokens regardless of question "
        "size. Measured over six days, chained calls were the largest single "
        "source of CodeGraph spend and ~1% of calls led directly to an edit. "
        "Use grep + Read to follow up on what the last call returned — that costs "
        "roughly 4x less for a single symbol or file. If this really is a wide "
        "orientation sweep that would otherwise open 6+ NEW files, say so by "
        "including cg-chain-ok in the query."
    )


if __name__ == "__main__":
    main()

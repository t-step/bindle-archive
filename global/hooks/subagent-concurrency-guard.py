#!/usr/bin/env python3
"""subagent-concurrency-guard.py — Claude Code PreToolUse/PostToolUse hook.

Caps concurrent Agent-tool dispatch at MAX_CONCURRENT and forbids nested
dispatch outright — a subagent's own Agent call is denied unconditionally, so
nesting cannot be used to route around the cap. Verified against real,
on-disk Claude Code transcripts for this repo (2026-07-21): the dispatch tool
is named `Agent`; each subagent gets its own transcript file at
`<session>/subagents/agent-<agentId>.jsonl`, distinct from the top-level
session's own `<session>.jsonl`; and each `tool_use` block carries a stable
`id`, confirmed by cross-referencing a real dispatch call's `tool_use.id`
against the dispatched subagent's own `meta.json.toolUseId`.

Nesting detection: `PreToolUse`/`PostToolUse`'s `transcript_path` always
names the transcript of the *calling* context (the same fact
`codegraph-chaining-guard.py` documents and relies on) — so a call is nested
exactly when `transcript_path`'s immediate parent directory is `subagents`.

Concurrency cap: a lock-protected slot directory under
`~/.claude/bindle/state/subagent-concurrency/slots/`, deliberately outside
`~/.claude/hooks/`, which `bin/install.sh`/`bin/doctor.sh` manage as a
symlink-only destination — runtime state has no business there. One file per
in-flight top-level dispatch, named by that call's `tool_use.id` (read from
the transcript tail, the same technique `codegraph-chaining-guard.py` uses to
find "the previous tool call" — here used to find "this call"). `PreToolUse`
allows and creates a slot if fewer than MAX_CONCURRENT non-stale slots exist;
`PostToolUse` removes the slot it created. A slot older than
BINDLE_SUBAGENT_SLOT_TTL_SECONDS (default 4 hours) is treated as abandoned (a
crashed subagent that never reached `PostToolUse`) and reaped on sight.

No escape hatch. Every other guard here ships a marker override; this one
does not, deliberately — an override would defeat the one thing this guard
was asked to close.

Fails OPEN: any failure to read/write guard state, or to find a matching
tool_use block, allows the call. A false allow costs at most one subagent
over cap; a false deny would silently brick all dispatch for the rest of a
session the first time this new mechanism's state handling hit a bug — the
same asymmetry `codegraph-chaining-guard.py` documents for its own choice.

Wire-up in ~/.claude/settings.json — note the ~/.claude/hooks path, a symlink
bin/install.sh maintains, so moving the checkout leaves a dangling link this
hook's own nonzero exit and bin/doctor.sh both report:
  "hooks": { "PreToolUse": [ { "matcher": "Agent",
    "hooks": [ { "type": "command",
    "command": "python3 ~/.claude/hooks/subagent-concurrency-guard.py",
    "timeout": 10 } ] } ],
    "PostToolUse": [ { "matcher": "Agent",
    "hooks": [ { "type": "command",
    "command": "python3 ~/.claude/hooks/subagent-concurrency-guard.py",
    "timeout": 10 } ] } ] }
Spell the path out with $HOME expanded (no leading ~);
settings.json is JSON, so an unexpanded ~ survives only if the shell that
runs the command expands it — do not rely on that (#312).
Do not wrap the command in `|| true`: for PreToolUse only exit code 2 blocks a
tool call, so a missing hook already fails visibly without blocking anything.

Self-test: bin/test-subagent-concurrency-guard.sh
"""

from __future__ import annotations

import contextlib
import fcntl
import json
import os
import sys
import time

MAX_CONCURRENT = 3
DEFAULT_TTL_SECONDS = 4 * 60 * 60
TAIL_BYTES = 256 * 1024
MAX_LINES = 400
DISPATCH_TOOL = "Agent"

STATE_DIR = os.path.expanduser("~/.claude/bindle/state/subagent-concurrency")
SLOTS_DIR = os.path.join(STATE_DIR, "slots")
LOCK_PATH = os.path.join(STATE_DIR, "slots.lock")


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


def is_nested(transcript_path: str) -> bool:
    return os.path.basename(os.path.dirname(transcript_path)) == "subagents"


def tail_lines(path: str) -> list[str]:
    """Last MAX_LINES whole lines of the transcript. Returns [] on any problem."""
    try:
        with open(path, "rb") as handle:
            handle.seek(0, 2)
            size = handle.tell()
            handle.seek(max(0, size - TAIL_BYTES))
            chunk = handle.read()
    except OSError:
        return []
    text = chunk.decode("utf-8", errors="replace")
    lines = text.splitlines()
    if size > TAIL_BYTES and lines:
        lines = lines[1:]  # first line is a partial record from the seek
    return lines[-MAX_LINES:]


def newest_dispatch_id(lines: list[str]) -> str | None:
    """The id of the newest Agent tool_use block in the transcript, or None."""
    newest: str | None = None
    for line in lines:
        try:
            record = json.loads(line)
        except (ValueError, TypeError):
            continue
        if not isinstance(record, dict):
            continue
        content = (record.get("message") or {}).get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue
            if block.get("name") != DISPATCH_TOOL:
                continue
            block_id = block.get("id")
            if isinstance(block_id, str):
                newest = block_id
    return newest


@contextlib.contextmanager
def slots_lock():
    os.makedirs(SLOTS_DIR, exist_ok=True)
    with open(LOCK_PATH, "a+") as lock_file:
        fcntl.flock(lock_file, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file, fcntl.LOCK_UN)


def ttl_seconds() -> float:
    raw = os.environ.get("BINDLE_SUBAGENT_SLOT_TTL_SECONDS")
    if raw:
        try:
            return float(raw)
        except ValueError:
            pass
    return float(DEFAULT_TTL_SECONDS)


def live_slot_count() -> int:
    """Non-stale slots, reaping stale ones. Call only while holding the lock."""
    ttl = ttl_seconds()
    now = time.time()
    count = 0
    for name in os.listdir(SLOTS_DIR):
        path = os.path.join(SLOTS_DIR, name)
        try:
            age = now - os.path.getmtime(path)
        except OSError:
            continue
        if age > ttl:
            with contextlib.suppress(OSError):
                os.remove(path)
            continue
        count += 1
    return count


def handle_pre_tool_use(data: dict) -> None:
    transcript = data.get("transcript_path")
    if not isinstance(transcript, str) or not transcript:
        return  # can't judge -> allow

    if is_nested(transcript):
        deny(
            "Subagent-concurrency guard: this call originates from inside a "
            "subagent. Nested Agent dispatch is forbidden outright — the cap "
            "on concurrent subagents is not per level, so nesting cannot be "
            "used to route around it."
        )

    dispatch_id = newest_dispatch_id(tail_lines(transcript))
    if dispatch_id is None:
        return  # can't identify this call -> allow, no slot created

    try:
        with slots_lock():
            if live_slot_count() >= MAX_CONCURRENT:
                deny(
                    f"Subagent-concurrency guard: {MAX_CONCURRENT} subagents "
                    "are already in flight. Wait for one to finish before "
                    "dispatching another."
                )
            slot_path = os.path.join(SLOTS_DIR, dispatch_id)
            with open(slot_path, "w"):
                pass
    except OSError:
        return  # state I/O failed -> allow


def handle_post_tool_use(data: dict) -> None:
    transcript = data.get("transcript_path")
    if not isinstance(transcript, str) or not transcript:
        return
    if is_nested(transcript):
        return  # never held a slot

    dispatch_id = newest_dispatch_id(tail_lines(transcript))
    if dispatch_id is None:
        return

    slot_path = os.path.join(SLOTS_DIR, dispatch_id)
    with contextlib.suppress(OSError):
        os.remove(slot_path)


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except Exception:  # noqa: BLE001 — never break the session over the guard
        return
    if not isinstance(data, dict):
        return
    if (data.get("tool_name") or "") != DISPATCH_TOOL:
        return

    event = data.get("hook_event_name")
    if event == "PreToolUse":
        handle_pre_tool_use(data)
    elif event == "PostToolUse":
        handle_post_tool_use(data)


if __name__ == "__main__":
    main()

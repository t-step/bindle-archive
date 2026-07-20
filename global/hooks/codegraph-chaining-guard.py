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

State comes from the transcript, not a state file. The matcher scopes this hook
to CodeGraph tools, so it never observes the intervening calls it needs in order
to judge "consecutive" — but `transcript_path` already records them. No state to
persist, no cleanup, no races between parallel subagents, and it works unchanged
inside a subagent because each subagent has its own transcript.

Fails OPEN — a missing, unreadable, or malformed transcript allows. This is the
opposite of the nested-notes guard's MCP path (#264), deliberately: that is a
correctness gate where a false allow lands unreviewable prose on a maintainer's
issue, while this is an efficiency gate where a false allow costs ~5.5k tokens
and a false deny wedges real work mid-task.

Wire-up in ~/.claude/settings.json — note the ~/.claude/hooks path, a symlink
bin/install.sh maintains, so moving the checkout leaves a dangling link this
hook's own nonzero exit and bin/doctor.sh both report:
  "hooks": { "PreToolUse": [ { "matcher": "Bash|mcp__.*codegraph.*",
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

import json
import re
import sys

MARKER = "cg-chain-ok"
TAIL_BYTES = 256 * 1024  # transcripts grow unbounded; the answer is always near the end
MAX_LINES = 400

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


def tool_uses(lines: list[str]) -> list[tuple[str, dict]]:
    """Every (name, input) tool_use in the tail, oldest first."""
    found: list[tuple[str, dict]] = []
    for line in lines:
        try:
            record = json.loads(line)
        except (ValueError, TypeError):
            continue  # a malformed line is skipped, not fatal — fail open
        if not isinstance(record, dict):
            continue
        content = (record.get("message") or {}).get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue
            name = block.get("name")
            payload = block.get("input")
            if isinstance(name, str):
                found.append((name, payload if isinstance(payload, dict) else {}))
    return found


def previous_tool_use(
    lines: list[str], tool_name: str, tool_input: dict
) -> tuple[str, dict] | None:
    """The tool call before this one, skipping this one's own transcript record.

    PreToolUse fires after the assistant message carrying the call is written, so
    the newest tool_use in the tail is usually this very call. Exactly one such
    self-match is dropped — dropping only one keeps a genuine identical repeat
    (`cg(X)` then `cg(X)` again) detectable, since the second-newest entry is
    then the real predecessor.
    """
    found = tool_uses(lines)
    if found and found[-1] == (tool_name, tool_input):
        found.pop()
    return found[-1] if found else None


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
    if not is_codegraph(tool_name, tool_input):
        return
    if MARKER in json.dumps(tool_input, default=str):
        return

    transcript = data.get("transcript_path")
    if not isinstance(transcript, str) or not transcript:
        return  # can't judge -> allow; CLAUDE.md still governs
    previous = previous_tool_use(tail_lines(transcript), tool_name, tool_input)
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

#!/usr/bin/env python3
"""nested-notes-guard.py — Claude Code PreToolUse hook (matcher: Bash).

Enforces the global CLAUDE.md rule that maintainer-facing GitHub prose in
domattioli-owned repos is rendered with the nested-notes skill (inline mode).
Blocks `gh` commands that write prose (pr/issue create|edit|comment, pr review,
`gh api` carrying a body= field to an issues/pulls path) to a domattioli repo
when the body shows no nested-notes structure.

Deliberately a heuristic, not a full outline lint: the presence of an `↪` leaf
is the compliance signal. Escape hatches (the skill's carve-outs):
  - bodies under SHORT_BODY chars (single-fact one-liners), footer lines excluded;
  - an explicit `<!-- nested-notes-exempt -->` marker in the body;
  - unreadable --body-file targets (can't judge -> allow; CLAUDE.md still governs).

Covers two write paths: Bash `gh` invocations, and GitHub MCP write tools
(#264), which carry structured tool_input fields instead of a command string.
The MCP path fails CLOSED — a write-shaped tool whose body/owner cannot be read
is denied, since an unrecognized write shape is exactly the gap this guard was
missing.

Wire-up in ~/.claude/settings.json — note the ~/.claude/hooks path, a symlink
bin/install.sh maintains. Pointing settings.json into a checkout means moving
the repo silently disables the hook; via the symlink, a move leaves a dangling
link that this hook's own nonzero exit and bin/doctor.sh both report:
  "hooks": { "PreToolUse": [ { "matcher": "Bash|mcp__.*github.*",
    "hooks": [ { "type": "command",
    "command": "python3 ~/.claude/hooks/nested-notes-guard.py",
    "timeout": 10 } ] } ] }
Spell the path out with $HOME expanded (no leading ~);
settings.json is JSON, so an unexpanded ~ survives only if the shell that
runs the command expands it — do not rely on that (#312).
Do not wrap the command in `|| true`: for PreToolUse only exit code 2 blocks a
tool call, so a missing hook already fails visibly without blocking anything,
and suppressing that is what made a moved repo undetectable.

Self-test: bin/test-nested-notes-guard.sh
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

MARKER = "↪"  # ↪ — nested-notes prose leaf
EXEMPT = "nested-notes-exempt"
SHORT_BODY = 200
OWNER = "domattioli"

PROSE_CMD = re.compile(r"\bgh\s+(?:pr|issue)\s+(?:create|edit|comment|review)\b")
API_CMD = re.compile(r"\bgh\s+api\b")
API_PROSE_PATH = re.compile(r"\b(?:issues|pulls)/")
BODY_FLAG = re.compile(r"(?:--body(?:-file)?\b|-b\s|-[fF]\s*body=)")
REPO_FLAG = re.compile(r"(?:-R|--repo)[=\s]+['\"]?([A-Za-z0-9_.-]+)/")
API_REPO = re.compile(r"\brepos/([A-Za-z0-9_.-]+)/")
MCP_GITHUB = re.compile(r"^mcp__.*github.*", re.I)
MCP_WRITE = re.compile(r"(?:create|update|comment|review|edit|add|reply)", re.I)
BODY_FILE = re.compile(r"--body-file[=\s]+['\"]?([^\s'\"]+)|-[fF]\s*body=@([^\s'\"]+)")
INLINE_BODY = re.compile(r"(?:--body|-b)\b(.*)$|-[fF]\s*body=(.*)$", re.S)
FOOTER_LINE = re.compile(r"claude\.ai/code|Generated with \[?Claude Code")


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


def deny_prose() -> None:
    """The shared unstructured-prose denial, used by both the Bash and MCP paths."""
    deny(
        f"nested-notes guard: this writes maintainer-facing prose to a {OWNER} "
        "repo without nested-notes structure. Re-render the body with the "
        "nested-notes skill in inline mode (bold L1 '-' concepts, '▸' "
        "attributes, literal enumerator glyphs, '↪' prose leaves, blank "
        "lines between siblings; keep tables/code intact and footers verbatim). "
        "Genuine carve-outs (bot-template fixed fields, single-fact one-liners) "
        "may include <!-- nested-notes-exempt --> in the body instead."
    )


def repo_owner(cmd: str, cwd: str) -> str | None:
    m = REPO_FLAG.search(cmd)
    if m:
        return m.group(1)
    m = API_REPO.search(cmd)
    if m:
        return m.group(1)
    # No explicit repo: gh resolves from the cwd's remotes (for forks this can
    # be the upstream), so treat any domattioli remote as targeting domattioli.
    try:
        remotes = subprocess.run(
            ["git", "-C", cwd or ".", "remote", "-v"],
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout
    except Exception:  # noqa: BLE001 — never break the session over the guard
        return None
    if re.search(rf"github\.com[:/]{OWNER}/", remotes, re.I):
        return OWNER
    return None


def effective_length(text: str) -> int:
    kept = [line for line in text.splitlines() if not FOOTER_LINE.search(line)]
    return len("\n".join(kept).strip())


def mcp_owner(tool_input: dict) -> str | None:
    """Owner from an MCP payload: an explicit `owner`, else an `owner/name` repo."""
    owner = tool_input.get("owner")
    if isinstance(owner, str) and owner:
        return owner
    repo = tool_input.get("repo")
    if isinstance(repo, str) and "/" in repo:
        return repo.split("/", 1)[0]
    return None


def check_mcp(data: dict, tool_name: str) -> None:
    """GitHub MCP write path (#264). Bash carries a command string; MCP carries
    structured fields, so normalize to (owner, body) and share every downstream
    rule with the Bash path.

    Fails CLOSED: a write-shaped tool whose body or owner can't be found is
    denied, not waved through. Unlike an unreadable --body-file — a `gh` command
    the guard did parse — an unrecognized write shape is the hole #264 was filed
    on, so silence there is the failure, not a safe default.
    """
    if not MCP_WRITE.search(tool_name):
        return  # read-shaped: nothing to judge
    tool_input = data.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        tool_input = {}
    body = tool_input.get("body")
    owner = mcp_owner(tool_input)
    if not isinstance(body, str) or owner is None:
        deny(
            f"nested-notes guard: `{tool_name}` looks like a GitHub write but the "
            "guard could not read its body and target owner, so it cannot tell "
            "whether the nested-notes rule applies. Use the `gh` CLI path via "
            "Bash (which the guard understands), or add "
            "<!-- nested-notes-exempt --> to the body if this is a genuine "
            "carve-out. If this tool's payload shape is legitimate, teach the "
            "guard about it in global/hooks/nested-notes-guard.py."
        )
    if owner.lower() != OWNER:
        return
    if EXEMPT in body or MARKER in body:
        return
    if effective_length(body) < SHORT_BODY:
        return
    deny_prose()


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except Exception:  # noqa: BLE001
        return
    tool_name = data.get("tool_name") or ""
    if MCP_GITHUB.search(tool_name):
        check_mcp(data, tool_name)
        return
    if tool_name != "Bash":
        return
    cmd = (data.get("tool_input") or {}).get("command") or ""
    if "gh" not in cmd:
        return
    is_prose = bool(PROSE_CMD.search(cmd)) or (
        bool(API_CMD.search(cmd)) and bool(API_PROSE_PATH.search(cmd))
    )
    if not is_prose or not BODY_FLAG.search(cmd):
        return
    owner = repo_owner(cmd, data.get("cwd") or "")
    if owner is None or owner.lower() != OWNER:
        return
    if EXEMPT in cmd or MARKER in cmd:
        return

    m = BODY_FILE.search(cmd)
    if m:
        rel = m.group(1) or m.group(2)
        path = Path(rel)
        if not path.is_absolute():
            path = Path(data.get("cwd") or ".") / rel
        try:
            content = path.read_text(encoding="utf-8")
        except OSError:
            return  # can't judge the file; the CLAUDE.md rule still governs
        if MARKER in content or EXEMPT in content:
            return
        if effective_length(content) < SHORT_BODY:
            return
    else:
        m = INLINE_BODY.search(cmd)
        zone = (m.group(1) or m.group(2) or "") if m else cmd
        if effective_length(zone) < SHORT_BODY:
            return

    deny_prose()


if __name__ == "__main__":
    main()

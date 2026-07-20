#!/usr/bin/env python3
"""label-hygiene-guard.py — Claude Code PreToolUse hook (matcher: Bash).

Enforces the label lifecycle rules in docs/issue-tracking.md at the moment a
transition happens, rather than leaving them to a later sweep. Three rules:

  R1  closing an issue that still carries a `status:` label is denied
  R2  merging a PR that closes such an issue is denied
  R3  moving an issue out of `status: triage` without a `priority:` label
      is denied

R2 is the one that matters. Both drifts this guard was built for (#279, #309)
closed through a closing keyword rather than `gh issue close`, so R2 scans the
PR body AND every commit message in the PR — a keyword in a commit closes the
issue just as surely, which is how #266 was closed three PRs early while this
guard was being designed.

Gating: the repo must carry docs/issue-tracking.md, the contract these rules
come from. Absent it, the hook exits silently — the convention is not this
repo's, so neither are the rules. The guard matches label PREFIXES rather than
specific values, so the vocabulary can grow without touching this file. The one
exception is `status: triage` in R3, which the rule is definitionally about.

Failure posture: fails OPEN. An unreachable or erroring GitHub API allows the
call and warns on stderr. This follows the doctrine #309 set: a false allow here
is a stale label that bin/check-issue-labels.sh catches on the next audit, while
a false deny is an unmergeable PR during a GitHub outage — and the v0.9.0 cut
hit a 503 mid-release (#265), so that window is not hypothetical.

Wire-up in ~/.claude/settings.json — note the ~/.claude/hooks path, a symlink
bin/install.sh maintains. Pointing settings.json into a checkout means moving
the repo silently disables the hook; via the symlink, a move leaves a dangling
link that bin/doctor.sh reports:
  "hooks": { "PreToolUse": [ { "matcher": "Bash",
    "hooks": [ { "type": "command",
    "command": "python3 ~/.claude/hooks/label-hygiene-guard.py",
    "timeout": 10 } ] } ] }
Spell the path out with $HOME expanded (no leading ~);
settings.json is JSON, so an unexpanded ~ survives only if the shell that
runs the command expands it — do not rely on that (#312).
Do not wrap the command in `|| true`: for PreToolUse only exit code 2 blocks a
tool call, so a missing hook already fails visibly without blocking anything.

Self-test: bin/test-label-hygiene-guard.sh
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

CONTRACT = "docs/issue-tracking.md"
STATUS = "status:"
PRIORITY = "priority:"
TRIAGE = "status: triage"  # the one value R3 must know; the rule is about it

ISSUE_CLOSE = re.compile(r"\bgh\s+issue\s+close\s+(\d+)")
PR_MERGE = re.compile(r"\bgh\s+pr\s+merge\s+(\d+)")
ISSUE_EDIT = re.compile(r"\bgh\s+issue\s+edit\s+(\d+)")
API_CMD = re.compile(r"\bgh\s+api\b")
API_ISSUE = re.compile(r"\bissues/(\d+)")
API_CLOSED = re.compile(r"\bstate=[\"']?closed\b")
# Label values contain a space ("status: ready"), so an unquoted-value pattern
# cannot be reused for the quoted form — a lazy quantifier stops at the space and
# captures a bare "status:". Each quoting style gets its own alternative.
_LABEL_VALUE = r"(?:'([^']*)'|\"([^\"]*)\"|(\S+))"
ADD_LABEL = re.compile(r"--add-label[=\s]+" + _LABEL_VALUE)
REMOVE_LABEL = re.compile(r"--remove-label[=\s]+" + _LABEL_VALUE)


def label_values(pattern: re.Pattern[str], cmd: str) -> list[str]:
    """Flatten _LABEL_VALUE's three alternatives into the one that matched."""
    return [next(g for g in groups if g).strip() for groups in pattern.findall(cmd)]
CLOSING_KEYWORD = re.compile(
    r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+#(\d+)", re.I
)


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


def warn(what: str) -> None:
    """Fail-open notice. Loud enough to notice, never blocking."""
    print(
        f"label-hygiene guard: could not verify {what} — labels NOT checked. "
        "Run bin/check-issue-labels.sh afterward.",
        file=sys.stderr,
    )


def gh_json(args: list[str], cwd: str) -> dict | None:
    """A `gh ... --json` read. None means the read failed — callers fail open."""
    try:
        proc = subprocess.run(
            ["gh", *args], capture_output=True, text=True, timeout=15, cwd=cwd or None
        )
    except Exception:  # noqa: BLE001 — never break the session over the guard
        return None
    if proc.returncode != 0:
        return None
    try:
        return json.loads(proc.stdout)
    except Exception:  # noqa: BLE001
        return None


def issue_label_names(num: str, cwd: str) -> list[str] | None:
    data = gh_json(["issue", "view", num, "--json", "labels,state"], cwd)
    if data is None:
        return None
    return [x.get("name", "") for x in data.get("labels") or []]


def status_labels(num: str, cwd: str) -> list[str] | None:
    names = issue_label_names(num, cwd)
    if names is None:
        return None
    return [n for n in names if n.startswith(STATUS)]


def has_priority(num: str, cwd: str) -> bool | None:
    names = issue_label_names(num, cwd)
    if names is None:
        return None
    return any(n.startswith(PRIORITY) for n in names)


def closing_refs(num: str, cwd: str) -> list[str] | None:
    """Issues this PR would close — from the body AND every commit message.

    The commit half is not decoration: GitHub parses closing keywords in commit
    messages too, and that is the path that closed #266 early.
    """
    data = gh_json(["pr", "view", num, "--json", "body,commits"], cwd)
    if data is None:
        return None
    chunks = [data.get("body") or ""]
    for c in data.get("commits") or []:
        chunks.append(c.get("messageHeadline") or "")
        chunks.append(c.get("messageBody") or "")
    refs: list[str] = []
    for chunk in chunks:
        refs.extend(CLOSING_KEYWORD.findall(chunk))
    return sorted(set(refs), key=int)


def check_close(num: str, cmd: str, cwd: str) -> None:
    labels = status_labels(num, cwd)
    if labels is None:
        warn(f"issue #{num}")
        return
    removing = set(label_values(REMOVE_LABEL, cmd))
    left = [x for x in labels if x not in removing]
    if not left:
        return
    joined = ", ".join(f"`{x}`" for x in left)
    flags = " ".join(f'--remove-label "{x}"' for x in left)
    deny(
        f"label-hygiene guard: closing #{num} would leave it carrying {joined}. "
        f"{CONTRACT} scopes `status:` labels to open issues — a closed issue "
        f"still advertising one is a false row on the dashboard. Append {flags} "
        "to this command, or strip the label first."
    )


def check_merge(num: str, cwd: str) -> None:
    refs = closing_refs(num, cwd)
    if refs is None:
        warn(f"PR #{num}")
        return
    offenders: list[tuple[str, list[str]]] = []
    for ref in refs:
        labels = status_labels(ref, cwd)
        if labels is None:
            warn(f"issue #{ref}")
            return
        if labels:
            offenders.append((ref, labels))
    if not offenders:
        return
    lines = "\n".join(
        f"  #{ref} carries {', '.join(f'`{x}`' for x in labels)}\n"
        f"    gh issue edit {ref} "
        + " ".join(f'--remove-label "{x}"' for x in labels)
        for ref, labels in offenders
    )
    deny(
        f"label-hygiene guard: merging PR #{num} closes issues that still carry "
        f"a `status:` label:\n{lines}\n"
        f"{CONTRACT} scopes `status:` labels to open issues. Strip them first, "
        "then merge. Closing keywords in commit messages count too — that is "
        "how this drift usually happens."
    )


def check_edit(num: str, cmd: str, cwd: str) -> None:
    adding = label_values(ADD_LABEL, cmd)
    leaving_triage = [x for x in adding if x.startswith(STATUS) and x != TRIAGE]
    if not leaving_triage:
        return
    priority = has_priority(num, cwd)
    if priority is None:
        warn(f"issue #{num}")
        return
    if priority:
        return
    deny(
        f"label-hygiene guard: #{num} has no `priority:` label, and "
        f"`{leaving_triage[0]}` moves it out of triage. Per {CONTRACT}, every "
        "open issue outside `status: triage` carries a priority — triage is the "
        "one state where having none is honest. Add one in the same command: "
        '--add-label "priority: normal".'
    )


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except Exception:  # noqa: BLE001
        return
    if (data.get("tool_name") or "") != "Bash":
        return
    cmd = (data.get("tool_input") or {}).get("command") or ""
    if "gh " not in cmd:
        return
    cwd = data.get("cwd") or ""

    # Gate: only repos carrying the contract these rules come from.
    try:
        root = subprocess.run(
            ["git", "-C", cwd or ".", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()
    except Exception:  # noqa: BLE001
        return
    if not root or not (Path(root) / CONTRACT).is_file():
        return

    m = ISSUE_CLOSE.search(cmd)
    if m:
        check_close(m.group(1), cmd, cwd)
        return
    if API_CMD.search(cmd) and API_CLOSED.search(cmd):
        m = API_ISSUE.search(cmd)
        if m:
            check_close(m.group(1), cmd, cwd)
        return
    m = PR_MERGE.search(cmd)
    if m:
        check_merge(m.group(1), cwd)
        return
    m = ISSUE_EDIT.search(cmd)
    if m:
        check_edit(m.group(1), cmd, cwd)


if __name__ == "__main__":
    main()

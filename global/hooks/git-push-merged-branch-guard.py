#!/usr/bin/env python3
"""git-push-merged-branch-guard.py — Claude Code PreToolUse hook (matcher: Bash).

Denies a `git push` to a branch whose PR is already MERGED.

When a PR merges and GitHub auto-deletes the branch, a later push from that
still-checked-out branch silently RE-CREATES the deleted remote branch. The
push succeeds. Nothing errors. The commit now sits on a branch no PR points
at, and reaches `main` only if someone happens to notice — a successful push
and a lost one look identical.

It has fired twice in this repo, in one day: PR #324 (commit 6807a08, a doc
correction) and PR #335 (commit cacf511, a rationale the operator had
explicitly rejected). The second landed on `main` and would have stayed.

Why a hook and not a rule: the prose rule already exists and already failed.
A safety note was written after the FIRST occurrence, and the second happened
later the same session with that note in context. #309 measured a prose rule
across n=275 transcripts and found it changed call volume not at all; what
worked was a PreToolUse guard. A rule that must be remembered exactly when
attention is elsewhere is the shape this repo has shown does not survive.

Verdicts:
  MERGED   deny, naming the cherry-pick recovery
  CLOSED   ALLOW, with a loud stderr notice. Reviving a closed-unmerged branch
           is a legitimate thing to do, so denying it would manufacture a false
           deny — but it has the same invisible-success shape, so it is said
           out loud.
  anything else, including no PR at all — allow, silently

Failure posture: fails OPEN. An unreachable, unauthenticated or slow `gh`
allows the push. This deliberately does NOT follow #264's write-path precedent
of failing closed: `gh` being down must not block every push in the repo, and
degrading to the manual workflow rather than blocking it is the admission
criterion for executable automation here.

What counts as an invocation: the same command-position matching
label-hygiene-guard.py uses (#388) — a `git push` quoted as inert data inside
an `echo`, a comment, or a grep pattern is not a push and is not denied.

Wire-up in ~/.claude/settings.json — via bin/install-claude-hooks.sh, which is
the ONE declared place this hook's event and matcher live (#323):
  "hooks": { "PreToolUse": [ { "matcher": "Bash",
    "hooks": [ { "type": "command",
    "command": "python3 $HOME/.claude/hooks/git-push-merged-branch-guard.py",
    "timeout": 10 } ] } ] }
Wiring is opt-in: `bin/install-claude-hooks.sh install --guard git-push-merged
--apply`. bin/install.sh only maintains the symlink, never settings.json.

Self-test: bin/test-git-push-merged-branch-guard.sh
"""

from __future__ import annotations

import json
import re
import shlex
import subprocess
import sys

# Command-position matching, per #388: patterns are anchored and applied to
# segments, so quoted text that merely CONTAINS a push is not a push.
_SEGMENT_SPLIT = re.compile(r"\n|&&|;|\||\(|\)")
_ENV_PREFIX = re.compile(r"^(?:[A-Za-z_][A-Za-z0-9_]*=\S*\s+)*")
GIT_PUSH = re.compile(r"^git\s+push\b")

# Pushes that carry no branch of work, so nothing can be orphaned by them.
NOT_A_BRANCH_PUSH = {"--delete", "-d", "--tags", "--mirror", "--prune"}

# The trunk is never the shape this guard is about.
TRUNK = {"main", "master"}


def command_segments(cmd: str) -> list[str]:
    """The command line split at every position a shell could start a command."""
    out = []
    for raw in _SEGMENT_SPLIT.split(cmd):
        seg = _ENV_PREFIX.sub("", raw.strip())
        if seg:
            out.append(seg)
    return out


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


def git(args: list[str], cwd: str) -> str | None:
    try:
        proc = subprocess.run(
            ["git", "-C", cwd or ".", *args],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception:  # noqa: BLE001 — never break the session over the guard
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.strip()


def pr_state(branch: str, cwd: str) -> tuple[str, str] | None:
    """(state, number) for the branch's PR. None means no PR, or no answer."""
    try:
        proc = subprocess.run(
            ["gh", "pr", "view", branch, "--json", "state,mergedAt,number"],
            capture_output=True,
            text=True,
            timeout=15,
            cwd=cwd or None,
        )
    except Exception:  # noqa: BLE001
        return None
    if proc.returncode != 0:
        return None
    try:
        data = json.loads(proc.stdout)
    except Exception:  # noqa: BLE001
        return None
    state = (data.get("state") or "").upper()
    if not state:
        return None
    return state, str(data.get("number") or "?")


def pushed_branch(seg: str, cwd: str) -> str | None:
    """The branch a push segment would write, or None if it writes no branch."""
    try:
        tokens = shlex.split(seg)
    except ValueError:
        return None  # unbalanced quotes — unparseable, so fail open
    if any(t in NOT_A_BRANCH_PUSH for t in tokens):
        return None
    # Drop `git push` itself and every option; what remains is
    # [<remote> [<refspec>]].
    rest = [t for t in tokens[2:] if not t.startswith("-")]
    if len(rest) >= 2:
        refspec = rest[1]
        if refspec.startswith("refs/tags/") or refspec == "--tags":
            return None
        # `src:dst` pushes to dst; a bare name pushes to itself.
        branch = refspec.split(":")[-1]
        return branch.replace("refs/heads/", "") or None
    # No refspec: the push follows HEAD.
    head = git(["symbolic-ref", "--quiet", "--short", "HEAD"], cwd)
    return head or None


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except Exception:  # noqa: BLE001
        return
    if (data.get("tool_name") or "") != "Bash":
        return
    cmd = (data.get("tool_input") or {}).get("command") or ""
    if "git push" not in cmd:
        return
    cwd = data.get("cwd") or ""

    seg = next((s for s in command_segments(cmd) if GIT_PUSH.search(s)), None)
    if seg is None:
        return

    branch = pushed_branch(seg, cwd)
    if not branch or branch in TRUNK:
        return

    verdict = pr_state(branch, cwd)
    if verdict is None:
        return  # no PR, or gh gave no answer — fail open either way
    state, number = verdict

    if state == "MERGED":
        deny(
            f"git-push-merged-branch guard: PR #{number} for `{branch}` is "
            f"already MERGED. Pushing would silently re-create the deleted "
            f"remote branch, and the commit would land on a branch no PR "
            f"points at — a lost push looks exactly like a successful one "
            f"(this cost PR #324 and PR #335 a commit each). Cherry-pick onto "
            f"fresh `main` as its own PR instead:\n"
            f"    git fetch --prune && git checkout -b <new-branch> origin/main\n"
            f"    git cherry-pick <sha>\n"
            f"Do not force-push a merged branch — never force-push to recover "
            f"from this; it rewrites history someone has already merged."
        )

    if state == "CLOSED":
        print(
            f"git-push-merged-branch guard: PR #{number} for `{branch}` is "
            f"CLOSED unmerged. Allowing the push — reviving a closed branch is "
            f"a real workflow — but note the commit lands where no open PR "
            f"points at it.",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()

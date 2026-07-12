#!/usr/bin/env bash
#
# test-nested-notes-guard.sh — self-test for global/hooks/nested-notes-guard.py.
#
# Pipes synthesized PreToolUse payloads through the hook and asserts the
# allow/deny decision. Hermetic: the cwd-fallback case uses a throwaway git
# repo with a fake domattioli remote, never a real checkout.
#
set -euo pipefail

# Under a git hook (pre-commit/post-merge), git exports GIT_DIR and friends to
# subprocesses; in a worktree GIT_DIR is absolute, so the fixture-repo git
# calls below would hit the real repository. Scrub the hook environment.
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_COMMON_DIR

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GUARD="$REPO_ROOT/global/hooks/nested-notes-guard.py"
PASS=0
FAIL=0

LONG_PROSE="This is deliberately plain paragraph prose that goes on long enough to clear the short-body carve-out threshold of the guard, describing repairs and reasoning in flowing sentences the way a default model reply would, with no outline structure anywhere in sight at all."
ARROW="$(printf '\xe2\x86\xaa')" # ↪ leaf marker, kept out of raw source so greps on this file stay quiet

payload() { # payload <command> [cwd]
  python3 - "$1" "${2:-/tmp}" <<'PY'
import json, sys
print(json.dumps({"tool_name": "Bash", "tool_input": {"command": sys.argv[1]}, "cwd": sys.argv[2]}))
PY
}

expect() { # expect <allow|deny> <name> <command> [cwd]
  local want="$1" name="$2" cmd="$3" cwd="${4:-/tmp}"
  local out got
  out="$(payload "$cmd" "$cwd" | python3 "$GUARD")"
  if grep -q '"permissionDecision": "deny"' <<<"$out"; then got=deny; else got=allow; fi
  if [[ "$got" == "$want" ]]; then
    PASS=$((PASS + 1))
    echo "  ok: $name"
  else
    FAIL=$((FAIL + 1))
    echo "  FAIL: $name (wanted $want, got $got)" >&2
  fi
}

echo "nested-notes-guard self-test"

# Non-gh and read-only commands pass through.
expect allow "plain command" "ls -la"
expect allow "gh read-only" "gh pr view 302 -R domattioli/Valence"
expect allow "gh label edit, no body" "gh issue edit 5 -R domattioli/Valence --add-label 'merge: squash'"

# Prose writes to domattioli without structure are denied.
expect deny "plain long pr body" "gh pr create -R domattioli/Valence --title t --body \"$LONG_PROSE\""
expect deny "plain long issue comment" "gh issue comment 282 --repo domattioli/Valence --body \"$LONG_PROSE\""
expect deny "gh api comment patch" "gh api -X PATCH repos/domattioli/Valence/issues/comments/1 -f body=\"$LONG_PROSE\""

# Compliance and carve-outs allow.
expect allow "nested-notes body" "gh issue comment 282 -R domattioli/Valence --body \"- **Status** ... $ARROW the packet is covered. $LONG_PROSE\""
expect allow "explicit exemption" "gh issue comment 282 -R domattioli/Valence --body \"<!-- nested-notes-exempt --> $LONG_PROSE\""
expect allow "short one-liner" "gh issue comment 282 -R domattioli/Valence --body 'done, see PR #302'"

# Other owners are out of scope.
expect allow "other owner" "gh pr create -R someoneelse/repo --title t --body \"$LONG_PROSE\""

# cwd fallback: a repo with a domattioli remote counts even without -R.
TMP_REPO="$(mktemp -d)"
trap 'rm -rf "$TMP_REPO"' EXIT
git -C "$TMP_REPO" init -q
git -C "$TMP_REPO" remote add upstream git@github.com:domattioli/Valence.git
expect deny "cwd-fallback domattioli remote" "gh issue comment 282 --body \"$LONG_PROSE\"" "$TMP_REPO"
expect allow "cwd-fallback plain dir" "gh issue comment 282 --body \"$LONG_PROSE\"" "/tmp"

# --body-file variants.
BODY_FILE="$TMP_REPO/body.md"
printf '%s\n' "$LONG_PROSE" >"$BODY_FILE"
expect deny "plain body-file" "gh pr create -R domattioli/Valence --title t --body-file $BODY_FILE"
printf -- '- **Status**\n\n    %s covered.\n' "$ARROW" >"$BODY_FILE"
expect allow "nested body-file" "gh pr create -R domattioli/Valence --title t --body-file $BODY_FILE"
expect allow "unreadable body-file" "gh pr create -R domattioli/Valence --title t --body-file $TMP_REPO/missing.md"

echo "passed $PASS, failed $FAIL"
[[ "$FAIL" -eq 0 ]]

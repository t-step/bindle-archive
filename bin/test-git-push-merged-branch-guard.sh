#!/usr/bin/env bash
#
# test-git-push-merged-branch-guard.sh — self-test for
# global/hooks/git-push-merged-branch-guard.py.
#
# Pipes synthesized PreToolUse payloads through the hook and asserts the
# allow/deny decision plus the stderr notice. Hermetic: a stub `gh` on PATH
# answers from canned JSON keyed by branch, so no case here reaches the
# network. A branch with no fixture makes the stub exit non-zero, which is the
# same shape as "no PR for this branch" and as an unreachable gh — both of
# which must ALLOW.
#
set -euo pipefail

# git exports GIT_DIR and friends to hook subprocesses; in a worktree it is
# absolute, so the fixture-repo git calls below would hit the real repository.
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_COMMON_DIR

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GUARD="$REPO_ROOT/global/hooks/git-push-merged-branch-guard.py"
PASS=0
FAIL=0

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

FIXTURES="$TMP/fixtures"
STUBBIN="$TMP/bin"
mkdir -p "$FIXTURES" "$STUBBIN"

# Stub gh: answers `gh pr view <branch> --json ...` from
# $GH_FIXTURES/pr-<branch-with-slashes-flattened>.json. Anything else, or a
# missing fixture, exits 1 — the "no PR" / "gh unreachable" shape.
cat >"$STUBBIN/gh" <<'STUB'
#!/usr/bin/env bash
[ "${GH_BROKEN:-0}" = "1" ] && exit 1
[ "${1:-}" = "pr" ] || exit 1
[ "${2:-}" = "view" ] || exit 1
branch="${3:-}"
f="$GH_FIXTURES/pr-${branch//\//-}.json"
[ -f "$f" ] || exit 1
cat "$f"
STUB
chmod +x "$STUBBIN/gh"

export GH_FIXTURES="$FIXTURES"
export PATH="$STUBBIN:$PATH"

pr_fixture() { # pr_fixture <branch> <state> [mergedAt]
  local branch="$1" state="$2" merged="${3:-}"
  python3 - "$FIXTURES/pr-${branch//\//-}.json" "$state" "$merged" <<'PY'
import json, sys
path, state, merged = sys.argv[1], sys.argv[2], sys.argv[3]
json.dump({"number": 1, "state": state, "mergedAt": merged or None}, open(path, "w"))
PY
}

# Fixture repo. HEAD sits on a branch whose PR is MERGED — the failing shape.
REPO="$TMP/repo"
mkdir -p "$REPO"
git -C "$REPO" init -q -b main
echo x >"$REPO/f"
git -C "$REPO" add -A
git -C "$REPO" -c user.email=t@e -c user.name=t commit -qm init

on_branch() { # on_branch <name> — put the fixture repo's HEAD on <name>
  git -C "$REPO" checkout -q -B "$1"
}

payload() { # payload <command> [cwd]
  python3 - "$1" "${2:-$REPO}" <<'PY'
import json, sys
print(json.dumps({"tool_name": "Bash", "tool_input": {"command": sys.argv[1]}, "cwd": sys.argv[2]}))
PY
}

run() { # run <command> [cwd] -> sets OUT (stdout) and ERR (stderr)
  local cmd="$1" cwd="${2:-$REPO}"
  local errfile="$TMP/err"
  set +e
  OUT="$(payload "$cmd" "$cwd" | python3 "$GUARD" 2>"$errfile")"
  set -e
  ERR="$(cat "$errfile")"
}

expect() { # expect <allow|deny> <name> <command> [cwd]
  local want="$1" name="$2" cmd="$3" cwd="${4:-$REPO}"
  local got
  run "$cmd" "$cwd"
  if grep -q '"permissionDecision": "deny"' <<<"$OUT"; then got=deny; else got=allow; fi
  if [[ "$got" == "$want" ]]; then
    PASS=$((PASS + 1))
    echo "  ok: $name"
  else
    FAIL=$((FAIL + 1))
    echo "  FAIL: $name (wanted $want, got $got)" >&2
  fi
}

expect_msg() { # expect_msg <substring> <name> <command> [cwd]
  local want="$1" name="$2" cmd="$3" cwd="${4:-$REPO}"
  run "$cmd" "$cwd"
  if grep -qF -- "$want" <<<"$OUT"; then
    PASS=$((PASS + 1))
    echo "  ok: $name"
  else
    FAIL=$((FAIL + 1))
    echo "  FAIL: $name (message lacked '$want')" >&2
  fi
}

expect_stderr() { # expect_stderr <substring|-none> <name> <command> [cwd]
  local want="$1" name="$2" cmd="$3" cwd="${4:-$REPO}"
  local ok=1
  run "$cmd" "$cwd"
  if [ "$want" = "-none" ]; then
    [ -z "$ERR" ] || ok=0
  else
    grep -qF -- "$want" <<<"$ERR" || ok=0
  fi
  if [ "$ok" = 1 ]; then
    PASS=$((PASS + 1))
    echo "  ok: $name"
  else
    FAIL=$((FAIL + 1))
    echo "  FAIL: $name (stderr was '$ERR')" >&2
  fi
}

echo "git-push-merged-branch-guard self-test"

pr_fixture "feature/merged" MERGED "2026-07-20T00:00:00Z"
pr_fixture "feature/open" OPEN
pr_fixture "feature/closed" CLOSED
pr_fixture "main" MERGED "2026-07-20T00:00:00Z"

# --- the failure this guard exists for --------------------------------------
on_branch feature/merged
expect deny "push to a branch whose PR is MERGED" "git push"
# Assert the RUNNABLE recovery, not the word. A bare "cherry-pick" substring
# also matches the surrounding prose, so a mutant that guts the prose still
# passes it — the recurring assertion trap in this repo (#366).
expect_msg "git cherry-pick <sha>" "the denial names a runnable cherry-pick" \
  "git push"
expect_msg "git checkout -b <new-branch> origin/main" \
  "the denial names how to get a fresh branch" "git push"
expect_msg "never force-push" "the denial warns off a force-push" "git push"
expect deny "push -u to a merged branch" "git push -u origin feature/merged"
expect deny "push after &&" "make check && git push"
expect deny "explicit refspec naming a merged branch" \
  "git push origin feature/merged"
# `src:dst` writes dst, so dst is the branch whose PR state matters.
on_branch feature/open
expect deny "src:dst refspec resolves the DESTINATION branch" \
  "git push origin HEAD:feature/merged"
expect deny "fully-qualified refs/heads refspec" \
  "git push origin refs/heads/feature/merged"

# The trunk is never the shape this guard is about, even though `main` here
# has a MERGED PR fixture — every merged PR's base does.
on_branch main
expect allow "push to trunk is out of scope" "git push"

# --- everything else is allowed ---------------------------------------------
on_branch feature/open
expect allow "push to a branch whose PR is OPEN" "git push"
expect_stderr -none "an OPEN PR pushes silently" "git push"

on_branch feature/nopr
expect allow "push to a branch with no PR" "git push"

on_branch feature/merged
expect allow "non-push git command" "git status"
expect allow "non-git command" "ls -la"
expect allow "branch deletion is not a push of work" \
  "git push origin --delete feature/merged"
expect allow "tag push carries no branch" "git push --tags"

# gh unreachable must not block every push in the repo — the fail-open
# doctrine #309 set, and the reason this is not modeled on #264's write path.
export GH_BROKEN=1
expect allow "gh unavailable fails OPEN" "git push"
unset GH_BROKEN

# Not a git repo at all: nothing to resolve, nothing to guard.
NOTGIT="$TMP/notgit"
mkdir -p "$NOTGIT"
expect allow "non-git cwd" "git push" "$NOTGIT"

# --- CLOSED-unmerged: allow, but say so -------------------------------------
# A closed-unmerged branch is sometimes revived deliberately, so denying it
# would manufacture a false deny. It still has the silent shape, so it warns.
on_branch feature/closed
expect allow "CLOSED-unmerged PR is allowed" "git push"
expect_stderr "CLOSED" "CLOSED-unmerged PR warns on stderr" "git push"
expect_stderr "no open PR" "the CLOSED notice explains the consequence" "git push"

# --- inert data is not an invocation (the #388 lesson, same repo, same week) -
on_branch feature/merged
expect allow "inert: git push inside an echo" \
  "echo \"next step: git push\""
expect allow "inert: git push in a comment" "# git push"
expect allow "inert: git push as a grep pattern" "grep -rn 'git push' docs/"

echo
if [ "$FAIL" -gt 0 ]; then
  echo "  $PASS passed, $FAIL FAILED" >&2
  exit 1
fi
echo "  all $PASS checks pass"

#!/usr/bin/env bash
# test-objective-worktree.sh — fixture tests for bin/objective-worktree.sh.
# Covers issue-work-loop pressure tests 1, 2, 4, 12: fresh-origin base even
# when local main is stale; dirty primary untouched; fail-closed on
# existing branch / occupied worktree; provenance in the READY line.
set -uo pipefail
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_COMMON_DIR

HELPER="$(cd "$(dirname "$0")" && pwd)/objective-worktree.sh"
PASS=0
FAIL=0

pass() {
  PASS=$((PASS + 1))
  echo "  ✓ $1"
}
fail() {
  FAIL=$((FAIL + 1))
  echo "  ✗ $1"
}

# make_sandbox <dir> — a bare origin with one commit on main, plus a clone.
# Prints the clone path on stdout.
make_sandbox() {
  local root="$1"
  git init -q --bare "$root/origin.git"
  git clone -q "$root/origin.git" "$root/work" 2>/dev/null
  git -C "$root/work" config user.email t@e.st
  git -C "$root/work" config user.name tester
  git -C "$root/work" checkout -q -b main
  echo seed >"$root/work/seed.txt"
  git -C "$root/work" add -A
  git -C "$root/work" commit -qm seed
  git -C "$root/work" push -q origin main 2>/dev/null
  echo "$root/work"
}

# advance_origin <clone> — add a commit to origin/main that the clone's local
# main does not have yet (simulates a stale local main). Prints the new SHA.
advance_origin() {
  local work="$1" tmp
  tmp="$(mktemp -d)"
  git clone -q "$(git -C "$work" remote get-url origin)" "$tmp/c" 2>/dev/null
  git -C "$tmp/c" config user.email t@e.st
  git -C "$tmp/c" config user.name tester
  git -C "$tmp/c" checkout -q main
  echo more >"$tmp/c/more.txt"
  git -C "$tmp/c" add -A
  git -C "$tmp/c" commit -qm more
  git -C "$tmp/c" push -q origin main 2>/dev/null
  git -C "$tmp/c" rev-parse HEAD
  rm -rf "$tmp"
}

# Case 1 (PT1): base is the fresh origin/main SHA, even when local main is stale.
T="$(mktemp -d)"
W="$(make_sandbox "$T")"
NEW_SHA="$(advance_origin "$W")"
OUT="$(cd "$W" && "$HELPER" feature/x)"
RC=$?
LINE1="$(printf '%s\n' "$OUT" | head -1)"
if [ "$RC" -eq 0 ] && printf '%s' "$LINE1" | grep -q "^READY: " &&
  printf '%s' "$LINE1" | grep -q "$NEW_SHA"; then
  pass "PT1: base SHA is fresh origin/main ($NEW_SHA), not stale local main"
else
  fail "PT1: expected READY with base-sha $NEW_SHA, got: $LINE1 (rc=$RC)"
fi
rm -rf "$T"

# Case 2 (PT2): a dirty primary checkout is left untouched.
T="$(mktemp -d)"
W="$(make_sandbox "$T")"
echo dirty >"$W/uncommitted.txt"
HEAD_BEFORE="$(git -C "$W" rev-parse HEAD)"
OUT="$(cd "$W" && "$HELPER" feature/y)"
RC=$?
STILL_DIRTY="$(git -C "$W" status --porcelain | grep -c uncommitted.txt)"
HEAD_AFTER="$(git -C "$W" rev-parse HEAD)"
if [ "$RC" -eq 0 ] && [ "$STILL_DIRTY" -eq 1 ] && [ "$HEAD_BEFORE" = "$HEAD_AFTER" ] &&
  [ -d "$W/.worktrees/y" ]; then
  pass "PT2: worktree created; primary tree still dirty; primary HEAD unmoved"
else
  fail "PT2: primary checkout disturbed (rc=$RC dirty=$STILL_DIRTY head==$([ "$HEAD_BEFORE" = "$HEAD_AFTER" ] && echo y || echo n))"
fi
rm -rf "$T"

# Case 3 (PT4a): an existing branch fails closed.
T="$(mktemp -d)"
W="$(make_sandbox "$T")"
git -C "$W" branch feature/z
OUT="$(cd "$W" && "$HELPER" feature/z)"
RC=$?
LINE1="$(printf '%s\n' "$OUT" | head -1)"
if [ "$RC" -eq 10 ] && printf '%s' "$LINE1" | grep -q "^BLOCKED: branch-exists"; then
  pass "PT4a: existing branch -> BLOCKED: branch-exists (exit 10)"
else
  fail "PT4a: expected BLOCKED: branch-exists exit 10, got: $LINE1 (rc=$RC)"
fi
rm -rf "$T"

# Case 4 (PT4b): an occupied worktree path fails closed.
T="$(mktemp -d)"
W="$(make_sandbox "$T")"
mkdir -p "$W/.worktrees/occupied"
OUT="$(cd "$W" && "$HELPER" feature/occupied)"
RC=$?
LINE1="$(printf '%s\n' "$OUT" | head -1)"
if [ "$RC" -eq 10 ] && printf '%s' "$LINE1" | grep -q "^BLOCKED: worktree-occupied"; then
  pass "PT4b: occupied path -> BLOCKED: worktree-occupied (exit 10)"
else
  fail "PT4b: expected BLOCKED: worktree-occupied exit 10, got: $LINE1 (rc=$RC)"
fi
rm -rf "$T"

# Case 5: an unresolvable base fails closed.
T="$(mktemp -d)"
W="$(make_sandbox "$T")"
OUT="$(cd "$W" && "$HELPER" feature/q --base origin/does-not-exist --no-fetch)"
RC=$?
LINE1="$(printf '%s\n' "$OUT" | head -1)"
if [ "$RC" -eq 10 ] && printf '%s' "$LINE1" | grep -q "^BLOCKED: base-unavailable"; then
  pass "base-unavailable: unresolvable --base -> BLOCKED (exit 10)"
else
  fail "base-unavailable: expected BLOCKED: base-unavailable, got: $LINE1 (rc=$RC)"
fi
rm -rf "$T"

# Case 6: no origin remote -> ERROR.
T="$(mktemp -d)"
git init -q "$T/solo"
git -C "$T/solo" config user.email t@e.st
git -C "$T/solo" config user.name tester
git -C "$T/solo" checkout -q -b main
echo a >"$T/solo/a"
git -C "$T/solo" add -A
git -C "$T/solo" commit -qm a
OUT="$(cd "$T/solo" && "$HELPER" feature/x --no-fetch)"
RC=$?
LINE1="$(printf '%s\n' "$OUT" | head -1)"
if [ "$RC" -eq 1 ] && printf '%s' "$LINE1" | grep -q "^ERROR:"; then
  pass "no-origin: ERROR (exit 1)"
else
  fail "no-origin: expected ERROR exit 1, got: $LINE1 (rc=$RC)"
fi
rm -rf "$T"

# Case 7: --check creates nothing but prints READY.
T="$(mktemp -d)"
W="$(make_sandbox "$T")"
OUT="$(cd "$W" && "$HELPER" feature/dry --check)"
RC=$?
LINE1="$(printf '%s\n' "$OUT" | head -1)"
if [ "$RC" -eq 0 ] && printf '%s' "$LINE1" | grep -q "^READY: " && [ ! -d "$W/.worktrees/dry" ]; then
  pass "--check: prints READY, creates no worktree"
else
  fail "--check: expected READY with nothing created, got: $LINE1 (rc=$RC, dir=$([ -d "$W/.worktrees/dry" ] && echo exists || echo none))"
fi
rm -rf "$T"

# Case 8 (PT12): the READY line carries all four provenance fields.
T="$(mktemp -d)"
W="$(make_sandbox "$T")"
BASE_SHA="$(git -C "$W" rev-parse origin/main)"
OUT="$(cd "$W" && "$HELPER" feature/prov --check)"
LINE1="$(printf '%s\n' "$OUT" | head -1)"
# READY: <path> <branch> <base-ref> <base-sha>  -> 5 fields incl. token
NFIELDS="$(printf '%s' "$LINE1" | awk '{print NF}')"
if [ "$NFIELDS" -eq 5 ] &&
  printf '%s' "$LINE1" | grep -q "\.worktrees/prov" &&
  printf '%s' "$LINE1" | grep -q " feature/prov " &&
  printf '%s' "$LINE1" | grep -q " origin/main " &&
  printf '%s' "$LINE1" | grep -q " $BASE_SHA$"; then
  pass "PT12: READY line carries path, branch, base-ref, base-sha"
else
  fail "PT12: provenance fields missing, got: $LINE1"
fi
rm -rf "$T"

# Case 9: missing <branch> -> usage error (exit 64).
OUT="$("$HELPER" 2>&1)"
RC=$?
if [ "$RC" -eq 64 ]; then
  pass "usage: missing branch -> exit 64"
else
  fail "usage: expected exit 64, got rc=$RC"
fi

# Case 10: invoked from inside a linked worktree -> sibling under the
# PRIMARY checkout, not nested under the calling worktree. Regression test
# for Fix 1 (primary-checkout resolution via git-common-dir).
T="$(mktemp -d)"
W="$(make_sandbox "$T")"
W_PHYS="$(cd "$W" && pwd -P)" # physical path: git resolves symlinks (e.g. macOS /var -> /private/var)
git -C "$W" worktree add -q "$W/.worktrees/existing" -b feature/existing HEAD
OUT="$(cd "$W/.worktrees/existing" && "$HELPER" feature/sib --check --no-fetch --base HEAD)"
RC=$?
LINE1="$(printf '%s\n' "$OUT" | head -1)"
if [ "$RC" -eq 0 ] && printf '%s' "$LINE1" | grep -q "^READY: $W_PHYS/.worktrees/sib "; then
  pass "from-worktree: sibling under primary '$W_PHYS/.worktrees/sib', not nested"
else
  fail "from-worktree: expected READY: $W_PHYS/.worktrees/sib ..., got: $LINE1 (rc=$RC)"
fi
rm -rf "$T"

# Case 11: origin unavailable during fetch -> BLOCKED: origin-unavailable
# (fail-closed branch, previously untested).
T="$(mktemp -d)"
W="$(make_sandbox "$T")"
git -C "$W" remote set-url origin /nonexistent/definitely-not-here.git
OUT="$(cd "$W" && "$HELPER" feature/of 2>/dev/null)"
RC=$?
LINE1="$(printf '%s\n' "$OUT" | head -1)"
if [ "$RC" -eq 10 ] && printf '%s' "$LINE1" | grep -q "^BLOCKED: origin-unavailable"; then
  pass "origin-unavailable: fetch failure -> BLOCKED (exit 10)"
else
  fail "origin-unavailable: expected BLOCKED: origin-unavailable exit 10, got: $LINE1 (rc=$RC)"
fi
rm -rf "$T"

echo
echo "objective-worktree: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]

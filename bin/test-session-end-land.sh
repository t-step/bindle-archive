#!/usr/bin/env bash
#
# test-session-end-land.sh — exercise bin/session-end-land.sh against throwaway
# git fixtures, each with a bare `origin` remote so origin/main comparisons work
# offline. Never touches the network or a real repo.
#
set -uo pipefail
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_COMMON_DIR

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LAND="$REPO_ROOT/bin/session-end-land.sh"

pass=0 fail=0
ok() {
  printf '  \342\234\223 %s\n' "$1"
  pass=$((pass + 1))
}
bad() {
  printf '  \342\234\227 %s\n' "$1"
  fail=$((fail + 1))
}

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

cfg() { # cfg <repo> — deterministic identity
  git -C "$1" config user.email t@e.st
  git -C "$1" config user.name t
}

# new_fixture <tag> — bare origin seeded with a `main` containing one commit;
# clone it and echo the clone's path (has `origin` remote + origin/main).
new_fixture() {
  # shellcheck disable=SC2034 # tag documents the arg; up/seed/repo use $1 directly
  local tag="$1" up="$TMP/up.$1" seed="$TMP/seed.$1" repo="$TMP/repo.$1"
  git init -q --bare "$up"
  git init -q "$seed"
  cfg "$seed"
  git -C "$seed" checkout -q -b main
  : >"$seed/base"
  git -C "$seed" add base
  git -C "$seed" commit -qm base
  git -C "$seed" remote add origin "$up"
  git -C "$seed" push -q origin main
  git clone -q "$up" "$repo"
  cfg "$repo"
  echo "$repo"
}

# run <repo> [args...] — sets $code and $out from the helper
run() {
  local repo="$1"
  shift
  out="$(cd "$repo" && "$LAND" "$@" 2>&1)"
  code=$?
}

# --- SAFE: on a merged feature branch -> lands on main, reports deletable ---
R="$(new_fixture merged)"
git -C "$R" switch -q -c feature
echo x >"$R/x"
git -C "$R" add x
git -C "$R" commit -qm "feat: x"
git -C "$R" switch -q main
git -C "$R" merge -q --ff-only feature
git -C "$R" push -q origin main
git -C "$R" switch -q feature # end the "session" on the merged branch
run "$R"
# shellcheck disable=SC2015
[ "$code" -eq 0 ] && head -1 <<<"$out" | grep -qx "SAFE" &&
  ok "merged branch -> SAFE exit 0" || bad "merged branch verdict ($code): $out"
# shellcheck disable=SC2015
[ "$(git -C "$R" branch --show-current)" = "main" ] &&
  ok "merged branch -> landed on main" || bad "merged branch not on main"
# shellcheck disable=SC2015
grep -q "git branch -d feature" <<<"$out" &&
  ok "merged branch reported safe-to-delete" || bad "no delete suggestion: $out"
# shellcheck disable=SC2015
git -C "$R" rev-parse --verify -q feature >/dev/null &&
  ok "merged branch not actually deleted" || bad "branch was deleted"

# --- SAFE: local main behind origin/main -> fast-forwards ---
R="$(new_fixture behind)"
# advance origin/main via a second clone, leaving R's main behind
git clone -q "$TMP/up.behind" "$TMP/other.behind"
cfg "$TMP/other.behind"
echo y >"$TMP/other.behind/y"
git -C "$TMP/other.behind" add y
git -C "$TMP/other.behind" commit -qm "feat: y"
git -C "$TMP/other.behind" push -q origin main
run "$R" # helper fetches, then ff
# shellcheck disable=SC2015
[ "$code" -eq 0 ] && head -1 <<<"$out" | grep -qx "SAFE" &&
  ok "behind main -> SAFE exit 0" || bad "behind verdict ($code): $out"
# shellcheck disable=SC2015
git -C "$R" merge-base --is-ancestor origin/main main &&
  ok "behind main -> fast-forwarded" || bad "behind main not ff'd"

# --- SAFE: already on clean up-to-date main -> no-op ---
R="$(new_fixture clean)"
run "$R"
# shellcheck disable=SC2015
[ "$code" -eq 0 ] && head -1 <<<"$out" | grep -qx "SAFE" &&
  ok "clean main -> SAFE no-op" || bad "clean main verdict ($code): $out"

# --- BLOCKED: dirty tree -> no mutation ---
R="$(new_fixture dirty)"
echo mut >>"$R/base" # modify a tracked file
run "$R"
# shellcheck disable=SC2015
[ "$code" -eq 10 ] && head -1 <<<"$out" | grep -qx "BLOCKED: dirty-tree" &&
  ok "dirty tree -> BLOCKED exit 10" || bad "dirty verdict ($code): $out"
git -C "$R" diff --quiet || dirty_kept=1
# shellcheck disable=SC2015
[ "${dirty_kept:-0}" = 1 ] && ok "dirty tree -> changes untouched" || bad "dirty change lost"

# --- BLOCKED: unmerged branch -> no mutation, stays on branch ---
R="$(new_fixture unmerged)"
git -C "$R" switch -q -c feature
echo z >"$R/z"
git -C "$R" add z
git -C "$R" commit -qm "feat: z" # never merged to origin/main
run "$R"
# shellcheck disable=SC2015
[ "$code" -eq 10 ] && head -1 <<<"$out" | grep -qx "BLOCKED: branch-unmerged" &&
  ok "unmerged -> BLOCKED exit 10" || bad "unmerged verdict ($code): $out"
# shellcheck disable=SC2015
[ "$(git -C "$R" branch --show-current)" = "feature" ] &&
  ok "unmerged -> stayed on feature" || bad "unmerged switched away"

# --- BLOCKED: local main diverged (local-only commit) -> no mutation ---
R="$(new_fixture diverged)"
echo d >"$R/d"
git -C "$R" add d
git -C "$R" commit -qm "local: d" # on main, not pushed
run "$R"
# shellcheck disable=SC2015
[ "$code" -eq 10 ] && head -1 <<<"$out" | grep -qx "BLOCKED: main-diverged" &&
  ok "diverged -> BLOCKED exit 10" || bad "diverged verdict ($code): $out"

# --- --check on a SAFE case -> verdict only, no mutation ---
R="$(new_fixture check)"
git clone -q "$TMP/up.check" "$TMP/other.check"
cfg "$TMP/other.check"
echo c >"$TMP/other.check/c"
git -C "$TMP/other.check" add c
git -C "$TMP/other.check" commit -qm "feat: c"
git -C "$TMP/other.check" push -q origin main
before="$(git -C "$R" rev-parse HEAD)"
run "$R" --check
# shellcheck disable=SC2015
[ "$code" -eq 0 ] && head -1 <<<"$out" | grep -qx "SAFE" &&
  ok "--check -> SAFE exit 0" || bad "--check verdict ($code): $out"
# shellcheck disable=SC2015
[ "$(git -C "$R" rev-parse HEAD)" = "$before" ] &&
  ok "--check -> HEAD unchanged" || bad "--check mutated HEAD"

# --- SAFE-path failure: main checked out in another worktree -> ERROR, no false SAFE ---
R="$(new_fixture switchfail)"
git -C "$R" switch -q -c feature
echo w >"$R/w"
git -C "$R" add w
git -C "$R" commit -qm "feat: w"
git -C "$R" switch -q main
git -C "$R" merge -q --ff-only feature
git -C "$R" push -q origin main
git -C "$R" switch -q feature                         # end the "session" on the merged branch
git -C "$R" worktree add -q "$TMP/wt.switchfail" main # main now checked out elsewhere
run "$R"
# shellcheck disable=SC2015
[ "$code" -eq 1 ] && head -1 <<<"$out" | grep -q "^ERROR:" &&
  ok "switch failure -> ERROR exit 1 (no false SAFE)" || bad "switch-fail verdict ($code): $out"
# shellcheck disable=SC2015
[ "$(git -C "$R" branch --show-current)" = "feature" ] &&
  ok "switch failure -> stayed on feature" || bad "switch-fail moved HEAD"

printf '\n%d passed, %d failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]

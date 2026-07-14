#!/usr/bin/env bash
#
# test-domi-status.sh — exercise bin/domi-status.sh against throwaway fixture
# repos. Never touches a real DomI-consumer repo (issue #58). Delegation cases
# (current/behind/forked) require DomI's offline_drift_check.sh to be locatable;
# when it is not, those cases SKIP (honest degraded coverage), never fail.
#
set -uo pipefail
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_COMMON_DIR

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DS="$REPO_ROOT/bin/domi-status.sh"

pass=0 fail=0 skip=0
ok() {
  printf '  ✓ %s\n' "$1"
  pass=$((pass + 1))
}
bad() {
  printf '  ✗ %s\n' "$1"
  fail=$((fail + 1))
}
skipt() {
  printf '  ⊘ %s (skipped: %s)\n' "$1" "$2"
  skip=$((skip + 1))
}

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# make_consumer <dir> <sha> <manifest_sha256> — write a fixture repo with a pin.
make_consumer() {
  local dir="$1" sha="$2" mhash="$3"
  mkdir -p "$dir"
  cat >"$dir/.domi-pin" <<EOF
upstream: domattioli/DomI
branch: main
sha: $sha
manifest_sha256: $mhash
pinned_at: 2026-07-13T00:00:00Z
EOF
}

# run_ds <target-repo> [env VAR=val ...] — echo exit code, capture stdout+stderr
# via files the caller reads.
OUT=""
ERR=""
CODE=0
run_ds() {
  local target="$1"
  shift
  OUT="$TMP/out"
  ERR="$TMP/err"
  env "$@" bash "$DS" --repo "$target" >"$OUT" 2>"$ERR"
  CODE=$?
}

FORTY="$(printf 'a%.0s' {1..40})" # 40 'a's — a valid-shaped SHA

# --- not-a-domi-consumer ---
mkdir -p "$TMP/plain"
run_ds "$TMP/plain"
# shellcheck disable=SC2015
[ "$CODE" -eq 2 ] && grep -q "not-a-domi-consumer" "$OUT" &&
  ok "no .domi-pin → not-a-domi-consumer (exit 2)" ||
  bad "no .domi-pin → not-a-domi-consumer (exit 2) [got $CODE]"

# --- malformed: bad sha ---
make_consumer "$TMP/bad" "not-a-sha" "$(printf 'b%.0s' {1..64})"
run_ds "$TMP/bad"
# shellcheck disable=SC2015
[ "$CODE" -eq 5 ] && grep -qi "malformed" "$ERR" && grep -qi "sha" "$ERR" &&
  ok "bad sha → malformed (exit 5) naming the field" ||
  bad "bad sha → malformed (exit 5) naming the field [got $CODE]"

# --- malformed: missing upstream ---
mkdir -p "$TMP/noup"
printf 'branch: main\nsha: %s\n' "$FORTY" >"$TMP/noup/.domi-pin"
run_ds "$TMP/noup"
# shellcheck disable=SC2015
[ "$CODE" -eq 5 ] && grep -qi "upstream" "$ERR" &&
  ok "missing upstream → malformed (exit 5)" ||
  bad "missing upstream → malformed (exit 5) [got $CODE]"

# --- unverifiable: valid pin, no DomI reachable ---
make_consumer "$TMP/unv" "$FORTY" "$(printf 'c%.0s' {1..64})"
# Force the locators to find nothing.
run_ds "$TMP/unv" DOMI_SCRIPTS_DIR=/nonexistent DOMI_LOCAL_CHECKOUT=/nonexistent
# shellcheck disable=SC2015
[ "$CODE" -eq 4 ] && grep -qi "unverifiable" "$OUT" && grep -q "pin: domattioli/DomI@aaaaaaa" "$OUT" &&
  ok "valid pin, no DomI → unverifiable (exit 4) + reports pin facts" ||
  bad "valid pin, no DomI → unverifiable (exit 4) + pin facts [got $CODE]"

# --- usage error: unknown flag ---
OUT="$TMP/out"
ERR="$TMP/err"
bash "$DS" --bogus >"$OUT" 2>"$ERR"
CODE=$?
# shellcheck disable=SC2015
[ "$CODE" -eq 64 ] && grep -q "unknown argument" "$ERR" &&
  ok "unknown flag --bogus → usage error (exit 64)" ||
  bad "unknown flag --bogus → usage error (exit 64) [got $CODE]"

# --- usage error: --repo with no value (guard against infinite loop) ---
OUT="$TMP/out"
ERR="$TMP/err"
if command -v timeout >/dev/null 2>&1; then
  timeout 5 bash "$DS" --repo >"$OUT" 2>"$ERR"
  CODE=$?
  # shellcheck disable=SC2015
  if [ "$CODE" -eq 124 ]; then
    bad "--repo no value → usage error (exit 64) [TIMEOUT, infinite loop]"
  elif [ "$CODE" -eq 64 ] && grep -q "requires a path" "$ERR"; then
    ok "--repo no value → usage error (exit 64)"
  else
    bad "--repo no value → usage error (exit 64) [got $CODE]"
  fi
else
  bash "$DS" --repo >"$OUT" 2>"$ERR" &
  pid=$!
  sleep 1
  if kill -0 "$pid" 2>/dev/null; then
    kill "$pid" 2>/dev/null || true
    bad "--repo no value → usage error (exit 64) [TIMEOUT, infinite loop]"
  else
    wait "$pid"
    CODE=$?
    # shellcheck disable=SC2015
    if [ "$CODE" -eq 64 ] && grep -q "requires a path" "$ERR"; then
      ok "--repo no value → usage error (exit 64)"
    else
      bad "--repo no value → usage error (exit 64) [got $CODE]"
    fi
  fi
fi

printf '\n%d passed, %d failed, %d skipped\n' "$pass" "$fail" "$skip"
[ "$fail" -eq 0 ]

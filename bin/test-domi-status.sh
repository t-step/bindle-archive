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
[ "$CODE" -eq 4 ] &&
  grep -qi "unverifiable" "$OUT" &&
  grep -q "pin: domattioli/DomI@aaaaaaa" "$OUT" &&
  grep -q "authority: domattioli/DomI (inherited:" "$OUT" &&
  grep -q "branch-commit-discipline" "$OUT" &&
  ok "valid pin, no DomI → unverifiable (exit 4) + pin facts + authority block" ||
  bad "valid pin, no DomI → unverifiable + pin facts + authority block [got $CODE]"

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

# --- delegation cases: require DomI's offline_drift_check.sh ---
find_odc() {
  if [ -n "${DOMI_SCRIPTS_DIR+x}" ]; then
    # Env var set: use only that path
    [ -n "$DOMI_SCRIPTS_DIR" ] && [ -f "$DOMI_SCRIPTS_DIR/offline_drift_check.sh" ] && {
      echo "$DOMI_SCRIPTS_DIR/offline_drift_check.sh"
      return 0
    }
  else
    # Env var not set: check defaults
    if [ -f "$HOME/.claude/skills/sync-from-domi/scripts/offline_drift_check.sh" ]; then
      echo "$HOME/.claude/skills/sync-from-domi/scripts/offline_drift_check.sh"
      return 0
    fi
  fi
  return 1
}

if ODC="$(find_odc)"; then
  # Build a fixture DomI checkout: a git repo with a MANIFEST.md at a known SHA.
  DOMI="$TMP/DomI"
  mkdir -p "$DOMI"
  git -C "$DOMI" init -q -b main
  git -C "$DOMI" config user.email t@t.t
  git -C "$DOMI" config user.name t
  printf 'fixture manifest\n' >"$DOMI/MANIFEST.md"
  git -C "$DOMI" add MANIFEST.md
  git -C "$DOMI" commit -qm init
  DHEAD="$(git -C "$DOMI" rev-parse HEAD)"
  DMHASH="$(git -C "$DOMI" show HEAD:MANIFEST.md | sha256sum | awk '{print $1}')"
  SCRIPTS_DIR="$(dirname "$ODC")"

  # current: pin sha == DomI HEAD, manifest hash matches.
  make_consumer "$TMP/cur" "$DHEAD" "$DMHASH"
  run_ds "$TMP/cur" DOMI_SCRIPTS_DIR="$SCRIPTS_DIR" DOMI_LOCAL_CHECKOUT="$DOMI"
  # shellcheck disable=SC2015
  [ "$CODE" -eq 0 ] && grep -q "current" "$OUT" &&
    ok "pin at HEAD → current (exit 0)" ||
    bad "pin at HEAD → current (exit 0) [got $CODE]"

  # behind: pin sha != DomI HEAD.
  make_consumer "$TMP/beh" "$FORTY" "$DMHASH"
  run_ds "$TMP/beh" DOMI_SCRIPTS_DIR="$SCRIPTS_DIR" DOMI_LOCAL_CHECKOUT="$DOMI"
  # shellcheck disable=SC2015
  [ "$CODE" -eq 1 ] && grep -q "behind" "$OUT" &&
    ok "pin behind HEAD → behind (exit 1)" ||
    bad "pin behind HEAD → behind (exit 1) [got $CODE]"

  # forked: pin sha == HEAD but manifest hash wrong.
  make_consumer "$TMP/fork" "$DHEAD" "$(printf 'd%.0s' {1..64})"
  run_ds "$TMP/fork" DOMI_SCRIPTS_DIR="$SCRIPTS_DIR" DOMI_LOCAL_CHECKOUT="$DOMI"
  # shellcheck disable=SC2015
  [ "$CODE" -eq 3 ] && grep -q "forked" "$OUT" &&
    ok "manifest mismatch → forked (exit 3)" ||
    bad "manifest mismatch → forked (exit 3) [got $CODE]"
else
  skipt "delegation (current/behind/forked)" "DomI offline_drift_check.sh not found"
fi

printf '\n%d passed, %d failed, %d skipped\n' "$pass" "$fail" "$skip"
[ "$fail" -eq 0 ]

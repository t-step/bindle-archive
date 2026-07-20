#!/usr/bin/env bash
#
# test-check-finding-codes.sh — exercise bin/check-finding-codes.py against
# throwaway fixture trees. Each case builds a tiny surface (an
# invariant-coverage.json plus a source file that emits codes) and runs the
# checker against it with --root, so nothing touches this repo.
#
# The last case runs the checker against THIS repo, which is the acceptance
# the issue asks for: every finding code a validator can emit is either
# classified or explicitly excluded, with a reason.
#
# Usage: bin/test-check-finding-codes.sh
#
set -uo pipefail

# Under a git hook, git exports GIT_DIR and friends; scrub them so a fixture
# tree can never resolve back to the real repository.
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_COMMON_DIR

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CHECKER="$REPO_ROOT/bin/check-finding-codes.py"

pass=0 fail=0
check() { # check "description" command...
  local desc="$1"
  shift
  if "$@"; then
    printf '  ✓ %s\n' "$desc"
    pass=$((pass + 1))
  else
    printf '  ✗ %s\n' "$desc"
    fail=$((fail + 1))
  fi
}

contains() { grep -qF -- "$1" <<<"$2"; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# build_surface DIR CODES_JSON SOURCE_BODY — a minimal one-surface tree.
build_surface() {
  local dir="$1" codes="$2" body="$3"
  rm -rf "$dir"
  mkdir -p "$dir/schemas/demo/v1" "$dir/bin/demo/tests"
  printf '%s\n' "$codes" >"$dir/schemas/demo/v1/invariant-coverage.json"
  printf '%s\n' "$body" >"$dir/bin/demo/validation.py"
  : >"$dir/bin/demo/tests/test_validation.py"
}

run_checker() { python3 "$CHECKER" --root "$1" 2>&1; }

echo "check-finding-codes:"

# --- a classified code passes ----------------------------------------------
build_surface "$TMP/clean" '{
  "schema_version": 1,
  "description": "demo",
  "sources": ["bin/demo"],
  "codes": {"E_DEMO_BAD_FIELD": "schema-and-native"}
}' 'def v():
    return {"code": "E_DEMO_BAD_FIELD"}'
out="$(run_checker "$TMP/clean")"
check "a classified emitted code passes" test $? -eq 0

# --- an unclassified code fails, and says where it came from ---------------
build_surface "$TMP/unclassified" '{
  "schema_version": 1,
  "description": "demo",
  "sources": ["bin/demo"],
  "codes": {"E_DEMO_BAD_FIELD": "schema-and-native"}
}' 'def v():
    return [{"code": "E_DEMO_BAD_FIELD"}, {"code": "E_DEMO_ORPHAN"}]'
out="$(run_checker "$TMP/unclassified")"
rc=$?
check "an emitted-but-unclassified code fails" test $rc -ne 0
check "the failure names the code" contains "E_DEMO_ORPHAN" "$out"
check "the failure names the emitting file" contains "bin/demo/validation.py" "$out"

# --- a stale classification fails ------------------------------------------
build_surface "$TMP/stale" '{
  "schema_version": 1,
  "description": "demo",
  "sources": ["bin/demo"],
  "codes": {"E_DEMO_BAD_FIELD": "schema-and-native",
            "E_DEMO_GONE": "native-only"}
}' 'def v():
    return {"code": "E_DEMO_BAD_FIELD"}'
out="$(run_checker "$TMP/stale")"
rc=$?
check "a classified-but-never-emitted code fails" test $rc -ne 0
check "the failure names the stale code" contains "E_DEMO_GONE" "$out"

# --- an explicit exclusion passes ------------------------------------------
build_surface "$TMP/excluded" '{
  "schema_version": 1,
  "description": "demo",
  "sources": ["bin/demo"],
  "codes": {"E_DEMO_BAD_FIELD": "schema-and-native"},
  "excluded_codes": {"E_DEMO_INPUT": "caller-input validation, not persisted state"}
}' 'def v():
    return [{"code": "E_DEMO_BAD_FIELD"}, {"code": "E_DEMO_INPUT"}]'
out="$(run_checker "$TMP/excluded")"
check "an explicitly excluded code passes" test $? -eq 0

# --- an exclusion without a reason fails -----------------------------------
build_surface "$TMP/noreason" '{
  "schema_version": 1,
  "description": "demo",
  "sources": ["bin/demo"],
  "codes": {"E_DEMO_BAD_FIELD": "schema-and-native"},
  "excluded_codes": {"E_DEMO_INPUT": ""}
}' 'def v():
    return [{"code": "E_DEMO_BAD_FIELD"}, {"code": "E_DEMO_INPUT"}]'
out="$(run_checker "$TMP/noreason")"
rc=$?
check "an exclusion with an empty reason fails" test $rc -ne 0
check "the empty-reason failure explains itself" contains "reason" "$out"

# --- a code both classified and excluded fails -----------------------------
build_surface "$TMP/both" '{
  "schema_version": 1,
  "description": "demo",
  "sources": ["bin/demo"],
  "codes": {"E_DEMO_BAD_FIELD": "schema-and-native"},
  "excluded_codes": {"E_DEMO_BAD_FIELD": "cannot be both"}
}' 'def v():
    return {"code": "E_DEMO_BAD_FIELD"}'
out="$(run_checker "$TMP/both")"
rc=$?
check "a code both classified and excluded fails" test $rc -ne 0
check "the conflict failure names the code" contains "E_DEMO_BAD_FIELD" "$out"

# --- codes emitted only by tests do not count ------------------------------
build_surface "$TMP/testsonly" '{
  "schema_version": 1,
  "description": "demo",
  "sources": ["bin/demo"],
  "codes": {"E_DEMO_BAD_FIELD": "schema-and-native"}
}' 'def v():
    return {"code": "E_DEMO_BAD_FIELD"}'
printf 'ASSERT = "E_DEMO_ONLY_IN_TESTS"\n' \
  >"$TMP/testsonly/bin/demo/tests/test_validation.py"
out="$(run_checker "$TMP/testsonly")"
check "a code named only under tests/ is not treated as emitted" test $? -eq 0

# --- the context-graph "invariants" list shape is understood too -----------
build_surface "$TMP/invariants" '{
  "schema_version": 1,
  "invariants": [
    { "code": "E_DEMO_BAD_FIELD", "classification": "schema-and-native" }
  ],
  "sources": ["bin/demo"]
}' 'def v():
    return {"code": "E_DEMO_BAD_FIELD"}'
out="$(run_checker "$TMP/invariants")"
check "the invariants-list coverage shape is understood" test $? -eq 0

build_surface "$TMP/invariants_gap" '{
  "schema_version": 1,
  "invariants": [
    { "code": "E_DEMO_BAD_FIELD", "classification": "schema-and-native" }
  ],
  "sources": ["bin/demo"]
}' 'def v():
    return [{"code": "E_DEMO_BAD_FIELD"}, {"code": "E_DEMO_ORPHAN"}]'
out="$(run_checker "$TMP/invariants_gap")"
rc=$?
check "a gap in the invariants-list shape still fails" test $rc -ne 0

# --- a coverage file without sources fails loudly --------------------------
build_surface "$TMP/nosources" '{
  "schema_version": 1,
  "description": "demo",
  "codes": {"E_DEMO_BAD_FIELD": "schema-and-native"}
}' 'def v():
    return {"code": "E_DEMO_BAD_FIELD"}'
out="$(run_checker "$TMP/nosources")"
rc=$?
check "a coverage file with no sources fails" test $rc -ne 0
check "the missing-sources failure explains itself" contains '"sources"' "$out"

# --- an ungoverned surface must declare itself -----------------------------
build_surface "$TMP/ungoverned_silent" '{
  "schema_version": 1,
  "description": "demo",
  "sources": [],
  "codes": {}
}' 'def v():
    return {"code": "E_DEMO_UNTRIAGED"}'
out="$(run_checker "$TMP/ungoverned_silent")"
rc=$?
check "an empty sources list without a reason fails" test $rc -ne 0
check "the failure asks for a reason" contains "ungoverned_reason" "$out"

build_surface "$TMP/ungoverned_declared" '{
  "schema_version": 1,
  "description": "demo",
  "sources": [],
  "ungoverned_reason": "runtime codes not yet triaged; tracked in demo#1",
  "codes": {}
}' 'def v():
    return {"code": "E_DEMO_UNTRIAGED"}'
out="$(run_checker "$TMP/ungoverned_declared")"
rc=$?
check "a declared-ungoverned surface passes" test $rc -eq 0
check "a clean run still reports what it did not cover" contains "not yet governed" "$out"

# --- a tree with no coverage file at all is not a silent pass --------------
mkdir -p "$TMP/nosurface/bin/demo"
printf 'X = "E_DEMO_BAD_FIELD"\n' >"$TMP/nosurface/bin/demo/validation.py"
out="$(run_checker "$TMP/nosurface")"
rc=$?
check "a tree with no invariant-coverage.json fails rather than passing vacuously" \
  test $rc -ne 0

# --- the real repository ----------------------------------------------------
out="$(run_checker "$REPO_ROOT")"
rc=$?
check "this repository's finding codes are fully accounted for" test $rc -eq 0
[ $rc -eq 0 ] || printf '%s\n' "$out" | sed 's/^/    /'

printf '\n  %d passed, %d failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]

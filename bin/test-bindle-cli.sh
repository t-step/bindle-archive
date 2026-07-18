#!/usr/bin/env bash
#
# test-bindle-cli.sh — process-level checks for the public bindle executable.
# The executable must stay a thin dispatcher over existing helpers while
# resolving its checkout through an installed symlink, not the caller's cwd.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BINDLE="$REPO_ROOT/bin/bindle"
PY="$(command -v python3)"

pass=0
fail=0
check() {
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
matches_context_node() {
  local project="$1" value="$2"
  grep -Eq "^context-node:${project}:[0-9a-f]{32}$" <<<"$value"
}

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

echo "== help + version =="
out="$("$BINDLE" --help 2>&1)"
status=$?
check "bindle --help exits zero" test "$status" -eq 0
check "help lists context command" contains "bindle context" "$out"

out="$("$BINDLE" version 2>&1)"
status=$?
check "bindle version exits zero" test "$status" -eq 0
check "version matches VERSION file" test "$out" = "$(cat "$REPO_ROOT/VERSION")"

echo "== installed symlink works outside checkout, including spaces in paths =="
BIN_DIR="$TMP/user bin"
mkdir -p "$BIN_DIR"
ln -s "$BINDLE" "$BIN_DIR/bindle"
OUTSIDE="$TMP/outside cwd"
mkdir -p "$OUTSIDE"
out="$(cd "$OUTSIDE" && "$BIN_DIR/bindle" version 2>&1)"
status=$?
check "installed symlink resolves repo root from outside checkout" test "$status" -eq 0
check "installed symlink prints version" test "$out" = "$(cat "$REPO_ROOT/VERSION")"

echo "== dispatcher preserves helper behavior =="
DOCTOR_HOME="$TMP/doctor home"
mkdir -p "$DOCTOR_HOME"
out="$(PATH="$BIN_DIR:$PATH" "$BIN_DIR/bindle" doctor --home "$DOCTOR_HOME" --bin-dir "$BIN_DIR" 2>&1)"
status=$?
check "bindle doctor forwards to doctor helper" test "$status" -eq 1
check "doctor stdout content is from helper" contains "Bindle v$(cat "$REPO_ROOT/VERSION")" "$out"

out="$("$BIN_DIR/bindle" map allocate --project cli-test 2>&1)"
status=$?
check "bindle map forwards to map helper" test "$status" -eq 0
check "map allocate stdout preserved" matches_context_node cli-test "$out"

out="$("$BIN_DIR/bindle" evidence normalize --project-id project:5f56c9b95c41c298f70d6dd4e5db8c2a \
  --value 'sessions/2026-07-18-note.md' 2>&1)"
status=$?
check "bindle evidence forwards to evidence helper" test "$status" -eq 0
check "evidence stdout preserved" contains '"status": "normalized"' "$out"

NH="$TMP/notes home"
out="$(BINDLE_NOTES_DIR="$NH" "$BIN_DIR/bindle" context init --project cli-proj 2>&1)"
status=$?
check "bindle context injects BINDLE_NOTES_DIR default" test "$status" -eq 0
check "context init created project under BINDLE_NOTES_DIR" test -f "$NH/projects/cli-proj/.bindle/context/config.json"

out="$(BINDLE_NOTES_DIR="$NH" "$BIN_DIR/bindle" context config validate --project missing --format text 2>&1)"
status=$?
check "bindle context preserves helper exit code" test "$status" -eq 1
check "context stdout content is from helper" contains "E_CONFIG_MISSING" "$out"

echo "== explicit notes-home override wins =="
NH_OVERRIDE="$TMP/override notes"
out="$(BINDLE_NOTES_DIR="$TMP/ignored notes" "$BIN_DIR/bindle" context init \
  --project override-proj --notes-home "$NH_OVERRIDE" 2>&1)"
status=$?
check "explicit --notes-home still works" test "$status" -eq 0
check "override notes-home used" test -f "$NH_OVERRIDE/projects/override-proj/.bindle/context/config.json"

echo "== direct helpers remain functional =="
out="$("$PY" "$REPO_ROOT/bin/map-entry-id.py" allocate --project direct-test 2>&1)"
status=$?
check "direct map helper invocation still works" test "$status" -eq 0
check "direct helper stdout preserved" matches_context_node direct-test "$out"

echo "== missing helper reports a dispatcher error =="
FAKE="$TMP/fake repo"
mkdir -p "$FAKE/bin"
cp "$BINDLE" "$FAKE/bin/bindle"
printf '9.9.9\n' >"$FAKE/VERSION"
out="$("$FAKE/bin/bindle" map --help 2>&1)"
status=$?
check "missing helper exits 127" test "$status" -eq 127
check "missing helper message names the missing helper" contains "missing helper" "$out"

echo
echo "test-bindle-cli: $pass passed, $fail failed"
[ "$fail" -eq 0 ]

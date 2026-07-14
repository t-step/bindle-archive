#!/usr/bin/env bash
# Fixture-driven tests for the release-integrity helper (issue #59).
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HELPER="$REPO_ROOT/skills/package-release-integrity/scripts/release_integrity.py"
FIX="$REPO_ROOT/skills/package-release-integrity/tests/fixtures"
pass=0
fail=0

# check <desc> <expected-exit> <cmd...>: run cmd, compare exit code.
run() {
  OUT="$("$@" 2>&1)"
  RC=$?
}
contains() { echo "$OUT" | grep -qF "$1"; }

expect_contains() {
  local desc="$1" needle="$2"
  if contains "$needle"; then
    echo "  ok: $desc"
    pass=$((pass + 1))
  else
    echo "  FAIL: $desc (missing: $needle)"
    printf '%s\n' "$OUT" | sed 's/^/    | /'
    fail=$((fail + 1))
  fi
}
expect_rc() {
  local desc="$1" want="$2"
  if [ "$RC" -eq "$want" ]; then
    echo "  ok: $desc"
    pass=$((pass + 1))
  else
    echo "  FAIL: $desc (rc=$RC want=$want)"
    fail=$((fail + 1))
  fi
}

echo "version-source consistency:"
run python3 "$HELPER" check --repo "$FIX/consistent"
expect_contains "consistent -> pass" "version_source_consistency: pass"
run python3 "$HELPER" check --repo "$FIX/inconsistent"
expect_contains "inconsistent -> fail" "version_source_consistency: fail"

echo "tag consistency:"
run python3 "$HELPER" check --repo "$FIX/consistent" --tag v1.2.0
expect_contains "matching tag -> pass" "tag_consistency: pass"
run python3 "$HELPER" check --repo "$FIX/tag-mismatch" --tag v1.1.0
expect_contains "mismatched tag -> fail" "tag_consistency: fail"
expect_rc "mismatched tag -> rc 1" 1

echo "changelog presence:"
run python3 "$HELPER" check --repo "$FIX/consistent"
expect_contains "changelog present -> pass" "changelog_present: pass"
run python3 "$HELPER" check --repo "$FIX/missing-changelog"
expect_contains "changelog absent -> fail" "changelog_present: fail"
run python3 "$HELPER" check --repo "$FIX/missing-changelog" --no-changelog-required
expect_contains "changelog absent + no-required -> uncertain" "changelog_present: uncertain"
expect_rc "changelog absent + no-required -> rc 0" 0

echo "tag consistency (no --tag supplied):"
run python3 "$HELPER" check --repo "$FIX/consistent"
expect_contains "no --tag -> uncertain" "tag_consistency: uncertain"

echo "test-package-release-integrity: $pass passed, $fail failed"
[ "$fail" -eq 0 ]

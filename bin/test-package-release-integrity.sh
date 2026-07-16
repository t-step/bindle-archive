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
expect_publication_json() {
  local desc="$1" want="$2"
  if printf '%s' "$OUT" | python3 -c '
import json
import sys

got = json.load(sys.stdin)
want = json.loads(sys.argv[1])
raise SystemExit(0 if got == want else 1)
' "$want"; then
    echo "  ok: $desc"
    pass=$((pass + 1))
  else
    echo "  FAIL: $desc (unexpected publication JSON)"
    printf '%s\n' "$OUT" | sed 's/^/    | /'
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

echo "classification + movement (judgment gated):"
run python3 "$HELPER" check --repo "$FIX/consistent"
expect_contains "no class -> classification uncertain" "change_classification: uncertain"
expect_contains "no class -> movement uncertain" "version_movement: uncertain"

run python3 "$HELPER" check --repo "$FIX/pre-1.0-breaking" --prev-version 0.3.0 --change-class breaking
expect_contains "pre-1.0 breaking minor -> pass" "version_movement: pass"
run python3 "$HELPER" check --repo "$FIX/post-1.0-breaking" --prev-version 1.2.0 --change-class breaking
expect_contains "post-1.0 breaking major -> pass" "version_movement: pass"
run python3 "$HELPER" check --repo "$FIX/additive" --prev-version 1.2.0 --change-class additive
expect_contains "additive minor -> pass" "version_movement: pass"
run python3 "$HELPER" check --repo "$FIX/patch" --prev-version 1.2.0 --change-class patch
expect_contains "patch -> pass" "version_movement: pass"

run python3 "$HELPER" check --repo "$FIX/data-only" --prev-version 1.2.0 --change-class data-only
expect_contains "data-only no move -> track pass" "track_routing: pass"
run python3 "$HELPER" check --repo "$FIX/additive" --prev-version 1.2.0 --change-class data-only
expect_contains "data-only but moved -> track fail" "track_routing: fail"

echo "build/test gates (shell-out):"
run python3 "$HELPER" check --repo "$FIX/consistent" --test-cmd "true"
expect_contains "passing test-cmd -> pass" "verification_gate: pass"
run python3 "$HELPER" check --repo "$FIX/consistent" --test-cmd "false"
expect_contains "failing test-cmd -> fail" "verification_gate: fail"
expect_rc "failing test-cmd -> rc 1" 1
run python3 "$HELPER" check --repo "$FIX/consistent"
expect_contains "no test-cmd -> uncertain" "verification_gate: uncertain"
run python3 "$HELPER" check --repo "$FIX/consistent" --test-cmd "definitely-not-a-real-cmd-xyz"
expect_contains "broken test-cmd -> uncertain (degraded)" "verification_gate: uncertain"

echo "DomI defer path:"
run python3 "$HELPER" check --repo "$FIX/domi-governed"
expect_contains "domi-governed -> defer mode" "mode: defer"
expect_contains "domi-governed -> defer banner" "DomI authoritative"
expect_rc "domi-governed -> rc 0 (defer is not a failure)" 0
run python3 "$HELPER" check --repo "$FIX/consistent"
expect_contains "plain repo -> portable mode" "mode: portable"

echo "strict publication check:"
PASS_REPORT='{"mode":"publication","verdicts":[{"check":"version_source_consistency","verdict":"pass"},{"check":"tag_consistency","verdict":"pass"},{"check":"changelog_present","verdict":"pass"}],"ready":true}'
TAG_FAIL_REPORT='{"mode":"publication","verdicts":[{"check":"version_source_consistency","verdict":"pass"},{"check":"tag_consistency","verdict":"fail"},{"check":"changelog_present","verdict":"pass"}],"ready":false}'
CHANGELOG_FAIL_REPORT='{"mode":"publication","verdicts":[{"check":"version_source_consistency","verdict":"pass"},{"check":"tag_consistency","verdict":"pass"},{"check":"changelog_present","verdict":"fail"}],"ready":false}'
VERSION_FAIL_REPORT='{"mode":"publication","verdicts":[{"check":"version_source_consistency","verdict":"fail"},{"check":"tag_consistency","verdict":"pass"},{"check":"changelog_present","verdict":"pass"}],"ready":false}'
DEFER_REPORT='{"mode":"defer","verdicts":[],"ready":false}'

run python3 "$HELPER" publication-check --repo "$FIX/version-file" --tag v1.2.0 --json
expect_publication_json "matching version.txt tag -> exact ready report" "$PASS_REPORT"
expect_rc "matching version.txt tag -> rc 0" 0

run python3 "$HELPER" publication-check --repo "$FIX/version-file" --tag v1.1.0 --json
expect_publication_json "mismatched tag -> strict not-ready report" "$TAG_FAIL_REPORT"
expect_rc "mismatched tag -> publication rc 1" 1

run python3 "$HELPER" publication-check --repo "$FIX/missing-changelog" --tag v1.2.0 --json
expect_publication_json "missing changelog -> strict not-ready report" "$CHANGELOG_FAIL_REPORT"
expect_rc "missing changelog -> publication rc 1" 1

TMP_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/bindle-publication-test.XXXXXX")"
trap 'rm -rf "$TMP_ROOT"' EXIT
mkdir -p "$TMP_ROOT/malformed-version"
printf '%s\n' 'not-semver' >"$TMP_ROOT/malformed-version/version.txt"
printf '%s\n' '# Changelog' '## [Unreleased]' >"$TMP_ROOT/malformed-version/CHANGELOG.md"
run python3 "$HELPER" publication-check --repo "$TMP_ROOT/malformed-version" --tag vnot-semver --json
expect_publication_json "matching malformed version.txt tag -> strict not-ready report" "$VERSION_FAIL_REPORT"
expect_rc "malformed version.txt -> publication rc 1" 1

run python3 "$HELPER" publication-check --repo "$FIX/domi-governed" --tag v1.2.0 --json
expect_publication_json "DomI authority -> defer not-ready report" "$DEFER_REPORT"
expect_rc "DomI authority -> publication rc 1" 1

echo "test-package-release-integrity: $pass passed, $fail failed"
[ "$fail" -eq 0 ]

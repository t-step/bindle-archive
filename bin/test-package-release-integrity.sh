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

# VERSION-file / release-please-manifest discovery (#217). Bindle is a bash +
# markdown kit whose version source of truth is the VERSION file plus
# .release-please-manifest.json, neither of which the helper used to read.
echo "VERSION-file + manifest discovery (#217):"
run python3 "$HELPER" check --repo "$FIX/version-file"
expect_contains "VERSION + manifest agree -> pass" "version_source_consistency: pass"
expect_contains "resolved version reaches changelog check" "changelog_present: pass"
run python3 "$HELPER" check --repo "$FIX/version-file" --tag v2.4.0
expect_contains "VERSION-file repo, matching tag -> pass" "tag_consistency: pass"

# The v0.9.0 shape: release-please advanced the manifest, the chained sync never
# wrote VERSION. This fixture is the discriminating one — drop EITHER new source
# and only one value remains, so the disagreement becomes an vacuous "pass".
run python3 "$HELPER" check --repo "$FIX/version-file-drift"
expect_contains "VERSION behind manifest -> fail" "version_source_consistency: fail"
expect_rc "VERSION behind manifest -> rc 1" 1

run python3 "$HELPER" check --repo "$FIX/version-file-nonsemver"
expect_contains "non-semver VERSION is not a source -> pass" "version_source_consistency: pass"
expect_contains "non-semver VERSION -> manifest still resolves" "changelog_present: pass"

# The same guard, mirrored on the manifest value. Without this fixture the
# manifest's semver guard is an untested branch: no other fixture carries a
# manifest value that could fail it.
run python3 "$HELPER" check --repo "$FIX/manifest-nonsemver"
expect_contains "non-semver manifest value is not a source -> pass" "version_source_consistency: pass"
expect_contains "non-semver manifest -> VERSION still resolves" "changelog_present: pass"

# Only the root "." key is a source. A monorepo's per-package versions differ by
# design; treating them as peers would fail a healthy repo.
run python3 "$HELPER" check --repo "$FIX/monorepo-manifest"
expect_contains "monorepo manifest -> only root key is a source" "version_source_consistency: pass"

# Sources are peers — no precedence. A python source disagreeing with VERSION is
# a genuine inconsistency.
run python3 "$HELPER" check --repo "$FIX/mixed-disagreement"
expect_contains "pyproject vs VERSION disagree -> fail" "version_source_consistency: fail"

# A check that could not run must not report failure. Before #217 this probed
# CHANGELOG.md for the literal string "[None]" and returned fail, which was the
# entire cause of Bindle's structural red.
echo "changelog check with no resolvable version (#217):"
run python3 "$HELPER" check --repo "$FIX/no-version-source"
expect_contains "no version source -> changelog uncertain, not fail" "changelog_present: uncertain"
expect_contains "no version source -> no [None] probe in detail" "no version resolved"
expect_rc "no version source -> rc 0" 0
run python3 "$HELPER" check --repo "$FIX/unreleased-only"
expect_contains "no version but [Unreleased] present -> pass" "changelog_present: pass"

echo "DomI defer path:"
run python3 "$HELPER" check --repo "$FIX/domi-governed"
expect_contains "domi-governed -> defer mode" "mode: defer"
expect_contains "domi-governed -> defer banner" "DomI authoritative"
expect_rc "domi-governed -> rc 0 (defer is not a failure)" 0
run python3 "$HELPER" check --repo "$FIX/consistent"
expect_contains "plain repo -> portable mode" "mode: portable"

# Fixture provenance (#224, checklist item 8). The defer fixture's pin was
# all-zeros until 2026-07-18; a pressure-test rep read the placeholder, decided
# the repo had "never actually been synced to a real DomI commit," and certified
# a release it should have deferred. Well-formed is not enough — the pin must
# also be believable to an agent that opens it.
echo "defer-fixture provenance:"
PIN="$FIX/domi-governed/.domi-pin"
pin_field() { grep -E "^$1:" "$PIN" | head -1 | sed -E "s/^$1:[[:space:]]*//"; }
if printf '%s' "$(pin_field sha)" | grep -qE '^[0-9a-f]{40}$'; then
  echo "  ok: pin sha is 40-hex (well-formed)"
  pass=$((pass + 1))
else
  echo "  FAIL: pin sha is not 40-hex"
  fail=$((fail + 1))
fi
if [ "$(pin_field sha)" = "0000000000000000000000000000000000000000" ]; then
  echo "  FAIL: pin sha is the all-zeros placeholder (checklist item 8)"
  fail=$((fail + 1))
else
  echo "  ok: pin sha is not the all-zeros placeholder"
  pass=$((pass + 1))
fi
if printf '%s' "$(pin_field manifest_sha256)" | grep -qE '^0{64}$'; then
  echo "  FAIL: pin manifest_sha256 is the all-zeros placeholder (checklist item 8)"
  fail=$((fail + 1))
else
  echo "  ok: pin manifest_sha256 is not the all-zeros placeholder"
  pass=$((pass + 1))
fi

echo "test-package-release-integrity: $pass passed, $fail failed"
[ "$fail" -eq 0 ]

#!/usr/bin/env bash
#
# test-check-pressure-series.sh — prove bin/check-pressure-series.sh's --all
# completeness mode against the real tree, not just hand-written fixtures
# (#467, #356).
#
# The gate exists because #459 shipped a green completeness check whose parser
# matched zero real blocks — a passing suite that measures nothing. Every
# fixture below is therefore COPIED verbatim out of a real skills/*/
# PRESSURE-TESTS.md file with extract_real_block, never hand-written in the
# shape the parser expects: a hand-written fixture proves the parser agrees
# with itself, not with the tree. Three block shapes exist in the tree and
# each gets its own copied fixture (Amendment 4):
#
#   contiguous            session-continuity Claim 9        (8 of 37)
#   blank-line-separated  hands-on-keyboard Claim 1          (29 of 37, majority)
#   prose-interleaved     license-compliance-auditor preamble — an unrelated
#                         sentence continues the **Model:** line with no blank
#                         line and is swallowed into the field's value
#
# The single most important assertion is the live-match count at the bottom:
# `--count-only` against the REAL repo must equal the line-anchored
# `grep -rh '^\*\*Model:\*\*'` count (37). A green run whose parser matches 0
# (or 35 — the same-or-shallower-depth trap Amendment 1 documents) is the #459
# failure recurring, not a pass.
#
# Usage: bin/test-check-pressure-series.sh
#
set -uo pipefail

# Under a git hook (pre-commit/post-merge), git exports GIT_DIR and friends to
# subprocesses; in a worktree GIT_DIR is absolute, so a fixture git call would
# hit the real repository. Scrub the hook environment. This suite does not
# shell out to git itself, but the gate under test walks a --root the caller
# controls, and the scrub costs nothing to carry forward from
# bin/test-check-gitleaks.sh's pattern.
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_COMMON_DIR

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GATE="$REPO_ROOT/bin/check-pressure-series.sh"

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

# shellcheck disable=SC2329 # invoked indirectly, by name, via check
contains() { grep -qF -- "$1" <<<"$2"; } # contains NEEDLE HAYSTACK
# shellcheck disable=SC2329 # invoked indirectly, by name, via check
not_contains() { ! grep -qF -- "$1" <<<"$2"; } # not_contains NEEDLE HAYSTACK
# shellcheck disable=SC2329 # invoked indirectly, by name, via check
equals() { [ "$1" = "$2" ]; } # equals EXPECTED ACTUAL

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# The primary checkout must be untouched by every fixture below. Captured
# here, compared at the end: a fixture that escapes its sandbox moves one of
# these.
GUARD_REFS_BEFORE="$(git -C "$REPO_ROOT" for-each-ref | wc -l | tr -d ' ')"
GUARD_HEAD_BEFORE="$(git -C "$REPO_ROOT" rev-parse HEAD)"

# Copied from skills/session-continuity/PRESSURE-TESTS.md — a real, complete,
# three-field block. A fixture hand-written in the form the parser expects
# proves the parser agrees with itself, not with the tree (#459).
#
# THREE shapes must be copied, not one (Amendment 4). Claim 9 below is the
# CONTIGUOUS shape (fields on consecutive lines), only 8 of 37 blocks. Also
# copy a BLANK-LINE-SEPARATED block (29 of 37 — e.g. skills/hands-on-keyboard)
# and the PROSE-INTERLEAVED shape in skills/license-compliance-auditor, where a
# sentence continues the **Model:** line with no blank line and is swallowed
# into the field's value. Assert on all three.
extract_real_block() { # extract_real_block FILE HEADING_REGEX > fixture
  awk -v pat="$2" '
    $0 ~ pat {inblock=1}
    inblock {print}
    inblock && /^#{2,3} / && $0 !~ pat {exit}
  ' "$1"
}

echo "the contiguous shape (session-continuity Claim 9, 8 of 37):"

mkdir -p "$TMP/real/skills/session-continuity"
{
  echo "# session-continuity — pressure-test log"
  echo
  extract_real_block "$REPO_ROOT/skills/session-continuity/PRESSURE-TESTS.md" '^## Claim 9'
} >"$TMP/real/skills/session-continuity/PRESSURE-TESTS.md"

out="$("$GATE" --all --root "$TMP/real" 2>&1)"
check "a real three-field block passes --all" contains "1 block" "$out"
check "a real block is not reported incomplete" not_contains "missing" "$out"

# Same block with **Protocol:** deleted — the pre-A state.
mkdir -p "$TMP/incomplete/skills/session-continuity"
sed '/^\*\*Protocol:\*\*/,/^$/d' "$TMP/real/skills/session-continuity/PRESSURE-TESTS.md" \
  >"$TMP/incomplete/skills/session-continuity/PRESSURE-TESTS.md"
out="$("$GATE" --all --root "$TMP/incomplete" 2>&1)"
check "a block missing **Protocol:** is red" equals 1 "$?"
check "the finding names the field" contains "Protocol" "$out"

# ===========================================================================
echo
echo "the blank-line-separated shape (hands-on-keyboard Claim 1, 29 of 37 — the majority):"

mkdir -p "$TMP/hok/skills/hands-on-keyboard"
{
  echo "# hands-on-keyboard — pressure-test log"
  echo
  extract_real_block "$REPO_ROOT/skills/hands-on-keyboard/PRESSURE-TESTS.md" '^## Claim 1'
} >"$TMP/hok/skills/hands-on-keyboard/PRESSURE-TESTS.md"

out="$("$GATE" --all --root "$TMP/hok" 2>&1)"
check "the blank-line-separated shape passes --all" contains "1 block" "$out"
check "the blank-line-separated shape is not reported incomplete" not_contains "missing" "$out"

# ===========================================================================
echo
echo "the prose-interleaved shape (license-compliance-auditor — a sentence swallowed into **Model:**):"

mkdir -p "$TMP/lca/skills/license-compliance-auditor"
extract_real_block "$REPO_ROOT/skills/license-compliance-auditor/PRESSURE-TESTS.md" \
  '^# license-compliance-auditor' >"$TMP/lca/skills/license-compliance-auditor/PRESSURE-TESTS.md"

out="$("$GATE" --all --root "$TMP/lca" 2>&1)"
check "the prose-interleaved shape passes --all" contains "1 block" "$out"
check "the prose-interleaved shape is not reported incomplete" not_contains "missing" "$out"

# ===========================================================================
echo
echo "an illegal **Protocol:** value:"

mkdir -p "$TMP/illegal/skills/s"
out="$(
  printf '%s\n' '**Model:** x' '**Content:** unrecorded' '**Protocol:** probably fine' |
    tee "$TMP/illegal/skills/s/PRESSURE-TESTS.md" >/dev/null
  "$GATE" --all --root "$TMP/illegal" 2>&1
)"
check "an illegal **Protocol:** value is red" contains "not a legal value" "$out"

# ===========================================================================
echo
echo "the per-arm override form (Amendment 3 — fork-pr-flow's real #190 series):"
#
# The override's second legal token lands on the line AFTER the one
# **Protocol:** starts on ('arm C `unrecorded`.' continues 'arms A-B
# `compliant`, arm'), so this is also the regression fixture for continuation
# folding: a parser that reads only the **Protocol:** line's own text sees one
# legal token and wrongly rejects the real series.

mkdir -p "$TMP/override/skills/fork-pr-flow"
{
  echo "# fork-pr-flow — pressure-test log"
  echo
  extract_real_block "$REPO_ROOT/skills/fork-pr-flow/PRESSURE-TESTS.md" \
    '^## Claim — the PR base follows'
} >"$TMP/override/skills/fork-pr-flow/PRESSURE-TESTS.md"

out="$("$GATE" --all --root "$TMP/override" 2>&1)"
check "a real per-arm **Protocol:** override is accepted" not_contains "not a legal value" "$out"
check "a real per-arm **Protocol:** override is not reported missing" not_contains "missing" "$out"

# ===========================================================================
echo
echo "the live-match count — the #459 alarm. Run against the REAL repo:"

live="$(grep -rh '^\*\*Model:\*\*' "$REPO_ROOT"/skills/*/PRESSURE-TESTS.md | wc -l | tr -d ' ')"
seen="$("$GATE" --all --count-only)"
check "the parser sees every real block, not zero" equals "$live" "$seen"

# ===========================================================================
echo
echo "fixture isolation:"

GUARD_REFS_AFTER="$(git -C "$REPO_ROOT" for-each-ref | wc -l | tr -d ' ')"
GUARD_HEAD_AFTER="$(git -C "$REPO_ROOT" rev-parse HEAD)"

check "the primary checkout's ref count is unchanged" \
  equals "$GUARD_REFS_BEFORE" "$GUARD_REFS_AFTER"
check "the primary checkout's HEAD is unchanged" \
  equals "$GUARD_HEAD_BEFORE" "$GUARD_HEAD_AFTER"

# ===========================================================================
echo
if [ "$fail" -eq 0 ]; then
  printf '  ✓ all %d assertions pass\n' "$pass"
  exit 0
fi
printf '  ✗ %d of %d assertions failed\n' "$fail" "$((pass + fail))"
exit 1

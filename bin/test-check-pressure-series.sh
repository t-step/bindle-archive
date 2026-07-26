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
#
# Terminates on a heading of ANY depth, not just ##/### — verify-then-commit
# has real content at #### (`#### GREEN follow-up`), and a terminator that
# only recognized ##/### would swallow the next ### or #### section into a
# fixture that was supposed to end before it.
extract_real_block() { # extract_real_block FILE HEADING_REGEX > fixture
  awk -v pat="$2" '
    $0 ~ pat {inblock=1}
    inblock {print}
    inblock && /^#+ / && $0 !~ pat {exit}
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
rc=$?
check "a real three-field block passes --all" equals 0 "$rc"
check "a real three-field block registers its one block" contains "1 block" "$out"
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
rc=$?
check "the blank-line-separated shape passes --all" equals 0 "$rc"
check "the blank-line-separated shape registers its one block" contains "1 block" "$out"
check "the blank-line-separated shape is not reported incomplete" not_contains "missing" "$out"

# ===========================================================================
echo
echo "the prose-interleaved shape (license-compliance-auditor — a sentence swallowed into **Model:**):"

mkdir -p "$TMP/lca/skills/license-compliance-auditor"
extract_real_block "$REPO_ROOT/skills/license-compliance-auditor/PRESSURE-TESTS.md" \
  '^# license-compliance-auditor' >"$TMP/lca/skills/license-compliance-auditor/PRESSURE-TESTS.md"

out="$("$GATE" --all --root "$TMP/lca" 2>&1)"
rc=$?
check "the prose-interleaved shape passes --all" equals 0 "$rc"
check "the prose-interleaved shape registers its one block" contains "1 block" "$out"
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
rc=$?
# A positive guard first: if extract_real_block ever returns nothing (a
# reworded heading in fork-pr-flow's file would silently break the
# '^## Claim — the PR base follows' pattern above), the gate sees zero blocks
# and prints "0 block(s) complete" — which trivially satisfies both
# not_contains checks below without ever exercising the override path at all.
check "the override fixture actually yielded a block" contains "1 block" "$out"
check "a real per-arm **Protocol:** override is accepted" not_contains "not a legal value" "$out"
check "a real per-arm **Protocol:** override is not reported missing" not_contains "missing" "$out"
check "a real per-arm **Protocol:** override makes --all pass" equals 0 "$rc"

# ===========================================================================
echo
echo "the live-match count — the #459 alarm. Run against the REAL repo:"

live="$(grep -rh '^\*\*Model:\*\*' "$REPO_ROOT"/skills/*/PRESSURE-TESTS.md | wc -l | tr -d ' ')"
seen="$("$GATE" --all --count-only)"
# A single assertion, not two: a floor check ("live > 0") and an equality
# check ("live == seen") run as SEPARATE assertions can each show a green ✓
# on a zero-evidence tree — the floor fails alone (correctly), but the
# equality (0 == 0) passes right next to it, printing "the parser sees every
# real block, not zero" while showing a ✓ at zero. That is the #459 shape
# recurring one layer up, in the suite built to catch it, and a reader
# scanning for checkmarks sees a true-looking line that is false. Collapsed
# into one predicate so it can never show ✓ while its own English is false:
# it demands the floor AND the equality together, or it fails, full stop.
# shellcheck disable=SC2329 # invoked indirectly, by name, via check
nonzero_and_equal() { [ "$1" -gt 0 ] && [ "$1" = "$2" ]; } # nonzero_and_equal LIVE SEEN
check "the parser sees every real block in the tree, and never zero" nonzero_and_equal "$live" "$seen"

# ===========================================================================
echo
echo "the --staged mode:"

# fixture_repo NAME SRC — a throwaway git repo whose one evidence file is a
# REAL file, copied verbatim under a generic skill directory name ("s"). The
# generic name matters: depth calibration is computed from the file's own
# already-declared depths (Amendment 2), never looked up by skill name — a
# fixture that renamed the file and still calibrates correctly is proof the
# parser reads the tree, not a table.
fixture_repo() { # fixture_repo NAME SRC > REPO_DIR
  local d="$TMP/$1"
  mkdir -p "$d/skills/s"
  cp "$2" "$d/skills/s/PRESSURE-TESTS.md"
  git -C "$d" init -q
  git -C "$d" add -A
  git -C "$d" -c user.email=t@e -c user.name=t commit -qm base
  printf '%s\n' "$d"
}

echo
echo "the NOT RUN disclosure — --staged must not hard-fail where it has nothing to read:"

# Outside a git repository entirely. A mode that hard-fails here would break
# any consumer that runs it in a scratch tree.
mkdir -p "$TMP/nogit/skills/s"
cp "$REPO_ROOT/skills/release-captain/PRESSURE-TESTS.md" "$TMP/nogit/skills/s/PRESSURE-TESTS.md"
out="$(cd "$TMP/nogit" && "$GATE" --staged 2>&1)"
rc=$?
check "--staged outside a git repository discloses NOT RUN, not a crash" contains "NOT RUN" "$out"
check "--staged outside a git repository names no false problem" not_contains "missing" "$out"
check "--staged outside a git repository exits 0" equals 0 "$rc"

# Inside a git repository, but nothing staged that matches the evidence glob.
d="$(fixture_repo notstaged "$REPO_ROOT/skills/release-captain/PRESSURE-TESTS.md")"
out="$(cd "$d" && "$GATE" --staged 2>&1)"
rc=$?
check "--staged with no staged evidence files discloses NOT RUN" contains "NOT RUN" "$out"
check "--staged with no staged evidence files exits 0" equals 0 "$rc"

echo
echo "depth calibration — computed from the file, never a table (Amendment 2):"

# verify-then-commit declares at ##, ### AND #### -> a new ### triggers there.
d="$(fixture_repo vtc "$REPO_ROOT/skills/verify-then-commit/PRESSURE-TESTS.md")"
printf '\n### Weaker-model rerun — Opus 5 (2026-07-27)\n\nRED 0/5, GREEN 5/5.\n' \
  >>"$d/skills/s/PRESSURE-TESTS.md"
git -C "$d" add -A
out="$(cd "$d" && "$GATE" --staged 2>&1)"
rc=$?
check "a ### append triggers in a file that declares at ###" contains "missing" "$out"
check "a ### append that triggers makes --staged exit 1" equals 1 "$rc"

# ...and one depth deeper still triggers, at #### — the depth the plan's
# original table missed entirely (Amendment 2).
d="$(fixture_repo vtc4 "$REPO_ROOT/skills/verify-then-commit/PRESSURE-TESTS.md")"
printf '\n#### New Sonnet rerun (2026-07-27)\n\nRED 0/5, GREEN 5/5.\n' \
  >>"$d/skills/s/PRESSURE-TESTS.md"
git -C "$d" add -A
out="$(cd "$d" && "$GATE" --staged 2>&1)"
rc=$?
check "a #### append triggers in a file that declares at ####" contains "missing" "$out"
check "a #### append that triggers makes --staged exit 1" equals 1 "$rc"

# release-captain declares at ## only -> a new ### is narrative, no trigger.
d="$(fixture_repo rc "$REPO_ROOT/skills/release-captain/PRESSURE-TESTS.md")"
printf '\n### Honest coverage caveat (new)\n\nProse only.\n' >>"$d/skills/s/PRESSURE-TESTS.md"
git -C "$d" add -A
out="$(cd "$d" && "$GATE" --staged 2>&1)"
rc=$?
check "a ### append does not trigger in a ##-only file" not_contains "missing" "$out"
check "a ### append that does not trigger leaves --staged exit 0" equals 0 "$rc"

# A ## append always triggers...
printf '\n## Claim 99 — a new series\n\nRED 0/5, GREEN 5/5.\n' >>"$d/skills/s/PRESSURE-TESTS.md"
git -C "$d" add -A
out="$(cd "$d" && "$GATE" --staged 2>&1)"
rc=$?
check "a ## append with no field block is red" contains "Claim 99" "$out"
check "a ## append with no field block makes --staged exit 1" equals 1 "$rc"

# ...unless it carries the escape marker. Reset the fixture to its clean
# committed base first: Claim 99 above is still staged and still
# noncompliant, so leaving it in place would let this assertion pass by
# accident (Claim 99 alone would still print "missing", so a not_contains
# check on the OLD state would already have failed for the wrong reason) —
# reset first so the only thing in the staged diff is the marked heading.
git -C "$d" reset --hard -q
printf '\n## Closed mechanically <!-- not-a-series: no reps, bookkeeping only -->\n\nProse.\n' \
  >>"$d/skills/s/PRESSURE-TESTS.md"
git -C "$d" add -A
out="$(cd "$d" && "$GATE" --staged 2>&1)"
rc=$?
check "the not-a-series marker exempts a ## append" not_contains "missing" "$out"
check "the not-a-series marker leaves --staged exit 0" equals 0 "$rc"

# A ## append WITH all three fields passes.
d="$(fixture_repo ok "$REPO_ROOT/skills/release-captain/PRESSURE-TESTS.md")"
{
  echo
  echo '## Claim 100 — a new, fully recorded series'
  echo
  # shellcheck disable=SC2016 # single-quoted on purpose: backticks are literal markdown, not command substitution
  echo '**Model:** Opus 5 (`claude-opus-5[1m]`), Claude Code — both arms.'
  echo '**Content:** unrecorded (dispatch-time id not captured).'
  echo '**Protocol:** compliant — arm declared before dispatch.'
} >>"$d/skills/s/PRESSURE-TESTS.md"
git -C "$d" add -A
out="$(cd "$d" && "$GATE" --staged 2>&1)"
rc=$?
check "a ## append carrying all three fields is counted as a checked series" \
  contains "1 new series" "$out"
check "a ## append carrying all three fields passes" not_contains "missing" "$out"
check "a ## append carrying all three fields makes --staged exit 0" equals 0 "$rc"

echo
echo "reads the STAGED blob, not the working tree — the #354 blind spot, one layer up:"

# Stage a fully-compliant new series, then dirty the working tree so the file
# ON DISK is missing **Protocol:** — --staged must judge what the commit will
# contain, not whatever is sitting in the working tree afterward.
d="$(fixture_repo dirty "$REPO_ROOT/skills/release-captain/PRESSURE-TESTS.md")"
{
  echo
  echo '## Claim 101 — a new, fully recorded series'
  echo
  # shellcheck disable=SC2016 # single-quoted on purpose: backticks are literal markdown, not command substitution
  echo '**Model:** Opus 5 (`claude-opus-5[1m]`), Claude Code — both arms.'
  echo '**Content:** unrecorded (dispatch-time id not captured).'
  echo '**Protocol:** compliant — arm declared before dispatch.'
} >>"$d/skills/s/PRESSURE-TESTS.md"
git -C "$d" add -A
# Dirty the working tree AFTER staging: strip the just-staged **Protocol:**
# field from the on-disk copy without staging that removal.
awk '/^\*\*Protocol:\*\*/{skip=1} skip && /^$/{skip=0; next} skip{next} {print}' \
  "$d/skills/s/PRESSURE-TESTS.md" >"$d/skills/s/PRESSURE-TESTS.md.tmp"
mv "$d/skills/s/PRESSURE-TESTS.md.tmp" "$d/skills/s/PRESSURE-TESTS.md"
out="$(cd "$d" && "$GATE" --staged 2>&1)"
rc=$?
check "a staged-compliant block is counted as a checked series despite the dirty disk copy" \
  contains "1 new series" "$out"
check "a staged-compliant block stays green though the working tree was dirtied after staging" \
  not_contains "missing" "$out"
check "a staged-compliant block dirtied afterward still exits 0" equals 0 "$rc"

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

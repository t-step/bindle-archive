#!/usr/bin/env bash
# shellcheck disable=SC2016  # assertions pass values into `bash -c '...'` as
# $1/$2; single quotes are deliberate — expansion happens in the inner shell.
#
# test-map-entry-id.sh — pressure tests for bin/map-entry-id.py, the stable
# opaque identity helper for project-map entries (issue #179). Covers the
# helper-level scenarios from the issue's pressure-test list: allocation
# format/uniqueness, marker placement per entry shape, duplicate/malformed
# detection, typed retirement tombstones + bindle:superseded-by validation,
# byte preservation, and zero-mutation validation. Confirm-none / aborted-run
# / update-preserves-ID behavior that lives in the knowledge-promotion
# *workflow* (prompt-driven, not this script) is pressure-tested separately
# per docs/knowledge-promotion-pressure-tests.md.
#
# Entirely offline and self-contained: every fixture is a throwaway file
# under a mktemp dir. BINDLE_NOTES_DIR is pointed at that same throwaway tree
# so nothing in this run can touch the real notes home, and a marker-file
# check at the end proves it.
#
set -uo pipefail

unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_COMMON_DIR

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HELPER="$REPO_ROOT/bin/map-entry-id.py"
PY="$(command -v python3)"

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
not_contains() { ! grep -qF -- "$1" <<<"$2"; }
export -f contains not_contains

# jget FIELD-EXPR JSON — evaluate a Python expression against the parsed JSON
# result (bound as `r`) and print it.
jget() {
  "$PY" -c 'import json,sys; r=json.load(sys.stdin); print(eval(sys.argv[1]))' \
    "$1" <<<"$2"
}
export -f jget
export PY HELPER

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
export BINDLE_NOTES_DIR="$TMP/notes-home"
mkdir -p "$BINDLE_NOTES_DIR"

sha() { "$PY" -c 'import hashlib,sys; print(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest())' "$1"; }

MARKER="$(mktemp)"

echo "== allocate =="

id1="$("$PY" "$HELPER" allocate --project demo)"
id2="$("$PY" "$HELPER" allocate --project demo)"
id_dec="$("$PY" "$HELPER" allocate --project demo)"
id_learn="$("$PY" "$HELPER" allocate --project demo)"
id_assum="$("$PY" "$HELPER" allocate --project demo)"
id_tension="$("$PY" "$HELPER" allocate --project demo)"
id_question="$("$PY" "$HELPER" allocate --project demo)"
id_old="$("$PY" "$HELPER" allocate --project demo)"
id_new="$("$PY" "$HELPER" allocate --project demo)"

check "allocate: format matches context-node:<slug>:<32-hex> exactly" \
  bash -c '[[ "$1" =~ ^context-node:demo:[0-9a-f]{32}$ ]]' _ "$id1"
check "allocate: hex component is exactly 32 chars" \
  bash -c '[ "${#1}" -eq $(( ${#1} )) ] && n="${1##*:}"; [ "${#n}" -eq 32 ]' _ "$id1"
check "scenario 5: two allocations are distinct" \
  bash -c '[ "$1" != "$2" ]' _ "$id1" "$id2"
check "allocate: exit 64 on a malformed --project slug" \
  bash -c '"$0" "$1" allocate --project "Not A Slug!" >/dev/null 2>&1; [ $? -eq 64 ]' "$PY" "$HELPER"

EMPTYDIR="$TMP/empty-during-allocate"
mkdir -p "$EMPTYDIR"
(cd "$EMPTYDIR" && "$PY" "$HELPER" allocate --project demo >/dev/null)
check "scenario 11: allocate writes no pending-id side file anywhere" \
  bash -c '[ "$(find "$1" -mindepth 1 | wc -l | tr -d " ")" = 0 ]' _ "$EMPTYDIR"

echo "== marker placement per supported entry shape (scenarios 1-4, 19-21) =="

cat >"$TMP/shapes.md" <<EOF
# demo — map

updated: 2026-07-16 · evidence through: none

## Brief

Thesis line, no entries here.

## Decisions

### A confirmed decision (2026-07, settled) <!-- bindle:context-id: $id_dec -->
why: w
so: s
revisit-when: r
evidence: #1

## Learnings

### A confirmed learning <!-- bindle:context-id: $id_learn -->
why: w
so: s
evidence: #2

## Assumptions & tensions

- a single assumption — confidence: high — evidence: #3 <!-- bindle:context-id: $id_assum -->
- a tension parent — confidence: low — evidence: #4 <!-- bindle:context-id: $id_tension -->
  - side a — evidence: #4a
  - side b — evidence: #4b

## Open questions

- an open question? (open) — so: implication — evidence: #5 <!-- bindle:context-id: $id_question -->

## Superseded
EOF

before="$(sha "$TMP/shapes.md")"
out="$("$PY" "$HELPER" validate --map "$TMP/shapes.md" --format json)"
after="$(sha "$TMP/shapes.md")"

check "shapes: validation is ok (no errors)" bash -c '[ "$(jget "r[\"ok\"]" "$1")" = True ]' _ "$out"
check "shapes: 5 anchored, 0 unanchored" \
  bash -c '[ "$(jget "r[\"anchored_count\"]" "$1")" = 5 ] && [ "$(jget "r[\"unanchored_count\"]" "$1")" = 0 ]' _ "$out"
check "scenario 1: decision heading is anchored with its id" \
  bash -c '[ "$(jget "r[\"entries\"][0][\"id\"]" "$1")" = "$2" ] && [ "$(jget "r[\"entries\"][0][\"kind\"]" "$1")" = decision ]' _ "$out" "$id_dec"
check "scenario 2: learning heading is anchored with its id" \
  bash -c '[ "$(jget "r[\"entries\"][1][\"id\"]" "$1")" = "$2" ] && [ "$(jget "r[\"entries\"][1][\"kind\"]" "$1")" = learning ]' _ "$out" "$id_learn"
check "scenario 19: single-assumption bullet is anchored with its id" \
  bash -c '[ "$(jget "r[\"entries\"][2][\"id\"]" "$1")" = "$2" ]' _ "$out" "$id_assum"
check "scenario 20: tension-parent bullet is anchored; sides carry no id" \
  bash -c '[ "$(jget "r[\"entries\"][3][\"id\"]" "$1")" = "$2" ] && [ "$(jget "len(r[\"entries\"])" "$1")" = 5 ]' _ "$out" "$id_tension"
check "scenario 3/4/21: open-question bullet is anchored with its id" \
  bash -c '[ "$(jget "r[\"entries\"][4][\"id\"]" "$1")" = "$2" ] && [ "$(jget "r[\"entries\"][4][\"kind\"]" "$1")" = question ]' _ "$out" "$id_question"
check "shapes: validation performs zero writes (byte-identical)" \
  bash -c '[ "$1" = "$2" ]' _ "$before" "$after"

echo "== typed retirement + supersession (scenarios 6, 7, 8, 9, 24, 25, 26) =="

cat >"$TMP/supersede.md" <<EOF
# demo — map

updated: 2026-07-16 · evidence through: none

## Brief

## Decisions

### Old decision, now superseded (2026-07, superseded) <!-- bindle:context-id: $id_old -->
why: original why
so: original so
revisit-when: met
evidence: #1

### New replacement decision (2026-07, settled) <!-- bindle:context-id: $id_new -->
why: new why
so: new so
revisit-when: never
evidence: #2, #1

## Learnings

## Assumptions & tensions

## Open questions

## Superseded

- decision: old decision, now superseded (retired 2026-07) → replaced by new replacement decision <!-- bindle:context-id: $id_old --> <!-- bindle:superseded-by: $id_new -->
- decision: clean retirement, no replacement yet (retired 2026-07) → no replacement decision exists <!-- bindle:context-id: $id1 -->
EOF

out="$("$PY" "$HELPER" validate --map "$TMP/supersede.md" --format json)"
check "supersede: validation is ok (no duplicate-id false positive)" \
  bash -c '[ "$(jget "r[\"ok\"]" "$1")" = True ]' _ "$out"
check "scenario 24: tombstone retains the retired entry's original id" \
  bash -c '[ "$(jget "[e for e in r[\"entries\"] if e[\"section\"]==\"superseded\"][0][\"id\"]" "$1")" = "$2" ]' _ "$out" "$id_old"
check "scenario 8/25: replacement entry gets a distinct newly allocated id" \
  bash -c '[ "$1" != "$2" ]' _ "$id_old" "$id_new"
check "scenario 7: the live (status-flipped) heading still carries its original id" \
  bash -c '[ "$(jget "r[\"entries\"][0][\"id\"]" "$1")" = "$2" ]' _ "$out" "$id_old"
check "scenario 26: retirement without a replacement omits superseded-by cleanly" \
  bash -c '[ "$(jget "[e for e in r[\"entries\"] if e[\"section\"]==\"superseded\"][1][\"id\"]" "$1")" = "$2" ]' _ "$out" "$id1"

# scenario 6/9: rewrite every field line (heading claim, why/so/revisit-when/
# evidence, status token) while leaving the marker untouched — the id must
# not move or change, proving discovery never recomputes from content.
sed -e 's/^why: original why$/why: REVISED why text entirely/' \
  -e 's/^so: original so$/so: REVISED so text entirely/' \
  -e 's/^revisit-when: met$/revisit-when: REVISED condition/' \
  -e 's/^evidence: #2, #1$/evidence: #99/' \
  -e 's/(2026-07, settled)/(2026-08, settled)/' \
  "$TMP/supersede.md" >"$TMP/supersede-edited.md"
out_edited="$("$PY" "$HELPER" validate --map "$TMP/supersede-edited.md" --format json)"
check "scenario 6/9: editing claim/why/so/revisit-when/evidence/date/status never recomputes the id" \
  bash -c '[ "$(jget "r[\"entries\"][0][\"id\"]" "$1")" = "$2" ] && [ "$(jget "r[\"entries\"][1][\"id\"]" "$1")" = "$3" ]' \
  _ "$out_edited" "$id_old" "$id_new"

echo "== duplicate / malformed / misplaced markers (scenarios 13-15, 22, 23, 28) =="

cat >"$TMP/bad.md" <<EOF
# demo — map

updated: 2026-07-16 · evidence through: none

## Brief

## Decisions

### Bad hex decision (2026-07, settled) <!-- bindle:context-id: context-node:demo:deadbeef -->
why: x
so: y
revisit-when: z
evidence: #1 <!-- bindle:context-id: $id_dec -->

### Short hex decision (2026-07, settled) <!-- bindle:context-id: context-node:demo:0123456789abcdef -->
why: x
so: y
revisit-when: z
evidence: #1

### Dup decision A (2026-07, settled) <!-- bindle:context-id: $id2 -->
why: x
so: y
revisit-when: z
evidence: #2

### Dup decision B (2026-07, settled) <!-- bindle:context-id: $id2 -->
why: x
so: y
revisit-when: z
evidence: #2

## Learnings

## Assumptions & tensions

- tension label — confidence: low — evidence: #4 <!-- bindle:context-id: $id_tension -->
  - side one — evidence: #4a <!-- bindle:context-id: $id_assum -->
  - side two — evidence: #4b

## Open questions

## Superseded
EOF

before="$(sha "$TMP/bad.md")"
out="$("$PY" "$HELPER" validate --map "$TMP/bad.md" --format json)"
after="$(sha "$TMP/bad.md")"

check "bad: validation is NOT ok" bash -c '[ "$(jget "r[\"ok\"]" "$1")" = False ]' _ "$out"
check "scenario 15: multiple markers on one entry reported" \
  bash -c '[ "$(jget "sum(1 for i in r[\"issues\"] if i[\"code\"]==\"multiple-markers\")" "$1")" -ge 1 ]' _ "$out"
check "scenario 14: malformed marker (bad hex) reported, not repaired" \
  bash -c '[ "$(jget "sum(1 for i in r[\"issues\"] if i[\"code\"]==\"malformed-marker\")" "$1")" -ge 1 ]' _ "$out"
check "scenario 28: a 16-char short hex component is rejected as malformed" \
  bash -c 'contains "0123456789abcdef" "$1"' _ "$out"
check "scenario 23: identity marker on a field line is rejected as malformed" \
  bash -c '[ "$(jget "sum(1 for i in r[\"issues\"] if i[\"code\"]==\"misplaced-marker\" and \"field line\" in i[\"message\"])" "$1")" -ge 1 ]' _ "$out"
check "scenario 22: identity marker on a tension side is rejected as malformed" \
  bash -c '[ "$(jget "sum(1 for i in r[\"issues\"] if i[\"code\"]==\"misplaced-marker\" and \"tension side\" in i[\"message\"])" "$1")" -ge 1 ]' _ "$out"
check "scenario 13: duplicate ids reported as a conflict" \
  bash -c '[ "$(jget "sum(1 for i in r[\"issues\"] if i[\"code\"]==\"duplicate-id\")" "$1")" -ge 1 ]' _ "$out"
check "bad: validation performs zero writes even when errors are found" \
  bash -c '[ "$1" = "$2" ]' _ "$before" "$after"

echo "== bindle:superseded-by validation (scenario 27) =="

cat >"$TMP/sb.md" <<EOF
# demo — map

updated: 2026-07-16 · evidence through: none

## Brief

## Decisions

## Learnings

## Assumptions & tensions

## Open questions

## Superseded

- assumption: dangling replacement (retired 2026-07) → nothing <!-- bindle:context-id: $id1 --> <!-- bindle:superseded-by: $id2 -->
- learning: empty value (retired 2026-07) → nothing <!-- bindle:context-id: $id_dec --> <!-- bindle:superseded-by:  -->
- decision: dup superseded-by (retired 2026-07) → x <!-- bindle:context-id: $id_learn --> <!-- bindle:superseded-by: $id_assum --> <!-- bindle:superseded-by: $id_assum -->
- question: self-referential (retired 2026-07) → nothing <!-- bindle:context-id: $id_question --> <!-- bindle:superseded-by: $id_question -->
- tension: untyped tombstone (retired 2026-07) → nothing
EOF

out="$("$PY" "$HELPER" validate --map "$TMP/sb.md" --format json)"
check "superseded-by: unresolved (dangling) reference reported" \
  bash -c '[ "$(jget "sum(1 for i in r[\"issues\"] if i[\"code\"]==\"superseded-by-unresolved\")" "$1")" -ge 1 ]' _ "$out"
check "superseded-by: empty/missing value reported" \
  bash -c '[ "$(jget "sum(1 for i in r[\"issues\"] if i[\"code\"]==\"superseded-by-missing-value\")" "$1")" -ge 1 ]' _ "$out"
check "superseded-by: duplicate marker on one tombstone reported" \
  bash -c '[ "$(jget "sum(1 for i in r[\"issues\"] if i[\"code\"]==\"superseded-by-duplicate\")" "$1")" -ge 1 ]' _ "$out"
check "superseded-by: self-referential reported" \
  bash -c '[ "$(jget "sum(1 for i in r[\"issues\"] if i[\"code\"]==\"superseded-by-self-referential\")" "$1")" -ge 1 ]' _ "$out"
check "superseded-by: none of these are repaired (still ok=False, never auto-fixed)" \
  bash -c '[ "$(jget "r[\"ok\"]" "$1")" = False ]' _ "$out"

echo "== existing unanchored maps: byte preservation + legacy tombstone (scenario 12, 16) =="

cat >"$TMP/legacy.md" <<'EOF'
# harborlight — map

updated: 2026-06-16 · evidence through: 2026-06-15-reflections.md

<!-- Purpose: recover the current mental model of this project in under
     five minutes. Owner-curated; /promote-knowledge proposes diffs. -->
<!-- OWNER NOTE: I reworded the Brief by hand — keep my phrasing. -->

## Brief

Harborlight is my bet that a small registry can be preservation-grade
without an institutional stack. (owner-authored, 2026-06-16)

## Decisions

### Rights-blocked assets are retained as records, never deleted (2026-06, settled)
why: rights and disposition are separate axes.
so: takedowns never remove records; serving gates carry the rights burden.
revisit-when: a statutory erasure demand requires physical deletion.
evidence: sessions/2026-06-02-disposition-rights-model.md, #12
<!-- owner: the wording above is mine, do not regenerate -->

## Learnings

## Assumptions & tensions

## Open questions

- should accession notes be public by default? (parked) — so: changes what donors can be promised — evidence: #16

## Superseded

- old-style untyped tombstone (retired 2026-06) → replaced by something
EOF

before="$(sha "$TMP/legacy.md")"
out="$("$PY" "$HELPER" validate --map "$TMP/legacy.md" --format json)"
after="$(sha "$TMP/legacy.md")"

check "scenario 12: existing unanchored map validates ok (unanchored is informational)" \
  bash -c '[ "$(jget "r[\"ok\"]" "$1")" = True ]' _ "$out"
check "legacy: 3 unanchored entries discovered (decision, question, superseded bullet)" \
  bash -c '[ "$(jget "r[\"unanchored_count\"]" "$1")" = 3 ]' _ "$out"
check "legacy: untyped tombstone reported as info, not an error" \
  bash -c '[ "$(jget "sum(1 for i in r[\"issues\"] if i[\"code\"]==\"untyped-tombstone\")" "$1")" -ge 1 ]' _ "$out"
check "scenario 16: user-authored HTML comments are never flagged" \
  bash -c 'not_contains "OWNER NOTE" "$1"' _ "$out"
check "scenario 12/17: existing unanchored map is byte-identical after validation" \
  bash -c '[ "$1" = "$2" ]' _ "$before" "$after"

echo "== determinism (repeated runs after persistence) =="

out1="$("$PY" "$HELPER" validate --map "$TMP/shapes.md" --format json)"
out2="$("$PY" "$HELPER" validate --map "$TMP/shapes.md" --format json)"
check "scenario: repeated validate runs on the same persisted map are identical" \
  bash -c '[ "$1" = "$2" ]' _ "$out1" "$out2"

echo "== real notes home untouched =="

check "the real notes home is provably untouched by this run" \
  bash -c '[ -z "$(find "$HOME/.bindle" -newer "$1" 2>/dev/null)" ]' "$MARKER"

echo
echo "map-entry-id: $pass passed, $fail failed"
[ "$fail" -eq 0 ]

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

echo "== universal retirement: all five kinds (cases 1-8) =="

# Retirement MOVES an entry into ## Superseded as one typed tombstone that
# carries the entry's existing id and its own body verbatim. Nothing is left
# behind in the active section, so one logical entry always has exactly one
# physical record and one id occurrence — retired or not. This block proves
# the model holds identically for decision / learning / assumption / tension /
# question, with no per-kind exception.
id_r_dec="$("$PY" "$HELPER" allocate --project demo)"
id_r_learn="$("$PY" "$HELPER" allocate --project demo)"
id_r_assum="$("$PY" "$HELPER" allocate --project demo)"
id_r_tension="$("$PY" "$HELPER" allocate --project demo)"
id_r_question="$("$PY" "$HELPER" allocate --project demo)"
id_replacement="$("$PY" "$HELPER" allocate --project demo)"
id_no_repl="$("$PY" "$HELPER" allocate --project demo)"

cat >"$TMP/retire-all-kinds.md" <<EOF
# demo — map

updated: 2026-07-16 · evidence through: none

## Brief

## Decisions

### The replacement decision, freshly added (2026-07, settled) <!-- bindle:context-id: $id_replacement -->
why: new why
so: new so
revisit-when: never
evidence: #2

## Learnings

## Assumptions & tensions

## Open questions

## Superseded

- decision: A retired decision (retired 2026-07) → replaced by the replacement decision <!-- bindle:context-id: $id_r_dec --> <!-- bindle:superseded-by: $id_replacement -->
  why: original why, carried down verbatim
  so: original so, carried down verbatim
  revisit-when: met by the donor contract
  evidence: sessions/2026-06-20-derivatives.md, #23
- learning: A retired learning (retired 2026-07) → no longer holds <!-- bindle:context-id: $id_r_learn -->
  why: original learning why
  so: original learning so
  evidence: #14
- assumption: stale reads are clock skew — confidence: low — evidence: #18 (retired 2026-07) → disproved by TTL tracing <!-- bindle:context-id: $id_r_assum -->
- tension: clock skew vs TTL rounding — confidence: low — evidence: #18, #19 (retired 2026-07) → resolved by the TTL fix <!-- bindle:context-id: $id_r_tension -->
  - clock-skew reading: ~4s node drift — evidence: #18
  - TTL reading: minute-rounding shortens TTLs — evidence: #19
- question: is an embargo a rights state? (retired 2026-07) → answered by the donor agreements <!-- bindle:context-id: $id_r_question -->
  so: the chosen axis constrains the tier model
  evidence: #27
- decision: A retirement with no replacement at all (retired 2026-07) → the whole approach was abandoned <!-- bindle:context-id: $id_no_repl -->
  why: w
  so: s
  revisit-when: r
  evidence: #30
EOF

before="$(sha "$TMP/retire-all-kinds.md")"
out="$("$PY" "$HELPER" validate --map "$TMP/retire-all-kinds.md" --format json)"
after="$(sha "$TMP/retire-all-kinds.md")"

check "retirement: the whole all-kinds map validates clean (ok, zero errors)" \
  bash -c '[ "$(jget "r[\"ok\"]" "$1")" = True ]' _ "$out"
check "retirement: exactly 7 entries, all anchored, one record per logical entry" \
  bash -c '[ "$(jget "len(r[\"entries\"])" "$1")" = 7 ] && [ "$(jget "r[\"anchored_count\"]" "$1")" = 7 ]' _ "$out"
check "case 1: anchored DECISION retirement -> one superseded/decision node keeping its id" \
  bash -c '[ "$(jget "[e[\"id\"] for e in r[\"entries\"] if e[\"section\"]==\"superseded\" and e[\"kind\"]==\"decision\"][0]" "$1")" = "$2" ]' _ "$out" "$id_r_dec"
check "case 2: anchored LEARNING retirement -> one superseded/learning node keeping its id" \
  bash -c '[ "$(jget "[e[\"id\"] for e in r[\"entries\"] if e[\"kind\"]==\"learning\"][0]" "$1")" = "$2" ]' _ "$out" "$id_r_learn"
check "case 3: anchored ASSUMPTION retirement -> one superseded/assumption node keeping its id" \
  bash -c '[ "$(jget "[e[\"id\"] for e in r[\"entries\"] if e[\"kind\"]==\"assumption\"][0]" "$1")" = "$2" ]' _ "$out" "$id_r_assum"
check "case 4: anchored TENSION retirement -> ONE superseded/tension node (sides absorbed, not nodes)" \
  bash -c '[ "$(jget "[e[\"id\"] for e in r[\"entries\"] if e[\"kind\"]==\"tension\"][0]" "$1")" = "$2" ] && [ "$(jget "sum(1 for e in r[\"entries\"] if e[\"kind\"]==\"tension\")" "$1")" = 1 ]' _ "$out" "$id_r_tension"
check "case 5: anchored QUESTION retirement -> one superseded/question node keeping its id" \
  bash -c '[ "$(jget "[e[\"id\"] for e in r[\"entries\"] if e[\"kind\"]==\"question\"][0]" "$1")" = "$2" ]' _ "$out" "$id_r_question"
check "case 6: retirement without a replacement is valid and omits superseded-by" \
  bash -c '[ "$(jget "[e[\"anchored\"] for e in r[\"entries\"] if e[\"id\"]==\"$2\"][0]" "$1")" = True ]' _ "$out" "$id_no_repl"
check "case 7: the replacement is a separate live entry with a DISTINCT id" \
  bash -c '[ "$1" != "$2" ] && [ "$(jget "[e[\"section\"] for e in r[\"entries\"] if e[\"id\"]==\"$1\"][0]" "$3")" = decisions ]' \
  _ "$id_replacement" "$id_r_dec" "$out"
check "retirement: nothing is left behind — zero entries remain in Learnings/A&T/Open questions" \
  bash -c '[ "$(jget "sum(1 for e in r[\"entries\"] if e[\"section\"] in (\"learnings\",\"assumptions\",\"questions\"))" "$1")" = 0 ]' _ "$out"
check "retirement: validation performs zero writes across all five kinds" \
  bash -c '[ "$1" = "$2" ]' _ "$before" "$after"

# case 20: repeated validation is byte-identical after persistence.
out_again="$("$PY" "$HELPER" validate --map "$TMP/retire-all-kinds.md" --format json)"
check "case 20: repeated validation of the retired map is byte-identical" \
  bash -c '[ "$1" = "$2" ]' _ "$out" "$out_again"

# case 9/10 (wrong-kind / wrong-target): the retired kind and the replacement
# target are read ONLY from the typed prefix and the id marker, never inferred
# from prose — so a tombstone whose prose names a different kind or a different
# replacement than its markers say is reported on its markers, not its words.
sed -e 's/^  why: original why, carried down verbatim$/  why: EDITED after retirement/' \
  -e 's/→ replaced by the replacement decision/→ prose now names a completely different successor/' \
  "$TMP/retire-all-kinds.md" >"$TMP/retire-prose-edited.md"
out_prose="$("$PY" "$HELPER" validate --map "$TMP/retire-prose-edited.md" --format json)"
check "cases 9/10: editing a tombstone's prose/fields never changes its id, kind, or replacement target" \
  bash -c '[ "$(jget "[e[\"id\"] for e in r[\"entries\"] if e[\"kind\"]==\"decision\" and e[\"section\"]==\"superseded\"][0]" "$1")" = "$2" ] && [ "$(jget "r[\"ok\"]" "$1")" = True ]' \
  _ "$out_prose" "$id_r_dec"

echo "== retirement recorded in place is not a valid representation (case 11) =="

# The shape an earlier cut of #179 wrongly blessed as a "retirement pair": the
# retired entry left behind, status-flipped, sharing its id with a tombstone.
# Under the universal model this is two records for one logical entry — a
# compiler would emit the leftover as a second node with status `current` —
# so it is now reported twice over: retirement-in-place AND duplicate-id.
cat >"$TMP/inplace.md" <<EOF
# demo — map

updated: 2026-07-16 · evidence through: none

## Brief

## Decisions

### Retired but left in place (2026-07, superseded) <!-- bindle:context-id: $id_r_dec -->
why: w
so: s
revisit-when: r
evidence: #1

## Learnings

## Assumptions & tensions

## Open questions

## Superseded

- decision: Retired but left in place (retired 2026-07) → gone <!-- bindle:context-id: $id_r_dec -->
EOF

out_ip="$("$PY" "$HELPER" validate --map "$TMP/inplace.md" --format json)"
check "case 11: an anchored entry retired in place is an ERROR (retirement-in-place)" \
  bash -c '[ "$(jget "sum(1 for i in r[\"issues\"] if i[\"code\"]==\"retirement-in-place\" and i[\"severity\"]==\"error\")" "$1")" = 1 ]' _ "$out_ip"
check "case 11: the same id in both places is ALSO a duplicate-id conflict (no pair exemption)" \
  bash -c '[ "$(jget "sum(1 for i in r[\"issues\"] if i[\"code\"]==\"duplicate-id\")" "$1")" = 1 ]' _ "$out_ip"
check "case 11: the map is not ok" \
  bash -c '[ "$(jget "r[\"ok\"]" "$1")" = False ]' _ "$out_ip"

echo "== legacy unanchored retirement + wrong-kind representation (cases 8, 9, 18) =="

# Case 8: retiring an entry that predates #179 and never had an id. It moves
# to Superseded and gets the typed prefix like any other retirement, but no
# identity is allocated — retirement is NOT an anchoring event and never
# invokes #184's anchor authority. Informational only, never an error.
cat >"$TMP/legacy-retire.md" <<'EOF'
# demo — map

updated: 2026-07-16 · evidence through: none

## Brief

## Decisions

## Learnings

## Assumptions & tensions

## Open questions

## Superseded

- decision: A legacy decision retired after #179 shipped (retired 2026-07) → replaced by nothing yet
  why: predates identity markers entirely
  so: nothing to preserve
  revisit-when: never
  evidence: #9
- A pre-#179 untyped tombstone left exactly as the owner wrote it (retired 2026-05) → superseded by something
EOF

before_leg="$(sha "$TMP/legacy-retire.md")"
out_leg="$("$PY" "$HELPER" validate --map "$TMP/legacy-retire.md" --format json)"
after_leg="$(sha "$TMP/legacy-retire.md")"

check "case 8: legacy unanchored retirement validates ok (no error)" \
  bash -c '[ "$(jget "r[\"ok\"]" "$1")" = True ]' _ "$out_leg"
check "case 8: it is typed (kind recovered) yet carries NO id — retirement allocated nothing" \
  bash -c '[ "$(jget "sum(1 for e in r[\"entries\"] if e[\"kind\"]==\"decision\" and e[\"section\"]==\"superseded\" and e[\"anchored\"] is False)" "$1")" = 1 ] && [ "$(jget "r[\"anchored_count\"]" "$1")" = 0 ]' _ "$out_leg"
check "case 8: the missing id is reported as info, never an error" \
  bash -c '[ "$(jget "sum(1 for i in r[\"issues\"] if i[\"severity\"]==\"error\")" "$1")" = 0 ]' _ "$out_leg"
check "case 8/19: a pre-#179 untyped tombstone stays informational and is left byte-identical" \
  bash -c '[ "$1" = "$2" ]' _ "$before_leg" "$after_leg"

# Case 9: a tombstone whose kind cannot be recovered from its own typed
# prefix. Anchored -> error (a compiler cannot type the node, and kind is
# never inferred from prose). Unanchored -> info (legacy shape, above).
id_wrongkind="$("$PY" "$HELPER" allocate --project demo)"
cat >"$TMP/wrongkind.md" <<EOF
# demo — map

## Superseded

- widget: not one of the five supported kinds (retired 2026-07) → x <!-- bindle:context-id: $id_wrongkind -->
EOF
out_wk="$("$PY" "$HELPER" validate --map "$TMP/wrongkind.md" --format json)"
check "case 9: an ANCHORED tombstone with an unrecoverable kind is an ERROR" \
  bash -c '[ "$(jget "sum(1 for i in r[\"issues\"] if i[\"code\"]==\"untyped-tombstone\" and i[\"severity\"]==\"error\")" "$1")" = 1 ] && [ "$(jget "r[\"ok\"]" "$1")" = False ]' _ "$out_wk"

# Case 18: a failed or aborted promotion persists no identity state. The
# allocator is the only thing that can mint an id, and it is pure stdout —
# it opens no file, creates no pending-id record, and touches nothing on
# disk, so a run that dies before its map write leaves nothing behind.
FAILDIR="$TMP/failed-promotion"
mkdir -p "$FAILDIR"
(
  cd "$FAILDIR" || exit 1
  "$PY" "$HELPER" allocate --project demo >/dev/null
  exit 1
)
check "case 18: an allocate whose caller then fails leaves zero files behind (no pending-id state)" \
  bash -c '[ "$(find "$1" -mindepth 1 | wc -l | tr -d " ")" = 0 ]' _ "$FAILDIR"

echo "== identity occurrence invariant: one id, one occurrence, for life (cases 12, 13) =="

# Because retirement MOVES an entry rather than copying it, one identity has
# exactly one occurrence for its whole life. There is no legitimate duplicate
# and no pair to carve out: any id occurring more than once, anywhere, in any
# section, in any combination of kinds, is a conflict. This is what makes
# #183's rule ("duplicate identities across current and superseded sections
# are conflicts") literally true with no exception attached.
id_two_live="$("$PY" "$HELPER" allocate --project demo)"
id_two_tombs="$("$PY" "$HELPER" allocate --project demo)"
id_live_and_tomb="$("$PY" "$HELPER" allocate --project demo)"
id_thrice="$("$PY" "$HELPER" allocate --project demo)"
id_cross_kind="$("$PY" "$HELPER" allocate --project demo)"

cat >"$TMP/occurrences.md" <<EOF
# demo — map

updated: 2026-07-16 · evidence through: none

## Brief

## Decisions

### Two live entries share an id, A (2026-07, settled) <!-- bindle:context-id: $id_two_live -->
why: a
so: a
revisit-when: a
evidence: #1

### Two live entries share an id, B (2026-07, settled) <!-- bindle:context-id: $id_two_live -->
why: b
so: b
revisit-when: b
evidence: #2

### A settled live entry whose id also appears on a tombstone (2026-07, settled) <!-- bindle:context-id: $id_live_and_tomb -->
why: c
so: c
revisit-when: c
evidence: #3

### An id used three times, occurrence one (2026-07, settled) <!-- bindle:context-id: $id_thrice -->
why: d
so: d
revisit-when: d
evidence: #4

## Learnings

### A learning sharing an id with a decision tombstone (2026-07) <!-- bindle:context-id: $id_cross_kind -->
why: e
so: e
evidence: #5

## Assumptions & tensions

## Open questions

## Superseded

- decision: Two tombstones share an id, A (retired 2026-07) → x <!-- bindle:context-id: $id_two_tombs -->
- decision: Two tombstones share an id, B (retired 2026-07) → x <!-- bindle:context-id: $id_two_tombs -->
- decision: An unrelated tombstone reusing a live id (retired 2026-07) → x <!-- bindle:context-id: $id_live_and_tomb -->
- decision: An id used three times, occurrence two (retired 2026-07) → x <!-- bindle:context-id: $id_thrice -->
- decision: An id used three times, occurrence three (retired 2026-07) → x <!-- bindle:context-id: $id_thrice -->
- decision: A decision tombstone sharing an id with a live learning (retired 2026-07) → x <!-- bindle:context-id: $id_cross_kind -->
EOF

before_occ="$(sha "$TMP/occurrences.md")"
out_occ="$("$PY" "$HELPER" validate --map "$TMP/occurrences.md" --format json)"
after_occ="$(sha "$TMP/occurrences.md")"

dupmsgs() { jget "[i[\"message\"] for i in r[\"issues\"] if i[\"code\"]==\"duplicate-id\"]" "$1"; }
export -f dupmsgs

check "case 12: two ORIGINALS (live entries) sharing an id is a conflict" \
  bash -c 'contains "$2" "$(dupmsgs "$1")"' _ "$out_occ" "$id_two_live"
check "case 13: two TOMBSTONES sharing an id is a conflict" \
  bash -c 'contains "$2" "$(dupmsgs "$1")"' _ "$out_occ" "$id_two_tombs"
check "occurrence: a live entry and an unrelated tombstone sharing an id is a conflict (no cross-section exemption)" \
  bash -c 'contains "$2" "$(dupmsgs "$1")"' _ "$out_occ" "$id_live_and_tomb"
check "occurrence: a third occurrence of an id is a conflict" \
  bash -c 'contains "$2" "$(dupmsgs "$1")"' _ "$out_occ" "$id_thrice"
check "occurrence: a cross-kind collision (live learning + decision tombstone) is a conflict" \
  bash -c 'contains "$2" "$(dupmsgs "$1")"' _ "$out_occ" "$id_cross_kind"
check "occurrence: every one of the 5 colliding ids is reported — exactly 5 duplicate-id conflicts" \
  bash -c '[ "$(jget "sum(1 for i in r[\"issues\"] if i[\"code\"]==\"duplicate-id\")" "$1")" = 5 ]' _ "$out_occ"
check "occurrence: the map is not ok" \
  bash -c '[ "$(jget "r[\"ok\"]" "$1")" = False ]' _ "$out_occ"
check "case 17: validation performs zero writes across every duplicate scenario" \
  bash -c '[ "$1" = "$2" ]' _ "$before_occ" "$after_occ"

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

echo "== bindle:superseded-by rejected on every active (non-tombstone) anchor =="

# The contract permits bindle:superseded-by only on a typed Superseded
# tombstone. A marker placed directly on an active Decision/Learning/
# Assumption/tension-parent/Open-question anchor must be reported as
# misplaced, never interpreted or silently dropped — regardless of whether
# its value is a real, resolvable id elsewhere in the map (proving rejection
# is about PLACEMENT, not resolution).
id_active_dec="$("$PY" "$HELPER" allocate --project demo)"
id_active_learn="$("$PY" "$HELPER" allocate --project demo)"
id_active_assum="$("$PY" "$HELPER" allocate --project demo)"
id_active_tension="$("$PY" "$HELPER" allocate --project demo)"
id_active_question="$("$PY" "$HELPER" allocate --project demo)"
id_valid_target="$("$PY" "$HELPER" allocate --project demo)"
id_valid_tombstone="$("$PY" "$HELPER" allocate --project demo)"

cat >"$TMP/active-sb.md" <<EOF
# demo — map

updated: 2026-07-16 · evidence through: none

## Brief

## Decisions

### A valid target decision, referenced only as a superseded-by pointer (2026-07, settled) <!-- bindle:context-id: $id_valid_target -->
why: w
so: s
revisit-when: r
evidence: #1

### An active decision wrongly carrying superseded-by on its anchor (2026-07, settled) <!-- bindle:context-id: $id_active_dec --> <!-- bindle:superseded-by: $id_valid_target -->
why: w
so: s
revisit-when: r
evidence: #2

## Learnings

### An active learning wrongly carrying superseded-by on its anchor <!-- bindle:context-id: $id_active_learn --> <!-- bindle:superseded-by: $id_valid_target -->
why: w
so: s
evidence: #3

## Assumptions & tensions

- an active assumption wrongly carrying superseded-by — confidence: high — evidence: #4 <!-- bindle:context-id: $id_active_assum --> <!-- bindle:superseded-by: $id_valid_target -->
- an active tension parent wrongly carrying superseded-by — confidence: low — evidence: #5 <!-- bindle:context-id: $id_active_tension --> <!-- bindle:superseded-by: $id_valid_target -->
  - side a — evidence: #5a
  - side b — evidence: #5b

## Open questions

- an active open question wrongly carrying superseded-by, twice over? (open) — so: implication — evidence: #6 <!-- bindle:context-id: $id_active_question --> <!-- bindle:superseded-by: $id_valid_target --> <!-- bindle:superseded-by: $id_valid_target -->

## Superseded

- decision: a valid typed tombstone still accepts one resolvable superseded-by (retired 2026-07) → replaced by the valid target decision <!-- bindle:context-id: $id_valid_tombstone --> <!-- bindle:superseded-by: $id_valid_target -->
EOF

before_asb="$(sha "$TMP/active-sb.md")"
out_asb="$("$PY" "$HELPER" validate --map "$TMP/active-sb.md" --format json)"
after_asb="$(sha "$TMP/active-sb.md")"

placed_msgs() { jget "[i[\"message\"] for i in r[\"issues\"] if i[\"code\"]==\"misplaced-marker\" and \"valid only on a typed Superseded tombstone\" in i[\"message\"]]" "$1"; }
export -f placed_msgs

check "active decision: anchor-line superseded-by is rejected as misplaced" \
  bash -c 'contains "$2" "$(placed_msgs "$1")"' _ "$out_asb" "$id_active_dec"
check "active learning: anchor-line superseded-by is rejected as misplaced" \
  bash -c 'contains "$2" "$(placed_msgs "$1")"' _ "$out_asb" "$id_active_learn"
check "active assumption: anchor-line superseded-by is rejected as misplaced" \
  bash -c 'contains "$2" "$(placed_msgs "$1")"' _ "$out_asb" "$id_active_assum"
check "active structured-tension parent: anchor-line superseded-by is rejected as misplaced" \
  bash -c 'contains "$2" "$(placed_msgs "$1")"' _ "$out_asb" "$id_active_tension"
check "active open question: anchor-line superseded-by is rejected as misplaced" \
  bash -c 'contains "$2" "$(placed_msgs "$1")"' _ "$out_asb" "$id_active_question"
check "case 6: TWO superseded-by markers on one active (open-question) anchor still yield an error, not silently ignored" \
  bash -c 'contains "$2" "$(placed_msgs "$1")"' _ "$out_asb" "$id_active_question"
check "exactly 5 active anchors (decision/learning/assumption/tension/question) are rejected, one finding each" \
  bash -c '[ "$(jget "sum(1 for i in r[\"issues\"] if i[\"code\"]==\"misplaced-marker\" and \"valid only on a typed Superseded tombstone\" in i[\"message\"])" "$1")" = 5 ]' _ "$out_asb"
check "the marker is rejected by PLACEMENT, not resolution: no superseded-by-unresolved finding anywhere, despite a real, resolvable target id" \
  bash -c '[ "$(jget "sum(1 for i in r[\"issues\"] if i[\"code\"] in (\"superseded-by-unresolved\",\"superseded-by-malformed\",\"superseded-by-missing-value\",\"superseded-by-self-referential\",\"superseded-by-duplicate\"))" "$1")" = 0 ]' _ "$out_asb"
tombstone_line="$(jget "[e[\"line\"] for e in r[\"entries\"] if e[\"id\"]==\"$id_valid_tombstone\"][0]" "$out_asb")"
check "case 7: a valid typed tombstone still accepts its own resolvable superseded-by (no error on it)" \
  bash -c '[ "$(jget "sum(1 for i in r[\"issues\"] if i[\"line\"]==$2)" "$1")" = 0 ]' _ "$out_asb" "$tombstone_line"
check "active anchors: the map is not ok (misplaced superseded-by is an error)" \
  bash -c '[ "$(jget "r[\"ok\"]" "$1")" = False ]' _ "$out_asb"
check "case 8: validation performs zero writes even with misplaced superseded-by findings (byte-identical)" \
  bash -c '[ "$1" = "$2" ]' _ "$before_asb" "$after_asb"

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

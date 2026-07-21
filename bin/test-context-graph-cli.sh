#!/usr/bin/env bash
# shellcheck disable=SC2016
#
# test-context-graph-cli.sh — CLI-process-level integration checks for
# bin/context-graph.py (issue #191, epic #140) that unittest cannot express:
# subprocess invocation, cross-directory execution, concurrent processes,
# and end-to-end command sequences. Module-level logic (context_graph.config
# / .lock / .atomic_io) is already exercised by
# `python3 -m unittest discover -s bin/context_graph/tests -t .`, which
# bin/test-context-graph-schema.sh already runs and which auto-discovers
# this task's new test_atomic_io.py / test_lock.py / test_config.py files —
# not repeated here.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$(command -v python3)"
CLI="$REPO_ROOT/bin/context-graph.py"

SCRATCH="$(mktemp -d)"
trap 'rm -rf "$SCRATCH"' EXIT

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

echo "== fixture 24: invocation outside a Git repo with explicit paths =="
OUTSIDE_DIR="$(mktemp -d)"
NH="$(mktemp -d)"
(cd "$OUTSIDE_DIR" && "$PY" "$CLI" init --notes-home "$NH" --project outsiderepo) >"$SCRATCH/cg-init.out" 2>&1
check "init succeeds from a directory outside any Git repo" test $? -eq 0

echo "== fixture 5: two concurrent init processes persist exactly one ID =="
NH2="$(mktemp -d)"
"$PY" "$CLI" init --notes-home "$NH2" --project racer >"$SCRATCH/cg-race-a.json" 2>&1 &
PID_A=$!
"$PY" "$CLI" init --notes-home "$NH2" --project racer >"$SCRATCH/cg-race-b.json" 2>&1 &
PID_B=$!
wait "$PID_A"
wait "$PID_B"
ID_A=$("$PY" -c "import json;print(json.load(open('$SCRATCH/cg-race-a.json'))['config']['project_id'])")
ID_B=$("$PY" -c "import json;print(json.load(open('$SCRATCH/cg-race-b.json'))['config']['project_id'])")
check "concurrent init processes agree on one project_id" bash -c "test '$ID_A' = '$ID_B'"

echo "== fixture 3: repeated init is byte-identical =="
NH3="$(mktemp -d)"
"$PY" "$CLI" init --notes-home "$NH3" --project stable >/dev/null
CFG="$NH3/projects/stable/.bindle/context/config.json"
SUM1=$(shasum -a 256 "$CFG" | awk '{print $1}')
"$PY" "$CLI" init --notes-home "$NH3" --project stable >/dev/null
SUM2=$(shasum -a 256 "$CFG" | awk '{print $1}')
check "repeated init leaves config.json byte-identical" bash -c "test '$SUM1' = '$SUM2'"

echo "== end-to-end command sequence =="
NH4="$(mktemp -d)"
"$PY" "$CLI" init --notes-home "$NH4" --project e2e >/dev/null
check "config validate on a fresh project reports no findings" bash -c \
  "\"$PY\" \"$CLI\" config validate --notes-home \"$NH4\" --project e2e | \"$PY\" -c 'import json,sys; d=json.load(sys.stdin); exit(0 if d[\"findings\"]==[] else 1)'"
"$PY" "$CLI" config add-repository --notes-home "$NH4" --project e2e \
  --alias main --provider github --coordinates thomas-estep/bindle --default >/dev/null
check "config add-repository succeeds" test $? -eq 0
BID=$("$PY" "$CLI" config status --notes-home "$NH4" --project e2e |
  "$PY" -c "import json,sys; print(json.load(sys.stdin)['config']['repositories'][0]['binding_id'])")
"$PY" "$CLI" config remove-repository --notes-home "$NH4" --project e2e --binding-id "$BID" >/dev/null
check "config remove-repository succeeds" test $? -eq 0

echo "== fixture 25: no command requires a skill or session (static check) =="
check "context-graph.py never imports skill machinery" bash -c \
  "! grep -q 'skills/' '$CLI'"

echo "== fixture 28: lock contention surfaces owner metadata, break-lock clears it =="
NH5="$(mktemp -d)"
"$PY" "$CLI" init --notes-home "$NH5" --project locked >/dev/null
# #228: the lock is project-scoped, at .bindle/.lock -- the parent of every
# surface under .bindle/, not inside any one of them.
LOCKDIR="$NH5/projects/locked/.bindle"
LEGACY_LOCKDIR="$NH5/projects/locked/.bindle/context"
check "the lock is not inside the context surface" bash -c \
  "test ! -f '$LEGACY_LOCKDIR/.lock'"
"$PY" -c "import json,os; open(os.path.join('$LOCKDIR','.lock'),'w').write(json.dumps({'pid':999999,'hostname':'nowhere','operation':'init','acquired_at':'x'}))"
"$PY" "$CLI" config break-lock --notes-home "$NH5" --project locked >/dev/null 2>&1
check "break-lock without --force is refused" test $? -ne 0
"$PY" "$CLI" config break-lock --notes-home "$NH5" --project locked --force >/dev/null
check "break-lock --force removes the lock" bash -c "test ! -f '$LOCKDIR/.lock'"

echo "== fixture 28b: a lock orphaned at the pre-#228 path is reported, then cleared =="
NH5B="$(mktemp -d)"
"$PY" "$CLI" init --notes-home "$NH5B" --project stranded >/dev/null
LEGACY5B="$NH5B/projects/stranded/.bindle/context/.lock"
"$PY" -c "import json,os; open('$LEGACY5B','w').write(json.dumps({'pid':999999,'hostname':'crashed','operation':'apply','acquired_at':'x'}))"
LEGACY_SEEN="$("$PY" "$CLI" config status --notes-home "$NH5B" --project stranded |
  "$PY" -c "import json,sys; print((json.load(sys.stdin).get('legacy_lock') or {}).get('hostname'))")"
check "config status reports the legacy lock owner" test "$LEGACY_SEEN" = "crashed"
check "config status does not remove the legacy lock" test -f "$LEGACY5B"
"$PY" "$CLI" config break-lock --notes-home "$NH5B" --project stranded --force >/dev/null
check "break-lock --force clears the legacy lock too" test ! -f "$LEGACY5B"

echo "== #184 process-level propose/confirm/candidates + cross-boundary endpoint-legality (§16) =="
NH6="$(mktemp -d)"
"$PY" "$CLI" init --notes-home "$NH6" --project proj >/dev/null
check "init succeeds for the judgment-ledger scenario" test $? -eq 0

# Minimal map.md carrying two ANCHORED entries (explicit bindle:context-id
# markers) -- the grammar proven by test_review.py's MAP_TWO_DECISIONS
# fixture and test_compiler.py's base_map. Unanchored entries only ever
# yield identity_anchor_candidates, never usable proposal endpoints, so the
# two node ids below (context-node:proj:1111.../context-node:proj:2222...)
# come straight off the markers, matching the literal ids baked into the
# testdata/context-graph-judgment/v1/proposal-*.json fixtures -- no id needs
# to be discovered at runtime.
MAP_PATH="$NH6/projects/proj/map.md"
cat >"$MAP_PATH" <<'MAPEOF'
## Brief

## Decisions
### A decision (2026-07, settled) <!-- bindle:context-id: context-node:proj:11111111111111111111111111111111 -->
why: x
so: y
revisit-when: z
evidence:

## Learnings
### A learning (2026-07) <!-- bindle:context-id: context-node:proj:22222222222222222222222222222222 -->
why: x
so: y
evidence:

## Assumptions & tensions

## Open questions

## Superseded
MAPEOF

LEGAL="$REPO_ROOT/testdata/context-graph-judgment/v1/proposal-legal.json"
ILLEGAL="$REPO_ROOT/testdata/context-graph-judgment/v1/proposal-illegal-endpoint.json"
ADVISORY="$REPO_ROOT/testdata/context-graph-judgment/v1/proposal-advisory-mismatch.json"

"$PY" "$CLI" propose --notes-home "$NH6" --project proj --input "$LEGAL" \
  >"$SCRATCH/cg-propose-legal.json" 2>&1
check "propose on a legal endpoint pair exits 0" test $? -eq 0
CANDKEY=$("$PY" -c "
import json
d = json.load(open('$SCRATCH/cg-propose-legal.json'))
print(d['candidate']['candidate_key'] if d.get('candidate') else '')
")
check "propose prints a candidate_key" bash -c "test -n '$CANDKEY'"

"$PY" "$CLI" confirm --notes-home "$NH6" --project proj \
  --candidate-key "$CANDKEY" --decision accepted --input "$LEGAL" \
  >"$SCRATCH/cg-confirm.json" 2>&1
check "confirm --decision accepted on the proposed candidate exits 0" test $? -eq 0
JUDGMENTS="$NH6/projects/proj/.bindle/context/judgments.jsonl"
check "confirm appends exactly one judgments.jsonl line" bash -c \
  "test -f '$JUDGMENTS' && test \$(wc -l <'$JUDGMENTS') -eq 1"

"$PY" "$CLI" candidates --notes-home "$NH6" --project proj --status accepted \
  >"$SCRATCH/cg-candidates.json" 2>&1
check "candidates --status accepted exits 0" test $? -eq 0
check "candidates --status accepted lists the confirmed candidate_key" bash -c "
\"$PY\" -c \"
import json
d = json.load(open('$SCRATCH/cg-candidates.json'))
raise SystemExit(0 if any(r['candidate_key'] == '$CANDKEY' for r in d['rows']) else 1)
\"
"

"$PY" "$CLI" propose --notes-home "$NH6" --project proj --input "$ILLEGAL" \
  >"$SCRATCH/cg-propose-illegal.json" 2>&1
check "propose on a cross-boundary illegal endpoint pair exits 1" test $? -eq 1
check "propose on an illegal endpoint pair mints no candidate" bash -c "
\"$PY\" -c \"
import json
d = json.load(open('$SCRATCH/cg-propose-illegal.json'))
raise SystemExit(0 if d['candidate'] is None else 1)
\"
"

"$PY" "$CLI" propose --notes-home "$NH6" --project proj --input "$ADVISORY" \
  >"$SCRATCH/cg-propose-advisory.json" 2>&1
check "propose with a mismatched advisory_candidate_key exits 1" test $? -eq 1
check "propose with a mismatched advisory_candidate_key mints no candidate" bash -c "
\"$PY\" -c \"
import json
d = json.load(open('$SCRATCH/cg-propose-advisory.json'))
raise SystemExit(0 if d['candidate'] is None else 1)
\"
"

echo
echo "test-context-graph-cli: $pass passed, $fail failed"
[ "$fail" -eq 0 ]

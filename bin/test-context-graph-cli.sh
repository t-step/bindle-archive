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
LOCKDIR="$NH5/projects/locked/.bindle/context"
"$PY" -c "import json,os; open(os.path.join('$LOCKDIR','.lock'),'w').write(json.dumps({'pid':999999,'hostname':'nowhere','operation':'init','acquired_at':'x'}))"
"$PY" "$CLI" config break-lock --notes-home "$NH5" --project locked >/dev/null 2>&1
check "break-lock without --force is refused" test $? -ne 0
"$PY" "$CLI" config break-lock --notes-home "$NH5" --project locked --force >/dev/null
check "break-lock --force removes the lock" bash -c "test ! -f '$LOCKDIR/.lock'"

echo
echo "test-context-graph-cli: $pass passed, $fail failed"
[ "$fail" -eq 0 ]

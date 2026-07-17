#!/usr/bin/env bash
# shellcheck disable=SC2016  # assertions pass values into `bash -c '...'` as
# $1/$2; single quotes are deliberate — expansion happens in the inner shell.
#
# test-context-evidence.sh — the single test harness for
# bin/context_graph/evidence.py and bin/context-evidence.py (issue #181,
# epic #140): stdlib unittest module tests plus the CLI-level fixture
# corpus (testdata/context-evidence/v1/{valid,invalid,expected}.jsonl).
# Entirely offline, stdlib-only, no network access, no filesystem writes
# outside this script's own stdout.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$(command -v python3)"
CLI="$REPO_ROOT/bin/context-evidence.py"
FIXTURE_DIR="$REPO_ROOT/testdata/context-evidence/v1"

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

echo "== module unit tests (stdlib unittest) =="
(cd "$REPO_ROOT" && "$PY" -m unittest discover -s bin/context_graph/tests -t . \
  -p "test_evidence.py" -v)
unit_status=$?
check "context_graph.evidence unit tests pass" bash -c "exit $unit_status"

echo "== CLI fixture corpus =="
run_fixture() {
  # $1: one fixture JSON line. Invokes the CLI, prints the resulting JSON
  # on stdout (or a {"__cli_error__": ...} envelope on failure).
  "$PY" - "$CLI" "$1" <<'PYEOF'
import json
import subprocess
import sys

cli = sys.argv[1]
fixture = json.loads(sys.argv[2])

argv = [sys.executable, cli, fixture["command"], "--project-id", fixture["project_id"]]
if fixture.get("repository") is not None:
    argv += ["--repository", fixture["repository"]]
for binding_id in fixture.get("binding_ids", []):
    argv += ["--binding-id", binding_id]
if fixture.get("kind_hint"):
    argv += ["--kind-hint", fixture["kind_hint"]]
argv += ["--value", fixture["value"]]

proc = subprocess.run(argv, capture_output=True, text=True)
if proc.returncode != 0:
    print(json.dumps({"__cli_error__": True, "exit_code": proc.returncode,
                       "stderr": proc.stderr.strip()}))
else:
    print(proc.stdout.strip())
PYEOF
}

while IFS= read -r fixture_line; do
  [ -z "$fixture_line" ] && continue
  fid="$("$PY" -c 'import json,sys; print(json.loads(sys.argv[1])["id"])' "$fixture_line")"
  desc="$("$PY" -c 'import json,sys; print(json.loads(sys.argv[1])["fixture"])' "$fixture_line")"
  expected="$(grep "\"id\": \"$fid\"" "$FIXTURE_DIR/expected.jsonl" | head -1)"
  if [ -z "$expected" ]; then
    printf '  ✗ [%s] %s -- no matching expected.jsonl entry\n' "$fid" "$desc"
    fail=$((fail + 1))
    continue
  fi
  actual_json="$(run_fixture "$fixture_line")"
  ok="$("$PY" -c '
import json, sys
actual = json.loads(sys.argv[1])
expected = json.loads(sys.argv[2])["expect"]
print("1" if actual == expected else "0")
' "$actual_json" "$expected")"
  if [ "$ok" = "1" ]; then
    printf '  ✓ [%s] %s\n' "$fid" "$desc"
    pass=$((pass + 1))
  else
    printf '  ✗ [%s] %s\n    got:      %s\n    expected: %s\n' \
      "$fid" "$desc" "$actual_json" "$expected"
    fail=$((fail + 1))
  fi
done < <(cat "$FIXTURE_DIR/valid.jsonl" "$FIXTURE_DIR/invalid.jsonl")

echo "== usage-error fixture (f54): repository-shaped --project-id =="
usage_output="$("$PY" "$CLI" normalize --project-id 'project:thomas-estep/bindle' \
  --value 'sessions/x.md' 2>&1)"
usage_exit=$?
check "f54: repository-shaped --project-id exits 64" bash -c "[ '$usage_exit' = '64' ]"
check "f54: repository-shaped --project-id reports a message" \
  bash -c '[ -n "$1" ]' _ "$usage_output"

echo "== deterministic ordering across repeated runs =="
run1="$(while IFS= read -r line; do
  [ -z "$line" ] && continue
  run_fixture "$line"
done < <(cat "$FIXTURE_DIR/valid.jsonl" "$FIXTURE_DIR/invalid.jsonl"))"
run2="$(while IFS= read -r line; do
  [ -z "$line" ] && continue
  run_fixture "$line"
done < <(cat "$FIXTURE_DIR/valid.jsonl" "$FIXTURE_DIR/invalid.jsonl"))"
check "repeated CLI runs over the same corpus are byte-identical" \
  bash -c '[ "$1" = "$2" ]' _ "$run1" "$run2"

echo
echo "== summary =="
echo "pass=$pass fail=$fail"
if [ "$fail" -gt 0 ]; then
  exit 1
fi
exit 0

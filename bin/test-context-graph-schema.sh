#!/usr/bin/env bash
# shellcheck disable=SC2016  # assertions pass values into `bash -c '...'` as
# $1/$2; single quotes are deliberate — expansion happens in the inner shell.
#
# test-context-graph-schema.sh — the single test harness for
# bin/context_graph/ (issue #180, epic #140): stdlib unittest module tests,
# the fixture-manifest CLI pass, and two harness-level assertions
# (fixtures 31/32 from the issue body's "Canonical fixtures" list, which
# are properties of the whole corpus rather than single JSON files).
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$(command -v python3)"
MANIFEST="$REPO_ROOT/testdata/context-graph/v1/manifest.json"
CLI="$REPO_ROOT/bin/check-context-graph-fixtures.py"

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
(cd "$REPO_ROOT" && "$PY" -m unittest discover -s bin/context_graph/tests -t . -v)
unit_status=$?
check "context_graph unit tests pass" bash -c "exit $unit_status"

echo "== fixture manifest corpus =="
fixture_output="$("$PY" "$CLI" --manifest "$MANIFEST")"
fixture_status=$?
echo "$fixture_output"
check "every manifest-registered fixture passes" bash -c "exit $fixture_status"

echo "== fixture 31: deterministic ordering across repeated runs =="
run1="$("$PY" "$CLI" --manifest "$MANIFEST" --format json)"
run2="$("$PY" "$CLI" --manifest "$MANIFEST" --format json)"
check "repeated CLI runs over the same manifest are byte-identical" \
  bash -c '[ "$1" = "$2" ]' _ "$run1" "$run2"

echo "== fixture 32: every v1 relationship appears in >=1 valid fixture =="
covered="$(
  "$PY" - "$MANIFEST" <<'PYEOF'
import json
import sys

RELATIONSHIPS = {
    "contains", "supported_by", "discussed_in", "implemented_by",
    "validated_by", "closes", "motivates", "constrains", "depends_on",
    "resolves", "supports", "contradicts", "supersedes", "revisits",
}

with open(sys.argv[1], encoding="utf-8") as fh:
    manifest = json.load(fh)

covered_tags = set()
for entry in manifest["fixtures"]:
    if entry.get("expect_valid") is True or entry.get("assertion") in (
        "candidate_key_equals", "candidate_key_distinct",
        "dependency_fingerprint_equals", "dependency_fingerprint_distinct",
        "canonicalization",
    ):
        covered_tags.update(entry.get("coverage_tags", []))

missing = sorted(RELATIONSHIPS - covered_tags)
print(" ".join(missing))
PYEOF
)"
check "no relationship is missing coverage (missing: '${covered:-none}')" \
  bash -c '[ -z "$1" ]' _ "$covered"

echo "== JSON Schema / native conformance (skip-if-absent locally) =="
conformance_output="$(cd "$REPO_ROOT" && "$PY" -m unittest bin.context_graph.tests.test_schema_conformance -v 2>&1)"
conformance_status=$?
echo "$conformance_output"
check "schema conformance module completes (skips cleanly if jsonschema absent)" \
  bash -c "exit $conformance_status"

echo
echo "test-context-graph-schema: $pass passed, $fail failed"
[ "$fail" -eq 0 ]

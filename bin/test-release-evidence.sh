#!/usr/bin/env bash
# shellcheck disable=SC2016  # assertions pass values into `bash -c '...'` as $1;
# the single quotes are deliberate — expansion happens in the inner shell, not
# here. Disabled file-wide rather than tagging each of ~20 assertion lines.
#
# test-release-evidence.sh — exercise bin/release-evidence.py against the
# checked-in dry-run fixtures and its pure classification logic. Offline by
# construction: the fixture path performs no git/gh calls, which one case
# proves by stripping PATH.
#
set -uo pipefail

unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_COMMON_DIR

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HELPER="$REPO_ROOT/bin/release-evidence.py"
FIX="$REPO_ROOT/bin/release-evidence-fixtures"
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
# result (bound as `r`) and print it. Keeps assertions reading structured
# fields, not fragile substring matches.
jget() {
  "$PY" -c 'import json,sys; r=json.load(sys.stdin); print(eval(sys.argv[1]))' \
    "$1" <<<"$2"
}
export -f jget
export PY

# --- the four contract cases + fail-safe, via --format json -----------------

no_release="$("$PY" "$HELPER" --fixture "$FIX/no-release.json" --format json)"
check "no-release: verdict ok" \
  bash -c '[ "$(jget "r[\"verdict\"]" "$1")" = ok ]' _ "$no_release"
check "no-release: highest class is none" \
  bash -c '[ "$(jget "r[\"aggregate\"][\"highest_deterministic_class\"]" "$1")" = none ]' _ "$no_release"
check "no-release: zero uncertain" \
  bash -c '[ "$(jget "r[\"aggregate\"][\"uncertain\"]" "$1")" = 0 ]' _ "$no_release"

batch="$("$PY" "$HELPER" --fixture "$FIX/batch-patch.json" --format json)"
check "batch-patch: highest class is patch" \
  bash -c '[ "$(jget "r[\"aggregate\"][\"highest_deterministic_class\"]" "$1")" = patch ]' _ "$batch"
check "batch-patch: zero uncertain" \
  bash -c '[ "$(jget "r[\"aggregate\"][\"uncertain\"]" "$1")" = 0 ]' _ "$batch"

minor="$("$PY" "$HELPER" --fixture "$FIX/release-now-minor.json" --format json)"
check "release-now-minor: highest class is minor" \
  bash -c '[ "$(jget "r[\"aggregate\"][\"highest_deterministic_class\"]" "$1")" = minor ]' _ "$minor"
check "release-now-minor: links #127 to the feat PR" \
  bash -c 'contains "#127" "$1"' _ "$minor"

bu="$("$PY" "$HELPER" --fixture "$FIX/breaking-uncertain.json" --format json)"
check "breaking-uncertain: highest class is breaking" \
  bash -c '[ "$(jget "r[\"aggregate\"][\"highest_deterministic_class\"]" "$1")" = breaking ]' _ "$bu"
check "breaking-uncertain: the unsignalled PR is uncertain, not guessed" \
  bash -c '[ "$(jget "r[\"aggregate\"][\"uncertain\"]" "$1")" -ge 2 ]' _ "$bu"
check "breaking-uncertain: label-vs-title conflict flagged as a contradiction" \
  bash -c '[ "$(jget "r[\"aggregate\"][\"contradictions\"]" "$1")" -ge 1 ]' _ "$bu"

# --- fail-safe: a failed sub-query is never laundered into a clean class -----

failed="$("$PY" "$HELPER" --fixture "$FIX/collection-failed.json" --format json)"
check "collection-failed: verdict is uncertain" \
  bash -c '[ "$(jget "r[\"verdict\"]" "$1")" = uncertain ]' _ "$failed"
check "collection-failed: no deterministic class asserted (None)" \
  bash -c '[ "$(jget "r[\"aggregate\"][\"highest_deterministic_class\"]" "$1")" = None ]' _ "$failed"
check "collection-failed: --strict exits nonzero" \
  bash -c '! "$0" --fixture "$1" --format json --strict >/dev/null' "$HELPER" "$FIX/collection-failed.json"
check "no-release: --strict exits zero on a clean verdict" \
  bash -c '"$0" "$1" --fixture "$2" --format json --strict >/dev/null' \
  "$PY" "$HELPER" "$FIX/no-release.json"

# --- the helper never fabricates a version or timing recommendation ---------

for f in no-release batch-patch release-now-minor breaking-uncertain collection-failed; do
  out="$("$PY" "$HELPER" --fixture "$FIX/$f.json" --format both)"
  check "$f: emits the authority (evidence-only) boundary" \
    bash -c 'contains "evidence only" "$1"' _ "$out"
  check "$f: no recommended_version key" \
    bash -c 'not_contains "recommended_version" "$1"' _ "$out"
  check "$f: no timing recommendation key" \
    bash -c 'not_contains "\"timing\"" "$1"' _ "$out"
done

# --- offline proof: fixture mode makes no git/gh calls ----------------------
# Run with a PATH that contains only python3 (no git, no gh). If the fixture
# path shelled out, this would fail; it must succeed.
STUB="$(mktemp -d)"
trap 'rm -rf "$STUB"' EXIT
ln -s "$PY" "$STUB/python3"
check "fixture mode succeeds with git and gh absent from PATH" \
  bash -c 'env -i PATH="$1" "$2" "$3" --fixture "$4" --format json >/dev/null' \
  _ "$STUB" "$PY" "$HELPER" "$FIX/no-release.json"

# --- error handling: unreadable / invalid fixture ---------------------------

check "missing fixture exits nonzero" \
  bash -c '! "$0" --fixture "$1" >/dev/null 2>&1' "$HELPER" "$STUB/does-not-exist.json"
printf 'not json{' >"$STUB/bad.json"
err="$("$PY" "$HELPER" --fixture "$STUB/bad.json" 2>&1)"
check "invalid-JSON fixture reports cleanly (no traceback)" \
  bash -c 'contains "cannot read fixture" "$1"' _ "$err"

# --- text format markers ----------------------------------------------------
txt="$("$PY" "$HELPER" --fixture "$FIX/breaking-uncertain.json" --format text)"
check "text: shows the CONTRADICTION marker" \
  bash -c 'contains "CONTRADICTION" "$1"' _ "$txt"
check "text: notes that uncertain changes need judgment" \
  bash -c 'contains "need human/model judgment" "$1"' _ "$txt"

# --- pure classification-logic unit tests (imported directly) ---------------
unit="$(
  "$PY" - "$HELPER" <<'PYEOF'
import importlib.util, sys
spec = importlib.util.spec_from_file_location("release_evidence", sys.argv[1])
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def cls(**kw):
    return m.classify_change(kw)


# conventional-title inference
assert cls(title="feat: x")["class"] == "minor"
assert cls(title="fix: x")["class"] == "patch"
assert cls(title="docs: x")["class"] == "none"
# breaking metadata (title bang and body token) outrank the base type
assert cls(title="feat!: x")["class"] == "breaking"
assert cls(title="feat: x", body="BREAKING CHANGE: y")["class"] == "breaking"
# explicit label wins when consistent / when no inference exists
assert cls(title="feat: x", labels=["release: minor"])["basis"] == "release-label"
assert cls(title="anything", labels=["release: patch"])["class"] == "patch"
# label conflicting with inference -> uncertain + contradiction, not override
c = cls(title="feat!: x", labels=["release: patch"])
assert c["class"] == "uncertain" and c["contradiction"] is True, c
# no deterministic signal -> uncertain, never guessed
c2 = cls(title="Reshape the thing")
assert c2["class"] == "uncertain" and c2["contradiction"] is False, c2
# a commit-sourced conventional change ranks as commits-since-tag (4)
assert cls(title="feat: x", source="commit")["precedence"] == 4
print("ok")
PYEOF
)"
check "classify_change precedence/contradiction/fail-safe unit tests" \
  bash -c 'contains "ok" "$1"' _ "$unit"

echo
echo "release-evidence tests: $pass passed, $fail failed"
[ "$fail" -eq 0 ]

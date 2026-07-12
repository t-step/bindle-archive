#!/usr/bin/env bash
#
# test-manifest-lib.sh — unit-test the shared manifest reader against a
# throwaway TSV. Nothing touches this repo's real install-manifest.tsv.
#
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=bin/lib/manifest.sh
source "$REPO_ROOT/bin/lib/manifest.sh"

pass=0 fail=0
check() {
  local d="$1"
  shift
  if "$@"; then
    printf '  ✓ %s\n' "$d"
    pass=$((pass + 1))
  else
    printf '  ✗ %s\n' "$d"
    fail=$((fail + 1))
  fi
}
grep_q() { grep -qF -- "$1" <<<"$2"; }
not_grep() { ! grep -qF -- "$1" <<<"$2"; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
cat >"$TMP/install-manifest.tsv" <<'TSV'
# GENERATED from capabilities.json — do not edit; run 'make manifest'
claude	skill	demo	skills/demo	skills/demo

codex	global-guidance	agents	global/AGENTS.md	AGENTS.md
TSV

LINES=""
collect() { LINES="${LINES}${1}|${2}|${3}|${4}|${5}"$'\n'; }
each_manifest_item "$TMP" collect

echo "manifest reader:"
check "banner line skipped" not_grep "# GENERATED" "$LINES"
check "blank line skipped (exactly 2 rows)" test "$(printf '%s' "$LINES" | grep -c '|')" -eq 2
check "skill row: src is absolutized" grep_q "claude|skill|demo|$TMP/skills/demo|skills/demo" "$LINES"
check "codex row present" grep_q "codex|global-guidance|agents|$TMP/global/AGENTS.md|AGENTS.md" "$LINES"
check "missing manifest is a no-op" each_manifest_item "$TMP/nope" collect

echo
echo "tests: ${pass} passed, ${fail} failed"
[ "$fail" -eq 0 ]

#!/usr/bin/env bash
# Single test harness for bin/architecture/ (#228, epic #141).
#
# Runs stdlib unittest discovery over the package's tests. Mirrors
# bin/test-structural-graph.sh.
set -euo pipefail

# Tests shell out to git in later slices; git sets GIT_DIR in a pre-commit
# hook env and it overrides `git -C`, which would silently target the real
# repo.
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_COMMON_DIR

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

pass=0
fail=0

# mktemp, not a $$-derived name: $$ is predictable, so a fixed /tmp path
# built from it is a symlink-attack target and collides across concurrent
# runs. Trapped so the file is removed even on an early set -e exit.
out="$(mktemp "${TMPDIR:-/tmp}/arch-check.XXXXXX")"
trap 'rm -f "$out"' EXIT

check() {
  local label="$1"
  shift
  if "$@" >"$out" 2>&1; then
    echo "  ✓ $label"
    pass=$((pass + 1))
  else
    echo "  ✗ $label"
    sed 's/^/      /' "$out"
    fail=$((fail + 1))
  fi
}

echo "architecture:"
check "unit tests" python3 -m unittest discover -s bin/architecture/tests -t bin

echo ""
if [ "$fail" -gt 0 ]; then
  echo "architecture: $fail check(s) failed, $pass passed"
  exit 1
fi
echo "architecture: all $pass check(s) passed"

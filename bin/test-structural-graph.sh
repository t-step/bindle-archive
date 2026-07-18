#!/usr/bin/env bash
# Single test harness for bin/structural_graph/ (#227).
#
# Runs stdlib unittest discovery over the package's tests, then the
# manifest-driven fixture runner once it exists. Mirrors
# bin/test-context-graph-schema.sh.
set -euo pipefail

# Fixture tests shell out to git; git sets GIT_DIR in a pre-commit hook env
# and it overrides `git -C`, which would silently target the real repo.
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_COMMON_DIR

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

pass=0
fail=0

check() {
  local label="$1"
  shift
  if "$@" >/tmp/sg-check.$$ 2>&1; then
    echo "  ✓ $label"
    pass=$((pass + 1))
  else
    echo "  ✗ $label"
    sed 's/^/      /' /tmp/sg-check.$$
    fail=$((fail + 1))
  fi
  rm -f /tmp/sg-check.$$
}

echo "structural-graph:"
check "unit tests" python3 -m unittest discover -s bin/structural_graph/tests -t .

echo ""
if [ "$fail" -gt 0 ]; then
  echo "structural-graph: $fail check(s) failed, $pass passed"
  exit 1
fi
echo "structural-graph: all $pass check(s) passed"

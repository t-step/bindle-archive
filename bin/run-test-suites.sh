#!/usr/bin/env bash
#
# run-test-suites.sh — discover and run every bin/test-*.sh suite.
#
# Convention, not configuration: any tracked bin/test-<name>.sh is a suite and
# runs automatically. Nothing needs registering in the Makefile or in
# .pre-commit-config.yaml, so a new suite cannot be written and then silently
# left out of the gate — which is exactly how eleven of them drifted out of
# commit-time coverage (#256, #257).
#
# Usage:
#   bin/run-test-suites.sh          # run every discovered suite
#   bin/run-test-suites.sh --list   # print the discovered suites, run nothing
#
# Exits non-zero if any suite fails, after running them all — one red suite
# should not hide the next.
#
set -uo pipefail # not -e: run every suite, then fail once

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT" || exit 1

suites=()
while IFS= read -r f; do
  [ -n "$f" ] || continue
  suites+=("$f")
done < <(git ls-files 'bin/test-*.sh' | sort)

if [ "${1:-}" = "--list" ]; then
  printf '%s\n' "${suites[@]}"
  exit 0
fi

if [ "${#suites[@]}" -eq 0 ]; then
  echo "test suites: none discovered (expected bin/test-*.sh)" >&2
  exit 1
fi

echo "test suites: ${#suites[@]} discovered"

failed=()
for s in "${suites[@]}"; do
  if [ ! -x "$s" ]; then
    printf '  ✗ %s (not executable)\n' "$s"
    failed+=("$s")
    continue
  fi
  if "$s" >/dev/null 2>&1; then
    printf '  ✓ %s\n' "$s"
  else
    printf '  ✗ %s\n' "$s"
    failed+=("$s")
  fi
done

echo
if [ "${#failed[@]}" -eq 0 ]; then
  printf '  ✓ all %d suites pass\n' "${#suites[@]}"
  exit 0
fi
printf '  %d of %d suites FAILED:\n' "${#failed[@]}" "${#suites[@]}"
printf '    %s\n' "${failed[@]}"
echo
echo "  re-run a failing suite directly to see its output."
exit 1

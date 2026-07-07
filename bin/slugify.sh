#!/usr/bin/env bash
#
# slugify.sh — turn an arbitrary string into the kebab-case slug the
# session-continuity notes home uses for <project> and <slug> path segments.
#
# The rule (canonical; the session-continuity SKILL.md points here):
#   1. lowercase
#   2. replace every run of non-[a-z0-9] characters with a single '-'
#   3. trim leading/trailing '-'
#
# Steps 2-3 (collapse runs, trim edges) are what keep messy names from
# producing 'my--app--' or '--spaces--'. Deliberately boring, dependency-free.
#
# Usage:
#   bin/slugify.sh "My_App.v2"     # -> my-app-v2
#   basename "$PWD" | ...            # or pipe a name in on stdin
#   bin/slugify.sh --self-test      # prove the rule against fixtures
#
set -euo pipefail

slugify() {
  # tr does lowercase + maps every non-[a-z0-9] byte to '-'; -s squeezes runs
  # of '-' to one; sed trims a leading/trailing '-'.
  printf '%s' "$1" |
    tr '[:upper:]' '[:lower:]' |
    tr -c 'a-z0-9' '-' |
    tr -s '-' |
    sed -e 's/^-//' -e 's/-$//'
  printf '\n'
}

self_test() {
  # input <TAB> expected
  local cases fails=0
  cases=$(
    cat <<'EOF'
My_App.v2	my-app-v2
My  App!!	my-app
v2.0	v2-0
a__b	a-b
  Spaces  	spaces
acme/api	acme-api
already-kebab	already-kebab
UPPER	upper
EOF
  )
  while IFS=$'\t' read -r input expected; do
    [ -z "$input" ] && continue
    got=$(slugify "$input")
    if [ "$got" = "$expected" ]; then
      printf '  ✓ %-14s -> %s\n' "$input" "$got"
    else
      printf '  ✗ %-14s -> %s (expected %s)\n' "$input" "$got" "$expected"
      fails=$((fails + 1))
    fi
  done <<<"$cases"
  if [ "$fails" -eq 0 ]; then
    echo "slugify self-test: all cases pass"
    return 0
  fi
  echo "slugify self-test: $fails case(s) failed"
  return 1
}

main() {
  case "${1-}" in
    --self-test) self_test ;;
    "") slugify "$(cat)" ;; # read from stdin when no arg
    *) slugify "$1" ;;
  esac
}

main "$@"

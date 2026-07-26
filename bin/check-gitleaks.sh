#!/usr/bin/env bash
#
# check-gitleaks.sh — run gitleaks as a gate, and state what it actually
# scanned (#354).
#
# gitleaks has been installed and its config narrowed and verified since #259,
# but it was wired into nothing: absent from the Makefile, bin/check.sh,
# .pre-commit-config.yaml and .github/workflows/. This is the call site.
#
# TWO MODES, because they see different things:
#
#   --staged   what the next commit will contain. The pre-commit hook's mode.
#   --history  every commit. `make check`'s mode.
#
# A history scan is BLIND to staged content — staged content is not yet a
# commit. A gate wired only into `make check` would therefore have reported
# clean on PR #345's three home-path hits at the moment they were staged,
# reproducing the #347 hole instead of closing it. Neither mode alone is the
# gate; the pair is.
#
# Both modes disclose their scope the way #347 made bin/check-private-info.sh
# disclose its own: name what was skipped, cap the list, and print the banner on
# red runs too, so fixing findings cannot silently promote a partial scan into a
# clean one. A missing binary reports NOT RUN and exits 0 —
# bin/check-private-info.sh is the always-on dependency-free layer, and a gate
# that blocks work over an absent optional tool gets bypassed rather than
# heeded.
#
# Usage: bin/check-gitleaks.sh [--staged | --history]   (default: --history)
#
set -uo pipefail

mode="${1:---history}"
case "$mode" in
  --staged | --history) ;;
  *)
    echo "usage: bin/check-gitleaks.sh [--staged | --history]" >&2
    exit 2
    ;;
esac

echo "gitleaks:"

# An absent binary is a disclosure, never a pass. The word "clean" — and the
# "no leaks" verdict this script prints on a real green — must not appear.
if ! command -v gitleaks >/dev/null 2>&1; then
  echo "  NOT RUN: gitleaks is not installed, so nothing was scanned."
  echo "    install it (brew install gitleaks) and re-run before quoting a result."
  exit 0
fi

# `-v` is load-bearing, not noise: without it gitleaks reports only
# "leaks found: N" and names no file, line or rule, so a red gate tells you
# something is wrong and nothing about where. `--redact` keeps the secret
# itself out of the output; `--no-color` keeps escape codes out of a piped log.
#
# What each mode cannot see. --staged misses everything not staged; --history
# misses everything not yet committed. Ignored files are out of scope by intent
# and are not counted: a banner that fires in every repo with build output is
# one nobody reads (#347).
untracked="$(git ls-files --others --exclude-standard)"
unstaged="$(git diff --name-only)"
staged="$(git diff --cached --name-only)"

if [ "$mode" = "--staged" ]; then
  scanned_n="$(grep -c . <<<"$staged")"
  unit="staged file(s)"
  skipped="$(printf '%s\n%s\n' "$unstaged" "$untracked" | grep -v '^$' | sort -u)"
  skipped_why="not staged"
  out="$(gitleaks git --staged --redact --no-banner --no-color -v 2>&1)"
  rc=$?
else
  unit="commit(s)"
  skipped="$(printf '%s\n%s\n%s\n' "$staged" "$unstaged" "$untracked" | grep -v '^$' | sort -u)"
  skipped_why="not yet committed"
  out="$(gitleaks git . --redact --no-banner --no-color -v 2>&1)"
  rc=$?
  # Take the count from GITLEAKS, never from `git rev-list --count HEAD`. The
  # two disagree — gitleaks counts commits it actually read a patch from, so an
  # empty or patch-less commit is counted by git and not by gitleaks (measured
  # on this repo: 758 vs 523). A scope line is a claim about what was examined,
  # so it has to come from the thing that did the examining; a plausible proxy
  # is how a disclosure becomes a fresh lie.
  scanned_n="$(grep -oE '[0-9]+ commits scanned' <<<"$out" | head -1 | cut -d' ' -f1)"
  [ -n "$scanned_n" ] || scanned_n="an unreported number of"
fi

if [ "$rc" -ne 0 ]; then
  printf '  ✗ gitleaks found something — %s scanned\n' "$scanned_n $unit"
  while IFS= read -r line; do echo "    $line"; done <<<"$out"
else
  printf '  ✓ no leaks — %s scanned\n' "$scanned_n $unit"
fi

# Scope banner. Prints on a red run too, for the #347 reason.
if [ -n "$skipped" ]; then
  skipped_n="$(grep -c . <<<"$skipped")"
  echo
  echo "  PARTIAL: $skipped_n file(s) were NOT scanned — $skipped_why:"
  head -n 10 <<<"$skipped" | while IFS= read -r p; do echo "    $p"; done
  [ "$skipped_n" -gt 10 ] && echo "    … and $((skipped_n - 10)) more"
  echo "    this run says nothing about them."
fi

exit "$rc"

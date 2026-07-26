#!/usr/bin/env bash
#
# check-pressure-series.sh — every rep series in skills/*/PRESSURE-TESTS.md
# records **Model:**, **Content:** and **Protocol:** (#467, #356).
#
# A SECTION is the span from a heading (or file start) to the next heading of
# ANY depth. Two real series nest a declaring block inside another section —
# verify-then-commit's `#### GREEN follow-up` inside `### Weaker-model rerun`,
# and session-continuity's `### Results — series 2` inside `## Claim 9` — so
# "next heading at the same or shallower depth" undercounts the tree by two
# (35 instead of 37). A section that declares ANY of the three fields must
# declare ALL three, and a declared **Protocol:** must be one of
# compliant | pre-protocol | unrecorded, OR the per-arm override form the
# protocol doc grants it (see legal_protocol_value below) — a first-token-only
# check rejects fork-pr-flow's real #190 series and produces exactly one false
# failure against the tree.
#
# TWO MODES, eventually — mirroring bin/check-gitleaks.sh:
#
#   --all      every tracked evidence file. make check's mode.
#   --staged   only what the next commit touches. The pre-commit hook's mode.
#              (not yet implemented — a later task wires this in)
#
# --count-only exists so the suite can assert the parser sees every real
# **Model:** line in the tree, not a fixture-shaped subset of it — a green
# --all run whose parser actually matches zero blocks is the #459 failure this
# gate exists to prevent, and counting from the parser's own accounting is the
# only way to catch it.
#
# --root DIR is a test seam; defaults to this script's repo root.
#
# Usage: bin/check-pressure-series.sh [--all | --staged] [--root DIR] [--count-only]
#
set -uo pipefail

mode="--all"
root=""
count_only=false
while [ $# -gt 0 ]; do
  case "$1" in
    --all | --staged) mode="$1" ;;
    --count-only) count_only=true ;;
    --root)
      root="$2"
      shift
      ;;
    *)
      echo "usage: bin/check-pressure-series.sh [--all | --staged] [--root DIR] [--count-only]" >&2
      exit 2
      ;;
  esac
  shift
done
[ -n "$root" ] || root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

LEGAL='compliant|pre-protocol|unrecorded'

# A value is either the simple form (first word is a legal token) or the
# per-arm override form the protocol doc sanctions for **Model:** and
# **Protocol:** alike — `mixed series — per-arm override (#356): arms A–B
# compliant, arm C unrecorded`. A first-token match alone rejects the override
# and produces one false failure against the real tree (fork-pr-flow's #190
# series, whose full value spans multiple lines — see sections() below, which
# folds continuation lines into the captured value for exactly this reason).
legal_protocol_value() { # legal_protocol_value FIELD_TEXT
  local v="$1"
  printf '%s' "$v" | grep -Eq "^($LEGAL)\b" && return 0
  printf '%s' "$v" | grep -q '^mixed series' &&
    [ "$(printf '%s' "$v" | grep -Eo "($LEGAL)" | wc -l | tr -d ' ')" -ge 2 ]
}

# Emit one line per declaring section: FILE<TAB>LINE<TAB>DEPTH<TAB>M<TAB>C<TAB>P<TAB>PVALUE
#
# A field's value is not always confined to its own line — three real shapes
# exist in the tree (contiguous, blank-line-separated, prose-interleaved), and
# a **Protocol:** override can wrap onto the following line(s) before the next
# blank line, bold field, or heading. PVALUE therefore folds in continuation
# lines; **Model:**/**Content:** are presence-only (m/c), since only
# **Protocol:**'s value is graded.
sections() {
  local f
  for f in "$root"/skills/*/PRESSURE-TESTS.md; do
    [ -f "$f" ] || continue
    awk -v F="$f" '
      function flush() {
        if (m || c || p) printf "%s\t%d\t%d\t%d\t%d\t%d\t%s\n", F, sline, depth, m, c, p, pval
        m = c = p = 0; pval = ""; capturing = 0
      }
      /^#+ / { flush(); match($0, /^#+/); depth = RLENGTH; sline = NR; next }
      /^\*\*Model:\*\*/    { m = 1; capturing = 0; next }
      /^\*\*Content:\*\*/  { c = 1; capturing = 0; next }
      /^\*\*Protocol:\*\*/ {
        p = 1; pval = $0; sub(/^\*\*Protocol:\*\* */, "", pval); capturing = 1; next
      }
      /^\*\*/ { capturing = 0 }
      /^$/    { capturing = 0 }
      capturing { pval = pval " " $0 }
      END { flush() }
    ' "$f"
  done
}

run_all() {
  local problems=0 blocks=0 files rows
  rows="$(sections)"
  if [ -n "$rows" ]; then
    # shellcheck disable=SC2034 # depth is part of the row shape; unused here
    while IFS="$(printf '\t')" read -r f line depth m c p pval; do
      blocks=$((blocks + 1))
      [ "$m" = 1 ] || {
        echo "  $f:$line — section declares fields but is missing **Model:**"
        problems=$((problems + 1))
      }
      [ "$c" = 1 ] || {
        echo "  $f:$line — section declares fields but is missing **Content:**"
        problems=$((problems + 1))
      }
      if [ "$p" != 1 ]; then
        echo "  $f:$line — section declares fields but is missing **Protocol:**"
        problems=$((problems + 1))
      elif ! legal_protocol_value "$pval"; then
        echo "  $f:$line — **Protocol:** \"${pval%% *}\" is not a legal value ($LEGAL)"
        problems=$((problems + 1))
      fi
    done <<<"$rows"
  fi

  files="$(find "$root"/skills -name PRESSURE-TESTS.md 2>/dev/null | wc -l | tr -d ' ')"
  if [ "$problems" -eq 0 ]; then
    echo "  ✓ $blocks block(s) complete across $files evidence file(s)"
    return 0
  fi
  echo "  ✗ $problems problem(s) in $blocks block(s) across $files evidence file(s)"
  return 1
}

if [ "$count_only" = true ]; then
  sections | wc -l | tr -d ' '
  exit 0
fi

echo "pressure-test series fields:"
case "$mode" in
  --all) run_all ;;
  --staged)
    echo "  NOT YET IMPLEMENTED: --staged mode is added by a later task (#467)."
    exit 1
    ;;
esac

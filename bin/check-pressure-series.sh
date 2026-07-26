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
# TWO MODES — mirroring bin/check-gitleaks.sh:
#
#   --all      every tracked evidence file. make check's mode.
#   --staged   only what the next commit touches. The pre-commit hook's mode.
#              Judges the STAGED blob (`git show ":$file"`), never the
#              working tree: a file can be staged clean and then further
#              edited before commit, and a --staged that read disk instead
#              would be blind to what the commit actually contains — the same
#              class of hole a --history-only gate left in #354. Exits 0
#              green, 1 red, and 0 with a NOT RUN disclosure when there is
#              nothing it can read (not a git repository, or no staged
#              evidence files) — a mode that hard-fails outside a git
#              repository would break any consumer that runs it in a scratch
#              tree.
#
#              A file's TRIGGERING DEPTHS — the heading depths at which a new
#              series must declare its fields to be flagged — are computed
#              from the file itself, never a table: they are whatever depths
#              the file's OWN already-declared sections use (## only, for
#              eleven of the thirteen; ## and ### for session-continuity; ##,
#              ### and #### for verify-then-commit, whose `#### GREEN
#              follow-up` is real and predates this gate). A file with no
#              declaring section yet defaults to ##.
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
if [ -z "$root" ]; then
  # --staged runs from inside whatever repo is being committed to, which need
  # not be the repo this script happens to be installed in — a throwaway
  # fixture repo in the test suite, or a linked worktree. Prefer the caller's
  # own toplevel; fall back to this script's install location only when the
  # caller isn't in a git repository at all (--all can still walk a --root
  # given explicitly, or its own install tree, with no git present).
  if git rev-parse --show-toplevel >/dev/null 2>&1; then
    root="$(git rev-parse --show-toplevel)"
  else
    root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
  fi
fi

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

# Shared awk program: emit FILE<TAB>LINE<TAB>DEPTH<TAB>M<TAB>C<TAB>P<TAB>PVALUE
# per declaring section. F is set by the caller via -v; sections() sets it to
# the real on-disk path, staged_sections() sets it to the file's git-relative
# path (its content comes from stdin, via `git show`, so it has no path of
# its own). One parsing model, two callers — see Task B4.
#
# A field's value is not always confined to its own line — three real shapes
# exist in the tree (contiguous, blank-line-separated, prose-interleaved), and
# a **Protocol:** override can wrap onto the following line(s) before the next
# blank line, bold field, or heading. PVALUE therefore folds in continuation
# lines; **Model:**/**Content:** are presence-only (m/c), since only
# **Protocol:**'s value is graded.
# shellcheck disable=SC2016  # single-quoted on purpose: it's an awk program, not shell interpolation
SECTIONS_AWK='
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
'

sections() {
  local f
  for f in "$root"/skills/*/PRESSURE-TESTS.md; do
    [ -f "$f" ] || continue
    awk -v F="$f" "$SECTIONS_AWK" "$f"
  done
}

# staged_sections FILE — same row shape as sections(), but read from the
# STAGED blob (`git show ":$file"`), not the working tree, so a file staged
# clean and then further edited on disk is still judged on what the commit
# will actually contain (#354's blind spot, one layer up).
staged_sections() { # staged_sections FILE
  git show ":$1" 2>/dev/null | awk -v F="$1" "$SECTIONS_AWK"
}

# A file's triggering depths are the depths at which it ALREADY declares
# fields — computed from the file, never a table: ### is the series depth in
# verify-then-commit and session-continuity, narrative everywhere else, and
# #### is real only in verify-then-commit (`#### GREEN follow-up`). A file
# with no declaring section yet defaults to ##.
trigger_depths() { # trigger_depths FILE
  local d
  d="$(sections | awk -v F="$1" -F'\t' '$1 == F && $3 > 0 { print $3 }' | sort -un | tr '\n' ' ')"
  [ -n "${d// /}" ] || d="2 "
  printf '%s' "$d"
}

# added_headings FILE — LINENO:HEADING for each markdown heading among the
# file's staged-diff ADDED lines. `-U0` means the diff carries only + and -
# lines (no context), so every `+` line is genuinely new; LINENO is the
# heading's line number in the staged (new) blob — the same numbering
# section_declares_all reads via `git show`.
added_headings() { # added_headings FILE
  git diff --cached -U0 -- "$1" | awk '
    /^@@/ {
      split($0, hdr, " ")
      newspec = hdr[3]
      sub(/^\+/, "", newspec)
      split(newspec, nn, ",")
      n = nn[1] + 0
      next
    }
    /^\+\+\+/ || /^---/ { next }
    /^\+/ {
      line = substr($0, 2)
      if (line ~ /^#+ /) print n ":" line
      n++
      next
    }
    /^-/ { next }
  '
}

# section_declares_all FILE LINE — does the section starting at LINE, read
# from FILE's STAGED blob, declare all three fields with a legal
# **Protocol:** value? Same section rule --all applies, via the same awk.
section_declares_all() { # section_declares_all FILE LINE
  local row m c p pval
  row="$(staged_sections "$1" | awk -F'\t' -v L="$2" '$2 == L')"
  [ -n "$row" ] || return 1
  IFS="$(printf '\t')" read -r _ _ _ m c p pval <<<"$row"
  [ "$m" = 1 ] && [ "$c" = 1 ] && [ "$p" = 1 ] && legal_protocol_value "$pval"
}

run_staged() {
  if ! git rev-parse --git-dir >/dev/null 2>&1; then
    echo "  NOT RUN: not a git repository, so nothing was read."
    return 0
  fi

  local files
  files="$(git diff --cached --name-only --diff-filter=AM -- 'skills/*/PRESSURE-TESTS.md')"
  if [ -z "$files" ]; then
    echo "  NOT RUN: no staged evidence files, so nothing was read."
    return 0
  fi

  local problems=0 checked=0 file heading depth line depths hit
  while IFS= read -r file; do
    [ -n "$file" ] || continue
    depths=" $(trigger_depths "$root/$file") "
    while IFS= read -r hit; do
      [ -n "$hit" ] || continue
      line="${hit%%:*}"
      heading="${hit#*:}"
      case "$heading" in
        *'<!-- not-a-series:'*) continue ;;
      esac
      depth="$(printf '%s' "$heading" | awk '{match($0, /^#+/); print RLENGTH}')"
      case "$depths" in
        *" $depth "*) ;;
        *) continue ;;
      esac
      checked=$((checked + 1))
      if ! section_declares_all "$file" "$line"; then
        echo "  $file:$line — new series \"$(printf '%s' "$heading" | cut -c1-60)\""
        echo "      is missing **Model:**/**Content:**/**Protocol:**"
        echo "      (or mark it <!-- not-a-series: reason --> if it records no reps)"
        problems=$((problems + 1))
      fi
    done <<<"$(added_headings "$file")"
  done <<<"$files"

  if [ "$problems" -eq 0 ]; then
    echo "  ✓ $checked new series heading(s) in the staged diff carry their fields"
    echo "    scope: staged content only; a file with no field block yet triggers"
    echo "    on ## alone, so a first series at ### depth in a new file is not seen."
    return 0
  fi
  return 1
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
  --staged) run_staged ;;
esac

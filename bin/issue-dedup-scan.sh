#!/usr/bin/env bash
#
# issue-dedup-scan.sh — read-only prior-work scan for a repository issue.
# Deterministically gathers evidence that issue #<n> may already be worked or
# done (git history, in-repo specs/plans, open + merged PRs, issue comments)
# and emits it as JSON, with the verdict in the EXIT CODE. Honest by
# construction: a failed sub-query yields `uncertain` (exit 4), never a clean
# verdict — an empty-but-successful scan is exit 0. Classification of an
# evidence-found result into in-progress / already-done / partially-done is
# left to the caller reading the emitted evidence (bash cannot judge it).
#
# Usage: bin/issue-dedup-scan.sh <issue-number>
#   GH env var overrides the `gh` binary (for testing).
#
# Exit codes:
#   0  no-evidence    all sub-queries ran, found nothing referencing #<n>
#   3  evidence-found at least one sub-query surfaced a reference
#   4  uncertain      at least one sub-query FAILED (tool/network error)
#   64 usage error
#
set -uo pipefail

GH="${GH:-gh}"
N=""
case "${1:-}" in
  -h | --help)
    awk 'NR==1{next} /^#/{sub(/^# ?/,""); print; next} {exit}' "$0"
    exit 0
    ;;
  '')
    echo "issue-dedup-scan.sh: missing <issue-number>" >&2
    exit 64
    ;;
  *[!0-9]*)
    echo "issue-dedup-scan.sh: <issue-number> must be numeric, got '$1'" >&2
    exit 64
    ;;
  *) N="$1" ;;
esac

failed=0         # 1 if any sub-query errored
evidence_json="" # accumulated JSON objects
queries_json=""  # per-query status objects

# record_query NAME STATUS
record_query() {
  local obj
  obj=$(printf '{"name": "%s", "status": "%s"}' "$1" "$2")
  queries_json="${queries_json:+$queries_json, }$obj"
  [ "$2" = failed ] && failed=1
}

# _json_safe VALUE — fold characters that would break a JSON string (backslash,
# double-quote, control chars incl. newlines) to a safe stand-in. Lossy but
# always valid JSON; evidence fields are agent/human hints, not authoritative
# data — the verdict lives in the exit code, never in this text.
# Fold backslash (octal \134) and double-quote to single-quote; strip controls.
_json_safe() {
  printf '%s' "$1" | tr -d '\000-\037' | tr '\134"' "''"
}

# add_evidence SOURCE REF DETAIL
add_evidence() {
  local obj
  obj=$(printf '{"source": "%s", "ref": "%s", "detail": "%s"}' \
    "$(_json_safe "$1")" "$(_json_safe "$2")" "$(_json_safe "$3")")
  evidence_json="${evidence_json:+$evidence_json, }$obj"
}

# 1. git log referencing #N
if out=$(git log --all --oneline --grep="#$N" 2>/dev/null); then
  if [ -n "$out" ]; then
    while IFS= read -r line; do
      [ -n "$line" ] && add_evidence "git-log" "${line%% *}" \
        "$(printf '%s' "${line#* }" | tr '"' "'" | cut -c1-80)"
    done <<<"$out"
  fi
  record_query git-log ok
else
  record_query git-log failed
fi

# 2. in-repo specs/plans/ADRs referencing #N (only dirs that exist)
spec_dirs=()
for d in docs/design docs/plans specs; do [ -d "$d" ] && spec_dirs+=("$d"); done
if [ "${#spec_dirs[@]}" -eq 0 ]; then
  record_query specs ok
elif out=$(grep -rIl -- "#$N" "${spec_dirs[@]}" 2>/dev/null); then
  while IFS= read -r f; do
    [ -n "$f" ] && add_evidence "spec" "$f" "references #$N"
  done <<<"$out"
  record_query specs ok
else
  # grep exit 1 == no match (success-empty); >1 == real error
  rc=$?
  if [ "$rc" -eq 1 ]; then
    record_query specs ok
  else record_query specs failed; fi
fi

# 3 + 4. open and merged PRs referencing the issue
scan_prs() { # scan_prs <state>
  local state="$1" json numbers
  if json=$("$GH" pr list --state "$state" --search "$N" \
    --json number,title,state,url 2>/dev/null); then
    # count matches by presence of a number field
    if printf '%s' "$json" | grep -q '"number"'; then
      numbers=$(printf '%s' "$json" | grep -oE '"number"[[:space:]]*:[[:space:]]*[0-9]+' |
        grep -oE '[0-9]+' | tr '\n' ',' | sed 's/,$//')
      add_evidence "pr-$state" "$state" \
        "$(printf 'PR(s) #%s referencing #%s' "$numbers" "$N" | tr '"' "'" | tr -d '\n' | cut -c1-80)"
    fi
    record_query "pr-$state" ok
  else
    record_query "pr-$state" failed
  fi
}
scan_prs open
scan_prs merged

# 5. the issue's own comments
if json=$("$GH" issue view "$N" --json comments 2>/dev/null); then
  if printf '%s' "$json" | grep -q '"body"'; then
    add_evidence "issue-comments" "#$N" "issue has comments to review"
  fi
  record_query issue-comments ok
else
  record_query issue-comments failed
fi

# verdict
if [ "$failed" -eq 1 ]; then
  verdict="uncertain"
  code=4
elif [ -n "$evidence_json" ]; then
  verdict="evidence-found"
  code=3
else
  verdict="no-evidence"
  code=0
fi

printf '{"issue": %s, "verdict": "%s", "evidence": [%s], "queries": [%s]}\n' \
  "$N" "$verdict" "$evidence_json" "$queries_json"
exit "$code"

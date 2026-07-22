#!/usr/bin/env bash
# skill-content-id.sh — derived content identity for a skill's rep evidence
# (#339). The id is sha256 over the LC_ALL=C-sorted "<sha256>  <path>" lines
# of every TRACKED file under skills/<name>/ except PRESSURE-TESTS.md (the
# evidence file cannot be part of the identity it records). Bytes come from
# the WORKING TREE — reps exercise installed disk content through the
# ~/.claude symlink, so the id describes what actually ran, uncommitted edits
# included. Recorded form: "sha256:" + first 12 hex.
#
# Usage:
#   bin/skill-content-id.sh <skill>          print the current id
#   bin/skill-content-id.sh --check <skill>  compare against the skill's
#                                            recorded **Content:** lines
#   bin/skill-content-id.sh --check --all    every skills/* except _template
#
# --check exits: 0 newest hashed series matches current; 1 drift; 2 no hashed
# series (grandfathered-only, or no evidence file). Environment errors exit 3;
# usage errors exit 64.
set -uo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.." || exit 3

usage() {
  echo "usage: bin/skill-content-id.sh <skill> | --check <skill> | --check --all" >&2
  exit 64
}

compute_id() { # compute_id <name> — prints sha256:<12 hex>
  local name="$1" f
  local files=()
  while IFS= read -r f; do
    [ -n "$f" ] || continue
    [ "$f" = "skills/$name/PRESSURE-TESTS.md" ] && continue
    files+=("$f")
  done < <(git ls-files -- "skills/$name" | LC_ALL=C sort)
  if [ "${#files[@]}" -eq 0 ]; then
    echo "skill-content-id: no tracked files under skills/$name" >&2
    return 2
  fi
  for f in "${files[@]}"; do
    if [ ! -f "$f" ]; then
      echo "skill-content-id: tracked file missing from working tree: $f" >&2
      return 3
    fi
  done
  local stream id
  stream="$(shasum -a 256 "${files[@]}")" || return 3
  id="$(shasum -a 256 <<<"$stream")" || return 3
  printf 'sha256:%s\n' "${id:0:12}"
}

check_skill() { # check_skill <name> [quiet] — verdict line(s); 0/1/2/3
  local name="$1" quiet="${2:-}" current line r rc
  current="$(compute_id "$name")" || {
    rc=$?
    return "$rc"
  }
  local recorded=()
  local pt="skills/$name/PRESSURE-TESTS.md"
  if [ -f "$pt" ]; then
    while IFS= read -r line; do
      [ -n "$line" ] || continue
      recorded+=("$line")
    done < <(grep -oE '\*\*Content:\*\* sha256:[0-9a-f]{12}' "$pt" |
      grep -oE 'sha256:[0-9a-f]{12}')
  fi
  if [ "${#recorded[@]}" -eq 0 ]; then
    echo "$name: NO-HASHED-SERIES (grandfathered-only or no evidence file; current $current)"
    return 2
  fi
  if [ -z "$quiet" ]; then
    for r in "${recorded[@]}"; do
      if [ "$r" = "$current" ]; then
        echo "  $r MATCH"
      else
        echo "  $r STALE"
      fi
    done
  fi
  local newest="${recorded[$((${#recorded[@]} - 1))]}"
  if [ "$newest" = "$current" ]; then
    echo "$name: FRESH (newest hashed series matches current $current)"
    return 0
  fi
  echo "$name: STALE (current $current, newest hashed series $newest)"
  return 1
}

check=false all=false skill=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    --check) check=true ;;
    --all) all=true ;;
    -*) usage ;;
    *)
      [ -z "$skill" ] || usage
      skill="$1"
      ;;
  esac
  shift
done

if $all; then
  $check || usage
  [ -z "$skill" ] || usage
  worst=0
  for d in skills/*/; do
    name="$(basename "$d")"
    [ "$name" = "_template" ] && continue
    check_skill "$name" quiet
    rc=$?
    [ "$rc" -eq 1 ] && worst=1
    [ "$rc" -ge 3 ] && exit "$rc"
  done
  exit "$worst"
fi

[ -n "$skill" ] || usage
if $check; then
  check_skill "$skill"
  exit "$?"
fi
compute_id "$skill"
exit "$?"

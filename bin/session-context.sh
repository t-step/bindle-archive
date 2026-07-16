#!/usr/bin/env bash
#
# session-context.sh — emit a compact orientation blob for the current
# project: notes-home resolution, latest session note / handoff *paths*
# (never contents), open `status: in-progress` issues, and a one-line git
# summary. Designed to run on every session start (see
# global/hooks/session-start-context.py), so output is deliberately small —
# a pointer, not a briefing. `/session-start` remains the deep version.
#
# Usage:
#   bin/session-context.sh [--cwd DIR] [--home DIR]
#
#   --cwd DIR   directory to orient from (default: $PWD)
#   --home DIR  Claude home override, for notes-home resolution parity with
#               bin/notes-home.sh (tests only; does not affect real installs)
#
# Degrades silently: no git repo, no notes home, no `gh`, or `gh` failing
# (offline, unauthenticated) all just omit that section — this never fails
# a session start over a missing optional tool.
#
# Exit codes: always 0. This is a read-only reporter, not a gate.
#
set -uo pipefail

CWD="$PWD"
MAX_BYTES=2000

while [ $# -gt 0 ]; do
  case "$1" in
    --cwd)
      [ $# -ge 2 ] || {
        echo "session-context.sh: --cwd needs a directory argument" >&2
        exit 2
      }
      CWD="$2"
      shift 2
      ;;
    --home)
      [ $# -ge 2 ] || {
        echo "session-context.sh: --home needs a directory argument" >&2
        exit 2
      }
      CLAUDE_HOME_OVERRIDE="$2"
      shift 2
      ;;
    *)
      echo "session-context.sh: unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

# --- notes-home resolution (mirrors bin/notes-home.sh's stable contract) ---

resolve_notes_home() {
  if [ -n "${BINDLE_NOTES_DIR:-}" ]; then
    NOTES_DIR="$BINDLE_NOTES_DIR"
    NOTES_SOURCE="BINDLE_NOTES_DIR"
  elif [ -n "${CLAUDE_KIT_NOTES_DIR:-}" ]; then
    NOTES_DIR="$CLAUDE_KIT_NOTES_DIR"
    NOTES_SOURCE="CLAUDE_KIT_NOTES_DIR (deprecated)"
  else
    local claude_home="${CLAUDE_HOME_OVERRIDE:-${HOME}/.claude}"
    local persisted=""
    if [ -f "$claude_home/settings.json" ]; then
      persisted="$(python3 -c 'import json,sys
try:
    print(json.load(open(sys.argv[1])).get("env", {}).get("BINDLE_NOTES_DIR", ""))
except Exception:
    print("")' "$claude_home/settings.json" 2>/dev/null)"
    fi
    if [ -n "$persisted" ]; then
      NOTES_DIR="$persisted"
      NOTES_SOURCE="persisted ($claude_home/settings.json)"
    else
      NOTES_DIR="${HOME}/.bindle"
      NOTES_SOURCE="default"
    fi
  fi
}

# --- project identity ------------------------------------------------------

REPO_ROOT="$(git -C "$CWD" rev-parse --show-toplevel 2>/dev/null || true)"
if [ -n "$REPO_ROOT" ]; then
  PROJECT_DIR="$REPO_ROOT"
else
  PROJECT_DIR="$CWD"
fi
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT="$(basename "$PROJECT_DIR" | "$SCRIPT_DIR/slugify.sh" 2>/dev/null || basename "$PROJECT_DIR")"

# --- git one-liner -----------------------------------------------------------

git_summary() {
  if [ -z "$REPO_ROOT" ]; then
    echo "not a git repo"
    return 0
  fi
  local branch dirty modified untracked
  branch="$(git -C "$REPO_ROOT" branch --show-current 2>/dev/null)"
  [ -n "$branch" ] || branch="(detached HEAD)"
  dirty="$(git -C "$REPO_ROOT" status --porcelain 2>/dev/null)"
  if [ -z "$dirty" ]; then
    echo "branch $branch, clean"
    return 0
  fi
  modified="$(grep -vc '^??' <<<"$dirty" || true)"
  untracked="$(grep -c '^??' <<<"$dirty" || true)"
  echo "branch $branch, $modified modified, $untracked untracked"
}

# --- latest note / handoff path (never contents) ----------------------------

latest_in() {
  local dir="$1"
  [ -d "$dir" ] || {
    echo "(none yet)"
    return 0
  }
  local f
  f="$(find "$dir" -maxdepth 1 -name '*.md' -type f 2>/dev/null | sort | tail -1)"
  [ -n "$f" ] && echo "$f" || echo "(none yet)"
}

# --- open status: in-progress issues (best-effort, silent on failure) ------

open_issues() {
  if [ -z "$REPO_ROOT" ] || ! command -v gh >/dev/null 2>&1; then
    echo "(unavailable)"
    return 0
  fi
  local runner=()
  command -v timeout >/dev/null 2>&1 && runner=(timeout 5)
  local out
  out="$(cd "$REPO_ROOT" && "${runner[@]+"${runner[@]}"}" gh issue list --state open \
    --label "status: in-progress" --limit 5 \
    --json number -q '.[].number' 2>/dev/null)" || {
    echo "(unavailable)"
    return 0
  }
  [ -n "$out" ] || {
    echo "(none)"
    return 0
  }
  echo "$out" | paste -sd, - | sed 's/,/, #/g; s/^/#/'
}

# --- install health (#192) --------------------------------------------------
# A co-installed tool can replace a Bindle-owned symlink with a real file. That
# voids every rule in global/CLAUDE.md and raises nothing: no error, no missing
# file. bin/doctor.sh already classifies it; the gap was that nothing ran doctor
# unprompted, so the failure waited on someone remembering to look.
#
# Only the silent states are worth a line. `missing` means Bindle isn't
# installed — self-evident the moment you look for a skill. `conflict` and
# `broken` are the ones that hide.
#
# Never fails a session: any problem resolving or running doctor prints nothing.
install_health() {
  local claude_home="${CLAUDE_HOME_OVERRIDE:-${HOME}/.claude}"
  local doctor="$SCRIPT_DIR/doctor.sh"
  [ -x "$doctor" ] || return 0
  [ -d "$claude_home" ] || return 0

  local out summary conflict broken names
  # doctor exits 1 on findings and 2 on usage errors; neither is our problem.
  out="$("$doctor" --home "$claude_home" 2>/dev/null)" || true
  summary="$(printf '%s\n' "$out" | grep -m1 '^summary: ' || true)"
  [ -n "$summary" ] || return 0

  conflict="$(printf '%s\n' "$summary" | sed -n 's/.*, \([0-9][0-9]*\) conflict.*/\1/p')"
  broken="$(printf '%s\n' "$summary" | sed -n 's/.*, \([0-9][0-9]*\) broken.*/\1/p')"
  conflict="${conflict:-0}"
  broken="${broken:-0}"
  [ "$conflict" -gt 0 ] || [ "$broken" -gt 0 ] || return 0

  # doctor prints findings as: "  ✗ NAME — STATE: DETAIL"
  names="$(printf '%s\n' "$out" |
    awk -F' — ' '/ — (conflict|broken):/ {
      sub(/^[[:space:]]*[^[:space:]]+[[:space:]]+/, "", $1); print $1
    }' | paste -sd',' - | sed 's/,/, /g')"

  printf 'install health: %s conflict, %s broken%s — run bin/doctor.sh\n' \
    "$conflict" "$broken" "${names:+ ($names)}"
}

# --- assemble ----------------------------------------------------------------

resolve_notes_home

{
  # Health first: a warning must survive the MAX_BYTES truncation below.
  install_health
  echo "project: $PROJECT ($(git_summary))"
  echo "notes home: $NOTES_DIR (via $NOTES_SOURCE)"
  echo "latest session note: $(latest_in "$NOTES_DIR/projects/$PROJECT/sessions")"
  echo "latest handoff: $(latest_in "$NOTES_DIR/projects/$PROJECT/handoffs")"
  echo "open in-progress issues: $(open_issues)"
} | head -c "$MAX_BYTES"

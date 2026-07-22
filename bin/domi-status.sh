#!/usr/bin/env bash
#
# domi-status.sh — read-only DomI-consumer detector. Parses a repo's .domi-pin
# and reports a compact drift verdict, DELEGATING the drift check to DomI's own
# scripts (report inherited policy, do not reimplement it — see
# docs/domi-consumer.md). Read-only toward the target repo.
#
# Usage: bin/domi-status.sh [--repo <path>]
#        bin/domi-status.sh [--repo <path>] --category <slug>
#
# `--category <slug>` (#278) answers ONE inherited-policy category as an
# observable read — `inherited=true|false|malformed` — replacing the
# three-row applicability table release-captain's SKILL.md used to ask the
# model to evaluate by hand. <slug> must be one of the seven categories in
# docs/domi-consumer.md's table; every well-formed pin inherits all seven
# together (the pin carries no per-category opt-out), so this differs from
# plain mode only in exit code / output shape, not in what it decides.
#
# Exit codes (identical to DomI check_pin.sh, so callers can treat the two
# interchangeably):
#   0 current    1 behind    2 not-a-domi-consumer (no .domi-pin)
#   3 forked     4 unverifiable (offline)    5 malformed
#   64 usage error
#
# --category exit codes (a distinct, smaller vocabulary — no drift check runs):
#   0 inherited=true    1 inherited=false (not a consumer)
#   5 inherited=malformed    64 usage error (unknown category / missing value)
#
set -uo pipefail

KNOWN_CATEGORIES="branch-commit-discipline destructive-action-hard-stops context-session-management delegation-dispatch release-semver-governance issue-session-workflow sync-update-ownership"

TARGET=""
CATEGORY=""
while [ $# -gt 0 ]; do
  case "$1" in
    --repo)
      [ $# -ge 2 ] || {
        echo "domi-status.sh: --repo requires a path" >&2
        exit 64
      }
      TARGET="$2"
      shift 2
      ;;
    --category)
      [ $# -ge 2 ] || {
        echo "domi-status.sh: --category requires a value" >&2
        exit 64
      }
      CATEGORY="$2"
      shift 2
      ;;
    -h | --help)
      tail -n +2 "$0" | grep '^#' | sed 's/^#\{1,\} \{0,1\}//'
      exit 0
      ;;
    *)
      echo "domi-status.sh: unknown argument '$1'" >&2
      exit 64
      ;;
  esac
done

if [ -n "$CATEGORY" ]; then
  case " $KNOWN_CATEGORIES " in
    *" $CATEGORY "*) ;;
    *)
      echo "domi-status.sh: unknown category '$CATEGORY' (want one of: $KNOWN_CATEGORIES)" >&2
      exit 64
      ;;
  esac
fi

if [ -z "$TARGET" ]; then
  TARGET="$(git rev-parse --show-toplevel 2>/dev/null || echo ".")"
fi
PIN_FILE="$TARGET/.domi-pin"

# 1. No pin → not a consumer.
if [ ! -f "$PIN_FILE" ]; then
  if [ -n "$CATEGORY" ]; then
    echo "inherited=false: no .domi-pin in $TARGET"
    exit 1
  fi
  echo "not-a-domi-consumer: no .domi-pin in $TARGET"
  exit 2
fi

# 2. Parse the five fields.
pin_get() { grep -E "^$1:" "$PIN_FILE" | head -1 | sed -E "s/^$1:[[:space:]]*//" | tr -d '"'; }
UPSTREAM="$(pin_get upstream)"
BRANCH="$(pin_get branch)"
SHA="$(pin_get sha)"
# shellcheck disable=SC2034
MANIFEST="$(pin_get manifest_sha256)"
PINNED_AT="$(pin_get pinned_at)"

# 3. Validate (offline-decidable).
if [ -z "$UPSTREAM" ]; then
  if [ -n "$CATEGORY" ]; then
    echo "inherited=malformed: .domi-pin missing 'upstream' field" >&2
  else
    echo "malformed: .domi-pin missing 'upstream' field" >&2
  fi
  exit 5
fi
if ! printf '%s' "$SHA" | grep -qE '^[0-9a-f]{40}$'; then
  if [ -n "$CATEGORY" ]; then
    echo "inherited=malformed: .domi-pin 'sha' is not a 40-hex commit ('$SHA')" >&2
  else
    echo "malformed: .domi-pin 'sha' is not a 40-hex commit ('$SHA')" >&2
  fi
  exit 5
fi

# `--category` is answered entirely by pin presence + well-formedness (every
# well-formed pin inherits all seven categories together) — stop here, no
# drift check needed.
if [ -n "$CATEGORY" ]; then
  echo "inherited=true"
  exit 0
fi

# 4. Fact reporting (always, offline-safe).
echo "pin: $UPSTREAM@${SHA:0:7} branch=$BRANCH pinned_at=$PINNED_AT"

# Inherited-policy categories and their authority (docs/domi-consumer.md).
echo "authority: $UPSTREAM (inherited: ${KNOWN_CATEGORIES// /, })"

# 5. Drift verdict — delegate to DomI's own scripts (report, don't reimplement).
find_domi_scripts() {
  if [ -n "${DOMI_SCRIPTS_DIR+x}" ]; then
    # Env var set: use only that path (no fallback to defaults)
    [ -n "$DOMI_SCRIPTS_DIR" ] && [ -f "$DOMI_SCRIPTS_DIR/offline_drift_check.sh" ] && {
      echo "$DOMI_SCRIPTS_DIR"
      return 0
    }
  else
    # Env var not set: check defaults
    [ -f "$HOME/.claude/skills/sync-from-domi/scripts/offline_drift_check.sh" ] && {
      echo "$HOME/.claude/skills/sync-from-domi/scripts"
      return 0
    }
  fi
  return 1
}
find_domi_checkout() {
  if [ -n "${DOMI_LOCAL_CHECKOUT+x}" ]; then
    # Env var set: use only that path (no fallback to defaults)
    [ -n "$DOMI_LOCAL_CHECKOUT" ] && [ -d "$DOMI_LOCAL_CHECKOUT/.git" ] && {
      echo "$DOMI_LOCAL_CHECKOUT"
      return 0
    }
  else
    # Env var not set: check defaults
    local d
    for d in "../DomI" "/home/user/DomI"; do
      [ -d "$d/.git" ] && {
        echo "$d"
        return 0
      }
    done
  fi
  return 1
}

report_verdict() { # report_verdict <label> <exit-code>
  echo "$1"
  exit "$2"
}

SCRIPTS="$(find_domi_scripts || true)"
CHECKOUT="$(find_domi_checkout || true)"

if [ -n "$SCRIPTS" ] && [ -n "$CHECKOUT" ]; then
  # Delegate to DomI's offline sibling-clone drift checker. Its exit codes:
  # 0 synced, 1 behind, 3 forked, 2 unpinned, 4 no-clone.
  REPO_ROOT="$TARGET" DOMI_LOCAL_CHECKOUT="$CHECKOUT" \
    bash "$SCRIPTS/offline_drift_check.sh" >/dev/null 2>&1
  rc=$?
  case "$rc" in
    0) report_verdict "current: pin verified against DomI@${SHA:0:7}" 0 ;;
    1) report_verdict "behind: pinned ${SHA:0:7} is behind DomI upstream — run sync-from-domi" 1 ;;
    3) report_verdict "forked: MANIFEST.md hash mismatch at pinned SHA — local edit or corruption" 3 ;;
    *) : ;; # 2/4/other → fall through to unverifiable
  esac
fi

report_verdict "unverifiable: drift not checked (no DomI delegation reachable)" 4

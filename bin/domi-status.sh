#!/usr/bin/env bash
#
# domi-status.sh — read-only DomI-consumer detector. Parses a repo's .domi-pin
# and reports a compact drift verdict, DELEGATING the drift check to DomI's own
# scripts (report inherited policy, do not reimplement it — see
# docs/domi-consumer.md). Read-only toward the target repo.
#
# Usage: bin/domi-status.sh [--repo <path>]
#
# Exit codes (identical to DomI check_pin.sh, so callers can treat the two
# interchangeably):
#   0 current    1 behind    2 not-a-domi-consumer (no .domi-pin)
#   3 forked     4 unverifiable (offline)    5 malformed
#   64 usage error
#
set -uo pipefail

TARGET=""
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

if [ -z "$TARGET" ]; then
  TARGET="$(git rev-parse --show-toplevel 2>/dev/null || echo ".")"
fi
PIN_FILE="$TARGET/.domi-pin"

# 1. No pin → not a consumer.
if [ ! -f "$PIN_FILE" ]; then
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
  echo "malformed: .domi-pin missing 'upstream' field" >&2
  exit 5
fi
if ! printf '%s' "$SHA" | grep -qE '^[0-9a-f]{40}$'; then
  echo "malformed: .domi-pin 'sha' is not a 40-hex commit ('$SHA')" >&2
  exit 5
fi

# 4. Fact reporting (always, offline-safe).
echo "pin: $UPSTREAM@${SHA:0:7} branch=$BRANCH pinned_at=$PINNED_AT"

# 5. Drift verdict. Task 2 wires delegation here; until then, unverifiable.
echo "unverifiable: drift not checked (no DomI delegation reachable)"
exit 4

#!/usr/bin/env bash
#
# domi-release-check.sh — run DomI's release-integrity checker for a
# DomI-governed repo and relay its verdict (#242). Deferring under a valid
# .domi-pin obliges LOCATING AND RUNNING the authority when it is
# discoverable — not just naming it. This helper mechanizes that obligation
# for package-release-integrity and release-captain as one command.
#
# Advisory boundary: Bindle relays DomI's verdict; it is never the release
# authority. A checker that cannot be reached is a DEGRADED outcome (verbal
# defer), reported explicitly — never a pass.
#
# Usage: bin/domi-release-check.sh [--repo <path>] [-- <args forwarded to
#        DomI's release_integrity.py verbatim>]
#
# Exit codes (helper-owned; DomI's own exit is relayed in the domi-exit
# banner, and the checker's stdout/stderr pass through untouched):
#   0  checker ran, DomI exited 0
#   6  checker ran, DomI exited nonzero (see domi-exit=<n> banner)
#   2  not-domi-governed (no .domi-pin — nothing to defer to)
#   4  checker-unreachable (degraded: verbal defer only, NOT a pass)
#   5  malformed .domi-pin
#   64 usage error
#
set -uo pipefail

BIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DS="$BIN_DIR/domi-status.sh"
CHECKER_REL="skills/release-integrity/scripts/release_integrity.py"

TARGET=""
FWD=()
while [ $# -gt 0 ]; do
  case "$1" in
    --repo)
      [ $# -ge 2 ] || {
        echo "domi-release-check.sh: --repo requires a path" >&2
        exit 64
      }
      TARGET="$2"
      shift 2
      ;;
    --)
      shift
      FWD=("$@")
      break
      ;;
    -h | --help)
      tail -n +2 "$0" | grep '^#' | sed 's/^#\{1,\} \{0,1\}//'
      exit 0
      ;;
    *)
      echo "domi-release-check.sh: unknown argument '$1'" >&2
      exit 64
      ;;
  esac
done

if [ -z "$TARGET" ]; then
  TARGET="$(git rev-parse --show-toplevel 2>/dev/null || echo ".")"
fi

# 1. Pin gate — delegate well-formedness to domi-status.sh (#278 mode); never
# re-parse validity here. Its stderr (malformed detail) passes through.
"$DS" --repo "$TARGET" --category release-semver-governance >/dev/null
case $? in
  0) ;; # governed — continue
  1)
    echo "not-domi-governed: no .domi-pin in $TARGET — nothing to defer to"
    exit 2
    ;;
  5) exit 5 ;;
  *)
    echo "domi-release-check.sh: unexpected domi-status.sh failure" >&2
    exit 70
    ;;
esac

# Display-only pin facts (validity was already decided above).
pin_get() { grep -E "^$1:" "$TARGET/.domi-pin" | head -1 | sed -E "s/^$1:[[:space:]]*//" | tr -d '"'; }
UPSTREAM="$(pin_get upstream)"
SHA="$(pin_get sha)"
echo "domi-release-check: governed by $UPSTREAM@${SHA:0:7} (release-semver-governance)"

# 2. Locate DomI's checker. DOMI_LOCAL_CHECKOUT set → that path only (no
# silent fallback); unset → installed-skill symlink, then the target's
# sibling ../DomI, then the container default.
find_checker() {
  if [ -n "${DOMI_LOCAL_CHECKOUT+x}" ]; then
    [ -n "$DOMI_LOCAL_CHECKOUT" ] && [ -f "$DOMI_LOCAL_CHECKOUT/$CHECKER_REL" ] && {
      echo "$DOMI_LOCAL_CHECKOUT/$CHECKER_REL"
      return 0
    }
  else
    local c
    for c in \
      "$HOME/.claude/skills/release-integrity/scripts/release_integrity.py" \
      "$TARGET/../DomI/$CHECKER_REL" \
      "/home/user/DomI/$CHECKER_REL"; do
      [ -f "$c" ] && {
        echo "$c"
        return 0
      }
    done
  fi
  return 1
}

if ! CHECKER="$(find_checker)"; then
  echo "checker-unreachable: no DomI release-integrity checker found" \
    "(searched: \$DOMI_LOCAL_CHECKOUT, ~/.claude/skills/release-integrity," \
    "$TARGET/../DomI, /home/user/DomI)"
  echo "degraded: verbal defer only — report this explicitly; it is NOT a pass"
  exit 4
fi

# 3. Run the authority from the target repo's root, forwarding args verbatim
# and passing its stdout/stderr through untouched.
echo "domi-release-check: checker $CHECKER"
echo "--- DomI release-integrity output ---"
(cd "$TARGET" && python3 "$CHECKER" ${FWD+"${FWD[@]}"})
RC=$?
echo "--- end (domi-exit=$RC) ---"
echo "domi-release-check: verdict relayed from DomI; Bindle is not the release authority"
[ "$RC" -eq 0 ] && exit 0
exit 6

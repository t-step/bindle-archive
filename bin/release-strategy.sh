#!/usr/bin/env bash
#
# release-strategy.sh — the provider-neutral release-strategy seam for Release
# Captain (L4 of #116). Reads the single `strategy` key from release-captain.toml
# and dispatches a verb to bin/release-strategies/<strategy>.sh. Fails closed on
# a missing file, missing key, or unknown strategy. Selection only — it performs
# no release action itself and knows nothing about approval.
#
# Authorities (never the bare word "authority"):
#   intent      -> Release Captain (the L3 orchestrator that calls this seam)
#   artifact    -> Release Please (via the selected strategy)
#   publication -> the human maintainer (separate, explicit, not here)
#
# Verbs:
#   which    print the resolved strategy name + script path, exit 0.
#   dry-run  dispatch to the strategy's read-only preview.
#   apply    dispatch to the strategy's create/update-release-PR action.
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG="${RC_CONFIG:-$REPO_ROOT/release-captain.toml}"

die() {
  echo "release-strategy: $1" >&2
  exit "${2:-64}"
}

[ -f "$CONFIG" ] || die "release-captain.toml missing at $CONFIG" 64

# Minimal, dependency-free parse of `strategy = "value"` (first match wins).
strategy="$(sed -n 's/^[[:space:]]*strategy[[:space:]]*=[[:space:]]*"\([^"]*\)".*/\1/p' "$CONFIG" | head -n1)"
[ -n "$strategy" ] || die "no 'strategy' key in $CONFIG" 64

script="$REPO_ROOT/bin/release-strategies/$strategy.sh"
[ -f "$script" ] || die "unknown strategy '$strategy' (no $script)" 64

verb="${1:-}"
case "$verb" in
  which)
    echo "strategy=$strategy"
    echo "script=$script"
    ;;
  dry-run | apply)
    shift
    exec bash "$script" "$verb" "$@"
    ;;
  *)
    die "unknown verb '${verb:-<none>}' (want: which|dry-run|apply)" 2
    ;;
esac

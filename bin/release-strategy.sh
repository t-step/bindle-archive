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

BINDLE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

die() {
  echo "release-strategy: $1" >&2
  exit "${2:-64}"
}

# The CONFIG belongs to the repo being operated on; the strategy SCRIPTS are
# Bindle's own. Bindle installs into other projects, so resolving the config
# from Bindle's checkout would answer with Bindle's strategy for every target
# (#246). RC_CONFIG stays an explicit override.
if [ -n "${RC_CONFIG:-}" ]; then
  CONFIG="$RC_CONFIG"
else
  target_root="$(git rev-parse --show-toplevel 2>/dev/null || true)"
  [ -n "$target_root" ] ||
    die "not inside a git repository — cannot locate the target repo's release-captain.toml (set RC_CONFIG to override)" 64
  CONFIG="$target_root/release-captain.toml"
fi

[ -f "$CONFIG" ] || die "release-captain.toml missing at $CONFIG" 64

# Minimal, dependency-free parse of `strategy = "value"` (first match wins).
strategy="$(sed -n 's/^[[:space:]]*strategy[[:space:]]*=[[:space:]]*"\([^"]*\)".*/\1/p' "$CONFIG" | head -n1)"
[ -n "$strategy" ] || die "no 'strategy' key in $CONFIG" 64

script="$BINDLE_ROOT/bin/release-strategies/$strategy.sh"
[ -f "$script" ] || die "unknown strategy '$strategy' (no $script)" 64

verb="${1:-}"
case "$verb" in
  which)
    echo "strategy=$strategy"
    echo "config=$CONFIG"
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

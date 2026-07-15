#!/usr/bin/env bash
#
# local-release-please.sh — the local Release Please ARTIFACT strategy for
# Release Captain (L4 of #116). Release Please is the artifact authority: it
# owns the VERSION bump, the CHANGELOG.md content, and the release PR. This
# strategy assembles the `release-please release-pr` invocation and nothing
# else. It NEVER merges, tags, creates a GitHub Release, publishes, or deploys —
# publication is a separate, explicitly human-authorized action.
#
# Verbs:
#   dry-run  read-only preview; proves zero mutation.
#   apply    create/update the release PR; requires --approval-token <ephemeral>
#            passed by the orchestrator for this one invocation. No token =>
#            hard stop, no invocation. The token is ephemeral invocation state,
#            never a reusable secret or a persisted approval marker.
#
set -euo pipefail

verb="${1:-}"
shift || true

: "${RELEASE_PLEASE_CMD:=npx release-please}"
repo_url="${RELEASE_PLEASE_REPO_URL:-}"
if [ -z "$repo_url" ]; then
  origin="$(git remote get-url origin 2>/dev/null || true)"
  # normalize git@github.com:o/r.git and https://github.com/o/r(.git) -> o/r
  repo_url="$(printf '%s' "$origin" | sed -E 's#^git@[^:]+:##; s#^https?://[^/]+/##; s#\.git$##')"
fi

rp() { # invoke the (possibly stubbed) release-please binary with args
  # shellcheck disable=SC2086 # RELEASE_PLEASE_CMD may be "npx release-please"
  $RELEASE_PLEASE_CMD "$@"
}

case "$verb" in
  dry-run)
    rp release-pr --repo-url="$repo_url" --dry-run "$@"
    ;;
  apply)
    token=""
    while [ "$#" -gt 0 ]; do
      case "$1" in
        --approval-token)
          token="${2:-}"
          shift 2
          ;;
        --approval-token=*)
          token="${1#*=}"
          shift
          ;;
        *) shift ;;
      esac
    done
    if [ -z "$token" ]; then
      echo "local-release-please: apply refused — no approval token" >&2
      exit 3
    fi
    rp release-pr --repo-url="$repo_url"
    ;;
  *)
    echo "local-release-please: unknown verb '${verb:-<none>}'" >&2
    exit 2
    ;;
esac

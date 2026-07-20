#!/usr/bin/env bash
#
# check-issue-labels.sh — audit the label lifecycle rules in docs/issue-tracking.md
# against live GitHub state.
#
# Asserts three invariants:
#   1. no closed issue carries a `status:` label
#   2. every open issue outside `status: triage` carries a `priority:` label
#   3. the retired `status: done` label does not exist
#
# This is the audit backstop to global/hooks/label-hygiene-guard.py. The guard
# prevents drift at the transition but only sees what passes through this
# harness; anything closed from the web UI, from a terminal outside a session,
# or while the guard is unwired is invisible to it. That gap is not theoretical:
# #287 closed carrying `status: in-progress` minutes after the guard was merged,
# because the guard is not wired into settings.json.
#
# Deliberately NOT a bin/check.sh section. Two independent reasons: check.sh is
# copied into throwaway fixture repos by bin/test-check.sh and
# bin/test-check-frontmatter.sh, which have no network and no GitHub repo; and
# the pre-commit path must stay offline. Run it on demand.
#
# Exit codes:
#   0  all invariants hold
#   1  at least one violation (each is printed)
#   2  SKIPPED — gh is absent or unauthenticated, so nothing was verified
#
# Exit 2 is deliberately distinct from 0. A gate that reports success when it did
# not run is the failure this repo already paid for once (#279).
#
# Self-test: bin/test-issue-labels.sh
#
set -euo pipefail

LIMIT="${ISSUE_LABEL_LIMIT:-500}"
PROBLEMS=0

problem() {
  echo "  ✗ $1"
  PROBLEMS=$((PROBLEMS + 1))
}

ok() { echo "  ✓ $1"; }

echo "issue label hygiene:"

if ! command -v gh >/dev/null 2>&1; then
  echo "  SKIPPED — gh is not installed; no invariant was verified" >&2
  exit 2
fi

if ! issues="$(gh issue list --state all --limit "$LIMIT" \
  --json number,state,labels 2>/dev/null)"; then
  echo "  SKIPPED — gh could not list issues (unauthenticated, offline, or not" \
    "a GitHub repo); no invariant was verified" >&2
  exit 2
fi

if ! labels="$(gh label list --limit 200 2>/dev/null)"; then
  echo "  SKIPPED — gh could not list labels; no invariant was verified" >&2
  exit 2
fi

# --- 1 + 2: per-issue invariants --------------------------------------------
# Prefix matching, not value matching: the vocabulary in docs/issue-tracking.md
# can grow without touching this script. `status: triage` is the one literal the
# rules are definitionally about.
findings="$(
  python3 - "$issues" <<'PY'
import json, sys

issues = json.loads(sys.argv[1] or "[]")
for it in issues:
    num = it.get("number")
    state = (it.get("state") or "").upper()
    names = [x.get("name", "") for x in it.get("labels") or []]
    status = [n for n in names if n.startswith("status:")]
    if state == "CLOSED":
        if status:
            print(f"closed|#{num} is closed but still carries "
                  + ", ".join(f"`{s}`" for s in status))
        continue
    if "status: triage" in status:
        continue
    if not any(n.startswith("priority:") for n in names):
        where = f"`{status[0]}`" if status else "no status: label"
        print(f"priority|#{num} is open ({where}) with no `priority:` label")
PY
)"

closed_hits=0
priority_hits=0
if [ -n "$findings" ]; then
  while IFS='|' read -r kind message; do
    [ -n "$kind" ] || continue
    case "$kind" in
      closed) closed_hits=$((closed_hits + 1)) ;;
      priority) priority_hits=$((priority_hits + 1)) ;;
    esac
    problem "$message"
  done <<<"$findings"
fi

if [ "$closed_hits" -eq 0 ]; then
  ok "no closed issue carries a \`status:\` label"
fi
if [ "$priority_hits" -eq 0 ]; then
  ok "every open non-triage issue carries a \`priority:\` label"
fi

# --- 3: the retired label ----------------------------------------------------
if printf '%s\n' "$labels" | cut -f1 | grep -qx 'status: done'; then
  problem "the \`status: done\` label still exists; it was retired in #287 — closure carries that meaning"
else
  ok "\`status: done\` is retired"
fi

echo
if [ "$PROBLEMS" -gt 0 ]; then
  echo "  $PROBLEMS problem(s). See docs/issue-tracking.md § Label lifecycle." >&2
  exit 1
fi
echo "  label hygiene OK"

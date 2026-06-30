#!/usr/bin/env bash
#
# install-hooks.sh — enable git hooks via the pre-commit framework, installing
# both the pre-commit and post-merge stages. Idempotent; safe to re-run.
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT" || exit 1

if ! command -v pre-commit >/dev/null 2>&1; then
  echo "pre-commit is not installed. Install it, then re-run:" >&2
  echo "  brew install pre-commit      # or: pipx install pre-commit" >&2
  exit 1
fi

# The framework manages .git/hooks directly; clear any legacy core.hooksPath
# (from an earlier native-hooks setup) so the two don't conflict.
git config --unset core.hooksPath 2>/dev/null || true

pre-commit install --hook-type pre-commit --hook-type post-merge
echo "Hooks enabled via pre-commit (pre-commit + post-merge stages)."

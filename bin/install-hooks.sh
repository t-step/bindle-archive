#!/usr/bin/env bash
#
# install-hooks.sh — point git at this repo's tracked hooks (.githooks/) so the
# pre-commit checks run automatically. Idempotent; safe to re-run.
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
git -C "$REPO_ROOT" config core.hooksPath .githooks

echo "Git hooks enabled (core.hooksPath=.githooks)."
echo "Pre-commit will run: bin/check.sh + bin/test-install.sh"

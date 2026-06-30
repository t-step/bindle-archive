#!/usr/bin/env bash
#
# release.sh — cut a toolkit-level release.
#
# Bumps VERSION (semver), rolls the CHANGELOG's [Unreleased] notes into a dated
# version section, commits "Release vX.Y.Z", and creates an annotated tag.
# It does NOT push — review the commit + tag, then:  git push && git push --tags
# Pushing a v* tag triggers .github/workflows/release.yml to publish a GitHub
# Release from the changelog section.
#
# Usage: bin/release.sh <major|minor|patch>
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT" || exit 1

bump="${1:-}"
case "$bump" in
  major | minor | patch) ;;
  *)
    echo "Usage: bin/release.sh <major|minor|patch>" >&2
    exit 2
    ;;
esac

# --- guardrails: never tag a dirty or broken state -------------------------
if [ -n "$(git status --porcelain)" ]; then
  echo "Working tree not clean — commit or stash changes first." >&2
  exit 1
fi
echo "Running checks before release..."
bin/check.sh
bin/test-install.sh

# --- compute the new version ----------------------------------------------
cur="$(cat VERSION)"
if ! [[ "$cur" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "VERSION ('$cur') is not semver MAJOR.MINOR.PATCH." >&2
  exit 1
fi
IFS=. read -r major minor patch <<<"$cur"
case "$bump" in
  major)
    major=$((major + 1))
    minor=0
    patch=0
    ;;
  minor)
    minor=$((minor + 1))
    patch=0
    ;;
  patch) patch=$((patch + 1)) ;;
esac
new="${major}.${minor}.${patch}"
today="$(date +%Y-%m-%d)"

# --- roll VERSION + CHANGELOG ---------------------------------------------
if ! grep -q '^## \[Unreleased\]' CHANGELOG.md; then
  echo "CHANGELOG.md is missing a '## [Unreleased]' section." >&2
  exit 1
fi
printf '%s\n' "$new" >VERSION

# Insert a dated version header right after the [Unreleased] line; the existing
# Unreleased notes become this release, leaving Unreleased empty for next time.
awk -v ver="$new" -v day="$today" '
  /^## \[Unreleased\]/ && !inserted {
    print
    print ""
    print "## [" ver "] - " day
    inserted = 1
    next
  }
  { print }
' CHANGELOG.md >CHANGELOG.md.tmp && mv CHANGELOG.md.tmp CHANGELOG.md

# --- commit + tag ----------------------------------------------------------
git add VERSION CHANGELOG.md
git commit -q -m "Release v${new}"
git tag -a "v${new}" -m "claude-kit v${new}"

echo
echo "Released v${new} (commit + annotated tag created locally)."
echo "Review, then publish with:  git push && git push --tags"

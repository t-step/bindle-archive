#!/usr/bin/env bash
# Exercise annotated-tag source verification against throwaway Git repositories.
set -uo pipefail

unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_COMMON_DIR

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HELPER="$REPO_ROOT/bin/release-provenance.py"
PY="$(command -v python3)"
pass=0
fail=0
OUT=""
RC=0

run() {
  OUT="$("$@" 2>&1)"
  RC=$?
}

expect_rc() {
  local desc="$1" want="$2"
  if [ "$RC" -eq "$want" ]; then
    printf '  ok: %s\n' "$desc"
    pass=$((pass + 1))
  else
    printf '  FAIL: %s (rc=%s want=%s)\n' "$desc" "$RC" "$want"
    printf '%s\n' "$OUT" | sed 's/^/    | /'
    fail=$((fail + 1))
  fi
}

expect_exact() {
  local desc="$1" want="$2"
  if [ "$OUT" = "$want" ]; then
    printf '  ok: %s\n' "$desc"
    pass=$((pass + 1))
  else
    printf '  FAIL: %s\n' "$desc"
    printf '    want: %s\n' "$want"
    printf '%s\n' "$OUT" | sed 's/^/     got: /'
    fail=$((fail + 1))
  fi
}

expect_json() {
  local desc="$1" expected_commit="$2" expected_tag_object="$3" expected_timestamp="$4"
  if printf '%s' "$OUT" | "$PY" -c '
import json
import sys

got = json.load(sys.stdin)
expected = {
    "repository": "example/bindle",
    "tag": "v0.5.1",
    "tag_object_sha": sys.argv[1],
    "tagger_timestamp": sys.argv[3],
    "commit_sha": sys.argv[2],
    "version": "0.5.1",
}
raise SystemExit(0 if got == expected else 1)
' "$expected_tag_object" "$expected_commit" "$expected_timestamp"; then
    printf '  ok: %s\n' "$desc"
    pass=$((pass + 1))
  else
    printf '  FAIL: %s (unexpected JSON)\n' "$desc"
    printf '%s\n' "$OUT" | sed 's/^/    | /'
    fail=$((fail + 1))
  fi
}

TMP="$(mktemp -d "${TMPDIR:-/tmp}/bindle-provenance-test.XXXXXX")"
trap 'rm -rf "$TMP"' EXIT

commit() {
  local repo="$1" message="$2"
  git -C "$repo" add -A
  GIT_AUTHOR_DATE=2026-07-15T12:34:56Z \
    GIT_COMMITTER_DATE=2026-07-15T12:34:56Z \
    git -C "$repo" -c user.email=test@example.com -c user.name='Bindle Test' \
    commit -q -m "$message"
}

annotate() {
  local repo="$1" tag="$2"
  GIT_COMMITTER_DATE=2026-07-15T12:34:56Z \
    git -C "$repo" -c user.email=test@example.com -c user.name='Bindle Test' \
    tag -a "$tag" -m "Bindle $tag"
}

mkfixture() {
  local repo="$1" manifest_version="${2:-0.5.1}" changelog_version="${3:-0.5.1}"
  mkdir -p "$repo"
  git -C "$repo" init -q
  git -C "$repo" symbolic-ref HEAD refs/heads/main
  git -C "$repo" remote add origin git@github.com:example/bindle.git

  printf '%s\n' '0.5.0' >"$repo/version.txt"
  printf '%s\n' '{".": "0.5.0"}' >"$repo/.release-please-manifest.json"
  printf '%s\n' '# Changelog' '' '## [0.5.0] - 2026-07-01' '' '- Previous.' >"$repo/CHANGELOG.md"
  commit "$repo" previous
  annotate "$repo" v0.5.0

  printf '%s\n' '0.5.1' >"$repo/version.txt"
  printf '{".": "%s"}\n' "$manifest_version" >"$repo/.release-please-manifest.json"
  printf '%s\n' '# Changelog' '' '## [Unreleased]' '' \
    "## [$changelog_version] - 2026-07-15" '' '- Current.' '' \
    '## [0.5.0] - 2026-07-01' '' '- Previous.' >"$repo/CHANGELOG.md"
  commit "$repo" current
  annotate "$repo" v0.5.1
}

echo "annotated-tag source verification:"
VALID="$TMP/valid"
mkfixture "$VALID"
expected_commit="$(git -C "$VALID" rev-parse 'v0.5.1^{commit}')"
expected_tag_object="$(git -C "$VALID" rev-parse v0.5.1)"
expected_timestamp="$(git -C "$VALID" for-each-ref \
  '--format=%(taggerdate:iso-strict)' refs/tags/v0.5.1)"
run "$PY" "$HELPER" verify-source --root "$VALID" --tag v0.5.1 --json
expect_rc "valid annotated tag exits zero" 0
expect_json "valid annotated tag reports exact source state" \
  "$expected_commit" "$expected_tag_object" "$expected_timestamp"

git -C "$VALID" tag v0.5.1-lightweight
run "$PY" "$HELPER" verify-source --root "$VALID" --tag v0.5.1-lightweight --json
expect_rc "lightweight tag exits nonzero" 1
expect_exact "lightweight tag has stable reason" \
  "v0.5.1-lightweight: annotated tag required"

GIT_COMMITTER_DATE=2026-07-15T12:34:56Z \
  git -C "$VALID" -c advice.nestedTag=false \
  -c user.email=test@example.com -c user.name='Bindle Test' \
  tag -a intermediate -m intermediate
GIT_COMMITTER_DATE=2026-07-15T12:34:56Z \
  git -C "$VALID" -c advice.nestedTag=false \
  -c user.email=test@example.com -c user.name='Bindle Test' \
  tag -a chained intermediate -m chained
run "$PY" "$HELPER" verify-source --root "$VALID" --tag chained --json
expect_rc "tag-to-tag object exits nonzero" 1
expect_exact "tag-to-tag object has stable reason" \
  "chained: tag must point directly to a commit"

HEAD_MISMATCH="$TMP/head-mismatch"
mkfixture "$HEAD_MISMATCH"
printf '%s\n' after-tag >"$HEAD_MISMATCH/after-tag.txt"
commit "$HEAD_MISMATCH" after-tag
run "$PY" "$HELPER" verify-source --root "$HEAD_MISMATCH" --tag v0.5.1 --json
expect_rc "tag/HEAD mismatch exits nonzero" 1
expect_exact "tag/HEAD mismatch has stable reason" \
  "v0.5.1: tagged commit does not match HEAD"

TAG_MISMATCH="$TMP/tag-mismatch"
mkfixture "$TAG_MISMATCH"
annotate "$TAG_MISMATCH" v0.5.2
run "$PY" "$HELPER" verify-source --root "$TAG_MISMATCH" --tag v0.5.2 --json
expect_rc "tag/version mismatch exits nonzero" 1
expect_exact "tag/version mismatch has stable reason" \
  "v0.5.2: expected tag v0.5.1 from version.txt"

MANIFEST_MISMATCH="$TMP/manifest-mismatch"
mkfixture "$MANIFEST_MISMATCH" 0.5.0
run "$PY" "$HELPER" verify-source --root "$MANIFEST_MISMATCH" --tag v0.5.1 --json
expect_rc "Release Please manifest mismatch exits nonzero" 1
expect_exact "Release Please manifest mismatch has stable reason" \
  ".release-please-manifest.json: root version 0.5.0 does not match version.txt 0.5.1"

NO_CHANGELOG="$TMP/no-changelog"
mkfixture "$NO_CHANGELOG" 0.5.1 9.9.9
run "$PY" "$HELPER" verify-source --root "$NO_CHANGELOG" --tag v0.5.1 --json
expect_rc "missing changelog section exits nonzero" 1
expect_exact "missing changelog section has stable reason" \
  "CHANGELOG.md: missing exact '## [0.5.1]' section"

echo "test-release-provenance: $pass passed, $fail failed"
[ "$fail" -eq 0 ]

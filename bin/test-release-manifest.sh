#!/usr/bin/env bash
#
# test-release-manifest.sh — exercise bin/release-manifest.py against
# throwaway fixture repos. Mirrors bin/test-check-inventory.sh's shape.
#
set -uo pipefail

unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_COMMON_DIR

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GENERATOR="$REPO_ROOT/bin/release-manifest.py"
PY="$(command -v python3)"

pass=0 fail=0
check() { # check "description" command...
  local desc="$1"
  shift
  if "$@"; then
    printf '  ✓ %s\n' "$desc"
    pass=$((pass + 1))
  else
    printf '  ✗ %s\n' "$desc"
    fail=$((fail + 1))
  fi
}
contains() { grep -qF -- "$1" <<<"$2"; }
not_contains() { ! grep -qF -- "$1" <<<"$2"; }
export -f contains not_contains

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# mkfixture DIR — a minimal, fully valid fixture repo the generator
# succeeds against: capabilities.json, install-manifest.tsv, a CHANGELOG.md
# with a [0.1.0] section, and a real git repo (git_commit_sha needs one).
mkfixture() {
  local r="$1"
  mkdir -p "$r"
  cat >"$r/capabilities.json" <<'JSON'
{
  "capabilities": [
    {"name": "demo", "type": "skill", "path": "skills/demo",
     "description": "Demo skill.",
     "provider": {"claude": "installed", "codex": "untested"},
     "maturity": "tested", "mutation": [], "version_introduced": "0.1.0"}
  ],
  "not_a_capability": []
}
JSON
  cat >"$r/install-manifest.tsv" <<'TSV'
# GENERATED from capabilities.json — do not edit; run 'make manifest'
claude	skill	demo	skills/demo	skills/demo
TSV
  cat >"$r/CHANGELOG.md" <<'MD'
# Changelog

## [Unreleased]

## [0.1.0] - 2026-01-01

### Added

- Initial release.

## [0.0.9] - 2025-12-01

### Added

- Prehistory.
MD
  (cd "$r" && git init -q && git symbolic-ref HEAD refs/heads/main &&
    git add -A && git -c user.email=t@e.com -c user.name=t commit -q -m init)
}

# --- happy path: --emit to a file -------------------------------------------
REPO="$TMP/happy"
mkfixture "$REPO"
"$PY" "$GENERATOR" --root "$REPO" --version 0.1.0 --previous 0.0.9 --emit >/dev/null
check "writes RELEASE-MANIFEST.json" test -f "$REPO/RELEASE-MANIFEST.json"
out="$(cat "$REPO/RELEASE-MANIFEST.json")"
# shellcheck disable=SC2016 # single-quoted on purpose: "$1" is expanded by the inner bash -c, not this shell
check "records version" bash -c 'contains "\"version\": \"0.1.0\"" "$1"' _ "$out"
# shellcheck disable=SC2016 # single-quoted on purpose: "$1" is expanded by the inner bash -c, not this shell
check "records previous_version" bash -c 'contains "\"previous_version\": \"0.0.9\"" "$1"' _ "$out"
# shellcheck disable=SC2016 # single-quoted on purpose: "$1" is expanded by the inner bash -c, not this shell
check "records commit_sha" bash -c 'contains "\"commit_sha\":" "$1"' _ "$out"
# shellcheck disable=SC2016 # single-quoted on purpose: "$1" is expanded by the inner bash -c, not this shell
check "records demo capability" bash -c 'contains "\"name\": \"demo\"" "$1"' _ "$out"
# shellcheck disable=SC2016 # single-quoted on purpose: "$1" is expanded by the inner bash -c, not this shell
check "records installed surface" bash -c 'contains "\"dest\": \"skills/demo\"" "$1"' _ "$out"
# shellcheck disable=SC2016 # single-quoted on purpose: "$1" is expanded by the inner bash -c, not this shell
check "records verification commands" bash -c 'contains "bin/check.sh" "$1"' _ "$out"
# shellcheck disable=SC2016 # single-quoted on purpose: "$1" is expanded by the inner bash -c, not this shell
check "records self_checksum" bash -c 'contains "\"self_checksum\": \"sha256:" "$1"' _ "$out"
# shellcheck disable=SC2016 # single-quoted on purpose: "$1" is expanded by the inner bash -c, not this shell
check "records changelog section text" bash -c 'contains "Initial release." "$1"' _ "$out"

# --- happy path: --emit - (stdout) ------------------------------------------
out2="$("$PY" "$GENERATOR" --root "$REPO" --version 0.1.0 --previous 0.0.9 --emit -)"
# shellcheck disable=SC2016 # single-quoted on purpose: "$1" is expanded by the inner bash -c, not this shell
check "--emit - writes to stdout" bash -c 'contains "\"version\": \"0.1.0\"" "$1"' _ "$out2"

# --- happy path: --verify-determinism ---------------------------------------
det_out="$("$PY" "$GENERATOR" --root "$REPO" --version 0.1.0 --previous 0.0.9 --verify-determinism)"
# shellcheck disable=SC2016 # single-quoted on purpose: "$1" is expanded by the inner bash -c, not this shell
check "verify-determinism succeeds on an unchanged fixture" \
  bash -c 'contains "deterministic" "$1"' _ "$det_out"

# --- error: missing capabilities.json ---------------------------------------
REPO2="$TMP/no-caps"
mkfixture "$REPO2"
rm "$REPO2/capabilities.json"
err="$("$PY" "$GENERATOR" --root "$REPO2" --version 0.1.0 --previous 0.0.9 --emit - 2>&1)"
# shellcheck disable=SC2016 # single-quoted on purpose: "$1" is expanded by the inner bash -c, not this shell
check "errors on missing capabilities.json" \
  bash -c 'contains "capabilities.json: missing" "$1"' _ "$err"

# --- error: missing install-manifest.tsv ------------------------------------
REPO3="$TMP/no-manifest"
mkfixture "$REPO3"
rm "$REPO3/install-manifest.tsv"
err3="$("$PY" "$GENERATOR" --root "$REPO3" --version 0.1.0 --previous 0.0.9 --emit - 2>&1)"
# shellcheck disable=SC2016 # single-quoted on purpose: "$1" is expanded by the inner bash -c, not this shell
check "errors on missing install-manifest.tsv" \
  bash -c 'contains "install-manifest.tsv: missing" "$1"' _ "$err3"

# --- error: no matching CHANGELOG section ------------------------------------
REPO4="$TMP/no-changelog-section"
mkfixture "$REPO4"
err4="$("$PY" "$GENERATOR" --root "$REPO4" --version 9.9.9 --previous 0.1.0 --emit - 2>&1)"
# shellcheck disable=SC2016 # single-quoted on purpose: "$1" is expanded by the inner bash -c, not this shell
check "errors on missing CHANGELOG section" \
  bash -c 'contains "## [9.9.9]" "$1"' _ "$err4"

# --- tool_versions: "not installed" when absent from PATH -------------------
STUB="$TMP/stubpath"
mkdir -p "$STUB"
for bin in git bash python3; do
  real="$(command -v "$bin")"
  printf '#!/bin/sh\nexec "%s" "$@"\n' "$real" >"$STUB/$bin"
  chmod +x "$STUB/$bin"
done
stub_out="$(PATH="$STUB" "$PY" "$GENERATOR" --root "$REPO" --version 0.1.0 --previous 0.0.9 --emit - 2>&1)"
# shellcheck disable=SC2016 # single-quoted on purpose: "$1" is expanded by the inner bash -c, not this shell
check "shellcheck reports not installed when absent from PATH" \
  bash -c 'contains "\"shellcheck\": \"not installed\"" "$1"' _ "$stub_out"
# shellcheck disable=SC2016 # single-quoted on purpose: "$1" is expanded by the inner bash -c, not this shell
check "shfmt reports not installed when absent from PATH" \
  bash -c 'contains "\"shfmt\": \"not installed\"" "$1"' _ "$stub_out"
# shellcheck disable=SC2016 # single-quoted on purpose: "$1" is expanded by the inner bash -c, not this shell
check "git still resolves via the stub PATH" \
  bash -c 'contains "\"git\":" "$1"' _ "$stub_out"

# --- _diff_manifests unit tests (imported directly, not via the CLI) --------
diff_check="$(
  "$PY" - "$GENERATOR" <<'PYEOF'
import importlib.util, sys
path = sys.argv[1]
spec = importlib.util.spec_from_file_location("release_manifest", path)
rm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rm)

d1 = rm._diff_manifests({"a": 1, "timestamp": "t1"}, {"a": 2, "timestamp": "t2"})
assert d1 == ["a"], d1

d2 = rm._diff_manifests({"a": 1, "timestamp": "t1"}, {"a": 1, "timestamp": "t2"})
assert d2 == [], d2

print("ok")
PYEOF
)"
# shellcheck disable=SC2016 # single-quoted on purpose: "$1" is expanded by the inner bash -c, not this shell
check "_diff_manifests flags a real field mismatch, ignores timestamp" \
  bash -c 'contains "ok" "$1"' _ "$diff_check"

echo
echo "release-manifest tests: $pass passed, $fail failed"
[ "$fail" -eq 0 ]

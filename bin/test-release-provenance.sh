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

  printf '%s\n' '{"capabilities":[{"name":"demo","type":"skill","provider":{"claude":"installed","codex":"untested"},"maturity":"tested","version_introduced":"0.5.0"}]}' >"$repo/capabilities.json"
  printf '%s\n' '# generated' \
    $'claude\tskill\tdemo\tskills/demo\tskills/demo' >"$repo/install-manifest.tsv"

  printf '%s\n' '0.5.0' >"$repo/version.txt"
  printf '%s\n' '{".": "0.5.0"}' >"$repo/.release-please-manifest.json"
  printf '%s\n' '# Changelog' '' '## [0.5.0] - 2026-07-01' '' '- Previous.' >"$repo/CHANGELOG.md"
  commit "$repo" previous
  git -C "$repo" tag v0.5.0

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

echo "evidence collection and validation:"
run "$PY" - "$HELPER" "$VALID" "$TMP" <<'PY'
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

helper, root, tmp = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
spec = importlib.util.spec_from_file_location("release_provenance", helper)
rp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rp)
tag = "v0.5.1"
commands = {
    "version_state": ["python3", "bin/release-provenance.py", "verify-source", "--tag", tag],
    "release_integrity": ["python3", "skills/package-release-integrity/scripts/release_integrity.py", "publication-check", "--repo", ".", "--tag", tag],
    "make_check": ["make", "check"],
    "make_test": ["make", "test"],
}
assert rp.required_commands(tag) == commands

seen = []
def passing_runner(argv, *, cwd, check=False):
    assert isinstance(argv, list)
    assert Path(cwd) == root.resolve()
    assert check is False
    seen.append(argv)
    return subprocess.CompletedProcess(argv, 0)

output = tmp / "evidence.json"
result = rp.collect_evidence(root, tag, output, runner=passing_runner)
assert result is True
assert seen == list(commands.values())
evidence = json.loads(output.read_text())
source = rp.verify_source(root, tag)
assert evidence == {
    "schema_version": 1,
    "repository": source["repository"],
    "tag": tag,
    "commit_sha": source["commit_sha"],
    "checks": [
        {"id": key, "required": True, "command": command,
         "status": "passed", "exit_code": 0}
        for key, command in commands.items()
    ],
}
assert output.read_bytes() == (json.dumps(evidence, sort_keys=True, indent=2) + "\n").encode()
assert rp.validate_evidence(evidence, source) == evidence

failed_output = tmp / "failed-evidence.json"
calls = 0
def failing_runner(argv, *, cwd, check=False):
    global calls
    calls += 1
    return subprocess.CompletedProcess(argv, 7 if calls == 1 else 0)
assert rp.collect_evidence(root, tag, failed_output, runner=failing_runner) is False
failed = json.loads(failed_output.read_text())
assert len(failed["checks"]) == 4
assert failed["checks"][0]["status"] == "failed"
assert failed["checks"][0]["exit_code"] == 7

throwing_output = tmp / "throwing-evidence.json"
throwing_seen = []
def throwing_runner(argv, *, cwd, check=False):
    throwing_seen.append(argv)
    if len(throwing_seen) == 2:
        raise OSError("simulated exec failure")
    return subprocess.CompletedProcess(argv, 0)
assert rp.collect_evidence(root, tag, throwing_output, runner=throwing_runner) is False
throwing = json.loads(throwing_output.read_text())
assert throwing_seen == list(commands.values())
assert len(throwing["checks"]) == 4
assert throwing["checks"][1] == {
    "id": "release_integrity", "required": True,
    "command": commands["release_integrity"], "status": "failed",
    "exit_code": 127, "error": "OSError: simulated exec failure",
}

def rejected(candidate):
    try:
        rp.validate_evidence(candidate, source)
    except ValueError:
        return
    raise AssertionError("invalid evidence accepted")

for check_id in commands:
    index = next(i for i, c in enumerate(evidence["checks"]) if c["id"] == check_id)
    absent = copy.deepcopy(evidence)
    absent["checks"].pop(index)
    rejected(absent)
    duplicate = copy.deepcopy(evidence)
    duplicate["checks"].append(copy.deepcopy(duplicate["checks"][index]))
    rejected(duplicate)
    for status in ("unknown", "skipped", "failed"):
        candidate = copy.deepcopy(evidence)
        candidate["checks"][index]["status"] = status
        rejected(candidate)
    candidate = copy.deepcopy(evidence)
    candidate["checks"][index]["exit_code"] = 9
    rejected(candidate)
    candidate = copy.deepcopy(evidence)
    candidate["checks"][index]["command"] = ["true"]
    rejected(candidate)

candidate = copy.deepcopy(evidence)
candidate["tag"] = "v9.9.9"
rejected(candidate)
candidate = copy.deepcopy(evidence)
candidate["commit_sha"] = "0" * 40
rejected(candidate)
candidate = copy.deepcopy(evidence)
candidate["checks"].append({"id": "surprise", "required": True,
                            "command": ["true"], "status": "passed",
                            "exit_code": 0})
rejected(candidate)
candidate = copy.deepcopy(evidence)
candidate["checks"].append({"id": "optional-surprise", "required": False,
                            "command": ["true"], "status": "passed",
                            "exit_code": 0})
rejected(candidate)
for field in ("schema_version", "repository", "tag", "commit_sha", "checks"):
    candidate = copy.deepcopy(evidence)
    del candidate[field]
    rejected(candidate)
candidate = copy.deepcopy(evidence)
candidate["checks"][0]["status"] = "bogus"
rejected(candidate)
candidate = copy.deepcopy(evidence)
candidate["schema_version"] = True
rejected(candidate)
print("evidence contract ok")
PY
expect_rc "required evidence contract accepts only exact successful checks" 0

run "$PY" "$HELPER" verify-source --root "$VALID" --tag v0.5.0 --json
expect_rc "historical lightweight v0.5.0 exits nonzero" 1
expect_exact "historical lightweight v0.5.0 has stable reason" \
  "v0.5.0: annotated tag required"

DIRTY="$TMP/dirty-authorities"
mkfixture "$DIRTY"
dirty_commit="$(git -C "$DIRTY" rev-parse 'v0.5.1^{commit}')"
dirty_tag_object="$(git -C "$DIRTY" rev-parse v0.5.1)"
dirty_timestamp="$(git -C "$DIRTY" for-each-ref \
  '--format=%(taggerdate:iso-strict)' refs/tags/v0.5.1)"
printf '%s\n' '9.9.9' >"$DIRTY/version.txt"
printf '%s\n' '{".": "9.9.9"}' >"$DIRTY/.release-please-manifest.json"
printf '%s\n' '# Changelog' '' '## [9.9.9] - 2099-09-09' '' \
  '- Dirty working tree only.' >"$DIRTY/CHANGELOG.md"
run "$PY" "$HELPER" verify-source --root "$DIRTY" --tag v0.5.1 --json
expect_rc "dirty authority files do not alter tagged verification" 0
expect_json "dirty authority files report committed tagged source state" \
  "$dirty_commit" "$dirty_tag_object" "$dirty_timestamp"

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

echo "provenance artifact generation and verification:"
EVIDENCE="$TMP/evidence.json"
OUTDIR="$TMP/artifacts"
mkdir -p "$OUTDIR"
run "$PY" "$HELPER" collect-evidence --root "$VALID" --tag v0.5.1 --output "$EVIDENCE"
expect_rc "real evidence collection exits nonzero when fixture commands fail" 1
run "$PY" - "$HELPER" "$VALID" "$EVIDENCE" <<'PY'
import importlib.util, json, pathlib, sys
helper, root, output = map(pathlib.Path, sys.argv[1:])
spec = importlib.util.spec_from_file_location("rp", helper)
rp = importlib.util.module_from_spec(spec); spec.loader.exec_module(rp)
source = rp.verify_source(root, "v0.5.1")
evidence = {
    "schema_version": 1, "repository": source["repository"],
    "tag": source["tag"], "commit_sha": source["commit_sha"],
    "checks": [{"id": key, "required": True, "command": command,
                "status": "passed", "exit_code": 0}
               for key, command in rp.required_commands(source["tag"]).items()],
}
output.write_text(json.dumps(evidence, sort_keys=True, indent=2) + "\n")
PY
expect_rc "fixture evidence document is created" 0

status_before="$(git -C "$VALID" status --porcelain=v1 --untracked-files=all)"
refs_before="$(git -C "$VALID" show-ref)"
run "$PY" "$HELPER" generate --root "$VALID" --tag v0.5.1 \
  --evidence "$EVIDENCE" --output-dir "$OUTDIR"
expect_rc "generation exits zero" 0
ARTIFACT="$OUTDIR/bindle-release-provenance.json"
CHECKSUM="$OUTDIR/bindle-release-provenance.json.sha256"
run test -f "$ARTIFACT"
expect_rc "generation writes exact JSON asset name" 0
run test -f "$CHECKSUM"
expect_rc "generation writes exact checksum asset name" 0
run "$PY" - "$ARTIFACT" "$CHECKSUM" "$expected_commit" <<'PY'
import hashlib, json, pathlib, re, sys
artifact, checksum = map(pathlib.Path, sys.argv[1:3])
payload = artifact.read_bytes()
document = json.loads(payload)
assert payload == (json.dumps(document, sort_keys=True, indent=2) + "\n").encode("utf-8")
digest = hashlib.sha256(payload).hexdigest()
assert checksum.read_bytes() == f"{digest}  bindle-release-provenance.json\n".encode("ascii")
assert document["schema_version"] == 1
assert document["artifact_type"] == "bindle-release-provenance"
assert document["commit_sha"] == sys.argv[3]
assert document["version"] == "0.5.1"
assert document["previous_version"] == "0.5.0"
assert document["verification_evidence"]["checks"]
assert document["capabilities"][0]["name"] == "demo"
assert document["installed_surfaces"][0]["dest"] == "skills/demo"
assert "Current." in document["changelog"]
assert set(document["tool_versions"]) == {"git", "bash", "python3", "shellcheck", "shfmt"}
print("artifact bytes ok")
PY
expect_rc "JSON and detached checksum bytes are exact and complete" 0
run test "$(git -C "$VALID" status --porcelain=v1 --untracked-files=all)" = "$status_before"
expect_rc "generation leaves Git status unchanged" 0
run test "$(git -C "$VALID" show-ref)" = "$refs_before"
expect_rc "generation leaves Git refs unchanged" 0
run "$PY" "$HELPER" verify --root "$VALID" --tag v0.5.1 \
  --artifact "$ARTIFACT" --checksum "$CHECKSUM"
expect_rc "semantic and checksum verification exits zero" 0

mkdir -p "$VALID/inside-output"
run "$PY" "$HELPER" generate --root "$VALID" --tag v0.5.1 \
  --evidence "$EVIDENCE" --output-dir "$VALID/inside-output"
expect_rc "generation rejects output below repo root" 1
run "$PY" "$HELPER" generate --root "$VALID" --tag v0.5.1 \
  --evidence "$EVIDENCE" --output-dir "$VALID"
expect_rc "generation rejects output equal to repo root" 1

printf '%s\n' stale-json >"$ARTIFACT"
printf '%s\n' stale-checksum >"$CHECKSUM"
run "$PY" "$HELPER" generate --root "$VALID" --tag v0.5.1 \
  --evidence "$EVIDENCE" --output-dir "$OUTDIR"
expect_rc "generation replaces ordinary existing external assets" 0
run "$PY" "$HELPER" verify --root "$VALID" --tag v0.5.1 \
  --artifact "$ARTIFACT" --checksum "$CHECKSUM"
expect_rc "replaced ordinary assets remain valid" 0

for asset in bindle-release-provenance.json bindle-release-provenance.json.sha256; do
  SAFE_REPO="$TMP/symlink-${asset##*.}"
  SAFE_OUT="$TMP/symlink-out-${asset##*.}"
  SAFE_EVIDENCE="$TMP/symlink-evidence-${asset##*.}.json"
  mkfixture "$SAFE_REPO"
  safe_commit="$(git -C "$SAFE_REPO" rev-parse 'v0.5.1^{commit}')"
  sed "s/$expected_commit/$safe_commit/g" "$EVIDENCE" >"$SAFE_EVIDENCE"
  mkdir -p "$SAFE_OUT"
  ln -s "$SAFE_REPO/version.txt" "$SAFE_OUT/$asset"
  safe_version_before="$(cat "$SAFE_REPO/version.txt")"
  safe_status_before="$(git -C "$SAFE_REPO" status --porcelain=v1 --untracked-files=all)"
  run "$PY" "$HELPER" generate --root "$SAFE_REPO" --tag v0.5.1 \
    --evidence "$SAFE_EVIDENCE" --output-dir "$SAFE_OUT"
  expect_rc "generation rejects $asset symlink into repo" 1
  run test "$(cat "$SAFE_REPO/version.txt")" = "$safe_version_before"
  expect_rc "$asset symlink target bytes stay unchanged" 0
  run test "$(git -C "$SAFE_REPO" status --porcelain=v1 --untracked-files=all)" = "$safe_status_before"
  expect_rc "$asset symlink rejection leaves Git status unchanged" 0
done

RACE_REPO="$TMP/parent-swap-repo"
RACE_EVIDENCE="$TMP/parent-swap-evidence.json"
mkfixture "$RACE_REPO"
race_commit="$(git -C "$RACE_REPO" rev-parse 'v0.5.1^{commit}')"
sed "s/$expected_commit/$race_commit/g" "$EVIDENCE" >"$RACE_EVIDENCE"
run "$PY" - "$HELPER" "$RACE_REPO" "$RACE_EVIDENCE" "$TMP" <<'PY'
import importlib.util
from pathlib import Path
import sys

helper, root, evidence, tmp = map(Path, sys.argv[1:])
spec = importlib.util.spec_from_file_location("rp", helper)
rp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rp)
parent = tmp / "race-parent"
output = parent / "out"
output.mkdir(parents=True)
saved_parent = tmp / "race-parent-saved"
redirect = root / "race-target"
(redirect / "out").mkdir(parents=True)

def swap_parent():
    parent.rename(saved_parent)
    parent.symlink_to(redirect, target_is_directory=True)

try:
    rp.generate(root, "v0.5.1", evidence, output,
                before_output_open=swap_parent)
except (OSError, ValueError):
    pass
else:
    raise AssertionError("parent-directory swap was accepted")
for name in (rp.ARTIFACT_NAME, rp.CHECKSUM_NAME):
    assert not (redirect / "out" / name).exists(), name
print("parent swap rejected")
PY
expect_rc "parent-directory swap cannot redirect asset writes into repo" 0
run test -z "$(git -C "$RACE_REPO" status --porcelain=v1 --untracked-files=all)"
expect_rc "parent-directory race leaves repository status unchanged" 0

cp "$ARTIFACT" "$TMP/corrupt.json"
printf 'x' >>"$TMP/corrupt.json"
run "$PY" "$HELPER" verify --root "$VALID" --tag v0.5.1 \
  --artifact "$TMP/corrupt.json" --checksum "$CHECKSUM"
expect_rc "verification rejects digest mismatch" 1

run "$PY" - "$ARTIFACT" "$TMP" <<'PY'
import hashlib, json, pathlib, sys
source, directory = map(pathlib.Path, sys.argv[1:])
document = json.loads(source.read_text())
cases = {
    "compact": json.dumps(document, sort_keys=True, separators=(",", ":")).encode(),
    "no-lf": source.read_bytes()[:-1],
    "duplicate": source.read_text().replace(
        '  "schema_version": 1,\n',
        '  "schema_version": 1,\n  "schema_version": 1,\n', 1
    ).encode(),
}
boolean = dict(document)
boolean["schema_version"] = True
cases["boolean-schema"] = (
    json.dumps(boolean, sort_keys=True, indent=2) + "\n"
).encode()
for name, payload in cases.items():
    artifact = directory / f"bytes-{name}.json"
    checksum = directory / f"bytes-{name}.json.sha256"
    artifact.write_bytes(payload)
    checksum.write_bytes(
        f"{hashlib.sha256(payload).hexdigest()}  bindle-release-provenance.json\n".encode()
    )
PY
expect_rc "noncanonical artifact fixtures have matching checksums" 0
for case in compact no-lf duplicate boolean-schema; do
  run "$PY" "$HELPER" verify --root "$VALID" --tag v0.5.1 \
    --artifact "$TMP/bytes-$case.json" \
    --checksum "$TMP/bytes-$case.json.sha256"
  expect_rc "verification rejects $case artifact bytes" 1
done

run "$PY" - "$EVIDENCE" "$TMP/duplicate-evidence.json" <<'PY'
import pathlib, sys
source, output = map(pathlib.Path, sys.argv[1:])
output.write_text(source.read_text().replace(
    '  "schema_version": 1,\n',
    '  "schema_version": 1,\n  "schema_version": 1,\n', 1
))
PY
expect_rc "duplicate-member evidence fixture is created" 0
run "$PY" "$HELPER" generate --root "$VALID" --tag v0.5.1 \
  --evidence "$TMP/duplicate-evidence.json" --output-dir "$TMP/duplicate-out"
expect_rc "generation rejects duplicate evidence members" 1

run "$PY" - "$EVIDENCE" "$TMP" <<'PY'
import json, pathlib, sys
source, directory = map(pathlib.Path, sys.argv[1:])
document = json.loads(source.read_text())
cases = {
    "compact": json.dumps(document, sort_keys=True, separators=(",", ":")).encode(),
    "no-lf": source.read_bytes()[:-1],
    "reordered": (json.dumps(dict(reversed(list(document.items()))),
                               indent=2) + "\n").encode(),
}
for name, payload in cases.items():
    (directory / f"evidence-{name}.json").write_bytes(payload)
PY
expect_rc "noncanonical evidence fixtures are created" 0
for case in compact no-lf reordered; do
  run "$PY" "$HELPER" generate --root "$VALID" --tag v0.5.1 \
    --evidence "$TMP/evidence-$case.json" \
    --output-dir "$TMP/evidence-$case-out"
  expect_rc "generation rejects $case evidence bytes" 1
done

run "$PY" - "$ARTIFACT" "$TMP" <<'PY'
import hashlib, json, pathlib, sys
source, directory = map(pathlib.Path, sys.argv[1:])
for field, value in {
    "tag": "v9.9.9",
    "commit_sha": "0" * 40,
    "version": "9.9.9",
    "verification_evidence": {"schema_version": 1},
}.items():
    document = json.loads(source.read_text())
    document[field] = value
    payload = (json.dumps(document, sort_keys=True, indent=2) + "\n").encode()
    artifact = directory / f"semantic-{field}.json"
    checksum = directory / f"semantic-{field}.json.sha256"
    artifact.write_bytes(payload)
    checksum.write_bytes(f"{hashlib.sha256(payload).hexdigest()}  bindle-release-provenance.json\n".encode())
PY
expect_rc "semantic mismatch fixtures are created with valid checksums" 0
for field in tag commit_sha version verification_evidence; do
  run "$PY" "$HELPER" verify --root "$VALID" --tag v0.5.1 \
    --artifact "$TMP/semantic-$field.json" \
    --checksum "$TMP/semantic-$field.json.sha256"
  expect_rc "verification rejects $field mismatch after checksum validation" 1
done

NO_PREVIOUS="$TMP/no-previous"
mkfixture "$NO_PREVIOUS"
git -C "$NO_PREVIOUS" tag -d v0.5.0 >/dev/null
no_previous_commit="$(git -C "$NO_PREVIOUS" rev-parse 'v0.5.1^{commit}')"
sed "s/$expected_commit/$no_previous_commit/g" "$EVIDENCE" >"$TMP/no-previous-evidence.json"
run "$PY" "$HELPER" generate --root "$NO_PREVIOUS" --tag v0.5.1 \
  --evidence "$TMP/no-previous-evidence.json" --output-dir "$TMP/no-previous-out"
expect_rc "generation rejects no previous SemVer tag candidate" 1

INVALID_SEMVER="$TMP/invalid-semver-previous"
mkfixture "$INVALID_SEMVER"
git -C "$INVALID_SEMVER" tag v0.5.0-01 v0.5.0
invalid_semver_commit="$(git -C "$INVALID_SEMVER" rev-parse 'v0.5.1^{commit}')"
sed "s/$expected_commit/$invalid_semver_commit/g" "$EVIDENCE" >"$TMP/invalid-semver-evidence.json"
run "$PY" "$HELPER" generate --root "$INVALID_SEMVER" --tag v0.5.1 \
  --evidence "$TMP/invalid-semver-evidence.json" \
  --output-dir "$TMP/invalid-semver-out"
expect_rc "invalid numeric-prerelease SemVer tag is ignored" 0
run "$PY" - "$TMP/invalid-semver-out/bindle-release-provenance.json" <<'PY'
import json, pathlib, sys
assert json.loads(pathlib.Path(sys.argv[1]).read_text())["previous_version"] == "0.5.0"
PY
expect_rc "strict previous-tag selection keeps the valid SemVer candidate" 0

TIED="$TMP/tied-previous"
mkfixture "$TIED"
git -C "$TIED" tag v0.4.9 v0.5.0
tied_commit="$(git -C "$TIED" rev-parse 'v0.5.1^{commit}')"
sed "s/$expected_commit/$tied_commit/g" "$EVIDENCE" >"$TMP/tied-evidence.json"
run "$PY" "$HELPER" generate --root "$TIED" --tag v0.5.1 \
  --evidence "$TMP/tied-evidence.json" --output-dir "$TMP/tied-out"
expect_rc "generation rejects tied nearest previous SemVer tags" 1

echo "test-release-provenance: $pass passed, $fail failed"
[ "$fail" -eq 0 ]

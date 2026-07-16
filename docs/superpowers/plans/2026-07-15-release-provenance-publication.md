# Post-Tag Release Provenance Publication Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Release Please's `version.txt` the sole checked-in version source and publish a verified `bindle-release-provenance.json` only from an annotated release tag through a fail-closed draft GitHub Release.

**Architecture:** A stdlib-only `bin/release-provenance.py` owns source-state verification, evidence collection, provenance generation, detached SHA-256 generation, and semantic verification. A separate stdlib-only `bin/release-publication.py` owns the GitHub draft lifecycle and calls the provenance helper; `.github/workflows/release.yml` only checks out the full tagged history and invokes that orchestrator. `package-release-integrity` gains a judgment-free `publication-check` mode used as one required evidence item.

**Tech Stack:** Bash, Python 3 stdlib, Git, GitHub CLI, GitHub Actions YAML, Release Please `simple` strategy, existing Make/pre-commit test harness.

## Global Constraints

- `version.txt` is the sole checked-in version source; remove `VERSION` with no duplicate, symlink, fallback, or compatibility shim.
- Release Please exclusively updates `version.txt`, `.release-please-manifest.json`, and `CHANGELOG.md` through its release PR.
- Canonical publication and local provenance generation require an annotated tag whose immediate object is the exact release commit; lightweight and tag-to-tag tags fail.
- `bindle-release-provenance.json` and `bindle-release-provenance.json.sha256` exist only after tagging and outside tracked source.
- `bin/release.sh`, `make release`, tracked `RELEASE-MANIFEST.json`, and the local version-bump/tag-cut path are retired.
- Required evidence IDs are exactly `version_state`, `release_integrity`, `make_check`, and `make_test`; every required result must be present, unique, known, unskipped, passed, and exit zero.
- Draft reuse is allowed only for the same repository/tag/commit and exact metadata; partial, duplicate, or unexpected assets stop for review.
- The downloaded draft assets must pass digest equality with the local upload plus independent checksum and semantic verification.
- Publishing is the final process operation. No cleanup or status command may run after it.
- Existing `v0.5.0` remains immutable lightweight-tag history and must be rejected by the new provenance path.
- No new runtime dependency beyond Python 3 stdlib, Git, and the already-required GitHub CLI.
- Work on `fix/137-release-provenance`; run `make check` and `make test` before every commit; never bypass hooks.

---

## File map

- `version.txt`: sole checked-in version value, natively updated by Release Please.
- `bin/release-provenance.py`: pure release-state/evidence/artifact functions plus `verify-source`, `collect-evidence`, `generate`, and `verify` CLI subcommands.
- `bin/release-publication.py`: canonical draft create/reuse/upload/download/verify/publish orchestrator; the only new GitHub Release mutation boundary.
- `skills/package-release-integrity/scripts/release_integrity.py`: portable version discovery plus strict mechanical `publication-check`.
- `.github/workflows/release.yml`: tag trigger, full checkout, Python orchestrator invocation.
- `bin/test-release-provenance.sh`: annotated-tag, schema, serialization, checksum, and no-mutation fixtures.
- `bin/test-release-publication.sh`: fake-`gh` state machine covering every draft and final-publication branch.
- `bin/test-release-strategy.sh` and `bin/fixtures/release-please-simple-dry-run.json`: native `version.txt` Release Please regression.
- `docs/release-provenance.md`: normative post-tag artifact/publication contract.
- `docs/workflows/release-captain.md` and `docs/package-release-integrity.md`: authority-boundary integrations.

### Task 1: Migrate the canonical version file and retire local release cutting

**Files:**
- Rename: `VERSION` → `version.txt`
- Create: `bin/fixtures/release-please-simple-dry-run.json`
- Modify: `release-please-config.json`
- Modify: `bin/check.sh`
- Modify: `bin/check-inventory.py`
- Modify: `bin/new.sh`
- Modify: `bin/install.sh`
- Modify: `bin/doctor.sh`
- Modify: `bin/release-evidence.py`
- Modify: `bin/test-check.sh`
- Modify: `bin/test-check-frontmatter.sh`
- Modify: `bin/test-check-inventory.sh`
- Modify: `bin/test-doctor.sh`
- Modify: `bin/test-release-evidence.sh`
- Modify: `bin/test-release-strategy.sh`
- Modify: `Makefile`
- Delete: `bin/release.sh`
- Delete: `RELEASE-MANIFEST.json`

**Interfaces:**
- Produces: root `version.txt` containing exactly `MAJOR.MINOR.PATCH` plus LF.
- Produces: every live version reader opens `version.txt`; missing-file diagnostics name `version.txt`.
- Produces: Release Please config with `release-type: simple` and no `extra-files` entry.

- [ ] **Step 1: Write the failing canonical-version and Release Please fixture assertions**

Add a fixture whose planned Release Please change is explicit and contains no custom updater:

```json
{
  "release_please_version": "17.6.1",
  "release_type": "simple",
  "before": {"version.txt": "0.5.0\n"},
  "after": {"version.txt": "0.5.1\n"},
  "custom_post_processing": false
}
```

Extend `bin/test-release-strategy.sh` with a Python assertion that the fixture changes only `version.txt`, the config's package has `release-type == "simple"`, `extra-files` is absent, `version.txt` equals `.release-please-manifest.json["."]`, and no root `VERSION` exists.

- [ ] **Step 2: Run the focused tests to prove RED**

Run: `bin/test-release-strategy.sh && bin/test-check.sh`

Expected: FAIL because `VERSION` still exists, `version.txt` is absent, and the config still declares `extra-files: ["VERSION"]`.

- [ ] **Step 3: Rename the file and update every live reader**

Run `git mv VERSION version.txt`. Replace root-file reads with these exact forms:

```bash
VERSION_FILE="$REPO_ROOT/version.txt"
version="$(cat "$VERSION_FILE")"
```

```python
def read_version(root):
    with open(os.path.join(root, "version.txt"), encoding="utf-8") as fh:
        return fh.read().strip()
```

Update fixture writers from `"$r/VERSION"` to `"$r/version.txt"`, diagnostics from `VERSION` to `version.txt`, and `release-please-config.json` to:

```json
{
  "$schema": "https://raw.githubusercontent.com/googleapis/release-please/main/schemas/config.json",
  "include-component-in-tag": false,
  "packages": {
    ".": {
      "release-type": "simple",
      "changelog-path": "CHANGELOG.md"
    }
  }
}
```

Remove the `release` phony target/help line, delete `bin/release.sh`, and delete tracked `RELEASE-MANIFEST.json`.

- [ ] **Step 4: Run focused and full verification**

Run: `bin/test-release-strategy.sh && bin/test-check.sh && bin/test-check-inventory.sh && bin/test-doctor.sh && bin/test-release-evidence.sh`

Expected: every suite reports zero failures.

Run: `make check && make test`

Expected: exit 0; `make check` reports `version.txt is valid semver (0.5.0)`.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor: make version.txt the release authority"
```

### Task 2: Add strict publication mode to package release integrity

**Files:**
- Modify: `skills/package-release-integrity/scripts/release_integrity.py`
- Modify: `skills/package-release-integrity/scripts/selftest.py`
- Modify: `bin/test-package-release-integrity.sh`
- Create: `skills/package-release-integrity/tests/fixtures/version-file/version.txt`
- Create: `skills/package-release-integrity/tests/fixtures/version-file/CHANGELOG.md`

**Interfaces:**
- Produces: `discover_version_sources(repo)` includes `file:version.txt` for a root bare-SemVer file.
- Produces: CLI `publication-check --repo PATH --tag TAG [--json]` with only `version_source_consistency`, `tag_consistency`, and `changelog_present` verdicts.
- Produces: publication mode exits 0 only when all three verdicts are `pass`; `uncertain`, `fail`, or DomI deferral exits 1.

- [ ] **Step 1: Write failing tests for `version.txt` discovery and publication strictness**

Add shell assertions for this JSON shape:

```json
{
  "mode": "publication",
  "verdicts": [
    {"check": "version_source_consistency", "verdict": "pass"},
    {"check": "tag_consistency", "verdict": "pass"},
    {"check": "changelog_present", "verdict": "pass"}
  ],
  "ready": true
}
```

Cover a matching tag, mismatched tag, missing changelog, malformed `version.txt`, and DomI-governed fixture. Assert every non-pass path exits 1 in publication mode.

- [ ] **Step 2: Run the focused suite to prove RED**

Run: `bin/test-package-release-integrity.sh`

Expected: FAIL because `publication-check` is not registered and `version.txt` is undiscovered.

- [ ] **Step 3: Implement the minimal strict mode**

Add discovery:

```python
version_file = repo / "version.txt"
if version_file.is_file():
    sources["file:version.txt"] = version_file.read_text().strip()
```

Add:

```python
def run_publication_check(repo, tag):
    if detect_domi_authority(repo):
        return {"mode": "defer", "verdicts": [], "ready": False}
    sources = discover_version_sources(repo)
    version = resolved_package_version(sources)
    verdicts = [
        check_version_source_consistency(sources),
        check_tag_consistency(version, tag),
        check_changelog_present(repo, version, True),
    ]
    return {
        "mode": "publication",
        "verdicts": verdicts,
        "ready": all(v["verdict"] == "pass" for v in verdicts),
    }
```

Register the subcommand and return 1 unless `ready is True`.

- [ ] **Step 4: Verify and commit**

Run: `bin/test-package-release-integrity.sh && make check && make test`

Expected: exit 0.

```bash
git add skills/package-release-integrity bin/test-package-release-integrity.sh
git commit -m "feat: add strict publication integrity mode"
```

### Task 3: Replace the old manifest generator with annotated-tag source verification

**Files:**
- Rename: `bin/release-manifest.py` → `bin/release-provenance.py`
- Rename: `bin/test-release-manifest.sh` → `bin/test-release-provenance.sh`
- Modify: `Makefile`

**Interfaces:**
- Produces: `verify_source(root: Path, tag: str) -> dict` with `repository`, `tag`, `tag_object_sha`, `tagger_timestamp`, `commit_sha`, and `version`.
- Produces: CLI `verify-source --root PATH --tag TAG [--json]`.
- Rejects: lightweight tags, tag-to-tag objects, tag/HEAD mismatch, tag/version mismatch, Release Please manifest mismatch, and missing changelog section.

- [ ] **Step 1: Replace old generator tests with annotated-tag fixtures**

Build throwaway repos containing `version.txt`, `.release-please-manifest.json`, `CHANGELOG.md`, two commits, a previous SemVer tag, and a current annotated tag. Add cases using:

```bash
git -C "$repo" tag -a v0.5.1 -m "Bindle v0.5.1"
git -C "$repo" tag v0.5.1-lightweight
git -C "$repo" tag -a intermediate -m intermediate
git -C "$repo" tag -a chained intermediate -m chained
```

Assert the valid fixture reports the exact `git rev-parse v0.5.1^{commit}` and all invalid fixtures exit nonzero with stable reason text.

- [ ] **Step 2: Run the focused test to prove RED**

Run: `bin/test-release-provenance.sh`

Expected: FAIL because the renamed helper has no `verify-source` subcommand.

- [ ] **Step 3: Implement exact annotated-tag/source verification**

Use argv-only Git calls and parse the immediate tag object:

```python
def git(root, *args):
    return subprocess.run(
        ["git", "-C", str(root), *args], check=True,
        capture_output=True, text=True,
    ).stdout.strip()

def annotated_tag(root, tag):
    if git(root, "cat-file", "-t", tag) != "tag":
        raise ValueError(f"{tag}: annotated tag required")
    fields = dict(
        line.split(" ", 1) for line in git(root, "cat-file", "-p", tag).splitlines()
        if line.startswith(("object ", "type "))
    )
    if fields.get("type") != "commit":
        raise ValueError(f"{tag}: tag must point directly to a commit")
    return git(root, "rev-parse", tag), fields["object"]
```

Validate `HEAD`, `v<version.txt>`, `.release-please-manifest.json["."]`, and the exact `## [<version>]` changelog header. Use `git for-each-ref --format=%(taggerdate:iso-strict)` for `tagger_timestamp`.

- [ ] **Step 4: Verify and commit**

Run: `bin/test-release-provenance.sh && make check && make test`

Expected: exit 0.

```bash
git add -A
git commit -m "feat: verify provenance source from annotated tags"
```

### Task 4: Implement stable evidence, provenance JSON, and detached checksum

**Files:**
- Modify: `bin/release-provenance.py`
- Modify: `bin/test-release-provenance.sh`

**Interfaces:**
- Produces: `collect-evidence --root PATH --tag TAG --output FILE`.
- Produces: `generate --root PATH --tag TAG --evidence FILE --output-dir DIR`.
- Produces: `verify --root PATH --tag TAG --artifact FILE --checksum FILE`.
- Produces: exact assets `bindle-release-provenance.json` and `bindle-release-provenance.json.sha256` outside the repo.

- [ ] **Step 1: Write failing evidence and artifact tests**

Import the module in an inline Python test and pass a fake runner to `collect_evidence`. Assert exact required commands:

```python
{
    "version_state": ["python3", "bin/release-provenance.py", "verify-source", "--tag", tag],
    "release_integrity": ["python3", "skills/package-release-integrity/scripts/release_integrity.py", "publication-check", "--repo", ".", "--tag", tag],
    "make_check": ["make", "check"],
    "make_test": ["make", "test"],
}
```

For each ID, test absent, duplicate, `unknown`, `skipped`, `failed`, nonzero, command mismatch, tag mismatch, commit mismatch, and unknown-required rejection. Test output-inside-repo rejection, exact sorted/indented/LF JSON bytes, checksum text bytes, digest mismatch, semantic mismatch, and unchanged Git status/refs after generation.

- [ ] **Step 2: Run the focused test to prove RED**

Run: `bin/test-release-provenance.sh`

Expected: FAIL on the first missing evidence API assertion.

- [ ] **Step 3: Implement evidence collection and validation**

Define:

```python
STATUS = {"passed", "failed", "unknown", "skipped"}

def required_commands(tag):
    return {
        "version_state": ["python3", "bin/release-provenance.py", "verify-source", "--tag", tag],
        "release_integrity": ["python3", "skills/package-release-integrity/scripts/release_integrity.py", "publication-check", "--repo", ".", "--tag", tag],
        "make_check": ["make", "check"],
        "make_test": ["make", "test"],
    }
```

Run all four commands, record `required: true`, `status: passed|failed`, and exact exit code, write evidence even on failure, then return nonzero if any failed. `validate_evidence` requires the exact key set and exact argv arrays; it never trusts an aggregate flag.

- [ ] **Step 4: Implement deterministic artifact and checksum generation**

Build the artifact from verified source state, validated evidence, capability/install snapshots, changelog section, tool versions, and the nearest reachable previous SemVer tag. Select the nearest tag by minimum `git rev-list --count <candidate>..<commit>^`; reject no candidate or a tied minimum.

Serialize and checksum exactly:

```python
payload = (json.dumps(document, sort_keys=True, indent=2) + "\n").encode("utf-8")
digest = hashlib.sha256(payload).hexdigest()
checksum = f"{digest}  bindle-release-provenance.json\n".encode("ascii")
```

Reject any output directory whose resolved path is equal to or below the repo root. `verify` first compares exact checksum bytes/digest, then validates schema, evidence, source tag, commit, and version semantics.

- [ ] **Step 5: Verify and commit**

Run: `bin/test-release-provenance.sh && make check && make test`

Expected: exit 0.

```bash
git add bin/release-provenance.py bin/test-release-provenance.sh
git commit -m "feat: generate verified release provenance"
```

### Task 5: Build and test the fail-closed draft publication orchestrator

**Files:**
- Create: `bin/release-publication.py`
- Create: `bin/test-release-publication.sh`
- Modify: `Makefile`

**Interfaces:**
- Produces: CLI `python3 bin/release-publication.py --repo OWNER/REPO --tag TAG`.
- Consumes: the four `bin/release-provenance.py` subcommands from Tasks 3–4.
- External boundary: `gh release view/create/upload/download/edit`; `edit --draft=false` is executed with `os.execvp` after explicit temp cleanup. Only `gh release view`'s exact not-found result permits draft creation; authentication, network, parsing, and every other inspection failure stop.

- [ ] **Step 1: Write a fake-`gh` state-machine test and RED scenarios**

The fake records argv to `GH_LOG`, reads/writes `GH_STATE`, copies uploaded assets into `GH_ASSETS`, and implements only the five release verbs. Cover:

Use this state protocol so assertions inspect external state, not prose output:

```python
state = {
    "release": None,  # or the exact gh-release-view JSON object
    "assets_dir": os.environ["GH_ASSETS"],
    "download_corruption": None,  # None | "json" | "checksum"
    "inspection_error": None,  # None | "auth" | "network"
}

# Every invocation appends JSON argv to GH_LOG. `release view` exits 1 with
# exactly "release not found" only when state["release"] is None; configured
# inspection errors use exit 2. `release create` writes a draft with the
# supplied tag/target/title/body. `release upload` copies each named file into
# assets_dir and records one asset object per name. `release download` copies
# only the requested patterns and optionally corrupts the configured file.
# `release edit --draft=false` flips isDraft only after logging the argv.
```

- no release → draft create → upload → download → publish;
- matching empty draft → upload → download → publish;
- matching draft with exactly both expected assets → one `upload --clobber`, no duplicate names, download, publish;
- partial expected assets, duplicate expected name, unexpected asset, wrong tag, wrong target commit, wrong title/body/prerelease flag, and already-published release → nonzero and no publish;
- corrupted downloaded JSON and corrupted downloaded checksum → nonzero and no publish;
- assertion that the final logged command on success is exactly `gh release edit <tag> --draft=false --repo <repo>`.

- [ ] **Step 2: Run the focused test to prove RED**

Run: `bin/test-release-publication.sh`

Expected: FAIL because `bin/release-publication.py` does not exist.

- [ ] **Step 3: Implement metadata and asset validation**

Query exact fields:

```python
VIEW_FIELDS = "tagName,targetCommitish,name,body,isDraft,isPrerelease,assets"
EXPECTED_ASSETS = {
    "bindle-release-provenance.json",
    "bindle-release-provenance.json.sha256",
}
```

Generate release notes from the verified changelog section before draft creation. A reusable draft must match repository argument, tag, commit, name=`tag`, body bytes, `isDraft is True`, and `isPrerelease is False`. Asset names must be either the empty set or exactly `EXPECTED_ASSETS`, with no duplicates. Any other state raises `PublicationError` before upload.

Treat a missing release as creatable only when `gh release view` exits 1 and
stderr is exactly the fake/real not-found classification normalized by one
small `release_not_found(stderr: str) -> bool` function. Add tests proving
exit 2 authentication/network errors never call `release create`.

- [ ] **Step 4: Implement ordered create/upload/download/verify/publish**

Use a temp directory outside the repo. Run evidence collection, generation, and local verification first. Create a draft only after those pass:

```python
["gh", "release", "create", tag, "--draft", "--verify-tag",
 "--target", commit, "--title", tag, "--notes-file", notes,
 "--repo", repo]
```

Upload both assets, adding `--clobber` only for the exact-two-assets rerun. Download both by explicit patterns to a separate directory. Compare the downloaded JSON SHA-256 to the locally validated JSON SHA-256, then invoke provenance `verify` on the downloaded pair.

Before publication, remove the temp directory explicitly. Publish as the process's final operation:

```python
os.execvp("gh", [
    "gh", "release", "edit", tag, "--draft=false", "--repo", repo,
])
```

Do not use `TemporaryDirectory` cleanup, `finally`, `atexit`, logging, or another command after `os.execvp`.

- [ ] **Step 5: Verify and commit**

Run: `bin/test-release-publication.sh && make check && make test`

Expected: exit 0; every failure scenario logs no publish command.

```bash
git add bin/release-publication.py bin/test-release-publication.sh Makefile
git commit -m "feat: publish provenance through verified drafts"
```

### Task 6: Make the tag workflow the single canonical publisher

**Files:**
- Modify: `.github/workflows/release.yml`
- Modify: `bin/test-release-publication.sh`

**Interfaces:**
- Consumes: `GITHUB_REF_NAME`, `GITHUB_REPOSITORY`, and `${{ github.token }}`.
- Produces: one tag-triggered job whose only publication command is the tested Python orchestrator.

- [ ] **Step 1: Add a failing workflow-structure regression**

Assert the YAML contains `fetch-depth: 0`, invokes `bin/release-publication.py`, grants `contents: write`, and contains none of `gh release create`, `gh release edit`, `RELEASE-MANIFEST.json`, or inline asset-generation commands.

- [ ] **Step 2: Run the focused test to prove RED**

Run: `bin/test-release-publication.sh`

Expected: FAIL because the workflow still creates a published release directly.

- [ ] **Step 3: Replace the workflow body**

Use this job shape:

```yaml
jobs:
  release:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
        with:
          fetch-depth: 0
      - name: Verify and publish tagged release provenance
        env:
          GH_TOKEN: ${{ github.token }}
        run: >-
          python3 bin/release-publication.py
          --repo "$GITHUB_REPOSITORY"
          --tag "$GITHUB_REF_NAME"
```

- [ ] **Step 4: Verify and commit**

Run: `bin/test-release-publication.sh && make check && make test`

Expected: exit 0.

```bash
git add .github/workflows/release.yml bin/test-release-publication.sh
git commit -m "ci: publish releases from verified provenance"
```

### Task 7: Update contracts, inventory, history, and prove no live fallback remains

**Files:**
- Rename: `docs/release-manifest.md` → `docs/release-provenance.md`
- Modify: `docs/workflows/release-captain.md`
- Modify: `docs/package-release-integrity.md`
- Modify: `skills/package-release-integrity/SKILL.md`
- Modify: `skills/release-captain/SKILL.md`
- Modify: `release-captain.toml`
- Modify: `README.md`
- Modify: `CONTRIBUTING.md`
- Modify: `docs/capability-inventory.md`
- Modify: `docs/product-boundary.md`
- Modify: `docs/runtime-security-privacy.md`
- Modify: `bin/release-strategies/local-release-please.sh`
- Modify: `capabilities.json`
- Modify: `CHANGELOG.md`
- Modify: `bin/test-check.sh`

**Interfaces:**
- Produces: capability `release-provenance`, path `docs/release-provenance.md`, `version_introduced: 0.5.1`.
- Produces: ledger rows for `bin/release-provenance.py`, `bin/release-publication.py`, the design, and this plan; removes rows for retired scripts.
- Produces: a live-surface regression scan with an explicit historical-doc allowlist.

- [ ] **Step 1: Write the failing no-fallback regression**

Add a `bin/test-check.sh` fixture/assertion that scans live files and fails on these patterns:

```text
root VERSION path
RELEASE-MANIFEST.json as current state
bin/release.sh invocation
make release invocation
extra-files containing VERSION
```

Allow only `CHANGELOG.md`, `docs/design/**`, `docs/plans/**`, and
`docs/superpowers/{specs,plans}/**` to mention retired names as explicit
history. Do not allow live instructions, skills, workflows, scripts, README,
CONTRIBUTING, capability descriptions, or contract docs.

- [ ] **Step 2: Run the regression to prove RED**

Run: `bin/test-check.sh`

Expected: FAIL and list current stale Release Captain, package integrity, README, CONTRIBUTING, capability, and release-strategy references.

- [ ] **Step 3: Rewrite the normative contracts**

In Release Captain, orient from `version.txt`, `.release-please-manifest.json`, and the latest tag; explicitly exclude provenance pre-release. In package integrity, document `publication-check` and require the attached artifact at publication. In `docs/release-provenance.md`, specify the exact evidence schema, artifact fields, detached checksum bytes, annotated tag checks, draft rules, local read-only path, and downloaded-asset verification.

Update the release-captain skill and strategy copy from `VERSION` to `version.txt` without adding publication authority to the recommendation skill.

- [ ] **Step 4: Reconcile inventory and user-facing docs**

Rename the capability row to:

```json
{
  "name": "release-provenance",
  "type": "contract",
  "path": "docs/release-provenance.md",
  "version_introduced": "0.5.1"
}
```

Preserve the row's provider/maturity/mutation shape, replace the retired script ledger rows with the two new Python helpers, and add this plan's `not_a_capability` row. Add an Unreleased `Fixed` entry closing #137 and naming the authority split, annotated-tag gate, draft verification, and retired cutter.

- [ ] **Step 5: Run the repository-wide search and all verification**

Run:

```bash
rg -n --hidden --glob '!.git/**' --glob '!.worktrees/**' \
  '\bVERSION\b|RELEASE-MANIFEST\.json|bin/release\.sh|make release|extra-files.*VERSION' .
```

Expected: matches only approved historical files and the explicit negative-test patterns.

Run: `make check && make test`

Expected: exit 0 with the new provenance and publication suites included.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "docs: define post-tag provenance publication"
```

## Final branch verification

- [ ] Run `git status --short --branch`; expect a clean `fix/137-release-provenance` worktree.
- [ ] Run `make check`; expect exit 0.
- [ ] Run `make test`; expect exit 0.
- [ ] Run `SKIP=no-commit-to-branch pre-commit run --all-files --show-diff-on-failure`; expect every hook passed.
- [ ] Review `git diff main...HEAD --stat` and `git log --oneline main..HEAD`; expect only issue #137 work plus the committed `.worktrees/` ignore guard, design, and plan.
- [ ] Do not create a real tag or GitHub Release during verification. The fake-`gh` suite is the publication proof.

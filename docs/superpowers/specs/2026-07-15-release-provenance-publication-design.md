# Design: post-tag release provenance publication

Date: 2026-07-15
Status: approved (brainstorm complete, pending plan)
Issue: #137

## Problem

Bindle's first Release Please release exposed two conflicting release models.
Release Please updated its own manifest and changelog but could not update the
repository's bare `VERSION` file. Separately, the tracked
`RELEASE-MANIFEST.json` remained a snapshot of the older `bin/release.sh`
release path, so Release Captain's pre-release cross-check treated stale
publication provenance as current version state.

The fix is to separate three authorities:

1. Release Please owns proposed and committed release state.
2. An annotated Git tag identifies the exact released source.
3. A rich provenance artifact records the verified publication after the tag
   exists, but never becomes checked-in version state.

## Locked authority and lifecycle contract

- `version.txt` is the sole checked-in version source.
- Release Please owns updates to `version.txt`,
  `.release-please-manifest.json`, and `CHANGELOG.md` through its release PR.
- `VERSION` is removed; no duplicate, symlink, fallback, or compatibility shim
  is retained. A scan of local development checkouts and public GitHub code
  found no external consumer of Bindle's old `VERSION` path.
- The canonical publication workflow requires an annotated tag. The tag's
  immediate target must be the exact released commit.
- `bindle-release-provenance.json` is generated only after the tag exists and
  final release-integrity verification succeeds. It exists outside tracked
  source and is attached to a GitHub Release as a publication artifact.
- The provenance artifact is never committed to `main` and is never a version
  source.
- `bin/release.sh`, `make release`, tracked `RELEASE-MANIFEST.json`, and the
  old local version-bump/tag-cut path are retired.
- Release Captain does not consume publication provenance during pre-release
  orientation.
- Publication is the final operation and occurs only after independent
  verification of the asset downloaded from the draft GitHub Release.

## Canonical version state

Rename the root `VERSION` file to `version.txt`. Release Please's `simple`
strategy natively updates that whole file; remove the ineffective
`extra-files: ["VERSION"]` configuration rather than introducing an annotation
or custom updater. The Release Please release PR must update all three owned
files together:

- `version.txt`;
- `.release-please-manifest.json`;
- `CHANGELOG.md`.

All scripts, Make targets, tests, fixtures, documentation, integrity checks,
and release tooling that currently read or write `VERSION` must move to
`version.txt`. Historical prose that names the old release implementation may
remain only where it is unambiguously historical; no executable fallback may
remain.

The release-strategy regression suite will include a checked-in Release Please
fixture showing the `simple` strategy's planned update from one bare
`version.txt` value to the next. The test must also assert that the checked-in
configuration has no custom updater or `VERSION` extra-file entry. This proves
the supported native path without making the ordinary offline test suite
depend on the GitHub API or an unpinned network download.

## Annotated-tag and source-state verification

Both canonical publication and local provenance generation require all of the
following:

1. `git cat-file -t <tag>` returns `tag`, rejecting lightweight tags.
2. The annotated tag object's immediate `object` is a commit, not another tag.
3. That immediate object equals `git rev-parse <tag>^{commit}` and the recorded
   `commit_sha`.
4. The workflow checkout's `HEAD` equals that same commit.
5. The tag name is exactly `v<version.txt>`.
6. `.release-please-manifest.json`'s root package (`.`) equals `version.txt`.
7. `CHANGELOG.md` contains the released version section.

Any mismatch is a hard failure before draft creation or reuse. The verifier
does not repair version files, manifests, changelog state, tags, or commits.

The existing `v0.5.0` tag is lightweight. It remains immutable historical
state: this issue does not rewrite or replace it. The annotated-tag contract
applies to future publication tags, and the new workflow must reject `v0.5.0`
if someone manually attempts to run the new provenance path against it.

## Verification evidence contract

Final verification produces a stable JSON evidence document consumed by the
provenance generator. Its top-level schema is:

```json
{
  "schema_version": 1,
  "repository": "thomas-estep/bindle",
  "tag": "v0.5.1",
  "commit_sha": "<40 lowercase hex>",
  "checks": [
    {
      "id": "version_state",
      "required": true,
      "command": ["python3", "bin/release-provenance.py", "verify-source", "--tag", "v0.5.1"],
      "status": "passed",
      "exit_code": 0
    }
  ]
}
```

`checks` uses stable identifiers, an argv array rather than a shell string,
and the status enum `passed | failed | unknown | skipped`. The exact required
check identifiers for Bindle publication are:

- `version_state` — annotated tag, tagged commit, `version.txt`, Release Please
  manifest, and changelog agreement;
- `release_integrity` — the publication-mode mechanical checks from
  `package-release-integrity` (version-source consistency, tag consistency,
  and changelog presence);
- `make_check` — the repository's full static/content gate;
- `make_test` — the repository's full test suite.

Their command templates are fixed:

- `version_state`: `python3 bin/release-provenance.py verify-source --tag
  <tag>`;
- `release_integrity`: `python3
  skills/package-release-integrity/scripts/release_integrity.py
  publication-check --repo . --tag <tag>`;
- `make_check`: `make check`;
- `make_test`: `make test`.

The evidence collector substitutes only the exact tag value and records each
template as an argv array. `release_integrity` does not duplicate the build and
test executions: the evidence envelope proves those separately through
`make_check` and `make_test`.

Release Captain owns the pre-release classification and version recommendation,
so post-tag publication does not re-infer a change class. The
package-release-integrity contract will define publication mode's required
mechanical subset explicitly; judgment-only checks are outside that mode, not
silently treated as passes.

The evidence collector records every required check separately with its exact
argv, status, and exit code. Provenance generation rejects evidence when:

- the schema version, repository, tag, or commit is missing or mismatched;
- any required identifier is absent or duplicated;
- a required command differs from the defined command for that identifier;
- a required status is `failed`, `unknown`, or `skipped`;
- a required exit code is absent or nonzero; or
- an unrecognized required check is present.

An aggregate success boolean is neither required nor trusted. Exact outcomes
are the authority.

## Provenance artifact

Rename the rich artifact to `bindle-release-provenance.json` and the generator
to `bin/release-provenance.py`. The new name distinguishes publication
provenance from `.release-please-manifest.json`, which is Release Please's
version-state file.

The provenance schema records at least:

- schema version and artifact type;
- repository, annotated tag name, tag-object SHA, tagger timestamp, exact
  released `commit_sha`, version, and previous version;
- the released changelog section;
- the capability inventory and installed-surface snapshots;
- the complete validated verification-evidence document;
- relevant tool versions.

`previous_version` is selected deterministically from the nearest reachable
SemVer-shaped `v*` tag before the released commit (excluding the current tag),
then normalized by removing its leading `v`. Absence or ambiguity is a hard
generation failure rather than a guessed value.

Unlike the old artifact, `commit_sha` is the exact tagged release commit, not
its parent. Generation reads only the already-tagged commit and caller-supplied
evidence. The output path must resolve outside the repository root. Generation
does not edit the checkout, commits, tags, Release Please state, or GitHub.

### Detached checksum

Use a detached `bindle-release-provenance.json.sha256` asset rather than an
in-document self-checksum. This avoids a circular exclusion rule and makes the
byte-integrity contract conventional and reproducible.

The JSON bytes are UTF-8, object keys sorted lexicographically, two-space
indentation, and exactly one trailing LF. The detached file uses the standard
`sha256sum` text form:

```text
<64 lowercase hex>  bindle-release-provenance.json
```

followed by exactly one LF. The digest covers every byte of the JSON artifact.
Semantic verification parses the JSON and checks its schema, evidence, tag,
commit, and version state; checksum verification independently covers exact
bytes.

## Canonical tag-triggered publication workflow

The single publication workflow runs in this order:

1. Check out the tagged commit with full tag history.
2. Verify the annotated tag, release commit, `version.txt`,
   `.release-please-manifest.json`, and changelog agree.
3. Run final release-integrity verification and write the machine-readable
   evidence document.
4. Generate `bindle-release-provenance.json` and its detached checksum in the
   runner's temporary directory.
5. Validate the local artifact semantically and validate its detached checksum.
6. Create a draft GitHub Release, or validate a same-tag draft eligible for
   safe reuse, and attach both named assets.
7. Download the exact uploaded JSON and checksum assets from that draft to a
   separate directory.
8. Compare the downloaded JSON digest to the locally validated upload digest,
   validate the downloaded detached checksum, and independently run semantic
   verification against the tag and release commit.
9. Publish the draft.

Step 9 is the final command and final mutation. No cleanup, status update, or
other fallible operation follows it. Any failure before step 9 leaves the
release unpublished.

## Draft creation and reruns

A new run creates a draft for the exact repository and tag. A rerun may reuse
an existing release only when it is still a draft in the same repository and
its tag, target commit, title, prerelease flag, and release-note metadata match
the workflow's expected values.

The only expected assets are:

- `bindle-release-provenance.json`;
- `bindle-release-provenance.json.sha256`.

If a reusable draft has neither asset, upload both. If it has exactly those
assets, replace them deterministically by name (no duplicates), then download
and verify the replacements. If it has only one expected asset, duplicate
names, any unexpected asset, or conflicting release metadata, stop for human
review without normalizing the draft. An already-published release is
immutable and causes a fail-safe stop.

## Local provenance path

Retire `bin/release.sh` rather than retaining a misleading wrapper after its
version-bump and release-cut authority is removed. If a local convenience path
is retained, it is only a read-only invocation of the same provenance
generator and verifier and must:

- require an already-existing annotated tag whose immediate target matches
  `HEAD` and the recorded commit;
- read `version.txt` and Release Please state from that tagged commit;
- require the same complete successful evidence schema;
- emit the same two untracked assets outside the repository; and
- never modify `version.txt`, `CHANGELOG.md`, `.release-please-manifest.json`,
  commits, tags, branches, GitHub Releases, or any other remote state.

No separate legacy schema or authority is permitted.

## Contract and documentation changes

- **Release Captain:** orient from repository policy, Release Please state,
  `version.txt`, and the latest valid tag. Remove
  `RELEASE-MANIFEST.json` from every pre-release cross-check and provider
  mapping. State that provenance is a post-tag publication requirement.
- **Package release integrity:** discover `version.txt` as a version source and
  define the mechanical publication-mode checks used in final evidence.
  Publication readiness requires the attached provenance artifact to match the
  release tag, commit, version, and recorded successful evidence.
- **Release provenance documentation:** replace the old tracked-manifest
  contract with the post-tag artifact schema, detached checksum, inspection,
  download verification, and authority separation.
- **README, CONTRIBUTING, project guidance, scripts, fixtures, and generated
  diagnostics:** replace live `VERSION` assumptions with `version.txt`; remove
  instructions for `bin/release.sh` and `make release`.
- **Capability inventory:** remove retired script entries, add or rename the
  provenance helper's ledger entry, and classify new planning artifacts.

## Testing strategy

Follow the repository's test-driven loop. Required coverage includes:

- RED fixture for the current stale `VERSION` behavior, then GREEN coverage
  that Release Please's native `simple` plan updates `version.txt` without a
  custom updater;
- annotated tag accepted; lightweight tag, tag-to-tag indirection, tag/HEAD
  mismatch, version mismatch, Release Please manifest mismatch, and missing
  changelog rejected;
- evidence schema accepts the exact complete successful set and rejects every
  missing, duplicate, unknown, skipped, failed, nonzero, or command-mismatch
  case;
- provenance records the exact tagged commit and validated evidence;
- output-under-repository rejection and proof that local generation changes no
  tracked state, refs, or remotes;
- deterministic JSON serialization and detached checksum bytes;
- downloaded-asset digest equality plus independent semantic verification;
- new draft, safe same-tag draft reuse, deterministic asset replacement,
  partial/duplicate/unexpected assets, conflicting metadata, and published
  release fail-safe behavior using a stubbed `gh` boundary;
- assertion that publish is the final operation and is never invoked on any
  earlier failure;
- repository-wide regression search proving no executable `VERSION`,
  `RELEASE-MANIFEST.json`, `bin/release.sh`, or `make release` fallback remains;
- `make check` and `make test` before every commit.

## Failure behavior

All validation is fail closed. The workflow reports the precise failing
authority boundary and exits nonzero. It never repairs release state, guesses
missing evidence, converts `unknown` or `skipped` into success, deletes
unexpected assets, modifies a published release, or publishes a draft whose
downloaded artifact has not passed both byte and semantic verification.

## Out of scope

- A compatibility `VERSION` file or symlink without a proven external consumer.
- Custom Release Please updaters or release-PR post-processing.
- Committing generated provenance to any branch.
- Reintroducing a local version bumper, changelog roller, tag cutter, or GitHub
  Release creator outside the canonical workflow.
- Signing or attestations beyond the detached SHA-256 integrity asset.
- Generalizing this workflow into a universal multi-package publisher.

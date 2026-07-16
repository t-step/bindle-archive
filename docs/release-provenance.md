# Release provenance

**Status:** Contract, v1 · **Issue:** thomas-estep/bindle#137

This contract separates release intent, checked-in release state, and
publication evidence. Release Please owns the release PR and the committed
version state; an annotated tag identifies the released source; the provenance
artifact records verification performed after that tag exists. Provenance is
never checked-in version state and Release Captain does not consume it while
recommending a release.

## Authority and lifecycle

- `version.txt` is the sole checked-in version source.
- Release Please owns updates to `version.txt`, the root (`.`) entry in
  `.release-please-manifest.json`, and `CHANGELOG.md` through its release PR.
  The merged release-PR commit is authoritative only when all three agree.
- Publication requires an annotated direct tag named `v<version.txt>`. Its tag
  object's immediate target must be the exact released commit and workflow
  `HEAD`; lightweight tags and tag-to-tag indirection fail.
- `bindle-release-provenance.json` and its detached checksum are generated
  after tagging, outside the repository, and attached to the GitHub Release.
- Publication is the final mutation, after the uploaded assets have been
  downloaded and independently verified. Nothing fallible follows it.

The verifier never repairs release state, rewrites a tag, or guesses missing
evidence.

## Source-state gate

Before evidence collection, draft creation, or draft reuse, run:

```bash
python3 bin/release-provenance.py verify-source --tag <tag>
```

It requires all of the following:

1. `git cat-file -t <tag>` reports `tag`.
2. The tag object's immediate `object` is a commit, not another tag.
3. That immediate object equals both `git rev-parse <tag>^{commit}` and the
   recorded 40-lowercase-hex `commit_sha`.
4. Checkout `HEAD` equals that commit.
5. The tag is exactly `v<version.txt>`.
6. `.release-please-manifest.json`'s root package equals `version.txt`.
7. `CHANGELOG.md` contains the released version section.

## Exact verification evidence

The evidence document has exactly one record for each required check:

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

The exact four identifiers and argv templates are:

| id | command |
|---|---|
| `version_state` | `python3 bin/release-provenance.py verify-source --tag <tag>` |
| `release_integrity` | `python3 skills/package-release-integrity/scripts/release_integrity.py publication-check --repo . --tag <tag>` |
| `make_check` | `make check` |
| `make_test` | `make test` |

Each record has `required: true`, exact argv as an array, `status: "passed"`,
and `exit_code: 0`. Allowed statuses are `passed`, `failed`, `unknown`, and
`skipped`; the latter three fail publication. Missing or duplicate identifiers,
an unknown required check, command drift, mismatched repository/tag/commit, or
a missing/nonzero exit code also fails. An aggregate success boolean is not
trusted. Collect the document with `release-provenance.py collect-evidence`.

## Artifact and detached checksum

`release-provenance.py generate` emits two assets outside the checkout. The
JSON contains at least:

- `schema_version` and `artifact_type` (`bindle-release-provenance`);
- repository, annotated tag name, tag-object SHA, tagger timestamp, released
  `commit_sha`, version, and deterministic previous version;
- the released changelog section;
- capability-inventory and installed-surface snapshots;
- the complete validated evidence document; and
- relevant tool versions.

The exact `commit_sha` is the tagged commit, never its parent. The previous
version is the nearest reachable SemVer-shaped `v*` tag before that commit,
excluding the current tag; absence or ambiguity fails rather than guessing.

The JSON bytes are UTF-8, keys sorted lexicographically, two-space indented,
with exactly one trailing LF. The detached
`bindle-release-provenance.json.sha256` bytes are exactly:

```text
<64 lowercase hex>  bindle-release-provenance.json
```

followed by one LF. The digest covers every JSON byte. Semantic verification
separately checks canonical serialization, schema, evidence, annotated tag,
commit, and version state:

```bash
python3 bin/release-provenance.py verify --tag <tag> \
  --artifact <outside>/bindle-release-provenance.json \
  --checksum <outside>/bindle-release-provenance.json.sha256
```

## Draft creation and exact reuse

Create a draft for the exact repository and tag. A rerun may reuse only an
unpublished draft whose tag, target commit, title, prerelease flag, and
release-note metadata exactly match the expected values.

The only allowed assets are `bindle-release-provenance.json` and
`bindle-release-provenance.json.sha256`:

- neither present: upload both;
- exactly one of each: replace both deterministically by name, with no
  duplicates, then download and verify the replacements;
- only one present, duplicate names, or any unexpected asset: stop for human
  review without normalizing the draft.

Conflicting metadata and already-published releases also fail closed. A rerun
never edits conflicting state into compliance.

## Upload, download, verify, publish

After local semantic and checksum validation, upload both assets to the draft.
Download those exact named assets into a separate directory. Require the
downloaded JSON digest to equal the locally validated upload digest, validate
the downloaded detached checksum against the downloaded JSON bytes, and run
independent semantic verification against the tag and released commit. Only
then publish the draft. Publishing is the last command; every earlier failure
leaves it unpublished.

## Local provenance path

The local path is read-only with respect to the checkout, Git, GitHub, and all
other remotes. It requires an existing annotated direct tag at `HEAD`, reads
`version.txt` and Release Please state from that tagged commit, requires the
same complete successful evidence, and emits the same two untracked assets
outside the repository. It never changes version/changelog/manifest files,
the index, commits, refs, branches, tags, releases, or any remote state.

## Inspection

Treat the GitHub Release assets as the publication record, not a file in a
checkout. Download both assets, verify the detached checksum, and run semantic
verification against a full-history checkout of the released tag. A green
pre-release recommendation or generic integrity report is not a substitute
for these post-tag checks.
